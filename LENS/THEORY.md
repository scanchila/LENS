# LENS Theoretical Framework

LENS is a problem-discovery system. Its theoretical object is not an idea, a market, or a prediction by itself. Its object is an evidence-bearing candidate problem: a claim that a specific actor experiences a costly gap between a present state and a desired state, and that this gap may be tractable, neglected, and worth validating now.

This document makes the product vocabulary formal enough to guide prompts, scoring, data models, and UI states.

## Source Review

The local research catalog is organized around the meta-problem of finding worthwhile problems. The sources support seven claims:

1. **Problem choice dominates downstream value.** Hamming argues that important work depends on working on important problems with a plausible attack, not merely on effort or intelligence. The 80,000 Hours problem-selection material makes the same claim quantitatively through scale, neglectedness, solvability, and fit.
2. **Good opportunities are usually noticed, not invented.** Paul Graham's startup-idea essays argue that strong startup ideas come from lived or observed gaps, urgent users, and prepared minds at the edge of a changing field. This is the source of LENS's bias toward corpus-grounded weak signals rather than free-form brainstorming.
3. **Problem formulation is part of the problem.** Rittel and Webber's wicked-problems frame warns that many real-world problems have no definitive formulation, no clean stopping rule, and no true-or-false solution. LENS should therefore represent assumptions, stakeholder perspective, and unresolved ambiguity explicitly.
4. **Search can be deceived by objectives.** Lehman and Stanley's novelty-search work shows that direct objective optimization can miss stepping stones. LENS should use lenses that surface novelty, contradiction, adjacency, and structural analogy before collapsing too early into a single score.
5. **Candidate areas should be judged as programs, not one-off statements.** Lakatos's progressive versus degenerating research-programme distinction maps naturally onto opportunity review: a candidate is stronger when new evidence produces new testable claims and useful next moves; it is weaker when it only absorbs objections ad hoc.
6. **Proposal quality requires adversarial questioning.** The Heilmeier catechism supplies a durable review pattern: what are you trying to do, what is new, who cares, what are the risks, what will it cost, and how will progress be measured. LENS's Challenger and Skeptic roles operationalize this stress test.
7. **Cross-domain transfer is a defensible lens.** Wing's computational-thinking work, Hamming's mathematics-transfer argument, and the CS/AI cross-domain corpus support the hypothesis that abstractions from computation can identify opportunities in other domains when the relational structure really matches.

## Formal Objects

Let `D` be a corpus: a finite set of source documents, transcripts, posts, papers, catalog entries, and prior dossiers. A source item `s in D` has provenance metadata:

```text
s = (source_id, origin, author, timestamp, retrieval_method, rights_note, content_hash)
```

A trace `t` is a cited span or extracted datum from a source:

```text
t = (trace_id, source_id, span_ref, extracted_claim, confidence, extraction_method)
```

A claim `q` is an atomic proposition asserted by the system:

```text
q = (subject, predicate, object, qualifiers, time_scope)
```

Claims can be linked to traces by evidential relations:

```text
supports(t, q)
weakens(t, q)
contradicts(t, q)
contextualizes(t, q)
```

A signal `g` is a pattern over traces that may indicate unmet need, change, or contradiction:

```text
g = (pattern_type, traces, lens_attribution, novelty, reliability)
```

Examples of signal types include repeated complaint, workaround, demand-capacity mismatch, regulatory shift, technical capability shift, incumbent blind spot, contradiction between stated and actual behavior, and structural analogy to a known CS/AI pattern.

A candidate problem `c` is a structured hypothesis:

```text
c = (
  actor,
  current_state,
  desired_state,
  gap,
  proposed_mechanism,
  affected_workflow,
  evidence_set,
  assumptions,
  lens_attribution,
  validation_path
)
```

A candidate is not yet an opportunity. It becomes an opportunity brief only after the system can explain why the gap matters, who has the pain, what evidence supports it, what evidence weakens it, why now, and what validation would change the decision.

## Scoring Model

LENS scores candidates as decision-support signals, not truth claims. The default components are:

```text
S(c)  = scale: magnitude of value if the gap is solved
N(c)  = neglectedness: inverse of credible effort already aimed at the gap
T(c)  = tractability: probability that a focused team can make progress
U(c)  = urgency: strength and immediacy of the actor's pain
M(c)  = momentum: evidence that enabling conditions are improving now
O(c)  = non_obviousness: degree to which the candidate is not already consensus
G(c)  = groundedness: quality and independence of supporting traces
R(c)  = refutation_pressure: strength of contradiction, missing evidence, and challenger findings
F(c)  = fit: optional match to the user's assets, taste, network, or mandate
```

A simple review score can be expressed as:

```text
V_hat(c) = wS*S + wN*N + wT*T + wU*U + wM*M + wO*O + wG*G + wF*F - wR*R
```

The score is deliberately provisional. A high `V_hat` queues deeper work; it does not validate the opportunity. Confidence must be reported separately:

```text
C_hat(c) = f(trace_count, source_independence, provenance_quality, contradiction_rate, dossier_depth)
```

This separation prevents a seductive but weakly sourced candidate from being treated like a validated one.

## Candidate Lifecycle

Candidate status is an epistemic state:

- `speculative`: a candidate exists, but evidence is thin or single-source.
- `supported`: evidence from one or more sources supports the gap or mechanism.
- `challenged`: an adversarial pass has produced objections, missing evidence, or refutations.
- `ready_to_validate`: the candidate is grounded enough to justify human validation work.
- `killed`: the candidate failed due to weak evidence, contradiction, duplication, low urgency, low tractability, or low actionability.

Killing a candidate is a successful outcome when it prevents wasted validation work.

## Lens Definition

A lens is a constrained transformation from corpus traces to candidate hypotheses:

```text
L_i: P(T) -> P(C)
```

Each lens must declare:

- the signal types it is allowed to use
- the assumptions it tends to introduce
- the failure modes it is prone to
- the evidence required before a candidate can advance

For example, the cross-domain-transfer lens maps a domain trace to an abstract structural signature, searches for a matching CS/AI principle, then proposes a domain-specific gap. Its failure mode is false analogy, so it needs relational-structure evidence, not just vocabulary overlap.

## Review Rules

LENS should enforce these rules across agents, storage, and UI:

1. No candidate without at least one trace.
2. No score without score-component explanations.
3. No status transition without an event record.
4. No `ready_to_validate` without explicit assumptions and kill criteria.
5. No opportunity brief without contradictory or weakening evidence, even if the contradiction set is empty and labeled as not found.
6. No benchmark claim without cutoff dates and source eligibility.
7. No generated source of truth: private corpora, dossiers, and human verdicts remain first-class provenance nodes.

## Opportunity Brief Definition

An opportunity brief is the final review artifact:

```text
b = (
  candidate_id,
  problem_statement,
  actor_and_pain,
  source_traces,
  supporting_claims,
  weakening_claims,
  why_now,
  existing_alternatives,
  assumptions,
  validation_plan,
  kill_criteria,
  human_verdict
)
```

The brief is not a pitch. It is a decision object. Its job is to let a venture team decide whether to accept, reject, park, or spend validation budget on the candidate.

## Evaluation

The YC RFS benchmark tests whether LENS can generate defensible RFS-style opportunity candidates using only pre-cutoff source material. For each prediction cycle:

- `precision`: share of predictions that directly or adjacently match the held-out RFS list
- `recall`: share of held-out RFS items covered by predictions
- `excess`: predictions not on the held-out list
- `excess_quality`: whether excess predictions are grounded enough to be plausible leading indicators
- `provenance_quality`: whether a human can follow the reasoning chain from brief to source traces
- `kill_rate`: share of weak candidates eliminated before review
- `time_to_brief`: elapsed time from corpus ingestion to reviewable artifact

The benchmark should reward honest uncertainty. A lower raw prediction count with stronger provenance is preferable to a longer list of plausible but unsupported ideas.

## Design Implication

LENS should feel like a research instrument: it reveals signals, records uncertainty, applies adversarial pressure, and preserves the path from source material to decision. If the system cannot explain a candidate's source traces, score movement, assumptions, and failure conditions, it has not produced a LENS-grade output.
