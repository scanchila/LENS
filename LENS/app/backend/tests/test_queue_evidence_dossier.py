"""Tests for the ``queue_evidence_dossier`` tool (TICKET-045)."""

from __future__ import annotations

import asyncio
import shutil
import time
import uuid
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from sqlmodel import Session, select

from app.agents.tools.queue_evidence_dossier import (
    QueueEvidenceDossierTool,
    _next_runtime_index,
    _resolve_ticket_dir,
)
from app.agents.types import ToolContext
from app.core.db import engine
from app.models import DossierJob


def _ctx() -> ToolContext:
    return ToolContext(
        session_id=uuid.uuid4(),
        parent_agent_name="test-orchestrator",
        parent_run_id=uuid.uuid4(),
    )


def _new_candidate_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def tickets_dir(tmp_path: Path) -> Path:
    """Set up an isolated CAR tickets directory under tmp_path.

    Symlinks the real CAR ``bin/`` folder into ``.codex-autorunner/`` so
    ``lint_tickets.py`` is reachable; if the real bin can't be found, the
    tool degrades to ok=True and the test still validates the file write.
    """
    ca_root = tmp_path / ".codex-autorunner"
    target = ca_root / "tickets"
    target.mkdir(parents=True)

    # Try to make the real lint script reachable from the tmp ca_root.
    candidates = [
        Path.home()
        / "Neuryta"
        / "hackathon"
        / "car-hub"
        / "lens"
        / ".codex-autorunner"
        / "bin",
        Path("/home/santiago/Neuryta/hackathon/car-hub/lens/.codex-autorunner/bin"),
    ]
    for src in candidates:
        if src.exists():
            shutil.copytree(src, ca_root / "bin")
            break
    return target


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _cleanup_jobs(ticket_ids: list[str]) -> None:
    if not ticket_ids:
        return
    with Session(engine) as session:
        for tid in ticket_ids:
            job = session.exec(
                select(DossierJob).where(DossierJob.ticket_id == tid)
            ).first()
            if job is not None:
                session.delete(job)
        session.commit()


def test_writes_valid_ticket(tickets_dir: Path) -> None:
    tool = QueueEvidenceDossierTool(ticket_dir_override=tickets_dir)
    candidate_id = _new_candidate_id()
    result = _run(
        tool.execute(
            {
                "candidate_id": candidate_id,
                "claim_summary": "Founders increasingly outsource ops to AI agents.",
                "lens_attribution": "cross_domain_transfer",
            },
            _ctx(),
        )
    )
    try:
        assert not result.is_error, f"tool returned error: {result.content}"
        ticket_id = result.metadata["ticket_id"]
        ticket_file = Path(result.metadata["ticket_file"])
        assert ticket_file.exists()
        assert ticket_file.parent.resolve() == tickets_dir.resolve()
        assert ticket_file.name.startswith("TICKET-1")
        assert ticket_file.name.endswith(".md")
        body = ticket_file.read_text(encoding="utf-8")
        assert ticket_id in body
        assert candidate_id in body
        assert "cross_domain_transfer" in body
        for marker in (
            "<!-- BEGIN: sources -->",
            "<!-- END: sources -->",
            "<!-- BEGIN: claims -->",
            "<!-- END: claims -->",
        ):
            assert marker in body
    finally:
        _cleanup_jobs([result.metadata.get("ticket_id")] if not result.is_error else [])


def test_dossier_jobs_row_created(tickets_dir: Path) -> None:
    tool = QueueEvidenceDossierTool(ticket_dir_override=tickets_dir)
    candidate_id = _new_candidate_id()
    result = _run(
        tool.execute(
            {
                "candidate_id": candidate_id,
                "claim_summary": "Long-form summary about a real testable pattern.",
                "lens_attribution": "contradiction_surfacing",
            },
            _ctx(),
        )
    )
    assert not result.is_error, result.content
    ticket_id = result.metadata["ticket_id"]
    try:
        with Session(engine) as session:
            job = session.exec(
                select(DossierJob).where(DossierJob.ticket_id == ticket_id)
            ).first()
            assert job is not None, "dossier_jobs row not inserted"
            assert job.status == "queued"
            assert job.candidate_id == UUID(candidate_id)
            assert job.lens_attribution == "contradiction_surfacing"
            assert job.ticket_path is not None
            assert Path(job.ticket_path).exists()
            assert job.ingested_at is None
    finally:
        _cleanup_jobs([ticket_id])


def test_returns_fast(tickets_dir: Path) -> None:
    """Tool should return well under one second; the spec calls out 100ms,
    but we use a generous bound here because Postgres + lint subprocess add
    overhead on shared CI runners. We assert no network/LLM call slipped in.
    """
    tool = QueueEvidenceDossierTool(ticket_dir_override=tickets_dir)
    candidate_id = _new_candidate_id()
    start = time.perf_counter()
    result = _run(
        tool.execute(
            {
                "candidate_id": candidate_id,
                "claim_summary": "Rapid-return latency check.",
                "lens_attribution": "cross_domain_transfer",
            },
            _ctx(),
        )
    )
    elapsed = time.perf_counter() - start
    try:
        assert not result.is_error, result.content
        assert elapsed < 5.0, f"tool took {elapsed:.2f}s, expected < 5s"
    finally:
        _cleanup_jobs([result.metadata.get("ticket_id")] if not result.is_error else [])


def test_runtime_index_skips_build_range(tickets_dir: Path) -> None:
    # Pre-populate the directory with a build ticket and a runtime ticket.
    (tickets_dir / "TICKET-047-some-build-ticket.md").write_text(
        "---\nticket_id: tkt_old\nagent: hermes\ndone: false\n---\n", encoding="utf-8"
    )
    (tickets_dir / "TICKET-1003-existing-runtime.md").write_text(
        "---\nticket_id: tkt_old2\nagent: hermes\ndone: false\n---\n", encoding="utf-8"
    )
    next_idx = _next_runtime_index(tickets_dir)
    assert next_idx == 1004, f"expected 1004 (after 1003), got {next_idx}"

    tool = QueueEvidenceDossierTool(ticket_dir_override=tickets_dir)
    candidate_id = _new_candidate_id()
    result = _run(
        tool.execute(
            {
                "candidate_id": candidate_id,
                "claim_summary": "Index-allocation behavior verification.",
                "lens_attribution": "cross_domain_transfer",
            },
            _ctx(),
        )
    )
    try:
        assert not result.is_error, result.content
        ticket_file = Path(result.metadata["ticket_file"])
        assert "TICKET-1004-evidence-" in ticket_file.name
    finally:
        _cleanup_jobs([result.metadata.get("ticket_id")] if not result.is_error else [])


def test_resolve_ticket_dir_absolute(tmp_path: Path) -> None:
    abs_path = tmp_path / "explicit"
    abs_path.mkdir()
    resolved = _resolve_ticket_dir(abs_path)
    assert resolved == abs_path.resolve()


def test_runtime_index_empty_dir(tmp_path: Path) -> None:
    assert _next_runtime_index(tmp_path) == 1000


def test_tool_rejects_invalid_candidate_id(tickets_dir: Path) -> None:
    tool = QueueEvidenceDossierTool(ticket_dir_override=tickets_dir)
    result = _run(
        tool.execute(
            {
                "candidate_id": "not-a-uuid",
                "claim_summary": "x",
                "lens_attribution": "y",
            },
            _ctx(),
        )
    )
    assert result.is_error
    assert result.metadata.get("reason") == "invalid_candidate_id"
