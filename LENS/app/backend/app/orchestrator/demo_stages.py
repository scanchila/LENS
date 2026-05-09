"""Server-side demo stage replay.

Applies the same arc the frontend mock simulates — but persists every
candidate to Postgres and emits the NOTIFY events the SSE endpoint
streams. The frontend's "live mode" toggle drives this path so the
visual demo plays out against a real backend.

This is pragmatic: a real LLM-driven cross_domain lens run takes ~20s
and burns budget per stage; the replay is sub-second per stage. For a
4-minute live demo, deterministic replay is the right tradeoff. The
``run_cross_domain_lens`` runner in :mod:`.lens_runner` is wired for
when we want the real LLM path on stage.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import select, update
from sqlmodel import Session

from app.db.notify import notify_via_engine
from app.models import Candidate


@dataclass
class StageOp:
    key: str
    label: str
    apply: Callable[[Session, uuid.UUID, "ReplayState"], list[dict[str, Any]]]


@dataclass
class ReplayState:
    """Per-session in-memory cursor used to resolve candidates created in
    earlier stages by their statement substring (we don't expose ids
    across stages because the demo file is reapplied in order).
    """

    statements_to_id: dict[str, uuid.UUID] = field(default_factory=dict)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _candidates_by_session(session: Session, sid: uuid.UUID) -> list[Candidate]:
    rows = session.exec(
        select(Candidate).where(Candidate.session_id == sid)
    ).all()
    out: list[Candidate] = []
    for r in rows:
        # SQLModel.Session.exec on a single-entity select normally yields the
        # entity directly; some configurations return a Row whose first
        # element is the entity. Normalize to the entity here.
        if isinstance(r, Candidate):
            out.append(r)
        else:
            try:
                out.append(r[0])  # type: ignore[index]
            except Exception:  # noqa: BLE001
                continue
    return out


def _refresh_cursor(session: Session, sid: uuid.UUID, state: ReplayState) -> None:
    state.statements_to_id = {
        c.statement: c.id for c in _candidates_by_session(session, sid)
    }


def _emit(
    session: Session,
    sid: uuid.UUID,
    candidate_id: uuid.UUID | None,
    kind: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "session_id": str(sid),
        "kind": kind,
    }
    if candidate_id is not None:
        payload["candidate_id"] = str(candidate_id)
    if extra:
        payload.update(extra)
    notify_via_engine(session, "candidate_updated", payload)
    return payload


def _add_cand(
    session: Session,
    sid: uuid.UUID,
    state: ReplayState,
    *,
    statement: str,
    lens: str,
    v_hat: float,
    c_hat: float,
    chunks: int = 0,
    pipeline: list[str] | None = None,
    sources: int = 0,
    status: str = "speculative",
) -> Candidate:
    cand = Candidate(
        session_id=sid,
        lens=lens,
        statement=statement,
        evidence_chunk_ids=[uuid.uuid4() for _ in range(chunks)],
        v_hat=v_hat,
        c_hat=c_hat,
        pipeline_steps=pipeline or [],
        source_count=sources,
        status=status,
    )
    session.add(cand)
    session.commit()
    session.refresh(cand)
    state.statements_to_id[statement] = cand.id
    return cand


def _update_cand(
    session: Session,
    cand: Candidate,
    **changes: Any,
) -> Candidate:
    for k, v in changes.items():
        setattr(cand, k, v)
    cand.updated_at = _now()
    session.add(cand)
    session.commit()
    session.refresh(cand)
    return cand


# ---------------------------------------------------------------------------
# Stage 0 — cold start
# ---------------------------------------------------------------------------


def _stage_cold_start(
    session: Session, sid: uuid.UUID, state: ReplayState
) -> list[dict[str, Any]]:
    seeds = [
        ("Founders need a structured way to compare opportunity briefs across studios", "cross_domain_transfer", 0.46, 0.32, 2, 2, ["Survey 5 studio partners", "Prototype brief schema"]),
        ("Vertical compliance copilots for sub-$50M SMBs are underbuilt", "contradiction_surfacing", 0.51, 0.28, 1, 1, ["Interview 10 SMB CFOs", "Compare 3 incumbent tools"]),
        ("Open-source agent observability is a missing dev-tools wedge", "distance_from_focus", 0.49, 0.34, 1, 1, ["Audit existing OSS observability", "Spec MVP"]),
        ("AI-native CRM tuned to startup-studio pipeline mechanics", "cross_domain_transfer", 0.41, 0.30, 1, 1, ["Map studio CRM workflow", "Build pipeline schema"]),
        ("Studios should run adversarial review on every opportunity brief", "contradiction_surfacing", 0.39, 0.27, 0, 0, ["Build challenger persona library", "Run on 5 historical briefs"]),
    ]
    events: list[dict[str, Any]] = []
    for s, lens, v, c, ch, sc, pl in seeds:
        cand = _add_cand(
            session, sid, state,
            statement=s, lens=lens, v_hat=v, c_hat=c,
            chunks=ch, sources=sc, pipeline=pl,
        )
        events.append(_emit(session, sid, cand.id, "candidate_added"))
    return events


# ---------------------------------------------------------------------------
# Stage 1 — HN drop
# ---------------------------------------------------------------------------


def _stage_hn_drop(
    session: Session, sid: uuid.UUID, state: ReplayState
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    cs1_id = state.statements_to_id.get("Vertical compliance copilots for sub-$50M SMBs are underbuilt")
    if cs1_id:
        cs1 = session.get(Candidate, cs1_id)
        if cs1:
            cs1 = _update_cand(
                session, cs1,
                v_hat=0.62, c_hat=0.41, source_count=5,
                evidence_chunk_ids=list(cs1.evidence_chunk_ids) + [uuid.uuid4(), uuid.uuid4()],
                status="supported",
            )
            events.append(_emit(session, sid, cs1.id, "candidate_v_hat_updated", {"to": 0.62}))

    new_cands = [
        ("Why does Stripe say 'AI is plug-and-play' while founders ship 6-month integrations?", "contradiction_surfacing", 0.71, 0.47, 3, 4, ["Talk to 10 founders shipping AI features", "Map integration time-to-value", "Compare to vendor claims"]),
        ("Personal RAG over a knowledge worker's full document trail (private, not enterprise)", "contradiction_surfacing", 0.69, 0.43, 2, 3, ["Survey 20 knowledge workers", "Compare 3 personal-RAG attempts"]),
        ("Voice-first ops for field workers — trades, logistics, last-mile", "contradiction_surfacing", 0.66, 0.40, 2, 3, ["Shadow 3 field crews", "Test voice-only journey for 2 trades"]),
    ]
    for s, lens, v, c, ch, sc, pl in new_cands:
        cand = _add_cand(
            session, sid, state,
            statement=s, lens=lens, v_hat=v, c_hat=c, chunks=ch, sources=sc, pipeline=pl,
            status="supported",
        )
        events.append(_emit(session, sid, cand.id, "candidate_added"))

    weak_id = state.statements_to_id.get("Studios should run adversarial review on every opportunity brief")
    if weak_id:
        weak = session.get(Candidate, weak_id)
        if weak:
            _update_cand(session, weak, v_hat=0.31, c_hat=0.21)
    return events


# ---------------------------------------------------------------------------
# Stage 2 — arxiv drop, cross-domain candidates appear
# ---------------------------------------------------------------------------


def _stage_arxiv_drop(
    session: Session, sid: uuid.UUID, state: ReplayState
) -> list[dict[str, Any]]:
    cands = [
        ("Browser-native LLM agents with tab-level context — apply OS-level scheduler primitives to attention budgets", 0.78, 0.55, 4, 6, ["Map current browser-agent architectures", "Spec a tab-context protocol", "Test on 3 vertical workflows"]),
        ("Real-time data quality for AI training — borrow stream-processing fault-tolerance from finance ETL", 0.74, 0.50, 2, 4, ["Audit 5 training pipelines for silent corruption", "Adapt finance ETL guarantees"]),
    ]
    events: list[dict[str, Any]] = []
    for s, v, c, ch, sc, pl in cands:
        cand = _add_cand(
            session, sid, state,
            statement=s, lens="cross_domain_transfer", v_hat=v, c_hat=c, chunks=ch, sources=sc, pipeline=pl, status="supported",
        )
        events.append(_emit(session, sid, cand.id, "candidate_added"))
    return events


# ---------------------------------------------------------------------------
# Stage 3 — dossier queue (no DB writes; the SSE listener just gets the event)
# ---------------------------------------------------------------------------


def _stage_dossier_queue(
    session: Session, sid: uuid.UUID, state: ReplayState
) -> list[dict[str, Any]]:
    target_id = state.statements_to_id.get(
        "Browser-native LLM agents with tab-level context — apply OS-level scheduler primitives to attention budgets"
    )
    if not target_id:
        return []
    return [
        _emit(
            session, sid, target_id, "dossier_queued",
            {"ticket_id": f"tkt_{target_id.hex}", "ticket_number": "TICKET-D-014"},
        )
    ]


# ---------------------------------------------------------------------------
# Stage 4 — founder transcripts; reinforce + dossier running
# ---------------------------------------------------------------------------


def _stage_founder_transcripts(
    session: Session, sid: uuid.UUID, state: ReplayState
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    target_id = state.statements_to_id.get(
        "Personal RAG over a knowledge worker's full document trail (private, not enterprise)"
    )
    if target_id:
        cand = session.get(Candidate, target_id)
        if cand:
            cand = _update_cand(
                session, cand,
                v_hat=0.81, c_hat=0.58, source_count=8,
                evidence_chunk_ids=list(cand.evidence_chunk_ids) + [uuid.uuid4() for _ in range(3)],
                reinforces=["contradiction_surfacing", "distance_from_focus"],
            )
            events.append(_emit(session, sid, cand.id, "candidate_v_hat_updated", {"to": 0.81}))

    browser_id = state.statements_to_id.get(
        "Browser-native LLM agents with tab-level context — apply OS-level scheduler primitives to attention budgets"
    )
    if browser_id:
        events.append(_emit(session, sid, browser_id, "dossier_running"))
    return events


# ---------------------------------------------------------------------------
# Stage 5 — dossier complete
# ---------------------------------------------------------------------------


def _stage_dossier_complete(
    session: Session, sid: uuid.UUID, state: ReplayState
) -> list[dict[str, Any]]:
    target_id = state.statements_to_id.get(
        "Browser-native LLM agents with tab-level context — apply OS-level scheduler primitives to attention budgets"
    )
    if not target_id:
        return []
    cand = session.get(Candidate, target_id)
    if not cand:
        return []
    sources = [
        {
            "title": "Browser agent runtime — design notes",
            "kind": "paper",
            "url": "https://arxiv.org/abs/2026.01234",
        },
        {
            "title": "Why tab-context matters for agent attention budgets",
            "kind": "blog",
            "url": "https://stratechery.com/2026/tab-context",
        },
        {
            "title": "Practitioner: shipped a browser agent in 6 weeks",
            "kind": "forum",
            "url": "https://news.ycombinator.com/item?id=987654",
        },
        {
            "title": "Survey: knowledge-worker browser-tab habits",
            "kind": "paper",
            "url": "https://arxiv.org/abs/2026.05678",
        },
    ]
    cand = _update_cand(
        session, cand,
        v_hat=0.91, c_hat=0.78,
        source_count=cand.source_count + 7,
        dossier_grounded=True,
        evidence_sources=sources,
    )
    notify_via_engine(
        session, "dossier_ready",
        {"session_id": str(sid), "candidate_id": str(cand.id)},
    )
    session.commit()
    return [
        _emit(session, sid, cand.id, "dossier_complete", {"to": 0.91}),
    ]


# ---------------------------------------------------------------------------
# Stage 6 — synthesizer merge
# ---------------------------------------------------------------------------


def _stage_synthesizer_merge(
    session: Session, sid: uuid.UUID, state: ReplayState
) -> list[dict[str, Any]]:
    pers_id = state.statements_to_id.get(
        "Personal RAG over a knowledge worker's full document trail (private, not enterprise)"
    )
    stripe_id = state.statements_to_id.get(
        "Why does Stripe say 'AI is plug-and-play' while founders ship 6-month integrations?"
    )
    if not pers_id or not stripe_id:
        return []
    pers = session.get(Candidate, pers_id)
    stripe = session.get(Candidate, stripe_id)
    if not pers or not stripe:
        return []
    pers = _update_cand(
        session, pers,
        statement=(
            "Personal RAG over a knowledge worker's full document trail "
            "(private; addresses the 'AI is plug-and-play' contradiction founders ship around)"
        ),
        merged_from=list(pers.merged_from) + [stripe.id],
        v_hat=0.84, c_hat=0.62,
        source_count=pers.source_count + stripe.source_count,
        evidence_chunk_ids=list(pers.evidence_chunk_ids) + list(stripe.evidence_chunk_ids),
    )
    state.statements_to_id[pers.statement] = pers.id
    _update_cand(session, stripe, status="merged_into")
    return [
        _emit(session, sid, pers.id, "candidate_merged"),
        _emit(session, sid, stripe.id, "candidate_merged_into"),
    ]


# ---------------------------------------------------------------------------
# Stage 7 — challenger pass
# ---------------------------------------------------------------------------


def _stage_challenger_pass(
    session: Session, sid: uuid.UUID, state: ReplayState
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    all_cands = _candidates_by_session(session, sid)
    for cand in all_cands:
        if cand.status in ("killed", "merged_into"):
            continue
        if cand.v_hat < 0.5 and not cand.dossier_grounded:
            cand = _update_cand(session, cand, status="killed", challenger_verdict="red_struck")
            events.append(_emit(session, sid, cand.id, "candidate_killed"))
        elif not cand.evidence_chunk_ids and not cand.dossier_grounded:
            cand = _update_cand(session, cand, status="killed", challenger_verdict="provenance_failed")
            events.append(_emit(session, sid, cand.id, "candidate_red_struck"))
        elif cand.dossier_grounded:
            cand = _update_cand(
                session, cand,
                challenger_verdict="held",
                provenance_audited=True,
                status="ready_to_validate",
            )
            events.append(_emit(session, sid, cand.id, "candidate_challenged_held"))
    return events


# ---------------------------------------------------------------------------
# Stage 8 — YC reveal (handled by the route; here just emit the event)
# ---------------------------------------------------------------------------


def _stage_yc_reveal(
    session: Session, sid: uuid.UUID, state: ReplayState
) -> list[dict[str, Any]]:
    return [_emit(session, sid, None, "yc_revealed")]


# ---------------------------------------------------------------------------
# Stage 9 — ahead of YC
# ---------------------------------------------------------------------------


def _stage_ahead_of_yc(
    session: Session, sid: uuid.UUID, state: ReplayState
) -> list[dict[str, Any]]:
    pers_substr = "personal rag over a knowledge worker"
    browser_substr = "browser-native llm agents with tab-level context"
    targets = []
    for cand in _candidates_by_session(session, sid):
        if cand.status in ("killed", "merged_into"):
            continue
        l = cand.statement.lower()
        if pers_substr in l or browser_substr in l:
            targets.append(cand)
    events: list[dict[str, Any]] = []
    for cand in targets[:2]:
        cand = _update_cand(session, cand, ahead_of_yc=True)
        events.append(_emit(session, sid, cand.id, "ahead_of_yc"))
    return events


# ---------------------------------------------------------------------------
# Stage 10 — open opportunity brief (enrich candidate fields)
# ---------------------------------------------------------------------------


def _stage_open_brief(
    session: Session, sid: uuid.UUID, state: ReplayState
) -> list[dict[str, Any]]:
    target = None
    for cand in _candidates_by_session(session, sid):
        if cand.dossier_grounded and cand.status == "ready_to_validate":
            target = cand
            break
    if not target:
        return []
    target = _update_cand(
        session, target,
        pain_owner=(
            "Knowledge workers at studios + analyst-heavy firms (5–50 users), and the "
            "EIRs / venture analysts whose document trails are private and growing"
        ),
        why_now=(
            "Browser agent runtimes shipped late 2025; on-device inference closed the latency "
            "gap; user habits have moved to tab-as-context (Stratechery 2026 archive)."
        ),
        contradictions=[
            "Vendors claim 'turn-key knowledge agents' while founders ship 6-month integrations",
            "Enterprise tools assume centralized doc stores — knowledge workers' docs span 10+ apps",
            "A 2026 arXiv survey shows 40% of knowledge workers explicitly distrust cloud-LLM products",
        ],
        open_assumptions=[
            "On-device retrieval can match cloud RAG quality within 18 months",
            "Users will share document trails with a private agent if local-only",
            "Tab-level context can be captured without breaking site privacy expectations",
        ],
        validation_path=[
            "Interview 10 analysts at studios about their personal doc trails",
            "Prototype a tab-context capture extension and ship to 20 alpha users",
            "Measure retrieval quality vs. centralized RAG on a fixed 100-doc corpus",
            "Kill if alpha users disable tab-capture > 50% of sessions",
        ],
    )
    return [_emit(session, sid, target.id, "brief_ready")]


DEMO_STAGES: list[StageOp] = [
    StageOp("00-cold-start", "0:00 Cold start (YC history + CS/AI catalog)", _stage_cold_start),
    StageOp("01-hn-drop", "0:30 HN top posts (last 90 days)", _stage_hn_drop),
    StageOp("02-arxiv-drop", "1:15 arXiv + Stratechery archives", _stage_arxiv_drop),
    StageOp("03-dossier-queue", "1:20 Queue evidence dossier", _stage_dossier_queue),
    StageOp("04-founder-transcripts", "1:45 Founder interview transcripts", _stage_founder_transcripts),
    StageOp("05-dossier-complete", "2:00 First dossier completes", _stage_dossier_complete),
    StageOp("06-synthesizer-merge", "2:30 Synthesizer re-runs", _stage_synthesizer_merge),
    StageOp("07-challenger-pass", "2:45 Challenger pass", _stage_challenger_pass),
    StageOp("08-yc-reveal", "3:15 Reveal YC Summer 2026 RFS", _stage_yc_reveal),
    StageOp("09-ahead-of-yc", "3:45 Highlight ahead-of-YC excess", _stage_ahead_of_yc),
    StageOp("10-open-brief", "4:00 Open opportunity brief", _stage_open_brief),
]


def apply_stage(
    session: Session,
    sid: uuid.UUID,
    stage_index: int,
    state: ReplayState | None = None,
) -> list[dict[str, Any]]:
    if stage_index < 0 or stage_index >= len(DEMO_STAGES):
        raise ValueError(
            f"stage_index {stage_index} out of range [0, {len(DEMO_STAGES)})"
        )
    stage = DEMO_STAGES[stage_index]
    cursor = state if state is not None else ReplayState()
    _refresh_cursor(session, sid, cursor)
    return stage.apply(session, sid, cursor)


def reset_session(session: Session, sid: uuid.UUID) -> int:
    """Wipe candidates for a session so a stage replay starts clean."""
    rows = _candidates_by_session(session, sid)
    n = len(rows)
    for r in rows:
        session.delete(r)
    session.commit()
    return n
