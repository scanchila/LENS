"""Demo replay endpoints: drive the §11.1 stage script server-side.

The frontend's "live mode" toggle hits these endpoints instead of
running the JS-only mock simulation. Every state change persists to
Postgres + emits a NOTIFY → SSE round-trip.

Endpoints:

  POST /sessions/{sid}/demo/reset
  POST /sessions/{sid}/demo/next        body: {stage_index: int}
  POST /sessions/{sid}/demo/jump        body: {target_index: int}
  GET  /sessions/{sid}/demo/stages      list available stages
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import SessionDep
from app.orchestrator.demo_stages import (
    DEMO_STAGES,
    ReplayState,
    apply_stage,
    reset_session,
)

router = APIRouter(prefix="/sessions", tags=["demo"])


class StageInfo(BaseModel):
    index: int
    key: str
    label: str


class StageList(BaseModel):
    stages: list[StageInfo]


class NextStageBody(BaseModel):
    stage_index: int = Field(..., ge=0, description="Zero-based stage index to apply.")


class JumpBody(BaseModel):
    target_index: int = Field(..., ge=0)


class StageResult(BaseModel):
    stage_index: int
    stage_key: str
    label: str
    events: list[dict[str, Any]]
    candidates_total: int


@router.get("/{session_id}/demo/stages", response_model=StageList)
def list_stages(session_id: uuid.UUID) -> StageList:
    return StageList(
        stages=[
            StageInfo(index=i, key=s.key, label=s.label)
            for i, s in enumerate(DEMO_STAGES)
        ]
    )


@router.post("/{session_id}/demo/reset", response_model=StageResult)
def reset(*, session: SessionDep, session_id: uuid.UUID) -> StageResult:
    deleted = reset_session(session, session_id)
    return StageResult(
        stage_index=-1,
        stage_key="reset",
        label=f"reset · {deleted} candidates removed",
        events=[],
        candidates_total=0,
    )


@router.post("/{session_id}/demo/next", response_model=StageResult)
def next_stage(
    *,
    session: SessionDep,
    session_id: uuid.UUID,
    body: NextStageBody,
) -> StageResult:
    if body.stage_index >= len(DEMO_STAGES):
        raise HTTPException(
            status_code=400,
            detail=f"stage_index {body.stage_index} >= total {len(DEMO_STAGES)}",
        )
    events = apply_stage(session, session_id, body.stage_index)
    from sqlmodel import select
    from app.models import Candidate

    total = len(
        list(
            session.exec(
                select(Candidate).where(Candidate.session_id == session_id)
            ).scalars()
        )
    )
    stage = DEMO_STAGES[body.stage_index]
    return StageResult(
        stage_index=body.stage_index,
        stage_key=stage.key,
        label=stage.label,
        events=events,
        candidates_total=total,
    )


@router.post("/{session_id}/demo/jump", response_model=StageResult)
def jump(
    *,
    session: SessionDep,
    session_id: uuid.UUID,
    body: JumpBody,
) -> StageResult:
    if body.target_index > len(DEMO_STAGES):
        raise HTTPException(status_code=400, detail="target out of range")
    reset_session(session, session_id)
    state = ReplayState()
    all_events: list[dict[str, Any]] = []
    for i in range(body.target_index):
        all_events.extend(apply_stage(session, session_id, i, state))
    from sqlmodel import select
    from app.models import Candidate

    total = len(
        list(
            session.exec(
                select(Candidate).where(Candidate.session_id == session_id)
            ).scalars()
        )
    )
    last_idx = max(0, body.target_index - 1)
    stage = DEMO_STAGES[last_idx] if body.target_index > 0 else DEMO_STAGES[0]
    return StageResult(
        stage_index=last_idx,
        stage_key=stage.key,
        label=stage.label if body.target_index > 0 else "reset",
        events=all_events,
        candidates_total=total,
    )
