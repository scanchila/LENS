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

## Scoring Foundations

The theoretical base for LENS should be decision theory, opportunity theory, and evidence appraisal. Applied frameworks such as RICE, ODI, TRL, GRADE, CHNRI, and Heilmeier are useful, but they are implementation adapters rather than foundations.

| Foundation | Role in LENS | Why it matters |
|---|---|---|
| Multi-attribute utility theory | Candidate value is a preference-weighted function over multiple attributes, not a single natural quantity | Forces explicit tradeoffs between value, tractability, novelty, urgency, fit, and risk |
| Value-focused thinking | Start from the decision-maker's values before generating or ranking alternatives | Prevents LENS from ranking generic opportunities that are irrelevant to the user's mandate |
| Bayesian decision analysis and value of information | Validation is valuable when it changes a decision under uncertainty | Turns dossier work and interviews into explicit information-gathering investments |
| Exploration/exploitation theory | Search must allocate effort between novel possibilities and known promising areas | Explains why LENS should preserve strange but grounded candidates instead of optimizing too early |
| Entrepreneurial opportunity theory | Opportunities are discovered, created, evaluated, and exploited by particular actors | Keeps the actor/opportunity fit central instead of treating opportunities as context-free objects |
| Creativity and idea-evaluation research | Novelty alone is insufficient; candidates also need workability, relevance, and specificity | Gives non-obviousness a more precise structure |
| Argumentation and evidence theory | Claims require grounds, warrants, qualifiers, backing, and rebuttals | Maps naturally to provenance graphs and Challenger/Skeptic review |

These foundations are subordinate to the LENS object model. They explain how to reason about a candidate problem; they do not replace the candidate-problem definition.

## Operational Scoring Models

The operational models below are useful only when attached to the right part of the LENS object:

| Model | What LENS borrows | Status |
|---|---|---|
| ITN / SNT | Scale, neglectedness, tractability/solvability, fit, and logarithmic comparison | Practical decomposition of value |
| ODI opportunity algorithm | Unmet-need score from importance and satisfaction | Useful when customer outcome data exists |
| RICE | Reach, impact, confidence, and effort for deciding what to validate next | Product heuristic, not a foundation |
| CHNRI | Independent expert scoring, explicit criteria, collective optimism, stakeholder weights | Useful for panel review |
| GRADE | Separate value from certainty; downgrade confidence for bias, inconsistency, indirectness, imprecision, and publication bias | Useful confidence scaffold, especially when adapted beyond medicine |
| TRL | Readiness level for enabling technology or solution approach | Useful feasibility subscore |
| Heilmeier | Hard review questions and "exams" for progress | Gate, not score |

## LENS Scoring Model

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

The core value score is a multi-attribute utility model framed around LENS's candidate-problem object:

```text
ProblemValue(c) = wS*S + wN*N + wT*T + wU*U + wM*M + wO*O + wF*F
```

Weights are not universal constants. They express the user's value model for a particular investigation: a startup studio, a climate fund, and a solo founder should not necessarily rank the same candidate the same way.

## Weight Calibration

LENS weights should begin as explicit user or organization preferences. Early trust matters more than hidden optimization, so the first version should store named weight profiles:

```text
WeightProfile = (
  profile_id,
  owner_id,
  mandate,
  weights,
  created_by,
  created_at,
  rationale
)
```

After enough historical decisions accumulate, LENS can add a learned calibration layer:

```text
w_effective = normalize(w_user + lambda * w_learned)
```

Where:

- `w_user` is the explicit preference vector set by the user or organization.
- `w_learned` is estimated from prior candidate scores, human verdicts, validation outcomes, and downstream success.
- `lambda` controls how much learned history is allowed to influence the score.

`lambda` should start at `0`. It should increase only when there is enough outcome history for a given organization, mandate, and candidate class. Sparse data should produce recommendations, not automatic weight changes.

The calibration targets should be staged:

```text
Stage 1: predict human verdicts
  accept, reject, park, request_dossier, ready_to_validate

Stage 2: predict validation outcomes
  strong_customer_signal, contradiction_found, low_urgency, no_budget, viable_wedge

Stage 3: predict downstream portfolio outcomes
  funded, incubated, revenue_signal, strategic_adoption, killed_after_validation
```

The learned layer must remain inspectable:

```text
scale:
  user_weight: 0.20
  learned_adjustment: +0.04
  effective_weight: 0.24
  evidence: "Past studio decisions advanced high-scale candidates 18% more often."
```

Calibration rules:

1. A learned adjustment cannot silently override a user-set mandate.
2. Learned weights must be versioned and reproducible from historical data.
3. Weight changes require enough examples in the same context; cross-org pooling is opt-in.
4. Users should be able to compare rankings under `user_only`, `learned_adjusted`, and `counterfactual` profiles.
5. The system should surface calibration uncertainty, not only adjusted weights.

When LENS has customer-outcome data, it should compute an ODI-style unmet-need component:

```text
UnmetNeed(o) = Importance(o) + max(0, Importance(o) - Satisfaction(o))
```

Here `o` is a desired outcome inside the candidate's actor/workflow context. If the input is only qualitative, LENS should estimate `Importance` and `Satisfaction` with explicit provenance and low confidence rather than pretend it has survey precision.

Evidence confidence is separate and GRADE-like:

```text
EvidenceConfidence(c) = f(
  trace_count,
  source_independence,
  provenance_quality,
  risk_of_bias,
  inconsistency,
  indirectness,
  imprecision,
  publication_or_selection_bias,
  contradiction_rate,
  dossier_depth
)
```

Readiness is separate again:

```text
Readiness(c) = g(technical_readiness, operational_readiness, data_readiness, regulatory_readiness)
```

`technical_readiness` can use a TRL-like 1-9 scale when the candidate depends on a technology whose maturity matters.

The displayed LENS score should therefore be a tuple, not a single opaque number:

```text
LensScore(c) = (
  problem_value,
  unmet_need,
  evidence_confidence,
  readiness,
  refutation_pressure,
  validation_priority
)
```

For ranking what to validate next, LENS can use a RICE-like validation priority:

```text
ValidationPriority(c) =
  Reach(c) * ProblemValue(c) * EvidenceConfidence(c) / ValidationEffort(c)
```

The more principled version is value-of-information driven:

```text
ValidationValue(c, action) =
  ExpectedDecisionImprovement(c, action) - Cost(action)
```

Here an interview, dossier, prototype, market map, or expert review is worth doing only if the expected information can change whether the candidate is killed, parked, advanced, or funded.

The score is deliberately provisional. A high `problem_value`, `validation_priority`, or `validation_value` queues deeper work; it does not validate the opportunity. This separation prevents a seductive but weakly sourced candidate from being treated like a validated one.

## Panel Review

For high-stakes candidates, LENS should support CHNRI-style independent scoring. A review panel can score each candidate against explicit criteria:

```text
answerability
novelty
importance
tractability
deliverability
affordability
strategic_fit
evidence_quality
```

Each reviewer gives criterion-level judgments independently. LENS aggregates them as:

```text
CollectiveOptimism(c, criterion) = positive_or_partial_scores / received_scores
PanelScore(c) = weighted_mean(CollectiveOptimism(c, criteria), stakeholder_weights)
```

Panel disagreement is signal, not noise. The UI should preserve dispersion and reviewer rationale instead of only showing the mean.

## Hard Gates

Heilmeier-style review should act as a gate before a candidate reaches `ready_to_validate`:

1. What is the candidate trying to change, stated without jargon?
2. How is the actor solving or tolerating the problem today?
3. What is new in the proposed mechanism or timing?
4. Who cares, and what changes if the problem is solved?
5. What are the technical, market, regulatory, and adoption risks?
6. What will validation cost?
7. How long will validation take?
8. What mid-term and final exams would change the decision?

If these questions cannot be answered with traces, assumptions, or explicit unknowns, the candidate cannot become an opportunity brief.

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
7. No single total score without displaying value, confidence, readiness, and refutation pressure separately.
8. No generated source of truth: private corpora, dossiers, and human verdicts remain first-class provenance nodes.

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

## References For Scoring

- Keeney and Raiffa, `Decisions with Multiple Objectives`: https://www.cambridge.org/core/books/decisions-with-multiple-objectives/
- Keeney, "Value-focused thinking: Identifying decision opportunities and creating alternatives": https://doi.org/10.1016/0377-2217(96)00004-5
- March, "Exploration and Exploitation in Organizational Learning": https://doi.org/10.1287/orsc.2.1.71
- Shane and Venkataraman opportunity-theory lineage, summarized in this open review: https://link.springer.com/article/10.1007/s11301-024-00466-5
- Sarasvathy, "Causation and Effectuation": https://doi.org/10.5465/AMR.2001.4378020
- Hayek, "The Use of Knowledge in Society": https://www.jstor.org/stable/1809376
- Amabile, "The Social Psychology of Creativity: A Consensual Assessment Technique": https://www.hbs.edu/faculty/Pages/item.aspx?num=7355
- Dean et al., "Identifying Quality, Novel, and Creative Ideas": https://doi.org/10.17705/1jais.00106
- Besemer and O'Quin, Creative Product Semantic Scale: https://doi.org/10.1080/10400418909534323
- Toulmin argument model overview: https://owl.purdue.edu/owl/general_writing/academic_writing/historical_perspectives_on_argumentation/toulmin_argument.html
- Bradford Hill, "The Environment and Disease: Association or Causation?": https://pmc.ncbi.nlm.nih.gov/articles/PMC1898525/
- 80,000 Hours, "A framework for comparing global problems in terms of expected impact": https://80000hours.org/articles/problem-framework/
- Strategyn / Outcome-Driven Innovation opportunity algorithm: https://strategyn.com/outcome-driven-innovation/market-opportunity/
- Intercom RICE prioritization: https://www.intercom.com/blog/rice-simple-prioritization-for-product-managers/
- CHNRI research priority setting method: https://pmc.ncbi.nlm.nih.gov/articles/PMC4938380/
- GRADE certainty of evidence guidance: https://pmc.ncbi.nlm.nih.gov/articles/PMC6542664/
- CDC ACIP GRADE handbook, certainty domains: https://www.cdc.gov/acip-grade-handbook/hcp/chapter-7-grade-criteria-determining-certainty-of-evidence/index.html
- NASA technology readiness levels: https://www.nasa.gov/directorates/somd/space-communications-navigation-program/technology-readiness-levels
- DARPA Heilmeier Catechism: https://www.darpa.mil/about/heilmeier-catechism
