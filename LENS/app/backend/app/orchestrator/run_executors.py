"""Run executors for the operator-driven session flow.

A `Run` is one operator-triggered action against a `LensSession`. Each
executor here:

  - mutates candidates (creates new ones, updates existing v_hat /
    status / sources, or kills them),
  - records every per-field delta as a `CandidateChange` row,
  - returns a summary (added/updated/killed counts) for the UI.

The same dispatcher handles both ``mode="scripted"`` (deterministic,
pre-baked deltas — safe for the demo) and ``mode="real"`` (real LLM /
file ingest / HN fetch). Scripted is the default; real paths are
stubbed where they don't exist yet.

Each executor calls :func:`_apply_with_history` / :func:`_create_with_history`
helpers that diff old↔new field values and persist a
:class:`CandidateChange` row pointing back to the run. This is what
the per-candidate history drawer renders.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

from sqlalchemy import select
from sqlmodel import Session

from app.db.notify import notify_via_engine
from app.models import (
    Candidate,
    CandidateChange,
    LensSession,
    Run,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared types
# ---------------------------------------------------------------------------


@dataclass
class RunSummary:
    candidates_added: int = 0
    candidates_updated: int = 0
    candidates_killed: int = 0
    candidates_merged: int = 0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidates_added": self.candidates_added,
            "candidates_updated": self.candidates_updated,
            "candidates_killed": self.candidates_killed,
            "candidates_merged": self.candidates_merged,
            "notes": self.notes,
        }


# ---------------------------------------------------------------------------
# Helpers — write candidates with attached change history
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


# Fields that are eligible for diff-tracking on update. Excluded:
# id, session_id, owner_id, created_at, updated_at (always change).
_TRACKED_FIELDS = (
    "lens",
    "statement",
    "v_hat",
    "c_hat",
    "evidence_chunk_ids",
    "pipeline_steps",
    "status",
    "challenger_verdict",
    "dossier_grounded",
    "provenance_audited",
    "source_count",
    "reinforces",
    "merged_from",
    "ahead_of_yc",
    "pain_owner",
    "why_now",
    "contradictions",
    "open_assumptions",
    "validation_path",
    "evidence_sources",
)


def _serialize(v: Any) -> Any:
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, list):
        return [_serialize(x) for x in v]
    if isinstance(v, dict):
        return {k: _serialize(x) for k, x in v.items()}
    return v


def _candidates_in_session(session: Session, sid: uuid.UUID) -> list[Candidate]:
    rows = session.exec(
        select(Candidate).where(Candidate.session_id == sid)
    ).all()
    out: list[Candidate] = []
    for r in rows:
        if isinstance(r, Candidate):
            out.append(r)
        else:
            try:
                out.append(r[0])  # type: ignore[index]
            except Exception:  # noqa: BLE001
                continue
    return out


def _record_change(
    session: Session,
    *,
    run_id: uuid.UUID,
    candidate_id: uuid.UUID,
    change_kind: str,
    field_diffs: dict[str, Any],
    reason: str | None,
) -> CandidateChange:
    change = CandidateChange(
        run_id=run_id,
        candidate_id=candidate_id,
        change_kind=change_kind,
        field_diffs=field_diffs,
        reason=reason,
    )
    session.add(change)
    session.commit()
    session.refresh(change)
    return change


def _create_with_history(
    session: Session,
    *,
    run_id: uuid.UUID,
    session_id: uuid.UUID,
    owner_id: uuid.UUID | None,
    reason: str,
    statement: str,
    lens: str,
    v_hat: float,
    c_hat: float,
    pipeline_steps: list[Any] | None = None,
    chunks: int = 0,
    sources: int = 0,
    status: str = "speculative",
) -> Candidate:
    cand = Candidate(
        session_id=session_id,
        owner_id=owner_id,
        lens=lens,
        statement=statement,
        evidence_chunk_ids=[uuid.uuid4() for _ in range(chunks)],
        v_hat=v_hat,
        c_hat=c_hat,
        pipeline_steps=pipeline_steps or [],
        source_count=sources,
        status=status,
    )
    session.add(cand)
    session.commit()
    session.refresh(cand)

    # Snapshot every tracked field as a "from null" diff for the history view.
    diffs: dict[str, Any] = {}
    for f in _TRACKED_FIELDS:
        diffs[f] = {"from": None, "to": _serialize(getattr(cand, f, None))}

    _record_change(
        session,
        run_id=run_id,
        candidate_id=cand.id,
        change_kind="created",
        field_diffs=diffs,
        reason=reason,
    )
    return cand


def _apply_with_history(
    session: Session,
    *,
    run_id: uuid.UUID,
    candidate: Candidate,
    reason: str,
    change_kind: str = "updated",
    **changes: Any,
) -> Candidate:
    diffs: dict[str, Any] = {}
    for k, new_val in changes.items():
        if k not in _TRACKED_FIELDS:
            # Allow unknown fields too (e.g. ad-hoc metadata) but record under same shape.
            pass
        old_val = getattr(candidate, k, None)
        if old_val == new_val:
            continue
        diffs[k] = {"from": _serialize(old_val), "to": _serialize(new_val)}
        setattr(candidate, k, new_val)

    if diffs:
        candidate.updated_at = _now()
        session.add(candidate)
        session.commit()
        session.refresh(candidate)
        _record_change(
            session,
            run_id=run_id,
            candidate_id=candidate.id,
            change_kind=change_kind,
            field_diffs=diffs,
            reason=reason,
        )
    return candidate


def _emit_event(
    session: Session,
    *,
    sid: uuid.UUID,
    candidate_id: uuid.UUID | None,
    kind: str,
    extra: dict[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {"session_id": str(sid), "kind": kind}
    if candidate_id is not None:
        payload["candidate_id"] = str(candidate_id)
    if extra:
        payload.update(extra)
    notify_via_engine(session, "candidate_updated", payload)


# ---------------------------------------------------------------------------
# Executors — scripted defaults
# ---------------------------------------------------------------------------


SEED_IDEAS_SCRIPTED: list[dict[str, Any]] = [
    {
        "statement": "Founders need a structured way to compare opportunity briefs across studios",
        "lens": "cross_domain_transfer",
        "v_hat": 0.46,
        "c_hat": 0.32,
        "chunks": 2,
        "sources": 2,
        "pipeline_steps": ["Survey 5 studio partners", "Prototype brief schema"],
    },
    {
        "statement": "Vertical compliance copilots for sub-$50M SMBs are underbuilt",
        "lens": "contradiction_surfacing",
        "v_hat": 0.51,
        "c_hat": 0.28,
        "chunks": 1,
        "sources": 1,
        "pipeline_steps": ["Interview 10 SMB CFOs", "Compare 3 incumbent tools"],
    },
    {
        "statement": "Open-source agent observability is a missing dev-tools wedge",
        "lens": "distance_from_focus",
        "v_hat": 0.49,
        "c_hat": 0.34,
        "chunks": 1,
        "sources": 1,
        "pipeline_steps": ["Audit existing OSS observability", "Spec MVP"],
    },
    {
        "statement": "AI-native CRM tuned to startup-studio pipeline mechanics",
        "lens": "cross_domain_transfer",
        "v_hat": 0.41,
        "c_hat": 0.30,
        "chunks": 1,
        "sources": 1,
        "pipeline_steps": ["Map studio CRM workflow", "Build pipeline schema"],
    },
    {
        "statement": "Studios should run adversarial review on every opportunity brief",
        "lens": "contradiction_surfacing",
        "v_hat": 0.39,
        "c_hat": 0.27,
        "chunks": 0,
        "sources": 0,
        "pipeline_steps": [
            "Build challenger persona library",
            "Run on 5 historical briefs",
        ],
    },
    {
        "statement": "Local-first knowledge agents for analyst-heavy firms (5–50 users)",
        "lens": "cross_domain_transfer",
        "v_hat": 0.44,
        "c_hat": 0.31,
        "chunks": 1,
        "sources": 1,
        "pipeline_steps": ["Map 3 analyst doc trails", "Prototype local index"],
    },
    {
        "statement": "Spec-first agent design tools — tools as deterministic API contracts",
        "lens": "distance_from_focus",
        "v_hat": 0.43,
        "c_hat": 0.29,
        "chunks": 1,
        "sources": 1,
        "pipeline_steps": ["Audit 10 popular agent tools", "Spec a contract DSL"],
    },
    {
        "statement": "Incident-replay infra for AI agent runs (deterministic re-execute)",
        "lens": "cross_domain_transfer",
        "v_hat": 0.47,
        "c_hat": 0.32,
        "chunks": 2,
        "sources": 2,
        "pipeline_steps": ["Talk to 5 AI infra teams", "Sketch replay protocol"],
    },
    {
        "statement": "Evals-as-a-service for vertical SaaS LLM features",
        "lens": "contradiction_surfacing",
        "v_hat": 0.42,
        "c_hat": 0.28,
        "chunks": 1,
        "sources": 1,
        "pipeline_steps": ["Survey 8 vertical SaaS teams", "Spec eval API"],
    },
    {
        "statement": "Synthetic data generation for regulated-industry agent training",
        "lens": "cross_domain_transfer",
        "v_hat": 0.45,
        "c_hat": 0.30,
        "chunks": 1,
        "sources": 1,
        "pipeline_steps": [
            "Catalog regulated-industry data constraints",
            "Pilot with 1 design partner",
        ],
    },
]


def _exec_seed_ideas_scripted(
    session: Session,
    *,
    run_id: uuid.UUID,
    lens_session: LensSession,
    input_payload: dict[str, Any],
) -> RunSummary:
    """Produce N seed candidates. Used as the cold-start of any session."""
    summary = RunSummary()
    n = int(input_payload.get("count", 10))
    n = max(1, min(n, len(SEED_IDEAS_SCRIPTED)))
    for spec in SEED_IDEAS_SCRIPTED[:n]:
        cand = _create_with_history(
            session,
            run_id=run_id,
            session_id=lens_session.id,
            owner_id=lens_session.owner_id,
            reason=f"seed: {lens_session.title}",
            **spec,
        )
        _emit_event(
            session,
            sid=lens_session.id,
            candidate_id=cand.id,
            kind="candidate_added",
        )
        summary.candidates_added += 1
    summary.notes.append(f"seeded {summary.candidates_added} candidates")
    return summary


def _exec_document_upload_scripted(
    session: Session,
    *,
    run_id: uuid.UUID,
    lens_session: LensSession,
    input_payload: dict[str, Any],
) -> RunSummary:
    """Simulate ingesting a document: rescore some existing, add 2 new."""
    summary = RunSummary()
    doc_label = str(input_payload.get("document_label") or "uploaded document")
    cands = _candidates_in_session(session, lens_session.id)

    # Rescore the first 2 existing candidates upward (the doc reinforced them).
    for cand in cands[:2]:
        if cand.status in ("killed", "merged_into"):
            continue
        new_v = round(min(0.95, cand.v_hat + 0.12), 2)
        new_c = round(min(0.95, cand.c_hat + 0.08), 2)
        _apply_with_history(
            session,
            run_id=run_id,
            candidate=cand,
            reason=f"reinforced by {doc_label}",
            change_kind="reinforced",
            v_hat=new_v,
            c_hat=new_c,
            source_count=cand.source_count + 2,
            status="supported" if cand.status == "speculative" else cand.status,
            evidence_chunk_ids=list(cand.evidence_chunk_ids)
            + [uuid.uuid4(), uuid.uuid4()],
        )
        _emit_event(
            session,
            sid=lens_session.id,
            candidate_id=cand.id,
            kind="candidate_v_hat_updated",
            extra={"to": new_v},
        )
        summary.candidates_updated += 1

    # Add 2 new candidates "discovered" in the doc.
    new_specs = [
        {
            "statement": (
                "Browser-native LLM agents with tab-level context — apply OS-level "
                "scheduler primitives to attention budgets"
            ),
            "lens": "cross_domain_transfer",
            "v_hat": 0.78,
            "c_hat": 0.55,
            "chunks": 4,
            "sources": 6,
            "pipeline_steps": [
                "Map current browser-agent architectures",
                "Spec a tab-context protocol",
                "Test on 3 vertical workflows",
            ],
            "status": "supported",
        },
        {
            "statement": (
                "Real-time data quality for AI training — borrow stream-processing "
                "fault-tolerance from finance ETL"
            ),
            "lens": "cross_domain_transfer",
            "v_hat": 0.74,
            "c_hat": 0.50,
            "chunks": 2,
            "sources": 4,
            "pipeline_steps": [
                "Audit 5 training pipelines for silent corruption",
                "Adapt finance ETL guarantees",
            ],
            "status": "supported",
        },
    ]
    for spec in new_specs:
        cand = _create_with_history(
            session,
            run_id=run_id,
            session_id=lens_session.id,
            owner_id=lens_session.owner_id,
            reason=f"surfaced from {doc_label}",
            **spec,
        )
        _emit_event(
            session,
            sid=lens_session.id,
            candidate_id=cand.id,
            kind="candidate_added",
        )
        summary.candidates_added += 1
    summary.notes.append(
        f"+{summary.candidates_added} new, ↑{summary.candidates_updated} reinforced"
    )
    return summary


def _exec_hn_search_scripted(
    session: Session,
    *,
    run_id: uuid.UUID,
    lens_session: LensSession,
    input_payload: dict[str, Any],
) -> RunSummary:
    """Simulate scanning HN top posts: rescore + add 3 contradictions."""
    summary = RunSummary()
    query = str(input_payload.get("query") or "AI tooling")
    cands = _candidates_in_session(session, lens_session.id)

    # First existing candidate (if any) gets a strong reinforcement.
    if cands:
        target = next((c for c in cands if c.status not in ("killed", "merged_into")), None)
        if target:
            new_v = round(min(0.95, target.v_hat + 0.10), 2)
            new_c = round(min(0.95, target.c_hat + 0.09), 2)
            _apply_with_history(
                session,
                run_id=run_id,
                candidate=target,
                reason=f"reinforced by HN posts ({query})",
                change_kind="reinforced",
                v_hat=new_v,
                c_hat=new_c,
                source_count=target.source_count + 3,
                status="supported" if target.status == "speculative" else target.status,
                evidence_chunk_ids=list(target.evidence_chunk_ids)
                + [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()],
            )
            _emit_event(
                session,
                sid=lens_session.id,
                candidate_id=target.id,
                kind="candidate_v_hat_updated",
                extra={"to": new_v},
            )
            summary.candidates_updated += 1

    new_specs = [
        {
            "statement": (
                "Why does Stripe say 'AI is plug-and-play' while founders ship "
                "6-month integrations?"
            ),
            "lens": "contradiction_surfacing",
            "v_hat": 0.71,
            "c_hat": 0.47,
            "chunks": 3,
            "sources": 4,
            "pipeline_steps": [
                "Talk to 10 founders shipping AI features",
                "Map integration time-to-value",
                "Compare to vendor claims",
            ],
            "status": "supported",
        },
        {
            "statement": (
                "Personal RAG over a knowledge worker's full document trail "
                "(private, not enterprise)"
            ),
            "lens": "contradiction_surfacing",
            "v_hat": 0.69,
            "c_hat": 0.43,
            "chunks": 2,
            "sources": 3,
            "pipeline_steps": [
                "Survey 20 knowledge workers",
                "Compare 3 personal-RAG attempts",
            ],
            "status": "supported",
        },
        {
            "statement": "Voice-first ops for field workers — trades, logistics, last-mile",
            "lens": "contradiction_surfacing",
            "v_hat": 0.66,
            "c_hat": 0.40,
            "chunks": 2,
            "sources": 3,
            "pipeline_steps": [
                "Shadow 3 field crews",
                "Test voice-only journey for 2 trades",
            ],
            "status": "supported",
        },
    ]
    for spec in new_specs:
        cand = _create_with_history(
            session,
            run_id=run_id,
            session_id=lens_session.id,
            owner_id=lens_session.owner_id,
            reason=f"surfaced from HN search ({query})",
            **spec,
        )
        _emit_event(
            session,
            sid=lens_session.id,
            candidate_id=cand.id,
            kind="candidate_added",
        )
        summary.candidates_added += 1
    summary.notes.append(
        f"+{summary.candidates_added} new from HN, ↑{summary.candidates_updated} reinforced"
    )
    return summary


def _exec_contradiction_lens_scripted(
    session: Session,
    *,
    run_id: uuid.UUID,
    lens_session: LensSession,
    input_payload: dict[str, Any],
) -> RunSummary:
    """Apply a challenger pass across existing candidates.

    Kills weak (v_hat < 0.5 with no dossier), holds strong dossier-grounded.
    Demote (without killing) borderline candidates so the score change is
    visible in history.
    """
    summary = RunSummary()
    for cand in _candidates_in_session(session, lens_session.id):
        if cand.status in ("killed", "merged_into"):
            continue
        if cand.v_hat < 0.5 and not cand.dossier_grounded:
            _apply_with_history(
                session,
                run_id=run_id,
                candidate=cand,
                reason="failed challenger pass — weak v_hat, no dossier",
                change_kind="killed",
                status="killed",
                challenger_verdict="red_struck",
            )
            _emit_event(
                session,
                sid=lens_session.id,
                candidate_id=cand.id,
                kind="candidate_killed",
            )
            summary.candidates_killed += 1
        elif not cand.evidence_chunk_ids and not cand.dossier_grounded:
            _apply_with_history(
                session,
                run_id=run_id,
                candidate=cand,
                reason="provenance failed — no evidence chunks",
                change_kind="red_struck",
                status="killed",
                challenger_verdict="provenance_failed",
            )
            _emit_event(
                session,
                sid=lens_session.id,
                candidate_id=cand.id,
                kind="candidate_red_struck",
            )
            summary.candidates_killed += 1
        else:
            new_v = round(max(0.05, cand.v_hat - 0.04), 2)
            _apply_with_history(
                session,
                run_id=run_id,
                candidate=cand,
                reason="held under contradiction lens — minor v_hat trim",
                change_kind="updated",
                v_hat=new_v,
                challenger_verdict="held",
                provenance_audited=True,
            )
            _emit_event(
                session,
                sid=lens_session.id,
                candidate_id=cand.id,
                kind="candidate_challenged_held",
            )
            summary.candidates_updated += 1
    summary.notes.append(
        f"✗{summary.candidates_killed} killed, ↓{summary.candidates_updated} held with v_hat trim"
    )
    return summary


# ---------------------------------------------------------------------------
# Executors — real-mode (LLM / external)
# ---------------------------------------------------------------------------


async def _exec_contradiction_lens_real(
    session: Session,
    *,
    run_id: uuid.UUID,
    lens_session: LensSession,
    input_payload: dict[str, Any],
) -> RunSummary:
    """Real path: invoke the contradiction lens via the existing runner.

    The lens runner persists its own candidates and emits NOTIFY. We
    snapshot the resulting set and record `created` change rows for the
    new ids so they show up in this run's history.
    """
    from app.orchestrator.lens_runner import run_lens

    summary = RunSummary()
    pre_ids = {c.id for c in _candidates_in_session(session, lens_session.id)}
    try:
        await run_lens(
            session=session,
            session_id=lens_session.id,
            owner_id=lens_session.owner_id,
            lens="contradiction_surfacing",
            timeout_seconds=int(input_payload.get("timeout_seconds", 600)),
            model_override=input_payload.get("model_override"),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("contradiction_lens real path failed")
        summary.notes.append(f"real path failed: {exc}")
        return summary

    post = _candidates_in_session(session, lens_session.id)
    for cand in post:
        if cand.id in pre_ids:
            continue
        # Backfill a `created` change row for the new candidate.
        diffs: dict[str, Any] = {}
        for f in _TRACKED_FIELDS:
            diffs[f] = {"from": None, "to": _serialize(getattr(cand, f, None))}
        _record_change(
            session,
            run_id=run_id,
            candidate_id=cand.id,
            change_kind="created",
            field_diffs=diffs,
            reason="contradiction lens (real LLM)",
        )
        summary.candidates_added += 1
    summary.notes.append(f"+{summary.candidates_added} from real contradiction lens")
    return summary


async def _exec_cross_domain_lens_real(
    session: Session,
    *,
    run_id: uuid.UUID,
    lens_session: LensSession,
    input_payload: dict[str, Any],
) -> RunSummary:
    from app.orchestrator.lens_runner import run_lens

    summary = RunSummary()
    pre_ids = {c.id for c in _candidates_in_session(session, lens_session.id)}
    try:
        await run_lens(
            session=session,
            session_id=lens_session.id,
            owner_id=lens_session.owner_id,
            lens="cross_domain_transfer",
            timeout_seconds=int(input_payload.get("timeout_seconds", 600)),
            model_override=input_payload.get("model_override"),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("cross_domain_lens real path failed")
        summary.notes.append(f"real path failed: {exc}")
        return summary

    post = _candidates_in_session(session, lens_session.id)
    for cand in post:
        if cand.id in pre_ids:
            continue
        diffs: dict[str, Any] = {}
        for f in _TRACKED_FIELDS:
            diffs[f] = {"from": None, "to": _serialize(getattr(cand, f, None))}
        _record_change(
            session,
            run_id=run_id,
            candidate_id=cand.id,
            change_kind="created",
            field_diffs=diffs,
            reason="cross-domain lens (real LLM)",
        )
        summary.candidates_added += 1
    summary.notes.append(f"+{summary.candidates_added} from real cross-domain lens")
    return summary


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


SUPPORTED_KINDS: tuple[str, ...] = (
    "seed_ideas",
    "document_upload",
    "hn_search",
    "contradiction_lens",
    "cross_domain_lens",
)

SUPPORTED_MODES: tuple[str, ...] = ("scripted", "real")


_SCRIPTED: dict[str, Callable[..., RunSummary]] = {
    "seed_ideas": _exec_seed_ideas_scripted,
    "document_upload": _exec_document_upload_scripted,
    "hn_search": _exec_hn_search_scripted,
    "contradiction_lens": _exec_contradiction_lens_scripted,
    # cross_domain_lens scripted is a thin wrapper: same as document_upload's
    # "+2 new candidates" but with a cross-domain lens label.
    "cross_domain_lens": _exec_document_upload_scripted,
}


_REAL: dict[str, Callable[..., Any]] = {
    "contradiction_lens": _exec_contradiction_lens_real,
    "cross_domain_lens": _exec_cross_domain_lens_real,
}


def execute_run(
    session: Session,
    *,
    run: Run,
    lens_session: LensSession,
) -> RunSummary:
    """Dispatch the run to its executor.

    Updates the Run row in-place (status, finished_at, summary, error).
    Returns the resolved summary.
    """
    if run.kind not in SUPPORTED_KINDS:
        raise ValueError(
            f"unsupported run kind {run.kind!r}; choose from {SUPPORTED_KINDS}"
        )
    if run.mode not in SUPPORTED_MODES:
        raise ValueError(
            f"unsupported run mode {run.mode!r}; choose from {SUPPORTED_MODES}"
        )

    run.status = "running"
    session.add(run)
    session.commit()

    try:
        if run.mode == "real" and run.kind in _REAL:
            coro = _REAL[run.kind](
                session,
                run_id=run.id,
                lens_session=lens_session,
                input_payload=run.input or {},
            )
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is not None:
                # Should not happen — FastAPI sync routes give us no running loop.
                # If we are accidentally inside one, run the coroutine in a thread.
                summary = asyncio.run_coroutine_threadsafe(coro, loop).result()
            else:
                summary = asyncio.run(coro)
        else:
            summary = _SCRIPTED[run.kind](
                session,
                run_id=run.id,
                lens_session=lens_session,
                input_payload=run.input or {},
            )
        run.status = "complete"
        run.summary = summary.to_dict()
    except Exception as exc:  # noqa: BLE001
        logger.exception("run %s failed", run.id)
        run.status = "failed"
        run.error = str(exc)[:500]
        summary = RunSummary(notes=[f"failed: {exc}"])
    finally:
        run.finished_at = _now()
        session.add(run)
        session.commit()
        session.refresh(run)
        notify_via_engine(
            session,
            "run_updated",
            {
                "session_id": str(lens_session.id),
                "run_id": str(run.id),
                "kind": run.kind,
                "status": run.status,
                "summary": run.summary,
            },
        )
        session.commit()
    return summary


__all__: Iterable[str] = (
    "RunSummary",
    "SUPPORTED_KINDS",
    "SUPPORTED_MODES",
    "execute_run",
)
