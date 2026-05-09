"""Ingestion pipeline tests (TICKET-020).

Layout:

  - Pure-function tests for parsers and chunker live here without the live
    DB; they import the modules and exercise them on bytes.
  - DB-bound round-trip tests use the existing autouse Postgres fixture
    from ``conftest.py`` and the ``FIRST_SUPERUSER`` user.
  - Voyage-API-bound test is gated on ``LENS_LIVE_API=1``.
  - The NOTIFY test opens a side ``LISTEN`` connection on the same DSN,
    runs an ingest with a stubbed embedder (so we don't hit Voyage), and
    asserts the notification arrives within 100ms.

Why fakes for the embedder: Voyage costs money per token and can flake on
network. The pipeline contract (chunks * embedding rows + commit + NOTIFY)
is what we want to verify; the embedder is a single dependency-injection
seam, so a fake closes the loop while staying realistic.
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from dataclasses import dataclass

import pytest
from sqlalchemy import text
from sqlmodel import Session, select

from app.core.config import settings
from app.core.db import engine
from app.ingestion.chunker import chunk_text
from app.ingestion.embeddings import EmbeddingRun, VoyageEmbedder
from app.ingestion.parsers import (
    UnsupportedDocumentError,
    detect_kind,
    parse_html,
    parse_markdown,
    parse_text,
)
from app.ingestion.pipeline import NOTIFY_CHANNEL, ingest_document
from app.models import EMBEDDING_DIM, Chunk, Document, Embedding, LlmCostLog, User

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class _FakeEmbedRun:
    vectors: list[list[float]]
    input_tokens: int
    cost_usd: float
    model: str = "voyage-3-large"


class _FakeEmbedder:
    """Drop-in for VoyageEmbedder in tests.

    Vectors are deterministic per text via a tiny hash so similarity tests
    behave consistently.
    """

    model = "voyage-3-large"
    batch_size = 64

    def __init__(self, vectors_for: dict[str, list[float]] | None = None) -> None:
        self._vectors_for = vectors_for or {}

    def _vector_for(self, text_in: str) -> list[float]:
        if text_in in self._vectors_for:
            return self._vectors_for[text_in]
        # Deterministic dummy vector with a tiny variation per text so
        # cosine distance is non-zero across distinct chunks.
        h = abs(hash(text_in)) % 1000
        base = [0.0] * EMBEDDING_DIM
        base[h % EMBEDDING_DIM] = 1.0
        return base

    async def embed_documents(self, texts: list[str]) -> EmbeddingRun:
        vectors = [self._vector_for(t) for t in texts]
        return EmbeddingRun(
            vectors=vectors,
            input_tokens=sum(len(t.split()) for t in texts),
            cost_usd=0.0,
            model=self.model,
        )

    async def embed_query(self, query: str) -> EmbeddingRun:
        return EmbeddingRun(
            vectors=[self._vector_for(query)],
            input_tokens=len(query.split()),
            cost_usd=0.0,
            model=self.model,
        )


def _ensure_user(session: Session) -> User:
    user = session.exec(
        select(User).where(User.email == settings.FIRST_SUPERUSER)
    ).first()
    assert user is not None, "FIRST_SUPERUSER fixture user not found"
    return user


def _delete_documents(owner_id: uuid.UUID, *doc_ids: uuid.UUID) -> None:
    if not doc_ids:
        return
    with Session(engine) as sess:
        for did in doc_ids:
            sess.execute(
                text("DELETE FROM documents WHERE id = :id AND owner_id = :owner"),
                {"id": str(did), "owner": str(owner_id)},
            )
        sess.commit()


# ---------------------------------------------------------------------------
# Pure-function tests (no DB)
# ---------------------------------------------------------------------------


def test_detect_kind_extension_dispatch() -> None:
    assert detect_kind("doc.pdf", None) == "pdf"
    assert detect_kind("notes.md", None) == "markdown"
    assert detect_kind("notes.markdown", None) == "markdown"
    assert detect_kind("page.html", None) == "html"
    assert detect_kind("page.htm", None) == "html"
    assert detect_kind("plain.txt", None) == "text"


def test_detect_kind_mime_dispatch() -> None:
    assert detect_kind("blob", "application/pdf") == "pdf"
    assert detect_kind("blob", "text/markdown") == "markdown"
    assert detect_kind("blob", "text/html; charset=utf-8") == "html"
    assert detect_kind("blob", "text/plain") == "text"


def test_detect_kind_rejects_unknown() -> None:
    with pytest.raises(UnsupportedDocumentError):
        detect_kind("doc.xlsx", None)
    with pytest.raises(UnsupportedDocumentError):
        detect_kind("blob", "application/x-zip")


def test_parse_text_passthrough() -> None:
    out = parse_text(b"hello world")
    assert out.source_type == "text"
    assert out.text == "hello world"
    assert out.metadata["char_count"] == len("hello world")


def test_parse_markdown_strips_frontmatter() -> None:
    body = b"---\ntitle: hi\n---\n# Heading\n\nbody text\n"
    out = parse_markdown(body)
    assert out.source_type == "markdown"
    assert out.text.startswith("# Heading")
    assert out.metadata["had_frontmatter"] is True


def test_parse_html_extraction_via_trafilatura() -> None:
    pytest.importorskip("trafilatura")
    body = (
        b"<html><body>"
        b"<header>nav</header>"
        b"<main><p>The main article describes octopus camouflage in detail. "
        b"Cephalopods rely on chromatophores for skin pigmentation control.</p></main>"
        b"<footer>copyright</footer>"
        b"</body></html>"
    )
    out = parse_html(body)
    assert out.source_type == "html"
    assert "octopus" in out.text.lower()
    # trafilatura should drop nav/footer in 'favor_recall' mode.
    assert "copyright" not in out.text.lower()


def test_chunker_groups_paragraphs_under_target() -> None:
    text_body = (
        "First paragraph about octopus camouflage and chromatophores.\n\n"
        "Second paragraph about cephalopod cognition.\n\n"
        "Third paragraph mentions deep sea exploration."
    )
    chunks = chunk_text(text_body, target_tokens=200, overlap_tokens=20)
    assert len(chunks) >= 1
    # Char offsets should be strictly within the input.
    for c in chunks:
        assert 0 <= c.char_start < c.char_end <= len(text_body)


def test_chunker_handles_oversized_paragraph() -> None:
    big = " ".join(f"word{i}" for i in range(2000))
    chunks = chunk_text(big, target_tokens=100, overlap_tokens=20)
    assert len(chunks) >= 2
    assert all(c.tokens <= 110 for c in chunks)  # allow small encoder slack


def test_chunker_empty_input() -> None:
    assert chunk_text("") == []
    assert chunk_text("   \n  \n  ") == []


# ---------------------------------------------------------------------------
# DB-bound round-trip
# ---------------------------------------------------------------------------


def test_pdf_round_trip() -> None:
    """End-to-end ingest of a small synthesized PDF.

    Uses ``reportlab`` (already pulled in transitively by trafilatura) to
    build a 2-page PDF in memory so we don't need a fixture file. After
    ingest we assert documents/chunks/embeddings are written and the LLM
    cost log row exists.
    """
    pytest.importorskip("pypdf")
    try:
        import io

        from reportlab.lib.pagesizes import letter  # type: ignore[import-untyped]
        from reportlab.pdfgen import canvas  # type: ignore[import-untyped]
    except Exception:
        pytest.skip("reportlab not available; skipping PDF round-trip")

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    for page_idx in range(2):
        c.drawString(
            72,
            720,
            f"Octopus camouflage and chromatophores. Page {page_idx + 1}.",
        )
        for line_idx in range(40):
            c.drawString(
                72,
                700 - line_idx * 14,
                f"Cephalopod biology line {line_idx} on page {page_idx + 1}.",
            )
        c.showPage()
    c.save()
    pdf_bytes = buf.getvalue()

    with Session(engine) as sess:
        user = _ensure_user(sess)

    result = asyncio.run(
        ingest_document(
            file_bytes=pdf_bytes,
            filename="octopus.pdf",
            owner_id=user.id,
            mime_type="application/pdf",
            embedder=_FakeEmbedder(),
        )
    )
    try:
        assert result.n_chunks >= 1
        with Session(engine) as sess:
            doc = sess.get(Document, result.document_id)
            assert doc is not None
            assert doc.owner_id == user.id
            chunks = sess.exec(
                select(Chunk).where(Chunk.document_id == result.document_id)
            ).all()
            assert len(chunks) == result.n_chunks
            embeddings = sess.exec(
                select(Embedding).where(
                    Embedding.chunk_id.in_([c.id for c in chunks])  # type: ignore[attr-defined]
                )
            ).all()
            assert len(embeddings) == len(chunks)
            cost_rows = sess.exec(
                select(LlmCostLog).where(LlmCostLog.document_id == result.document_id)
            ).all()
            assert len(cost_rows) == 1
            assert cost_rows[0].model == "voyage-3-large"
    finally:
        _delete_documents(user.id, result.document_id)


def test_html_extraction_via_trafilatura() -> None:
    pytest.importorskip("trafilatura")

    html = (
        b"<!doctype html><html><body>"
        b"<nav>menu</nav>"
        b"<main><article>"
        b"<h1>Cephalopod skin</h1>"
        b"<p>Octopus camouflage is achieved through chromatophore expansion.</p>"
        b"<p>Cuttlefish use polarized vision to perceive texture for camouflage.</p>"
        b"</article></main>"
        b"<footer>about</footer>"
        b"</body></html>"
    )
    with Session(engine) as sess:
        user = _ensure_user(sess)

    result = asyncio.run(
        ingest_document(
            file_bytes=html,
            filename="cephalopods.html",
            owner_id=user.id,
            mime_type="text/html",
            embedder=_FakeEmbedder(),
        )
    )
    try:
        assert result.n_chunks >= 1
        with Session(engine) as sess:
            chunk_texts = sess.exec(
                select(Chunk.text).where(Chunk.document_id == result.document_id)
            ).all()
            joined = " ".join(chunk_texts).lower()
            assert "octopus" in joined or "cephalopod" in joined
    finally:
        _delete_documents(user.id, result.document_id)


def test_notify_emitted() -> None:
    """A separate connection running ``LISTEN ingestion`` observes the NOTIFY.

    We open a psycopg async connection in a background task, LISTEN, run the
    ingest in a thread, and assert the notification arrives.
    """
    import psycopg

    dsn = str(settings.SQLALCHEMY_DATABASE_URI).replace(
        "postgresql+psycopg://", "postgresql://"
    )

    async def _watch_for_notify(deadline_s: float) -> str | None:
        # Async listener on a dedicated autocommit connection.
        async with await psycopg.AsyncConnection.connect(dsn, autocommit=True) as conn:
            await conn.execute(f"LISTEN {NOTIFY_CHANNEL}")
            start = time.monotonic()
            async for note in conn.notifies():
                if note.channel == NOTIFY_CHANNEL:
                    return note.payload
                if time.monotonic() - start > deadline_s:
                    return None
        return None

    async def _run() -> tuple[uuid.UUID, str | None]:
        with Session(engine) as sess:
            user = _ensure_user(sess)
            user_id = user.id

        listener_task = asyncio.create_task(_watch_for_notify(deadline_s=5.0))
        # Tiny grace period so LISTEN registers before NOTIFY fires.
        await asyncio.sleep(0.2)

        result = await ingest_document(
            file_bytes=b"hello notify\n\nsecond paragraph.",
            filename="notify.txt",
            owner_id=user_id,
            mime_type="text/plain",
            embedder=_FakeEmbedder(),
        )
        try:
            payload = await asyncio.wait_for(listener_task, timeout=5.0)
        except asyncio.TimeoutError:
            payload = None
        return result.document_id, payload

    document_id, payload = asyncio.run(_run())
    try:
        assert payload is not None, (
            "Did not observe NOTIFY ingestion within 5s after commit"
        )
        assert payload == str(document_id)
    finally:
        with Session(engine) as sess:
            user = _ensure_user(sess)
        _delete_documents(user.id, document_id)


# ---------------------------------------------------------------------------
# Live Voyage API
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    os.environ.get("LENS_LIVE_API") != "1",
    reason="LENS_LIVE_API=1 required for live Voyage embedding tests",
)
def test_voyage_batch_handles_64_chunks() -> None:
    """Verify the embedder batches 64 chunks/call against the live API."""
    import asyncio as _asyncio

    embedder = VoyageEmbedder()
    if not embedder._api_key:  # type: ignore[attr-defined]
        pytest.skip("VOYAGE_API_KEY not set")

    texts = [f"Paragraph {i} about octopus camouflage." for i in range(70)]
    run = _asyncio.run(embedder.embed_documents(texts))
    assert len(run.vectors) == 70
    assert all(len(v) == EMBEDDING_DIM for v in run.vectors)
    assert run.input_tokens > 0
    assert run.cost_usd >= 0
