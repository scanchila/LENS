# LENS Demo Plan

This document is the canonical planning artifact for the hackathon demo. The implementation plan explains how the system is built; this document explains what the audience should understand, what the operator should do on stage, and how the demo proves the product thesis.

## Demo Goal

Show that LENS is not an AI idea generator. It is a decision-support system for opportunity discovery.

The formal vocabulary for the demo lives in [`THEORY.md`](THEORY.md). In the demo, a candidate is not "an idea"; it is an evidence-bearing hypothesis about an actor, a gap, supporting and weakening traces, assumptions, and a validation path.

The audience should leave with three beliefs:

1. LENS can surface non-obvious opportunity candidates from messy signals.
2. LENS can explain why a candidate is worth attention through evidence, provenance, and adversarial review.
3. LENS helps a venture team decide what to kill, park, or validate next.

## Customer and User Thesis

Primary customer:

- Startup studios and venture builders
- Buyer: studio partner, venture builder lead, head of incubation
- Budget reason: choosing the wrong opportunity burns founder time, analyst time, partner attention, and capital

Primary user:

- Venture analysts
- EIRs
- Founders-in-residence
- Thesis researchers

User job:

- Select or upload source corpora
- Run investigation sessions
- Inspect candidates, evidence, contradictions, and confidence movement
- Request deeper evidence dossiers
- Export surviving candidates into opportunity briefs for partner review

Secondary customer hypotheses:

- Early-stage VC funds
- Corporate innovation and strategy teams
- Accelerators and university entrepreneurship programs
- Solo founders and indie hackers

The startup studio wedge remains the cleanest first bet because opportunity selection is repeated, expensive, and central to the workflow.

## Core Positioning

Short version:

> LENS turns messy public and private signals into evidence-backed opportunity briefs, then challenges them so teams can decide which problems are worth validating.

What LENS is:

- An opportunity discovery workflow
- A research compression tool
- A provenance and challenge layer for venture thesis work
- A way to create better opportunity review artifacts

What LENS is not:

- A generic brainstormer
- A chat interface for startup ideas
- A replacement for founder or investor judgment
- A claim that every surfaced opportunity is validated

## What Buyers Pay For

They pay for:

- Faster thesis research and opportunity memo creation
- Broader weak-signal coverage across public and private corpora
- Fewer bad opportunities entering partner review
- Evidence-backed discussion artifacts instead of raw AI suggestions
- Clear next validation steps for surviving candidates
- A private corpus that compounds as studio notes, founder calls, and market research accumulate

The ROI argument is not "LENS finds ideas." The ROI argument is "LENS changes costly decisions earlier."

## Why They Might Not Pay

Use these objections as demo risks to actively answer.

| Objection | Demo answer |
|---|---|
| The output is too speculative | Show candidate lifecycle states and make weak candidates visibly die. |
| We do not trust AI venture judgment | Show evidence, source traces, contradiction checks, and Challenger outcomes. |
| We already do this manually | Position LENS as compression and coverage for the existing thesis process. |
| It is unclear what category this belongs to | Frame it as an AI research copilot for venture thesis and opportunity discovery. |
| Value is hard to measure quickly | Report candidates generated, killed, dossier-backed, briefed, and rated worth exploring. |
| Data ingestion is a bottleneck | Start from prebuilt public corpora, then show private uploads improving specificity. |
| This feels like AI novelty | End on an opportunity brief, not a list of ideas. |

## Demo Narrative

Title:

> Watch it get smarter

Narrative:

1. Start with a weak prior.
2. Add evidence bundles.
3. Watch candidates appear, move, merge, and die.
4. Queue deep evidence work for high-value candidates.
5. Let Challenger attack the claims.
6. Reveal the benchmark.
7. End with a practical artifact: an opportunity brief.

The emotional arc should be: "This is not magic. I can see the system updating its beliefs."

## Stage Script

Target length: 4 to 5 minutes.

| Time | Operator action | Audience sees | Product point |
|---|---|---|---|
| 0:00 | Cold start with YC history and CS/AI principles catalog | Generic predictions, low confidence, no dossier badges | The system starts uncertain. |
| 0:30 | Drop HN top posts from the last 90 days before cutoff | Board churns; complaint-shaped opportunities appear | Messy user pain changes the board. |
| 1:15 | Drop arXiv recent papers and Stratechery archives | Cross-domain transfer surfaces a structurally analogous candidate | LENS can find non-obvious patterns. |
| 1:20 | Queue evidence dossier for high-value candidate | CAR ticket appears as pending | The system knows when to invest deeper. |
| 1:45 | Drop founder interview transcripts | Reinforced candidate emerges across multiple sources | Private corpus makes output more proprietary. |
| 2:00 | First dossier completes | Source badge appears; confidence changes; graph evidence available | Deep research affects ranking. |
| 2:30 | Synthesizer re-runs on populated graph | Duplicate candidates merge; shared sources appear | LENS reduces noise. |
| 2:45 | Challenger pass runs | Weak candidates are killed; one dossiered candidate survives | Trust comes from adversarial review. |
| 3:15 | Reveal YC Summer 2026 RFS benchmark | Precision/recall curve improves across stages | The system can be evaluated. |
| 3:45 | Highlight "ahead of YC" excess predictions | Defensible non-overlap examples with signals | Excess can be leading indicator, not noise. |
| 4:00 | Run judge-persona coda | Personalized candidate appears from interest doc | YC is one benchmark, not the only use case. |
| 4:30 | Open opportunity brief | Problem, pain owner, evidence, contradictions, assumptions, next validation steps | This is the paid artifact. |

## Required Demo Surfaces

Prediction board:

- Ranked candidates
- Candidate lifecycle status
- Confidence and uncertainty bars
- Lens attribution chips
- Dossier badges
- Challenge/provenance badges

Diff feed:

- Candidate added
- Candidate confidence changed
- Candidate killed
- Candidate merged
- Dossier queued
- Dossier completed
- Candidate advanced to ready_to_validate

CAR side panel:

- Pending ticket
- Running ticket
- Complete ticket
- Link from ticket to candidate

Benchmark panel:

- Held-out YC RFS list
- Precision by stage
- Recall by stage
- Excess predictions
- Provenance quality notes

Opportunity brief:

- Problem statement
- Who has the pain
- Customer/user hypothesis
- Evidence sources
- Contradictory signals
- Why now
- Existing alternatives
- Open assumptions
- Recommended validation path
- Human verdict controls: accept, reject, park, request dossier

## Candidate Lifecycle

Candidate states:

- speculative: generated but weakly supported
- supported: has evidence from one or more sources
- challenged: has survived or failed an adversarial pass
- ready_to_validate: strong enough for customer discovery or partner discussion
- killed: collapsed under weak evidence, contradiction, duplication, or low actionability

The demo should show at least one candidate moving forward and at least one candidate being killed. Killing a weak candidate is part of the value proposition.

## Opportunity Brief Template

```text
Opportunity Brief

Problem
- One-sentence problem statement

Who Has The Pain
- Primary customer hypothesis
- Primary user hypothesis
- Why this pain is acute

Evidence
- Source 1
- Source 2
- Source 3

Contradictions / Risks
- Evidence that weakens the candidate
- Reasons the problem may not be urgent
- Existing alternatives

Why Now
- Technical shift
- Market shift
- Behavioral shift
- Regulatory or economic shift

Open Assumptions
- Assumption 1
- Assumption 2
- Assumption 3

Recommended Validation Path
- First customer segment to interview
- Questions to ask
- Data to collect
- Kill criteria

Human Verdict
- Accept
- Reject
- Park
- Request dossier
```

## Demo Data Plan

Prebaked corpora:

- YC prior RFS history
- Curated CS/AI principles catalog
- HN top posts before cutoff
- Recent arXiv papers before cutoff
- Stratechery archives before cutoff
- Founder interview transcripts, synthetic but plausible
- Judge-persona interest document

Benchmark:

- YC Summer 2026 RFS as held-out reveal
- All ingested demo data restricted to data available on or before 2026-05-03

Fallback data:

- Pre-vetted high-value candidate
- Pre-vetted killed candidate
- Pre-vetted "ahead of YC" excess candidate
- Pre-rendered opportunity brief
- Recorded fallback video

## Success Criteria

The demo succeeds if:

1. The audience sees at least three distinct state changes per data drop.
2. At least one weak candidate is visibly killed.
3. At least one high-value candidate survives Challenger after dossier completion.
4. Precision/recall improves across data stages.
5. At least one excess prediction is defensible with real-world signals.
6. The judge-persona coda produces at least one interesting personalized candidate.
7. The final screen is an opportunity brief, not a raw list of ideas.

## Metrics To Capture During Dry Runs

Capture these numbers for the pitch and post-demo discussion:

- Time from corpus drop to first candidate
- Time from high-value candidate to dossier queued
- Time from dossier completion to confidence update
- Number of candidates generated
- Number of candidates killed
- Number of candidates merged
- Number of dossier-backed candidates
- Number of opportunity briefs produced
- Number of candidates rated worth exploring by humans
- Estimated manual research time replaced per brief

## Rehearsal Checklist

Before demo:

- Preload corpora and confirm each bundle can be dropped independently.
- Confirm benchmark reveal is hidden until the reveal step.
- Confirm CAR ticket panel shows pending, running, and complete states.
- Confirm at least one dossier can complete on demo timing.
- Confirm the diff feed receives and displays events in order.
- Confirm candidate lifecycle statuses render clearly.
- Confirm opportunity brief view opens from a surviving candidate.
- Confirm fallback video is ready.
- Confirm a full re-eval fallback button exists if dirty-set re-eval fails.

During demo:

- Narrate decisions, not architecture.
- Say "candidate" or "opportunity" more than "agent."
- Point out killed candidates as value.
- Point out source traces before confidence numbers.
- End on the opportunity brief.

## Open Decisions

- Exact judge persona and interest document
- Exact pre-vetted "ahead of YC" candidates
- Opportunity brief visual layout
- Whether the brief export is Markdown-only or visible in the web UI
- Manual scoring rubric for "worth exploring"
- Pricing anchor for post-demo customer conversations
