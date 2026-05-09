"""Note tool — append a structured note to ``session_notes``.

Backbone of the provenance ledger and intermediate-finding scratchpad.
Each call inserts one row keyed by ``ToolContext.session_id`` and tagged
with the calling agent. Other tools (and post-run analytics) can read
the table back; the orchestrator no longer owns an ephemeral buffer.

Ports for testing: the tool depends on a small ``NoteSink`` protocol
rather than a SQLModel session directly. The default factory binds it
to the application engine. The phase-0 smoke test injects an
in-memory implementation so it can keep running without a database.
"""

from __future__ import annotations

import uuid
from typing import Any, Protocol

from sqlalchemy.engine import Engine
from sqlmodel import Session

from app.core.db import engine as default_engine
from app.models import SessionNote

from ..tool import Tool
from ..types import ToolContext, ToolResult, ToolSpec

VALID_KINDS: frozenset[str] = frozenset(
    {"scratch", "finding", "provenance", "hypothesis", "candidate"}
)


class NoteSink(Protocol):
    """Sink that persists a note row and returns the new id.

    The default implementation writes to Postgres via SQLModel; tests and
    the smoke test can substitute an in-memory adapter.
    """

    def append(self, note: SessionNote) -> uuid.UUID: ...


class _SqlNoteSink:
    """Default sink: append-only insert into ``session_notes``."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def append(self, note: SessionNote) -> uuid.UUID:
        with Session(self._engine) as session:
            session.add(note)
            session.commit()
            session.refresh(note)
            return note.id


class NoteTool(Tool):
    spec = ToolSpec(
        name="note",
        description=(
            "Persist a structured note into the current session's note ledger. "
            "Use during the SCAN phase to capture candidate patterns, during "
            "evidence work to record provenance, and at any point to leave "
            "breadcrumbs for the synthesizer. Each call writes one row; "
            "notes are durable and visible to later agents in the same session."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The note content. One observation per call.",
                },
                "kind": {
                    "type": "string",
                    "enum": sorted(VALID_KINDS),
                    "default": "scratch",
                    "description": (
                        "Note category: 'scratch' (working thought), "
                        "'finding' (concrete observation), "
                        "'provenance' (claim-to-source link), "
                        "'hypothesis' (testable conjecture), "
                        "'candidate' (proposed problem/opportunity)."
                    ),
                },
                "payload": {
                    "type": "object",
                    "description": (
                        "Optional structured side-channel (e.g. citation list, "
                        "provenance map). Free-form JSON object."
                    ),
                },
            },
            "required": ["text"],
        },
    )

    def __init__(self, sink: NoteSink | None = None) -> None:
        self._sink = sink if sink is not None else _SqlNoteSink(default_engine)

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        text = args.get("text")
        if not isinstance(text, str) or not text.strip():
            return ToolResult(
                content="invalid text: must be a non-empty string", is_error=True
            )

        kind = args.get("kind", "scratch")
        if not isinstance(kind, str) or kind not in VALID_KINDS:
            return ToolResult(content=f"invalid kind: {kind!r}", is_error=True)

        payload = args.get("payload")
        if payload is not None and not isinstance(payload, dict):
            return ToolResult(
                content="invalid payload: must be a JSON object or omitted",
                is_error=True,
            )

        note = SessionNote(
            session_id=ctx.session_id,
            agent_name=ctx.parent_agent_name,
            kind=kind,
            text=text,
            payload=payload,
        )
        try:
            note_id = self._sink.append(note)
        except Exception as exc:  # noqa: BLE001 — surface as recoverable error
            return ToolResult(content=f"failed to persist note: {exc!r}", is_error=True)

        return ToolResult(
            content=f"note recorded (id={note_id})",
            is_error=False,
            metadata={"note_id": str(note_id), "kind": kind},
        )


class InMemoryNoteSink:
    """Minimal sink for tests and the phase-0 smoke runner.

    Stores notes in a list (publicly accessible as ``.notes``) and returns
    a fresh UUID per append. Does not exercise any DB code paths.
    """

    def __init__(self) -> None:
        self.notes: list[SessionNote] = []

    def append(self, note: SessionNote) -> uuid.UUID:
        if note.id is None:
            note.id = uuid.uuid4()
        self.notes.append(note)
        return note.id
