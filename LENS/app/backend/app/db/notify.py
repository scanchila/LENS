"""Postgres ``NOTIFY`` helper.

All publishers (lens proposers, dossier worker, orchestrator, API
verdict handlers) call into this module to publish state-change events.
The SSE endpoint (TICKET-080) is the only consumer.

The payload always includes a ``session_id`` so the SSE listener can
filter server-side. Channels:

  - ``ingestion``               — new document(s) ready
  - ``dossier_ready``           — CAR evidence_dossier ingested
  - ``candidate_updated``       — any candidate row changed
  - ``pending_user_questions``  — ask_user tool emitted a question

Synchronous and async variants are provided. Inline call patterns:

    from app.db.notify import notify_sync
    notify_sync("candidate_updated", {"session_id": sid, "candidate_id": cid})
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from uuid import UUID

import psycopg
from sqlalchemy import text

from app.core.config import settings

logger = logging.getLogger(__name__)


VALID_CHANNELS = {
    "ingestion",
    "dossier_ready",
    "candidate_updated",
    "pending_user_questions",
}


def _serialize(payload: dict[str, Any]) -> str:
    def _default(o: Any) -> Any:
        if isinstance(o, UUID):
            return str(o)
        raise TypeError(
            f"Object of type {type(o).__name__} is not JSON serializable"
        )

    return json.dumps(payload, default=_default)


def _check(channel: str, payload: dict[str, Any]) -> None:
    if channel not in VALID_CHANNELS:
        raise ValueError(
            f"unknown notify channel {channel!r}; pick from {sorted(VALID_CHANNELS)}"
        )
    if "session_id" not in payload:
        raise ValueError(
            "every notify payload must include a session_id (server-side "
            "filter expects it)"
        )


def notify_sync(channel: str, payload: dict[str, Any]) -> None:
    """Publish a NOTIFY using a short-lived sync connection.

    Uses ``psycopg.connect`` directly (not the SQLModel session) so the
    notification is committed immediately without depending on the
    surrounding transaction's commit.
    """
    _check(channel, payload)
    body = _serialize(payload)
    dsn = str(settings.SQLALCHEMY_DATABASE_URI).replace(
        "postgresql+psycopg://", "postgresql://"
    )
    try:
        with psycopg.connect(dsn, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT pg_notify(%s, %s)",
                    (channel, body),
                )
    except Exception:  # noqa: BLE001
        logger.exception("notify_sync(%s) failed", channel)


async def notify_async(channel: str, payload: dict[str, Any]) -> None:
    """Publish a NOTIFY from async code (used by the SSE endpoint and any
    async tool/worker)."""
    _check(channel, payload)
    body = _serialize(payload)
    dsn = str(settings.SQLALCHEMY_DATABASE_URI).replace(
        "postgresql+psycopg://", "postgresql://"
    )
    try:
        async with await psycopg.AsyncConnection.connect(dsn, autocommit=True) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT pg_notify(%s, %s)",
                    (channel, body),
                )
    except Exception:  # noqa: BLE001
        logger.exception("notify_async(%s) failed", channel)


def notify_via_engine(engine_or_session, channel: str, payload: dict[str, Any]) -> None:
    """Issue NOTIFY using an existing SQLAlchemy engine/session.

    Convenience for callers already inside a transaction. The notification
    is part of the transaction; subscribers see it on commit.
    """
    _check(channel, payload)
    body = _serialize(payload)
    if hasattr(engine_or_session, "exec"):
        # SQLModel Session
        engine_or_session.exec(text("SELECT pg_notify(:c, :p)").bindparams(c=channel, p=body))  # type: ignore[arg-type]
    else:
        # Engine
        with engine_or_session.connect() as conn:
            conn.execute(text("SELECT pg_notify(:c, :p)"), {"c": channel, "p": body})
            conn.commit()
