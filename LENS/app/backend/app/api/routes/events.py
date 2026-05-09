"""SSE endpoint streaming Postgres NOTIFY events to the prediction board.

A long-lived ``psycopg.AsyncConnection`` per client. Filters by
``session_id`` server-side. Emits a heartbeat every 15s so proxies
don't drop idle connections.

Frontend uses ``EventSource("/api/v1/sessions/{sid}/events")`` to
consume.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid
from typing import AsyncIterator

import psycopg
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sessions", tags=["sessions", "events"])


CHANNELS = (
    "ingestion",
    "dossier_ready",
    "candidate_updated",
    "pending_user_questions",
    "run_updated",
)


def _dsn() -> str:
    return str(settings.SQLALCHEMY_DATABASE_URI).replace(
        "postgresql+psycopg://", "postgresql://"
    )


async def _event_stream(session_id: uuid.UUID) -> AsyncIterator[bytes]:
    """Yield SSE-encoded events scoped to one session.

    The connection runs in autocommit mode so LISTEN takes effect
    immediately. Heartbeats keep connections warm; the loop exits if
    the client disconnects (StreamingResponse will detect the
    WriteCancelledError and shut us down).
    """
    sid = str(session_id)
    yield b": connected\n\n"

    try:
        async with await psycopg.AsyncConnection.connect(
            _dsn(), autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                for ch in CHANNELS:
                    await cur.execute(f"LISTEN {ch}")

            heartbeat_at = asyncio.get_event_loop().time() + 15.0
            gen = conn.notifies()
            try:
                while True:
                    timeout_left = max(
                        0.1, heartbeat_at - asyncio.get_event_loop().time()
                    )
                    try:
                        notify = await asyncio.wait_for(
                            gen.__anext__(), timeout=timeout_left
                        )
                    except asyncio.TimeoutError:
                        yield b"event: heartbeat\ndata: {}\n\n"
                        heartbeat_at = (
                            asyncio.get_event_loop().time() + 15.0
                        )
                        continue
                    except StopAsyncIteration:
                        break

                    payload_text = notify.payload or "{}"
                    try:
                        payload_obj = json.loads(payload_text)
                    except json.JSONDecodeError:
                        logger.warning(
                            "non-JSON notify payload on %s: %r",
                            notify.channel,
                            payload_text,
                        )
                        continue

                    if str(payload_obj.get("session_id")) != sid:
                        continue

                    body = json.dumps(
                        {
                            "type": notify.channel,
                            "payload": payload_obj,
                        }
                    )
                    yield f"event: {notify.channel}\ndata: {body}\n\n".encode()
            finally:
                with contextlib.suppress(Exception):
                    await gen.aclose()
    except asyncio.CancelledError:
        logger.info("SSE session %s disconnected", sid)
        raise
    except Exception:  # noqa: BLE001
        logger.exception("SSE session %s crashed", sid)
        yield b"event: error\ndata: {\"message\":\"stream-failed\"}\n\n"


@router.get(
    "/{session_id}/events",
    response_class=StreamingResponse,
    summary="Subscribe to session-scoped Postgres NOTIFY events as SSE",
)
async def session_events(session_id: uuid.UUID) -> StreamingResponse:
    return StreamingResponse(
        _event_stream(session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


