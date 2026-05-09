"""End-to-end ingestion pipeline (TICKET-020).

``ingest_document`` is the single entry point used by the API route and by
batch / fixture loaders. It is idempotent in the failure-recovery sense:
on partial failure (e.g. the embedding service returns a transient error
mid-document), we abort the transaction and the partially-written rows are
rolled back. Re-uploading the same file produces a fresh ``document_id``;
content-addressing of uploads is not yet a product requirement.

After the durable commit, the pipeline emits ``NOTIFY ingestion '<id>'``
on a fresh connection so the dirty-set orchestrator (TICKET-070) can pick
it up. The notify is best-effort; a logged failure does not roll back the
ingest because the durable state is already persisted.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlmodel import Session

from app.core.config import settings
from app.core.db import engine
from app.models import Chunk, Document, Embedding, LlmCostLog
from app.storage import ensure_bucket, get_minio_client

from .chunker import chunk_text
from .embeddings import VoyageEmbedder, get_embedder
from .parsers import (
    ParserError,
    UnsupportedDocumentError,
    detect_kind,
    parse_document,
)

logger = logging.getLogger("app.ingestion.pipeline")

NOTIFY_CHANNEL = "ingestion"


@dataclass
class IngestionResult:
    document_id: uuid.UUID
    n_chunks: int
    cost_usd: float
    model: str
    raw_blob_key: str
    parsed_metadata: dict[str, Any]


def _raw_blob_key(owner_id: uuid.UUID, document_id: uuid.UUID, filename: str) -> str:
    safe = filename.replace("\\", "/").rsplit("/", 1)[-1]
    safe = safe.replace("\x00", "").strip()
    if not safe:
        safe = "upload.bin"
    return f"{owner_id}/{document_id}/{safe}"


def _emit_notify(document_id: uuid.UUID) -> None:
    """Emit ``NOTIFY ingestion '<document_id>'`` on a fresh autocommit connection.

    Postgres only delivers NOTIFY at COMMIT, so we open a side connection
    rather than reusing the (already-closed) ingest transaction. Failures
    are logged but not raised: durable state is what matters.
    """
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql(f"NOTIFY {NOTIFY_CHANNEL}, '{document_id}'")
    except Exception as exc:  # noqa: BLE001
        logger.warning("NOTIFY ingestion '%s' failed: %s", document_id, exc)


async def ingest_document(
    file_bytes: bytes,
    filename: str,
    owner_id: uuid.UUID,
    *,
    mime_type: str | None = None,
    embedder: VoyageEmbedder | None = None,
    session: Session | None = None,
) -> IngestionResult:
    """Parse, chunk, embed, persist a single document.

    Args:
        file_bytes: raw upload bytes
        filename: original filename; used for parser dispatch + blob naming
        owner_id: User.id this document belongs to (authorization filter
                  source of truth for downstream queries)
        mime_type: optional Content-Type hint
        embedder: dependency-injection seam for tests; defaults to
                  ``get_embedder()`` at the process level
        session: optional pre-opened SQLModel session (the caller commits);
                  if omitted, the function manages its own session and commit

    Raises:
        UnsupportedDocumentError: file extension/mime not supported
        ParserError: file is supported but parsing failed
        ValueError: empty payload (after parse) — no chunks would be written
    """
    if not file_bytes:
        raise ValueError("Empty upload payload")
    if len(file_bytes) > settings.LENS_UPLOAD_MAX_BYTES:
        raise ValueError(
            f"Upload exceeds LENS_UPLOAD_MAX_BYTES ({settings.LENS_UPLOAD_MAX_BYTES})"
        )

    # Validate type before doing any heavy work.
    kind = detect_kind(filename, mime_type)  # raises UnsupportedDocumentError

    # 1) Parse to text + metadata.
    parsed = parse_document(file_bytes, filename, mime_type=mime_type)
    if not parsed.text.strip():
        raise ParserError(f"Document {filename!r} parsed to empty text")

    # 2) Chunk.
    chunks = chunk_text(parsed.text)
    if not chunks:
        raise ParserError(
            f"Document {filename!r} produced no chunks (parsed text not chunkable)"
        )

    # 3) Embed (Voyage). Done before any persistence so a transient embed
    #    failure aborts the whole upload cleanly.
    embedder = embedder or get_embedder()
    embed_run = await embedder.embed_documents([c.text for c in chunks])
    if len(embed_run.vectors) != len(chunks):
        raise RuntimeError(
            "Embedder returned mismatched vector count "
            f"({len(embed_run.vectors)} vs {len(chunks)})"
        )

    document_id = uuid.uuid4()

    # 4) Raw bytes → MinIO. Best-effort; we can complete ingest without it
    #    but we surface the failure to the caller so they can retry.
    blob_key = _raw_blob_key(owner_id, document_id, filename)
    try:
        ensure_bucket()
        get_minio_client().put_object(
            data=file_bytes,
            key=blob_key,
            content_type=mime_type or "application/octet-stream",
        )
    except Exception as exc:
        # Persist intent but record raw_blob_key=None when MinIO is down so
        # we never leave a dangling key. The caller decides whether to retry.
        logger.warning("MinIO put failed for %s: %s", blob_key, exc)
        blob_key = ""

    # 5) Persist documents/chunks/embeddings/cost atomically.
    metadata = dict(parsed.metadata)
    metadata.update(
        {
            "filename": filename,
            "mime_type": mime_type,
            "kind": kind,
            "chunker": {
                "n_chunks": len(chunks),
                "total_tokens": sum(c.tokens for c in chunks),
            },
            "embedder": {
                "model": embed_run.model,
                "input_tokens": embed_run.input_tokens,
                "cost_usd": embed_run.cost_usd,
            },
        }
    )

    own_session = session is None
    sess = session or Session(engine)
    try:
        document = Document(
            id=document_id,
            owner_id=owner_id,
            source_type=parsed.source_type,
            source_uri=f"minio://{blob_key}" if blob_key else None,
            raw_blob_key=blob_key or None,
            parsed_metadata=metadata,
            ingested_at=datetime.now(timezone.utc),
        )
        sess.add(document)
        sess.flush()

        for chunk_meta, vector in zip(chunks, embed_run.vectors, strict=True):
            chunk_row = Chunk(
                document_id=document_id,
                ord=chunk_meta.ord,
                text=chunk_meta.text,
                char_start=chunk_meta.char_start,
                char_end=chunk_meta.char_end,
                tokens=chunk_meta.tokens,
            )
            sess.add(chunk_row)
            sess.flush()
            sess.add(
                Embedding(
                    chunk_id=chunk_row.id,
                    model=embed_run.model,
                    vector=list(vector),
                )
            )

        sess.add(
            LlmCostLog(
                owner_id=owner_id,
                document_id=document_id,
                model=embed_run.model,
                input_tokens=embed_run.input_tokens,
                output_tokens=0,
                cost_usd=Decimal(str(round(embed_run.cost_usd, 6))),
            )
        )

        if own_session:
            sess.commit()
    except Exception:
        if own_session:
            sess.rollback()
        raise
    finally:
        if own_session:
            sess.close()

    # 6) NOTIFY (only after the transaction is durable).
    if own_session:
        _emit_notify(document_id)

    return IngestionResult(
        document_id=document_id,
        n_chunks=len(chunks),
        cost_usd=float(embed_run.cost_usd),
        model=embed_run.model,
        raw_blob_key=blob_key,
        parsed_metadata=metadata,
    )


__all__ = [
    "IngestionResult",
    "NOTIFY_CHANNEL",
    "UnsupportedDocumentError",
    "ParserError",
    "ingest_document",
]
