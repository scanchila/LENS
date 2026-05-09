"""Ask-user tool — pause the agent until the user answers.

Persists the question to ``pending_user_questions``, fires a
``pg_notify`` on the ``pending_user_questions`` channel for the
SSE listener (TICKET-080), then polls the row every 250ms until the
``answer`` column is non-null or the timeout expires. The matching
``POST /api/v1/sessions/{session_id}/answer-question`` endpoint writes
the answer.

Polling cadence (250ms) and timeout default (120s) come from the
spec. The timeout can be overridden via ``LENS_ASK_USER_TIMEOUT_SEC``
to keep tests fast.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any

from sqlalchemy import text as sql_text
from sqlalchemy.engine import Engine
from sqlmodel import Session

from app.core.db import engine as default_engine
from app.models import PendingUserQuestion

from ..tool import Tool
from ..types import ToolContext, ToolResult, ToolSpec

POLL_INTERVAL_SEC = 0.25
DEFAULT_TIMEOUT_SEC = 120.0
TIMEOUT_ENV_VAR = "LENS_ASK_USER_TIMEOUT_SEC"
NOTIFY_CHANNEL = "pending_user_questions"


def _resolve_timeout() -> float:
    raw = os.environ.get(TIMEOUT_ENV_VAR)
    if raw is None:
        return DEFAULT_TIMEOUT_SEC
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_TIMEOUT_SEC
    return value if value > 0 else DEFAULT_TIMEOUT_SEC


class AskUserTool(Tool):
    spec = ToolSpec(
        name="ask_user",
        description=(
            "Pose a clarifying or validating question to the user and wait for "
            "their answer. Use sparingly — only when the answer would meaningfully "
            "change the rest of the run. Each call blocks the agent until the user "
            "responds (or the timeout fires), so questions should be specific and "
            "minimal."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The question to ask the user, in natural language.",
                },
                "expected_answer_kind": {
                    "type": "string",
                    "description": (
                        "Optional hint about the expected answer shape "
                        "(e.g. 'one of A/B/C', 'short phrase', 'yes/no')."
                    ),
                },
            },
            "required": ["question"],
        },
    )

    def __init__(self, engine: Engine | None = None) -> None:
        self._engine = engine if engine is not None else default_engine

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        question = args.get("question")
        if not isinstance(question, str) or not question.strip():
            return ToolResult(content="Empty question; nothing asked.", is_error=True)

        try:
            question_id = self._enqueue(
                question=question.strip(),
                session_id=ctx.session_id,
                asked_by_agent=ctx.parent_agent_name,
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                content=f"failed to enqueue question: {exc!r}", is_error=True
            )

        timeout = _resolve_timeout()
        try:
            answer = await self._await_answer(question_id, timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                content=f"failed while awaiting answer: {exc!r}", is_error=True
            )

        if answer is None:
            return ToolResult(content="<no answer; timed out>", is_error=True)

        return ToolResult(
            content=answer,
            is_error=False,
            metadata={"question_id": str(question_id)},
        )

    # -- helpers ------------------------------------------------------------

    def _enqueue(
        self,
        *,
        question: str,
        session_id: uuid.UUID,
        asked_by_agent: str,
    ) -> uuid.UUID:
        row = PendingUserQuestion(
            session_id=session_id,
            question=question,
            asked_by_agent=asked_by_agent,
        )
        with Session(self._engine) as session:
            session.add(row)
            session.commit()
            session.refresh(row)
            # NOTIFY in the same connection scope so 080's LISTEN sees the
            # committed row before the wake-up. pg_notify takes literal
            # channel + payload; both are bound parameters to dodge any
            # accidental injection from tool inputs (asked_by_agent, etc.).
            session.execute(
                sql_text("SELECT pg_notify(:channel, :payload)"),
                {"channel": NOTIFY_CHANNEL, "payload": str(row.id)},
            )
            session.commit()
            return row.id

    async def _await_answer(
        self, question_id: uuid.UUID, *, timeout: float
    ) -> str | None:
        deadline = asyncio.get_event_loop().time() + timeout
        while True:
            answer = await asyncio.to_thread(self._read_answer, question_id)
            if answer is not None:
                return answer
            if asyncio.get_event_loop().time() >= deadline:
                return None
            await asyncio.sleep(POLL_INTERVAL_SEC)

    def _read_answer(self, question_id: uuid.UUID) -> str | None:
        with Session(self._engine) as session:
            row = session.execute(
                sql_text("SELECT answer FROM pending_user_questions WHERE id = :id"),
                {"id": str(question_id)},
            ).first()
        if row is None:
            return None
        value = row[0]
        return value if isinstance(value, str) else None
