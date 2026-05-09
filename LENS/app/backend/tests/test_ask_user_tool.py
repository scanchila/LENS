"""Tests for the web-mediated ask_user tool (TICKET-042)."""

from __future__ import annotations

import asyncio
import os
import threading
import time
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlmodel import Session

from app.agents.tools.ask_user import (
    POLL_INTERVAL_SEC,
    TIMEOUT_ENV_VAR,
    AskUserTool,
)
from app.agents.types import ToolContext
from app.core.config import settings
from app.core.db import engine


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _ctx(*, agent_name: str = "user_liaison") -> ToolContext:
    return ToolContext(
        session_id=uuid.uuid4(),
        parent_agent_name=agent_name,
        parent_run_id=uuid.uuid4(),
    )


def _delete_question(question_id: uuid.UUID) -> None:
    with Session(engine) as session:
        session.execute(
            text("DELETE FROM pending_user_questions WHERE id = :id"),
            {"id": str(question_id)},
        )
        session.commit()


def _delete_questions_for_session(session_id: uuid.UUID) -> None:
    with Session(engine) as session:
        session.execute(
            text("DELETE FROM pending_user_questions WHERE session_id = :sid"),
            {"sid": str(session_id)},
        )
        session.commit()


def _read_pending_for_session(session_id: uuid.UUID) -> uuid.UUID | None:
    """Return the most recent unanswered question id for the session, or None."""
    with Session(engine) as session:
        row = session.execute(
            text(
                "SELECT id FROM pending_user_questions "
                "WHERE session_id = :sid AND answer IS NULL "
                "ORDER BY asked_at DESC LIMIT 1"
            ),
            {"sid": str(session_id)},
        ).first()
    return uuid.UUID(str(row[0])) if row is not None else None


def _read_pending_ids_for_session(session_id: uuid.UUID) -> list[uuid.UUID]:
    with Session(engine) as session:
        rows = session.execute(
            text(
                "SELECT id FROM pending_user_questions "
                "WHERE session_id = :sid AND answer IS NULL "
                "ORDER BY asked_at ASC"
            ),
            {"sid": str(session_id)},
        ).all()
    return [uuid.UUID(str(r[0])) for r in rows]


def test_round_trip_via_api() -> None:
    """A background thread answers the question via the API after ~200ms;
    tool returns within 500ms of that."""
    os.environ[TIMEOUT_ENV_VAR] = "10"
    try:
        from app.main import app

        tool = AskUserTool()
        ctx = _ctx()
        answer_text = "yes, X is true"
        errors: list[str] = []

        def answer_when_ready() -> None:
            try:
                with TestClient(app) as client:
                    deadline = time.monotonic() + 5.0
                    qid: uuid.UUID | None = None
                    while qid is None:
                        qid = _read_pending_for_session(ctx.session_id)
                        if qid is not None:
                            break
                        if time.monotonic() >= deadline:
                            errors.append("tool never enqueued a question row")
                            return
                        time.sleep(0.025)
                    # Answer ~200ms after the row appeared.
                    time.sleep(0.2)
                    resp = client.post(
                        f"{settings.API_V1_STR}/sessions/{ctx.session_id}/answer-question",
                        json={"question_id": str(qid), "answer": answer_text},
                    )
                    if resp.status_code != 204:
                        errors.append(
                            f"answer endpoint returned {resp.status_code}: {resp.text}"
                        )
            except Exception as exc:  # pragma: no cover — bubble into assertion
                errors.append(repr(exc))

        worker = threading.Thread(target=answer_when_ready, daemon=True)
        worker.start()

        t0 = time.monotonic()
        result = _run(tool.execute({"question": "Is X true?"}, ctx))
        elapsed = time.monotonic() - t0

        worker.join(timeout=5)
        assert not errors, errors
        assert not result.is_error, result.content
        assert result.content == answer_text
        # Allow generous CI slack: 200ms answer delay + a couple poll cycles.
        assert elapsed < 1.5, f"tool returned too slowly: {elapsed:.3f}s"

        question_id = uuid.UUID(result.metadata["question_id"])
        _delete_question(question_id)
    finally:
        os.environ.pop(TIMEOUT_ENV_VAR, None)


def test_timeout() -> None:
    """A short timeout (env-overridden) returns the expected error result."""
    # Slightly above one poll interval so we exercise at least one poll cycle.
    os.environ[TIMEOUT_ENV_VAR] = "0.4"
    try:
        tool = AskUserTool()
        ctx = _ctx()

        t0 = time.monotonic()
        result = _run(tool.execute({"question": "Will anyone answer?"}, ctx))
        elapsed = time.monotonic() - t0

        assert result.is_error
        assert "timed out" in str(result.content)
        assert 0.3 <= elapsed < 5.0, f"unexpected elapsed: {elapsed:.3f}s"
        _delete_questions_for_session(ctx.session_id)
    finally:
        os.environ.pop(TIMEOUT_ENV_VAR, None)


def test_concurrent_questions() -> None:
    """Two ask_user calls in the same session each get their own question_id."""
    os.environ[TIMEOUT_ENV_VAR] = "10"
    try:
        from app.main import app

        tool = AskUserTool()
        session_id = uuid.uuid4()
        ctx_a = ToolContext(
            session_id=session_id,
            parent_agent_name="user_liaison",
            parent_run_id=uuid.uuid4(),
        )
        ctx_b = ToolContext(
            session_id=session_id,
            parent_agent_name="user_liaison",
            parent_run_id=uuid.uuid4(),
        )

        errors: list[str] = []

        def answer_each() -> None:
            try:
                with TestClient(app) as client:
                    deadline = time.monotonic() + 5.0
                    while True:
                        ids = _read_pending_ids_for_session(session_id)
                        if len(ids) >= 2:
                            break
                        if time.monotonic() >= deadline:
                            errors.append(f"expected 2 enqueued rows, saw {len(ids)}")
                            return
                        time.sleep(0.025)
                    for qid, ans in zip(
                        ids, ["alpha-answer", "beta-answer"], strict=False
                    ):
                        resp = client.post(
                            f"{settings.API_V1_STR}/sessions/{session_id}/answer-question",
                            json={"question_id": str(qid), "answer": ans},
                        )
                        if resp.status_code != 204:
                            errors.append(
                                f"answer endpoint returned {resp.status_code}: {resp.text}"
                            )
                            return
            except Exception as exc:  # pragma: no cover
                errors.append(repr(exc))

        worker = threading.Thread(target=answer_each, daemon=True)
        worker.start()

        async def driver() -> Any:
            return await asyncio.gather(
                tool.execute({"question": "Question A?"}, ctx_a),
                tool.execute({"question": "Question B?"}, ctx_b),
            )

        a, b = _run(driver())
        worker.join(timeout=5)
        assert not errors, errors
        assert not a.is_error and not b.is_error, (a.content, b.content)

        qid_a = uuid.UUID(a.metadata["question_id"])
        qid_b = uuid.UUID(b.metadata["question_id"])
        assert qid_a != qid_b, "concurrent calls must produce distinct question ids"
        # Each tool returns the answer associated with the row it enqueued.
        # Order of resolution is not guaranteed; just check the set.
        assert {a.content, b.content} == {"alpha-answer", "beta-answer"}

        _delete_questions_for_session(session_id)
    finally:
        os.environ.pop(TIMEOUT_ENV_VAR, None)


def test_answer_question_endpoint_404_and_409() -> None:
    """Endpoint responds 404 for unknown questions and 409 for duplicates."""
    from app.main import app

    session_id = uuid.uuid4()

    with TestClient(app) as client:
        # 404: unknown question id.
        resp = client.post(
            f"{settings.API_V1_STR}/sessions/{session_id}/answer-question",
            json={"question_id": str(uuid.uuid4()), "answer": "x"},
        )
        assert resp.status_code == 404, resp.text

        # Insert a question, answer it, then attempt to answer again.
        qid = uuid.uuid4()
        with Session(engine) as session:
            session.execute(
                text(
                    "INSERT INTO pending_user_questions "
                    "(id, session_id, question, asked_by_agent) "
                    "VALUES (:id, :sid, :q, :a)"
                ),
                {
                    "id": str(qid),
                    "sid": str(session_id),
                    "q": "duplicate?",
                    "a": "user_liaison",
                },
            )
            session.commit()

        try:
            ok = client.post(
                f"{settings.API_V1_STR}/sessions/{session_id}/answer-question",
                json={"question_id": str(qid), "answer": "first"},
            )
            assert ok.status_code == 204, ok.text

            again = client.post(
                f"{settings.API_V1_STR}/sessions/{session_id}/answer-question",
                json={"question_id": str(qid), "answer": "second"},
            )
            assert again.status_code == 409, again.text
        finally:
            _delete_question(qid)


def test_poll_interval_unchanged() -> None:
    """The 250ms poll interval is part of the spec; assert it matches."""
    assert POLL_INTERVAL_SEC == pytest.approx(0.25)
