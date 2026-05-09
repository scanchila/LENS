"""Tests for the persisted note tool (TICKET-041)."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from sqlalchemy import text
from sqlmodel import Session

from app.agents.tools.note import VALID_KINDS, NoteTool
from app.agents.types import ToolContext
from app.core.db import engine


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _ctx(*, agent_name: str = "cross_domain_proposer") -> ToolContext:
    return ToolContext(
        session_id=uuid.uuid4(),
        parent_agent_name=agent_name,
        parent_run_id=uuid.uuid4(),
    )


def _delete_notes(ids: list[uuid.UUID]) -> None:
    with Session(engine) as session:
        for nid in ids:
            session.execute(
                text("DELETE FROM session_notes WHERE id = :id"),
                {"id": str(nid)},
            )
        session.commit()


def test_append() -> None:
    """A successful note() call writes a row visible via SQL."""
    tool = NoteTool()
    ctx = _ctx()

    result = _run(
        tool.execute(
            {
                "text": "found something interesting",
                "kind": "finding",
                "payload": {"score": 0.42},
            },
            ctx,
        )
    )

    assert not result.is_error, result.content
    note_id = uuid.UUID(result.metadata["note_id"])

    try:
        with Session(engine) as session:
            row = session.execute(
                text(
                    "SELECT session_id, agent_name, kind, text, payload "
                    "FROM session_notes WHERE id = :id"
                ),
                {"id": str(note_id)},
            ).first()
        assert row is not None, "note row not persisted"
        assert uuid.UUID(str(row[0])) == ctx.session_id
        assert row[1] == "cross_domain_proposer"
        assert row[2] == "finding"
        assert row[3] == "found something interesting"
        assert row[4] == {"score": 0.42}
    finally:
        _delete_notes([note_id])


def test_kind_enum_validation() -> None:
    """Invalid kind values fail without writing a row; all valid kinds work."""
    tool = NoteTool()
    ctx = _ctx()

    bad = _run(tool.execute({"text": "x", "kind": "garbage"}, ctx))
    assert bad.is_error
    assert "invalid kind" in str(bad.content)

    written: list[uuid.UUID] = []
    try:
        for kind in sorted(VALID_KINDS):
            ok = _run(tool.execute({"text": f"sample for {kind}", "kind": kind}, ctx))
            assert not ok.is_error, ok.content
            written.append(uuid.UUID(ok.metadata["note_id"]))
    finally:
        _delete_notes(written)


def test_agent_name_from_context() -> None:
    """agent_name is taken from ToolContext, not from arguments."""
    tool = NoteTool()
    ctx = _ctx(agent_name="synthesizer")

    result = _run(
        tool.execute({"text": "synthesis observation", "kind": "scratch"}, ctx)
    )
    assert not result.is_error, result.content
    note_id = uuid.UUID(result.metadata["note_id"])

    try:
        with Session(engine) as session:
            row = session.execute(
                text("SELECT agent_name FROM session_notes WHERE id = :id"),
                {"id": str(note_id)},
            ).first()
        assert row is not None
        assert row[0] == "synthesizer"
    finally:
        _delete_notes([note_id])
