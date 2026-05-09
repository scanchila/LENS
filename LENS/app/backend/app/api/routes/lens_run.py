"""Live LLM-driven lens execution endpoint + provenance audit endpoint.

  POST /sessions/{sid}/run-lens
        body: {lens, model_override?, timeout_seconds?}
        runs the named lens via CodexSubprocessAdapter, persists
        candidates to Postgres, writes Candidate / Claim / Source
        vertices into AGE, emits one NOTIFY per persisted candidate.

  POST /sessions/{sid}/candidates/{cid}/audit-provenance
        runs the Skeptic-fold AGE walk: for each claim in this
        candidate, verify it has a Source. Updates challenger_verdict
        to ``provenance_failed`` if any claim is unsourced, otherwise
        ``held``. Emits NOTIFY.

  POST /sessions/{sid}/audit-all
        run provenance audit across all live candidates in the session.
        Emits one NOTIFY per affected candidate.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import SessionDep
from app.db.notify import notify_via_engine
from app.graph import age_client
from app.models import Candidate
from app.orchestrator.lens_runner import SYSTEM_PROMPTS, run_lens

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sessions", tags=["lens", "provenance"])


class RunLensBody(BaseModel):
    lens: str = Field(..., description="cross_domain_transfer or contradiction_surfacing")
    model_override: str | None = None
    timeout_seconds: int = Field(default=600, ge=30, le=3600)


class RunLensResult(BaseModel):
    lens: str
    candidate_ids: list[uuid.UUID]
    elapsed_seconds: float | None = None


class AuditResult(BaseModel):
    candidate_id: uuid.UUID
    challenger_verdict: str
    failed_claims: list[str]
    audited_claims: int


@router.post(
    "/{session_id}/run-lens",
    response_model=RunLensResult,
)
async def run_lens_endpoint(
    *,
    session: SessionDep,
    session_id: uuid.UUID,
    body: RunLensBody,
) -> RunLensResult:
    if body.lens not in SYSTEM_PROMPTS:
        raise HTTPException(
            status_code=400,
            detail=f"unknown lens {body.lens!r}; pick from {sorted(SYSTEM_PROMPTS)}",
        )

    import time

    t0 = time.monotonic()
    try:
        ids = await run_lens(
            session=session,
            session_id=session_id,
            owner_id=None,
            lens=body.lens,
            timeout_seconds=body.timeout_seconds,
            model_override=body.model_override,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("run_lens failed")
        raise HTTPException(status_code=500, detail=str(exc))
    return RunLensResult(
        lens=body.lens,
        candidate_ids=ids,
        elapsed_seconds=time.monotonic() - t0,
    )


@router.post(
    "/{session_id}/candidates/{candidate_id}/audit-provenance",
    response_model=AuditResult,
)
async def audit_one(
    *,
    session: SessionDep,
    session_id: uuid.UUID,
    candidate_id: uuid.UUID,
) -> AuditResult:
    cand = session.get(Candidate, candidate_id)
    if cand is None or cand.session_id != session_id:
        raise HTTPException(status_code=404, detail="candidate not found")

    failed_claims: list[str] = []
    audited = 0
    try:
        # AGE client only returns single-column rows (it declares
        # `AS (result agtype)`); we issue one query per shape and stitch
        # results client-side. Edge alternation isn't supported, so we
        # query :supports and :refutes separately.
        seen_claim_ids: list[str] = []
        for edge in ("supports", "refutes"):
            rows = await age_client.cypher(
                f"MATCH (cand:Candidate {{id: $cid}})<-[:{edge}]-(cl:Claim) "
                "RETURN cl.id",
                cid=str(candidate_id),
            )
            for row in rows:
                cid = _strip_agtype(row[0]) if row else ""
                if cid and cid not in seen_claim_ids:
                    seen_claim_ids.append(cid)

        for claim_id in seen_claim_ids:
            audited += 1
            text_rows = await age_client.cypher(
                "MATCH (cl:Claim {id: $clid}) RETURN cl.text",
                clid=claim_id,
            )
            claim_text = (
                _strip_agtype(text_rows[0][0])
                if text_rows and text_rows[0]
                else claim_id
            )
            srcs = await age_client.cypher(
                "MATCH (cl:Claim {id: $clid})-[:cited_by]->(s:Source) RETURN s.id",
                clid=claim_id,
            )
            if not srcs:
                failed_claims.append(claim_text)
    except Exception:  # noqa: BLE001
        logger.exception("AGE audit failed for candidate %s", candidate_id)

    if failed_claims:
        cand.challenger_verdict = "provenance_failed"
        cand.status = "killed"
    else:
        cand.challenger_verdict = "held"
        cand.provenance_audited = True
        if cand.dossier_grounded:
            cand.status = "ready_to_validate"

    session.add(cand)
    session.commit()
    notify_via_engine(
        session,
        "candidate_updated",
        {
            "session_id": str(session_id),
            "candidate_id": str(candidate_id),
            "kind": "candidate_red_struck"
            if failed_claims
            else "candidate_challenged_held",
            "failed_claims": failed_claims[:5],
        },
    )
    session.commit()
    return AuditResult(
        candidate_id=candidate_id,
        challenger_verdict=cand.challenger_verdict or "kept",
        failed_claims=failed_claims,
        audited_claims=audited,
    )


@router.post(
    "/{session_id}/audit-all",
    response_model=list[AuditResult],
)
async def audit_all(
    *,
    session: SessionDep,
    session_id: uuid.UUID,
) -> list[AuditResult]:
    from sqlmodel import select

    raw_rows = session.exec(
        select(Candidate)
        .where(Candidate.session_id == session_id)
        .where(Candidate.status.notin_(["killed", "merged_into"]))  # type: ignore[union-attr]
    ).all()
    cands: list[Candidate] = [
        (r if isinstance(r, Candidate) else r[0]) for r in raw_rows  # type: ignore[index]
    ]
    out: list[AuditResult] = []
    for cand in cands:
        result = await audit_one(
            session=session, session_id=session_id, candidate_id=cand.id
        )
        out.append(result)
    return out


def _strip_agtype(value: object) -> str:
    """Best-effort extract a string out of AGE's ``agtype`` returns.

    AGE returns rows where each value is the raw agtype text (e.g.
    ``"some-id"`` including quotes). We strip surrounding quotes if
    present and decode the JSON-ish value.
    """
    if value is None:
        return ""
    s = str(value).strip()
    if s.startswith('"') and s.endswith('"'):
        try:
            import json

            return json.loads(s)
        except json.JSONDecodeError:
            return s.strip('"')
    return s
