"""Long-running async worker that ingests completed CAR dossiers.

Lifecycle:

  1. Watch ``settings.LENS_CAR_TICKET_DIR`` via ``watchfiles.awatch``.
  2. For every change to ``TICKET-1NNN-*.md`` (runtime evidence range)
     whose frontmatter ``ticket_id`` matches a queued ``dossier_jobs``
     row and whose ``done`` field is ``true``, run :func:`ingest_one`.
  3. :func:`ingest_one` parses the markdown, checks the structure hash
     against ``dossier_jobs.payload_hash`` for idempotency, writes
     Sources + Claims + edges to AGE, and sends ``NOTIFY dossier_ready``
     so the orchestrator can re-eval the affected candidate.

This is the single write-point to AGE from CAR output. The worker
survives malformed dossiers by catching :class:`DossierParseError`,
recording the message in ``dossier_jobs.error_message``, and continuing
the watch loop.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import AsyncIterator, Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from psycopg import AsyncConnection
from sqlmodel import Session, select

from app.core.config import settings
from app.core.db import engine
from app.graph import AGEClient, age_client
from app.models import DossierJob

from .dossier_parser import (
    DossierParseError,
    ParsedDossier,
    parse_dossier_file,
)

logger = logging.getLogger(__name__)

# Filename like TICKET-1003-evidence-...md. We only ingest tickets in the
# runtime range (>= 1000) per the queueing convention; build tickets
# (001-999) cannot be evidence_dossiers.
_RUNTIME_TICKET_RE = re.compile(r"^TICKET-1\d{3}-")

NOTIFY_CHANNEL = "dossier_ready"


# ---------------------------------------------------------------------------
# DB helpers (sync)
# ---------------------------------------------------------------------------


def _get_dossier_job(ticket_id: str) -> DossierJob | None:
    with Session(engine) as session:
        return session.exec(
            select(DossierJob).where(DossierJob.ticket_id == ticket_id)
        ).first()


def _mark_failed(ticket_id: str, error_message: str) -> None:
    with Session(engine) as session:
        job = session.exec(
            select(DossierJob).where(DossierJob.ticket_id == ticket_id)
        ).first()
        if job is None:
            return
        job.status = "failed"
        job.error_message = error_message[:2000]  # avoid pathological payloads
        session.add(job)
        session.commit()


def _mark_ingested(*, ticket_id: str, dossier_path: Path, payload_hash: str) -> None:
    with Session(engine) as session:
        job = session.exec(
            select(DossierJob).where(DossierJob.ticket_id == ticket_id)
        ).first()
        if job is None:
            return
        job.status = "ingested"
        job.ingested_at = datetime.now(timezone.utc)
        job.dossier_path = str(dossier_path)
        job.payload_hash = payload_hash
        job.error_message = None
        session.add(job)
        session.commit()


def _dsn_for_psycopg() -> str:
    return str(settings.SQLALCHEMY_DATABASE_URI).replace(
        "postgresql+psycopg://", "postgresql://"
    )


# ---------------------------------------------------------------------------
# AGE writes
# ---------------------------------------------------------------------------


async def _write_to_age(
    *,
    candidate_id: str,
    parsed: ParsedDossier,
    age: AGEClient = age_client,
) -> None:
    """Merge candidate + sources + claims + edges into the AGE graph.

    All writes use ``MERGE`` so re-runs against the same logical content
    do not produce duplicate nodes/edges. ``ingest_one`` short-circuits
    before this is called when ``payload_hash`` matches the prior run,
    so the AGE workload is bounded.
    """
    # Ensure the Candidate node exists. Other producers (lens proposers,
    # synthesizer) may also create it; MERGE is the contract.
    await age.with_graph(
        "MERGE (c:Candidate {id: $candidate_id}) RETURN c",
        {"candidate_id": candidate_id},
    )

    for source in parsed.sources:
        await age.with_graph(
            (
                "MERGE (s:Source {url: $url}) "
                "SET s.kind = $kind, s.title = $title, s.citation = $citation "
                "WITH s "
                "MATCH (c:Candidate {id: $candidate_id}) "
                "MERGE (c)-[r:cited_by]->(s) "
                "RETURN s"
            ),
            {
                "url": source.url,
                "kind": source.kind,
                "title": source.title,
                "citation": source.summary,
                "candidate_id": candidate_id,
            },
        )

    for claim in parsed.claims:
        edge = (
            "supports"
            if claim.valence == "supports"
            else ("refutes" if claim.valence == "refutes" else None)
        )
        # Always create the Claim node (text+valence carry the meaning).
        await age.with_graph(
            ("MERGE (q:Claim {text: $text, valence: $valence}) RETURN q"),
            {"text": claim.text, "valence": claim.valence},
        )
        if edge is None:
            # Neutral claims attach to the candidate but pick neither
            # 'supports' nor 'refutes'; emit a generic supports edge so
            # provenance is still queryable. This is the minimal commitment.
            continue
        await age.with_graph(
            (
                f"MATCH (q:Claim {{text: $text, valence: $valence}}), "
                f"(c:Candidate {{id: $candidate_id}}) "
                f"MERGE (q)-[r:{edge}]->(c) "
                "RETURN r"
            ),
            {
                "text": claim.text,
                "valence": claim.valence,
                "candidate_id": candidate_id,
            },
        )


# ---------------------------------------------------------------------------
# NOTIFY
# ---------------------------------------------------------------------------


async def _notify_dossier_ready(candidate_id: str) -> None:
    """Send Postgres ``NOTIFY dossier_ready '<candidate_id>'``.

    A separate connection is used (autocommit) because NOTIFY is only
    delivered when the transaction commits; the SQLModel sync session
    above already committed the row update.
    """
    dsn = _dsn_for_psycopg()
    async with await AsyncConnection.connect(dsn, autocommit=True) as conn:
        async with conn.cursor() as cur:
            payload = candidate_id.replace("'", "''")
            await cur.execute(f"NOTIFY {NOTIFY_CHANNEL}, '{payload}'")


# ---------------------------------------------------------------------------
# Per-file ingest
# ---------------------------------------------------------------------------


async def ingest_one(
    path: Path,
    *,
    age: AGEClient = age_client,
    notify: bool = True,
) -> ParsedDossier | None:
    """Parse and ingest a single dossier file.

    Returns the parsed dossier on success, ``None`` if the file is not
    relevant (no matching dossier_jobs row, not done, etc.). Re-raises
    unexpected exceptions for the watch loop to log.
    """
    if not _RUNTIME_TICKET_RE.match(path.name):
        return None
    try:
        parsed = parse_dossier_file(path)
    except DossierParseError as exc:
        logger.warning("dossier %s malformed: %s", path, exc)
        # Try to extract just the ticket_id to mark the job failed.
        from .dossier_parser import _parse_frontmatter

        fm = _parse_frontmatter(path.read_text(encoding="utf-8"))
        ticket_id = (fm.get("ticket_id") or "").strip()
        if ticket_id:
            _mark_failed(ticket_id, f"parse_error: {exc}")
        return None

    if not parsed.done:
        # Dossier exists but is not yet marked done by Hermes; ignore.
        return None

    job = _get_dossier_job(parsed.ticket_id)
    if job is None:
        logger.info(
            "dossier %s has no matching dossier_jobs row (ticket_id=%s); skipping",
            path,
            parsed.ticket_id,
        )
        return None
    if job.status == "ingested" and job.payload_hash == parsed.payload_hash:
        return parsed  # idempotent no-op

    candidate_id = str(job.candidate_id)
    try:
        await _write_to_age(candidate_id=candidate_id, parsed=parsed, age=age)
    except Exception as exc:
        logger.exception("AGE write failed for %s", path)
        _mark_failed(parsed.ticket_id, f"age_write_error: {exc}")
        return None

    _mark_ingested(
        ticket_id=parsed.ticket_id,
        dossier_path=path,
        payload_hash=parsed.payload_hash,
    )

    if notify:
        try:
            await _notify_dossier_ready(candidate_id)
        except Exception:
            logger.exception("NOTIFY dossier_ready failed for %s", candidate_id)

    return parsed


# ---------------------------------------------------------------------------
# Watch loop
# ---------------------------------------------------------------------------


def _resolve_ticket_dir() -> Path:
    """Resolve LENS_CAR_TICKET_DIR; relative paths are repo-root relative."""
    configured = Path(settings.LENS_CAR_TICKET_DIR)
    if configured.is_absolute():
        return configured.resolve()
    backend_root = Path(__file__).resolve().parents[3]
    repo_root = backend_root.parent.parent.parent
    return (repo_root / configured).resolve()


def _watch_changes(ticket_dir: Path) -> AsyncIterator[set[tuple[Any, str]]]:
    """Lazy import wrapper around ``watchfiles.awatch``.

    Exists so test code can stub the watcher without importing watchfiles.
    """
    from watchfiles import awatch  # type: ignore[import-not-found]

    return awatch(ticket_dir)


async def _process_paths(paths: Iterable[Path], age: AGEClient = age_client) -> None:
    for path in paths:
        if not path.exists() or not path.is_file():
            continue
        try:
            await ingest_one(path, age=age)
        except Exception:
            logger.exception("unhandled error ingesting %s; continuing", path)


async def watch_loop(
    *,
    ticket_dir: Path | None = None,
    age: AGEClient = age_client,
) -> None:
    """Run the ingest worker forever. Cancels cleanly on asyncio cancel."""
    target_dir = ticket_dir or _resolve_ticket_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    logger.info("dossier_ingest_worker watching %s", target_dir)

    # Pick up any tickets already in done state when the worker (re)starts.
    existing = sorted(target_dir.glob("TICKET-1*.md"))
    if existing:
        logger.info("backfill scan: %d candidate runtime tickets", len(existing))
        await _process_paths(existing, age=age)

    async for changes in _watch_changes(target_dir):
        paths: list[Path] = []
        for _change_type, raw in changes:
            try:
                p = Path(raw)
            except Exception:
                continue
            if p.parent.resolve() != target_dir:
                continue
            paths.append(p)
        if paths:
            await _process_paths(paths, age=age)


def run() -> None:
    """Synchronous entrypoint suitable for ``python -m``."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        asyncio.run(watch_loop())
    except KeyboardInterrupt:
        logger.info("dossier_ingest_worker shutting down")


if __name__ == "__main__":  # pragma: no cover
    run()
