"""Read-mostly API for the prediction board.

Endpoints:

  - ``GET    /sessions/{sid}/candidates`` — list (filterable by status)
  - ``GET    /sessions/{sid}/candidates/{cid}`` — single
  - ``POST   /sessions/{sid}/candidates`` — create (used by lens runners
    that don't have direct DB access; usually unused — most writers
    persist via SQLModel directly).
  - ``PATCH  /sessions/{sid}/candidates/{cid}/verdict`` — record human verdict
  - ``POST   /sessions/{sid}/yc_reveal`` — flip the reveal flag (no DB
    state for now; client-side animation hint via NOTIFY).

The YC scoring endpoint reads a JSON fixture (TICKET-110) so demos
don't pay an LLM round-trip mid-stage.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlmodel import select

from app.api.deps import SessionDep
from app.db.notify import notify_via_engine
from app.models import Candidate, CandidatePublic, CandidatesPublic

router = APIRouter(prefix="/sessions", tags=["candidates"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CandidateCreate(BaseModel):
    lens: str
    statement: str
    evidence_chunk_ids: list[uuid.UUID] = Field(default_factory=list)
    v_hat: float = 0.5
    c_hat: float = 0.3
    pipeline_steps: list[Any] = Field(default_factory=list)
    source_count: int = 0


class VerdictUpdate(BaseModel):
    verdict: str = Field(..., pattern="^(accept|reject|park|request_dossier)$")


class YcMatch(BaseModel):
    prediction_id: uuid.UUID
    rfs_item_id: str | None = None
    match_kind: str  # 'direct' | 'adjacent' | 'none'
    rationale: str | None = None


class YcRfsItem(BaseModel):
    id: str
    title: str
    description: str
    tags: list[str] = Field(default_factory=list)


class YcScore(BaseModel):
    revealed: bool
    precision: float
    recall: float
    direct_matches: int
    adjacent: int
    missed: int
    excess: int
    matches: list[YcMatch]
    rfs_items: list[YcRfsItem]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "/{session_id}/candidates",
    response_model=CandidatesPublic,
    summary="List candidates for a session",
)
def list_candidates(
    *,
    session: SessionDep,
    session_id: uuid.UUID,
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
) -> CandidatesPublic:
    stmt = select(Candidate).where(Candidate.session_id == session_id)
    if status_filter:
        stmt = stmt.where(Candidate.status == status_filter)
    stmt = stmt.order_by(Candidate.created_at.desc()).limit(limit)  # type: ignore[union-attr]
    rows = session.exec(stmt).all()
    public = [CandidatePublic.model_validate(c, from_attributes=True) for c in rows]
    return CandidatesPublic(data=public, count=len(public))


@router.get(
    "/{session_id}/candidates/{candidate_id}",
    response_model=CandidatePublic,
)
def get_candidate(
    *,
    session: SessionDep,
    session_id: uuid.UUID,
    candidate_id: uuid.UUID,
) -> CandidatePublic:
    cand = session.get(Candidate, candidate_id)
    if cand is None or cand.session_id != session_id:
        raise HTTPException(status_code=404, detail="candidate not found")
    return CandidatePublic.model_validate(cand, from_attributes=True)


@router.post(
    "/{session_id}/candidates",
    response_model=CandidatePublic,
    status_code=status.HTTP_201_CREATED,
)
def create_candidate(
    *,
    session: SessionDep,
    session_id: uuid.UUID,
    body: CandidateCreate,
) -> CandidatePublic:
    cand = Candidate(
        session_id=session_id,
        lens=body.lens,
        statement=body.statement,
        evidence_chunk_ids=body.evidence_chunk_ids,
        v_hat=body.v_hat,
        c_hat=body.c_hat,
        pipeline_steps=list(body.pipeline_steps),
        source_count=body.source_count,
        status="speculative",
    )
    session.add(cand)
    session.commit()
    session.refresh(cand)
    notify_via_engine(
        session,
        "candidate_updated",
        {
            "session_id": str(session_id),
            "candidate_id": str(cand.id),
            "kind": "candidate_added",
        },
    )
    session.commit()
    return CandidatePublic.model_validate(cand, from_attributes=True)


@router.patch(
    "/{session_id}/candidates/{candidate_id}/verdict",
    response_model=CandidatePublic,
)
def patch_verdict(
    *,
    session: SessionDep,
    session_id: uuid.UUID,
    candidate_id: uuid.UUID,
    body: VerdictUpdate,
) -> CandidatePublic:
    cand = session.get(Candidate, candidate_id)
    if cand is None or cand.session_id != session_id:
        raise HTTPException(status_code=404, detail="candidate not found")

    if body.verdict == "accept":
        cand.status = "ready_to_validate"
    elif body.verdict == "reject":
        cand.status = "killed"
    # 'park' / 'request_dossier' are tracked in pipeline_steps for the demo
    cand.pipeline_steps = list(cand.pipeline_steps) + [
        {"verdict": body.verdict, "at": datetime.now(timezone.utc).isoformat()}
    ]
    cand.updated_at = datetime.now(timezone.utc)
    session.add(cand)
    session.commit()
    session.refresh(cand)
    notify_via_engine(
        session,
        "candidate_updated",
        {
            "session_id": str(session_id),
            "candidate_id": str(cand.id),
            "kind": f"verdict_{body.verdict}",
        },
    )
    session.commit()
    return CandidatePublic.model_validate(cand, from_attributes=True)


@router.post(
    "/{session_id}/yc_reveal",
    response_model=YcScore,
    summary="Reveal the held-out YC RFS list and score top-K against it",
)
def yc_reveal(
    *,
    session: SessionDep,
    session_id: uuid.UUID,
    top_k: int = Query(default=10, ge=1, le=50),
) -> YcScore:
    fixture_path = (
        Path(__file__).resolve().parents[3]
        / "fixtures"
        / "yc_rfs_summer_2026.json"
    )
    gold_path = (
        Path(__file__).resolve().parents[3]
        / "fixtures"
        / "yc_rfs_summer_2026_gold.json"
    )

    rfs_items: list[YcRfsItem] = []
    if fixture_path.exists():
        try:
            data = json.loads(fixture_path.read_text())
            for item in data.get("items", []):
                rfs_items.append(YcRfsItem(**item))
        except Exception:  # noqa: BLE001
            pass

    gold: dict[str, dict[str, str]] = {}
    if gold_path.exists():
        try:
            gold_raw = json.loads(gold_path.read_text())
            for entry in gold_raw.get("matches", []):
                gold[str(entry["statement_substring"]).lower()] = {
                    "rfs_item_id": entry["rfs_item_id"],
                    "match_kind": entry.get("match_kind", "direct"),
                    "rationale": entry.get("rationale", ""),
                }
        except Exception:  # noqa: BLE001
            pass

    live = session.exec(
        select(Candidate)
        .where(Candidate.session_id == session_id)
        .where(Candidate.status.notin_(["killed", "merged_into"]))  # type: ignore[union-attr]
        .order_by((Candidate.v_hat * Candidate.c_hat).desc())  # type: ignore[union-attr]
        .limit(top_k)
    ).all()

    matches: list[YcMatch] = []
    for cand in live:
        statement_l = cand.statement.lower()
        for sub, entry in gold.items():
            if sub in statement_l:
                matches.append(
                    YcMatch(
                        prediction_id=cand.id,
                        rfs_item_id=entry["rfs_item_id"],
                        match_kind=entry["match_kind"],
                        rationale=entry["rationale"],
                    )
                )
                break

    direct = sum(1 for m in matches if m.match_kind == "direct")
    adjacent = sum(1 for m in matches if m.match_kind == "adjacent")
    rfs_total = max(1, len(rfs_items))
    precision = direct / max(1, len(live))
    recall = direct / rfs_total

    notify_via_engine(
        session,
        "candidate_updated",
        {
            "session_id": str(session_id),
            "kind": "yc_revealed",
            "direct": direct,
            "precision": precision,
            "recall": recall,
        },
    )
    session.commit()

    return YcScore(
        revealed=True,
        precision=precision,
        recall=recall,
        direct_matches=direct,
        adjacent=adjacent,
        missed=len(rfs_items) - direct,
        excess=max(0, len(live) - direct - adjacent),
        matches=matches,
        rfs_items=rfs_items,
    )
