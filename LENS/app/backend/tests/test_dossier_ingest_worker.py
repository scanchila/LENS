"""Tests for the CAR dossier_ingest_worker (TICKET-046).

These tests use the AGE schema seeded by PR 1's migrations. They issue
real Cypher (via :mod:`app.graph.age_client`) so they require the
backend's Postgres+AGE container to be running.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any
from uuid import UUID

from psycopg import AsyncConnection
from sqlmodel import Session, select

from app.core.db import engine
from app.graph import age_client
from app.models import DossierJob
from app.workers.dossier_ingest_worker import (
    NOTIFY_CHANNEL,
    _dsn_for_psycopg,
    ingest_one,
)

# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _candidate_id() -> str:
    return str(uuid.uuid4())


def _build_dossier(
    *,
    candidate_id: str,
    ticket_id: str,
    sources: list[tuple[str, str, str, str]],
    claims: list[tuple[str, str, list[int]]],
    done: bool = True,
) -> str:
    """Return a hand-crafted dossier MD body matching the 047 template.

    ``sources`` items are (title, url, kind, summary).
    ``claims`` items are (text, valence, source_indices).
    """
    src_lines = []
    for i, (title, url, kind, summary) in enumerate(sources, start=1):
        src_lines.append(f"{i}. [{title}]({url}) — {kind} — {summary}")
    sources_block = "\n".join(src_lines) if src_lines else "_No sources found._"

    claim_lines = []
    for text, valence, idx_list in claims:
        cite = ", ".join(str(i) for i in idx_list) or "—"
        claim_lines.append(f"- {text} — {valence} — based on sources [{cite}]")
    claims_block = "\n".join(claim_lines) if claim_lines else "_No claims extracted._"

    done_str = "true" if done else "false"
    return f"""---
title: "Evidence dossier — synthetic"
agent: hermes
done: {done_str}
ticket_id: "{ticket_id}"
candidate_id: "{candidate_id}"
lens_attribution: "cross_domain_transfer"
model: claude-sonnet-4-6
---

## Context

<!-- BEGIN: context -->
**Candidate:** {candidate_id}
<!-- END: context -->

## Search plan

<!-- BEGIN: search_plan -->
plan
<!-- END: search_plan -->

## Sources found

<!-- BEGIN: sources -->
{sources_block}
<!-- END: sources -->

## Claims extracted

<!-- BEGIN: claims -->
{claims_block}
<!-- END: claims -->

## Confidence note

<!-- BEGIN: confidence -->
note
<!-- END: confidence -->

## Run record

<!-- BEGIN: run_record -->
- Termination: completed
<!-- END: run_record -->
"""


def _seed_dossier_job(*, ticket_id: str, candidate_id: str, ticket_path: Path) -> None:
    with Session(engine) as session:
        job = DossierJob(
            ticket_id=ticket_id,
            candidate_id=UUID(candidate_id),
            status="queued",
            lens_attribution="cross_domain_transfer",
            ticket_path=str(ticket_path),
        )
        session.add(job)
        session.commit()


def _cleanup_dossier(*, ticket_id: str, candidate_id: str) -> None:
    """Remove DossierJob row + AGE traces created in a test."""
    with Session(engine) as session:
        job = session.exec(
            select(DossierJob).where(DossierJob.ticket_id == ticket_id)
        ).first()
        if job is not None:
            session.delete(job)
            session.commit()
    try:
        _run(
            age_client.with_graph(
                "MATCH (c:Candidate {id: $id}) DETACH DELETE c RETURN 1",
                {"id": candidate_id},
            )
        )
    except Exception:
        pass


def _count_age_sources_for_candidate(candidate_id: str) -> int:
    rows = _run(
        age_client.with_graph(
            "MATCH (c:Candidate {id: $id})-[:cited_by]->(s:Source) RETURN count(s)",
            {"id": candidate_id},
        )
    )
    raw = str(rows[0][0])
    return int(raw.split("::")[0])


def _count_age_claims_attached_to_candidate(candidate_id: str) -> int:
    rows = _run(
        age_client.with_graph(
            (
                "MATCH (q:Claim)-[r:supports|refutes]->(c:Candidate {id: $id}) "
                "RETURN count(q)"
            ),
            {"id": candidate_id},
        )
    )
    raw = str(rows[0][0])
    return int(raw.split("::")[0])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_round_trip(tmp_path: Path) -> None:
    candidate_id = _candidate_id()
    ticket_id = f"tkt_{uuid.uuid4().hex}"
    sources = [
        ("Paper A", "https://example.com/a", "paper", "Strong support."),
        ("HN Thread", "https://news.ycombinator.com/x", "forum", "Mixed signal."),
        ("Blog post", "https://example.com/b", "blog", "Direct refutation."),
    ]
    claims = [
        ("Adoption is accelerating.", "supports", [1, 2]),
        ("Cost is prohibitive at scale.", "refutes", [3]),
    ]
    body = _build_dossier(
        candidate_id=candidate_id,
        ticket_id=ticket_id,
        sources=sources,
        claims=claims,
    )
    file_path = tmp_path / "TICKET-1090-evidence-trip.md"
    file_path.write_text(body, encoding="utf-8")
    _seed_dossier_job(
        ticket_id=ticket_id, candidate_id=candidate_id, ticket_path=file_path
    )
    try:
        parsed = _run(ingest_one(file_path, notify=False))
        assert parsed is not None
        assert len(parsed.sources) == 3
        assert len(parsed.claims) == 2

        assert _count_age_sources_for_candidate(candidate_id) == 3
        assert _count_age_claims_attached_to_candidate(candidate_id) == 2

        with Session(engine) as session:
            job = session.exec(
                select(DossierJob).where(DossierJob.ticket_id == ticket_id)
            ).first()
            assert job is not None
            assert job.status == "ingested"
            assert job.ingested_at is not None
            assert job.payload_hash is not None
            assert job.dossier_path == str(file_path)
    finally:
        _cleanup_dossier(ticket_id=ticket_id, candidate_id=candidate_id)


def test_idempotent(tmp_path: Path) -> None:
    candidate_id = _candidate_id()
    ticket_id = f"tkt_{uuid.uuid4().hex}"
    sources = [("S", "https://x.test/y", "web", "ok.")]
    claims = [("Single claim.", "neutral", [1])]
    body = _build_dossier(
        candidate_id=candidate_id,
        ticket_id=ticket_id,
        sources=sources,
        claims=claims,
    )
    file_path = tmp_path / "TICKET-1091-evidence-idem.md"
    file_path.write_text(body, encoding="utf-8")
    _seed_dossier_job(
        ticket_id=ticket_id, candidate_id=candidate_id, ticket_path=file_path
    )
    try:
        first = _run(ingest_one(file_path, notify=False))
        second = _run(ingest_one(file_path, notify=False))

        assert first is not None
        assert second is not None
        assert first.payload_hash == second.payload_hash

        # Source count remains 1 because the second pass short-circuited
        # before any AGE writes.
        assert _count_age_sources_for_candidate(candidate_id) == 1
    finally:
        _cleanup_dossier(ticket_id=ticket_id, candidate_id=candidate_id)


def test_malformed_skipped(tmp_path: Path) -> None:
    candidate_id = _candidate_id()
    ticket_id = f"tkt_{uuid.uuid4().hex}"
    # Frontmatter present, but the required ``sources`` section is absent.
    body = (
        f'---\nticket_id: "{ticket_id}"\ncandidate_id: "{candidate_id}"\n'
        f"agent: hermes\ndone: true\n---\n\n## Claims\n\n"
        "<!-- BEGIN: claims -->\n_None._\n<!-- END: claims -->\n"
    )
    file_path = tmp_path / "TICKET-1092-evidence-malformed.md"
    file_path.write_text(body, encoding="utf-8")
    _seed_dossier_job(
        ticket_id=ticket_id, candidate_id=candidate_id, ticket_path=file_path
    )
    try:
        parsed = _run(ingest_one(file_path, notify=False))
        assert parsed is None  # malformed → skipped, not raised
        with Session(engine) as session:
            job = session.exec(
                select(DossierJob).where(DossierJob.ticket_id == ticket_id)
            ).first()
            assert job is not None
            assert job.status == "failed"
            assert job.error_message and "parse_error" in job.error_message
    finally:
        _cleanup_dossier(ticket_id=ticket_id, candidate_id=candidate_id)


def test_notify_dossier_ready(tmp_path: Path) -> None:
    candidate_id = _candidate_id()
    ticket_id = f"tkt_{uuid.uuid4().hex}"
    body = _build_dossier(
        candidate_id=candidate_id,
        ticket_id=ticket_id,
        sources=[("S", "https://notify.test/", "web", "x.")],
        claims=[("c", "supports", [1])],
    )
    file_path = tmp_path / "TICKET-1093-evidence-notify.md"
    file_path.write_text(body, encoding="utf-8")
    _seed_dossier_job(
        ticket_id=ticket_id, candidate_id=candidate_id, ticket_path=file_path
    )

    received: list[str] = []

    async def listen_then_ingest() -> None:
        dsn = _dsn_for_psycopg()
        conn = await AsyncConnection.connect(dsn, autocommit=True)
        try:
            async with conn.cursor() as cur:
                await cur.execute(f"LISTEN {NOTIFY_CHANNEL}")
            # Trigger the ingest after the LISTEN is in place.
            await ingest_one(file_path, notify=True)
            try:
                async with asyncio.timeout(5.0):
                    async for notify in conn.notifies():
                        received.append(notify.payload)
                        break
            except asyncio.TimeoutError:
                pass
        finally:
            await conn.close()

    try:
        _run(listen_then_ingest())
        assert candidate_id in received, f"NOTIFY did not deliver; got {received!r}"
    finally:
        _cleanup_dossier(ticket_id=ticket_id, candidate_id=candidate_id)
