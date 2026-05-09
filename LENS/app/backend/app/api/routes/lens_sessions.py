"""Operator-driven session + run flow.

Endpoints:

  POST   /lens-sessions                              create
  GET    /lens-sessions                              list (most-recent first)
  GET    /lens-sessions/{sid}                        detail
  DELETE /lens-sessions/{sid}                        cascade-delete

  POST   /lens-sessions/{sid}/runs                   kick off a run
  GET    /lens-sessions/{sid}/runs                   timeline
  GET    /lens-sessions/{sid}/runs/{rid}             detail with embedded changes

  GET    /lens-sessions/{sid}/candidates/{cid}/history    per-candidate timeline

Each run synchronously executes via :mod:`app.orchestrator.run_executors`
and persists candidate_changes rows for every per-field delta. The UI
reads those to render the per-idea history drawer.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select as sa_select
from sqlmodel import select

from app.api.deps import SessionDep
from app.models import (
    Candidate,
    CandidateChange,
    CandidateChangePublic,
    CandidateHistoryPublic,
    LensSession,
    LensSessionPublic,
    LensSessionsPublic,
    Run,
    RunDetailPublic,
    RunPublic,
    RunsPublic,
)
from app.orchestrator.run_executors import (
    SUPPORTED_KINDS,
    SUPPORTED_MODES,
    execute_run,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/lens-sessions", tags=["lens-sessions"])


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class LensSessionCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    goal_query: str | None = Field(default=None, max_length=2000)


class RunCreate(BaseModel):
    kind: str = Field(..., description="One of: " + ", ".join(SUPPORTED_KINDS))
    mode: str = Field(default="scripted", description="scripted | real")
    input: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _all_rows(session, stmt) -> list:
    rows = session.exec(stmt).all()
    out = []
    for r in rows:
        if hasattr(r, "_mapping"):
            try:
                out.append(r[0])  # type: ignore[index]
                continue
            except Exception:  # noqa: BLE001
                pass
        out.append(r)
    return out


def _get_session_or_404(session: SessionDep, sid: uuid.UUID) -> LensSession:
    obj = session.get(LensSession, sid)
    if obj is None:
        raise HTTPException(status_code=404, detail="lens session not found")
    return obj


def _get_run_or_404(
    session: SessionDep, sid: uuid.UUID, rid: uuid.UUID
) -> Run:
    obj = session.get(Run, rid)
    if obj is None or obj.session_id != sid:
        raise HTTPException(status_code=404, detail="run not found")
    return obj


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=LensSessionPublic,
    status_code=status.HTTP_201_CREATED,
)
def create_session(
    *, session: SessionDep, body: LensSessionCreate
) -> LensSessionPublic:
    obj = LensSession(
        title=body.title.strip(),
        description=(body.description or None),
        goal_query=(body.goal_query or None),
    )
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return LensSessionPublic.model_validate(obj, from_attributes=True)


@router.get("", response_model=LensSessionsPublic)
def list_sessions(
    *,
    session: SessionDep,
    limit: int = Query(default=50, ge=1, le=200),
) -> LensSessionsPublic:
    stmt = (
        select(LensSession)
        .order_by(LensSession.updated_at.desc())  # type: ignore[union-attr]
        .limit(limit)
    )
    rows = _all_rows(session, stmt)
    public = [LensSessionPublic.model_validate(r, from_attributes=True) for r in rows]
    return LensSessionsPublic(data=public, count=len(public))


@router.get("/{session_id}", response_model=LensSessionPublic)
def get_session(
    *, session: SessionDep, session_id: uuid.UUID
) -> LensSessionPublic:
    obj = _get_session_or_404(session, session_id)
    return LensSessionPublic.model_validate(obj, from_attributes=True)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(*, session: SessionDep, session_id: uuid.UUID) -> None:
    obj = _get_session_or_404(session, session_id)
    # Manually delete the candidates — Candidate.session_id has no FK.
    cands = _all_rows(
        session,
        select(Candidate).where(Candidate.session_id == session_id),
    )
    for c in cands:
        session.delete(c)
    session.delete(obj)
    session.commit()


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


@router.post(
    "/{session_id}/runs",
    response_model=RunDetailPublic,
    status_code=status.HTTP_201_CREATED,
)
def create_run(
    *,
    session: SessionDep,
    session_id: uuid.UUID,
    body: RunCreate,
) -> RunDetailPublic:
    if body.kind not in SUPPORTED_KINDS:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported kind {body.kind!r}; pick from {SUPPORTED_KINDS}",
        )
    if body.mode not in SUPPORTED_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported mode {body.mode!r}; pick from {SUPPORTED_MODES}",
        )

    lens_session = _get_session_or_404(session, session_id)

    run = Run(
        session_id=lens_session.id,
        kind=body.kind,
        mode=body.mode,
        input=dict(body.input or {}),
        status="pending",
    )
    session.add(run)
    session.commit()
    session.refresh(run)

    execute_run(session, run=run, lens_session=lens_session)

    # Bump the session's updated_at
    lens_session.updated_at = datetime.now(timezone.utc)
    session.add(lens_session)
    session.commit()

    # Return run + its changes
    changes_rows = _all_rows(
        session,
        select(CandidateChange)
        .where(CandidateChange.run_id == run.id)
        .order_by(CandidateChange.created_at.asc()),  # type: ignore[union-attr]
    )
    return RunDetailPublic(
        run=RunPublic.model_validate(run, from_attributes=True),
        changes=[
            CandidateChangePublic.model_validate(c, from_attributes=True)
            for c in changes_rows
        ],
    )


@router.get("/{session_id}/runs", response_model=RunsPublic)
def list_runs(
    *,
    session: SessionDep,
    session_id: uuid.UUID,
    limit: int = Query(default=50, ge=1, le=200),
) -> RunsPublic:
    _get_session_or_404(session, session_id)
    stmt = (
        select(Run)
        .where(Run.session_id == session_id)
        .order_by(Run.started_at.desc())  # type: ignore[union-attr]
        .limit(limit)
    )
    rows = _all_rows(session, stmt)
    return RunsPublic(
        data=[RunPublic.model_validate(r, from_attributes=True) for r in rows],
        count=len(rows),
    )


@router.get("/{session_id}/runs/{run_id}", response_model=RunDetailPublic)
def get_run(
    *,
    session: SessionDep,
    session_id: uuid.UUID,
    run_id: uuid.UUID,
) -> RunDetailPublic:
    run = _get_run_or_404(session, session_id, run_id)
    changes_rows = _all_rows(
        session,
        select(CandidateChange)
        .where(CandidateChange.run_id == run.id)
        .order_by(CandidateChange.created_at.asc()),  # type: ignore[union-attr]
    )
    return RunDetailPublic(
        run=RunPublic.model_validate(run, from_attributes=True),
        changes=[
            CandidateChangePublic.model_validate(c, from_attributes=True)
            for c in changes_rows
        ],
    )


# ---------------------------------------------------------------------------
# Candidate history
# ---------------------------------------------------------------------------


@router.get(
    "/{session_id}/candidates/{candidate_id}/history",
    response_model=CandidateHistoryPublic,
)
def candidate_history(
    *,
    session: SessionDep,
    session_id: uuid.UUID,
    candidate_id: uuid.UUID,
) -> CandidateHistoryPublic:
    cand = session.get(Candidate, candidate_id)
    if cand is None or cand.session_id != session_id:
        raise HTTPException(status_code=404, detail="candidate not found in session")

    changes_rows = _all_rows(
        session,
        select(CandidateChange)
        .where(CandidateChange.candidate_id == candidate_id)
        .order_by(CandidateChange.created_at.asc()),  # type: ignore[union-attr]
    )
    changes_public = [
        CandidateChangePublic.model_validate(c, from_attributes=True)
        for c in changes_rows
    ]

    run_ids = sorted({c.run_id for c in changes_rows}, key=str)
    runs_map: dict[str, RunPublic] = {}
    for rid in run_ids:
        r = session.get(Run, rid)
        if r is not None:
            runs_map[str(rid)] = RunPublic.model_validate(r, from_attributes=True)

    return CandidateHistoryPublic(
        candidate_id=candidate_id,
        changes=changes_public,
        runs=runs_map,
    )
