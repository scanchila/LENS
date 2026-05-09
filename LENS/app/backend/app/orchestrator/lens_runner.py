"""Live LLM-driven lens execution.

For the live demo path: drives a real cross_domain (or contradiction)
lens via :class:`CodexSubprocessAdapter`. The output is parsed as
structured JSON, persisted into ``candidates``, written into the AGE
graph (``Candidate``, ``Source``, ``Claim``, edges), and emitted as a
``candidate_updated`` NOTIFY for the SSE feed.

The runner is intentionally simple — it does not mediate tool calls
during the LLM run. Retrieval is done server-side before invocation;
the resulting chunks + catalog snippets are spliced into the prompt.
This trades some ad-hoc reasoning depth for cost predictability and
a clean audit trail.
"""

from __future__ import annotations

import json
import logging
import textwrap
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlmodel import Session, select

from app.agents.adapters import (
    CodexInvocationError,
    CodexSubprocessAdapter,
    parse_json_response,
)
from app.agents.types import AgentDefinition, AgentRunInput
from app.db.notify import notify_via_engine
from app.graph import age_client
from app.models import Candidate, Chunk, Document

logger = logging.getLogger(__name__)


# JSON schema for the structured response. Codex respects --output-schema
# when running gpt-5+ models and emits a single JSON object.
CANDIDATES_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["candidates"],
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "statement",
                    "v_hat",
                    "c_hat",
                    "evidence_chunk_ids",
                    "claims",
                    "pipeline_steps",
                    "non_obviousness_note",
                ],
                "properties": {
                    "statement": {"type": "string"},
                    "v_hat": {"type": "number"},
                    "c_hat": {"type": "number"},
                    "evidence_chunk_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "claims": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["text", "valence", "source_refs"],
                            "properties": {
                                "text": {"type": "string"},
                                "valence": {
                                    "type": "string",
                                    "enum": ["supports", "refutes", "neutral"],
                                },
                                "source_refs": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                        },
                    },
                    "pipeline_steps": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "non_obviousness_note": {"type": "string"},
                },
            },
        }
    },
}


CROSS_DOMAIN_SYSTEM_PROMPT = textwrap.dedent(
    """\
    You are the cross-domain transfer Lens-Proposer in the LENS opportunity-discovery system.
    Your job: read the user's corpus snippets and a curated CS/AI principles catalog,
    then surface 2-4 candidate problems where a structurally analogous principle from
    one domain transfers to the user's domain.

    Methodology (follow exactly):

    1. SCAN the corpus snippets to identify the dominant domain(s), recurring entities,
       frustrations, capacity-vs-demand mismatches, and contradictions.
    2. ABSTRACT each pattern into domain-neutral structural language: producer, consumer,
       medium, bottleneck, deterministic vs stochastic, stateful vs stateless, failure modes.
    3. MATCH each abstraction to a principle in the catalog. Be skeptical of surface
       similarities — only treat as a match if the relational structure is genuinely the same.
    4. PROPOSE a candidate problem in the form:
       "In <user-domain area>, <observed phenomenon>. This is structurally a
        <CS/AI principle> problem. Importing the principle's solution shape would produce:
        <concrete description>. The problem worth solving is therefore <pointed problem statement>."

    Constraints:
    - Every candidate must cite at least one corpus chunk_id in evidence_chunk_ids.
    - Every claim should reference one or more source_refs (chunk_id or catalog principle).
    - v_hat ∈ [0,1] is your estimated value if the bet pays out.
    - c_hat ∈ [0,1] is your confidence in v_hat (lower if evidence is thin).
    - Drop candidates that fail the non-obviousness test ("would the domain expert immediately say 'we already do that'?").

    Output: JSON object matching the supplied schema. No prose outside the JSON.
    """
)


CONTRADICTION_SYSTEM_PROMPT = textwrap.dedent(
    """\
    You are the contradiction-surfacing Lens-Proposer in LENS. Find candidates where multiple
    sources in the corpus disagree, and surface the contradiction itself as a problem to investigate.

    Methodology:

    1. Identify high-frequency claims in the corpus snippets.
    2. For each, scan for snippets that contradict — opposite valence, conflicting metrics,
       divergent recommendations.
    3. Score pair-wise contradiction strength using your reasoning.
    4. Output 2-4 candidates phrased as either:
       - "Why does X disagree with Y about Z?"
       - "Resolve the gap between A's claim and B's claim about Z."

    Constraints:
    - Both contradicting chunk_ids must appear in evidence_chunk_ids.
    - Each claim should reference its source chunk_id.
    - v_hat reflects the value of resolving the contradiction.
    - c_hat reflects confidence the contradiction is real (not a definitional mismatch).

    Output: JSON object matching the supplied schema. No prose outside the JSON.
    """
)


SYSTEM_PROMPTS = {
    "cross_domain_transfer": CROSS_DOMAIN_SYSTEM_PROMPT,
    "contradiction_surfacing": CONTRADICTION_SYSTEM_PROMPT,
}


def _load_catalog_seed(limit: int = 8) -> list[dict[str, Any]]:
    """Load a subset of the CS/AI catalog from the seed JSON."""
    seed_path = (
        Path(__file__).resolve().parents[1]
        / "agents"
        / "data"
        / "catalog_seed.json"
    )
    if not seed_path.exists():
        return []
    try:
        data = json.loads(seed_path.read_text())
        if isinstance(data, list):
            return data[:limit]
    except json.JSONDecodeError:
        pass
    return []


def _gather_corpus_snippets(
    session: Session,
    session_id: uuid.UUID,
    owner_id: uuid.UUID | None,
    limit: int = 30,
) -> list[dict[str, Any]]:
    """Pull a representative slice of the user's corpus.

    For the demo we don't run a real semantic query; we just take the
    most recent chunks scoped to the owner. The lens prompt receives
    them with chunk_ids so the model can ground claims by reference.
    """
    stmt = (
        select(Chunk, Document)
        .join(Document, Chunk.document_id == Document.id)
        .order_by(Document.ingested_at.desc())  # type: ignore[union-attr]
    )
    if owner_id:
        stmt = stmt.where(Document.owner_id == owner_id)
    stmt = stmt.limit(limit)
    rows = session.exec(stmt).all()
    snippets: list[dict[str, Any]] = []
    for chunk, doc in rows:
        text = chunk.text.strip().replace("\n", " ")
        if len(text) > 600:
            text = text[:600] + "…"
        snippets.append(
            {
                "chunk_id": str(chunk.id),
                "document_source": doc.source_uri or doc.source_type,
                "text": text,
            }
        )
    return snippets


def _build_user_prompt(
    *,
    snippets: list[dict[str, Any]],
    catalog: list[dict[str, Any]],
    extra_instruction: str = "",
) -> str:
    cat_text = "\n\n".join(
        textwrap.dedent(
            f"""
            # Principle: {p.get('principle_name')}
            domain: {p.get('domain')}
            description: {p.get('description')}
            structural_signature: {p.get('structural_signature')}
            canonical_examples: {', '.join(p.get('canonical_examples', [])[:3])}
            cross_domain_examples: {', '.join(p.get('cross_domain_examples', [])[:3])}
            """
        ).strip()
        for p in catalog
    )

    if snippets:
        snip_text = "\n\n".join(
            f"chunk_id: {s['chunk_id']}\nsource: {s['document_source']}\ntext: {s['text']}"
            for s in snippets
        )
    else:
        snip_text = (
            "(corpus is empty; produce 2 speculative candidates labeled "
            "v_hat ≤ 0.5 and c_hat ≤ 0.4, citing only catalog principles, "
            "and explicitly note coverage gaps)"
        )

    return textwrap.dedent(
        f"""
        ## Corpus snippets

        {snip_text}

        ## Catalog (CS/AI principles)

        {cat_text}

        {extra_instruction}

        Return a JSON object with key "candidates" matching the supplied schema.
        """
    ).strip()


async def _write_candidate_to_age(candidate: Candidate, claims: list[dict[str, Any]]) -> None:
    """Write the candidate, claim, and source vertices/edges into AGE.

    Best-effort: failures are logged and don't block persistence into
    the relational candidates table. The Skeptic-fold provenance walk
    later reads these vertices to verify each claim has a source.
    """
    try:
        await age_client.cypher(
            "MERGE (c:Candidate {id: $cid}) SET c.statement = $stmt, c.lens = $lens",
            cid=str(candidate.id),
            stmt=candidate.statement,
            lens=candidate.lens,
        )
        for i, claim in enumerate(claims):
            claim_id = f"{candidate.id}::claim::{i}"
            await age_client.cypher(
                "MERGE (cl:Claim {id: $clid}) SET cl.text = $txt, cl.valence = $val",
                clid=claim_id,
                txt=str(claim.get("text", ""))[:500],
                val=str(claim.get("valence", "neutral")),
            )
            valence = str(claim.get("valence", "neutral"))
            edge = "supports" if valence == "supports" else (
                "refutes" if valence == "refutes" else "supports"
            )
            await age_client.cypher(
                f"MATCH (cand:Candidate {{id: $cid}}), (cl:Claim {{id: $clid}}) "
                f"MERGE (cl)-[:{edge}]->(cand)",
                cid=str(candidate.id),
                clid=claim_id,
            )
            for sref in claim.get("source_refs", []) or []:
                src_id = str(sref)
                await age_client.cypher(
                    "MERGE (s:Source {id: $sid})",
                    sid=src_id,
                )
                await age_client.cypher(
                    "MATCH (cl:Claim {id: $clid}), (s:Source {id: $sid}) "
                    "MERGE (cl)-[:cited_by]->(s)",
                    clid=claim_id,
                    sid=src_id,
                )
    except Exception:  # noqa: BLE001
        logger.exception("AGE write failed for candidate %s", candidate.id)


async def run_lens(
    *,
    session: Session,
    session_id: uuid.UUID,
    owner_id: uuid.UUID | None,
    lens: str,
    timeout_seconds: int = 600,
    model_override: str | None = None,
) -> list[uuid.UUID]:
    """Execute one lens against the live session corpus.

    Returns the ids of newly persisted candidates. Emits a NOTIFY per
    candidate so the SSE board updates in real time.
    """
    if lens not in SYSTEM_PROMPTS:
        raise ValueError(
            f"unknown lens {lens!r}; choose from {sorted(SYSTEM_PROMPTS)}"
        )

    snippets = _gather_corpus_snippets(session, session_id, owner_id)
    catalog = _load_catalog_seed()
    user_prompt = _build_user_prompt(snippets=snippets, catalog=catalog)

    agent = AgentDefinition(
        name=f"{lens}_proposer",
        role="lens_proposer",
        system_prompt=SYSTEM_PROMPTS[lens],
        tool_names=[],
        model=model_override or "gpt-5.5",
        max_turns=4,
        temperature=0.7,
    )
    adapter = CodexSubprocessAdapter(timeout_seconds=timeout_seconds)
    run_input = AgentRunInput(
        initial_prompt=user_prompt,
        metadata={
            "session_id": str(session_id),
            "output_schema": CANDIDATES_OUTPUT_SCHEMA,
            "model_override": model_override,
        },
    )

    try:
        run_output = await adapter.run(agent, run_input, tools=[])
    except CodexInvocationError:
        logger.exception("codex invocation failed for lens=%s", lens)
        raise

    parsed: dict[str, Any]
    try:
        parsed = parse_json_response(run_output.final_message)
    except ValueError:
        logger.warning(
            "lens=%s produced unparseable JSON: %r", lens, run_output.final_message[:500]
        )
        return []

    raw_cands = parsed.get("candidates", []) if isinstance(parsed, dict) else []
    if not isinstance(raw_cands, list):
        return []

    persisted_ids: list[uuid.UUID] = []
    for raw in raw_cands:
        if not isinstance(raw, dict):
            continue
        statement = str(raw.get("statement", "")).strip()
        if not statement:
            continue

        evidence_ids: list[uuid.UUID] = []
        for cid in raw.get("evidence_chunk_ids", []) or []:
            try:
                evidence_ids.append(uuid.UUID(str(cid)))
            except (ValueError, TypeError):
                continue

        v_hat = float(raw.get("v_hat", 0.5))
        c_hat = float(raw.get("c_hat", 0.3))
        v_hat = max(0.0, min(1.0, v_hat))
        c_hat = max(0.0, min(1.0, c_hat))

        candidate = Candidate(
            session_id=session_id,
            owner_id=owner_id,
            lens=lens,
            statement=statement,
            evidence_chunk_ids=evidence_ids,
            v_hat=v_hat,
            c_hat=c_hat,
            pipeline_steps=[
                str(s) for s in raw.get("pipeline_steps", []) or []
            ],
            source_count=len({str(s) for c in raw.get("claims", []) or [] for s in (c.get("source_refs") or [])}),
            status="supported" if evidence_ids else "speculative",
            updated_at=datetime.now(timezone.utc),
        )
        session.add(candidate)
        session.commit()
        session.refresh(candidate)
        persisted_ids.append(candidate.id)

        # Best-effort AGE provenance writes
        await _write_candidate_to_age(candidate, raw.get("claims", []) or [])

        notify_via_engine(
            session,
            "candidate_updated",
            {
                "session_id": str(session_id),
                "candidate_id": str(candidate.id),
                "kind": "candidate_added",
                "lens": lens,
                "via": "codex",
            },
        )
        session.commit()

    return persisted_ids
