# LENS Pitch

## One-line pitch

LENS helps venture teams find problem candidates in messy source material, trace the evidence, and reject weak opportunities before they waste validation time.

## 45-second pitch

Venture teams have plenty of ideas. The hard part is deciding which problems deserve time, interviews, and capital.

LENS is a multi-agent investigation system for opportunity discovery. It reads founder calls, papers, forums, market notes, and internal research, then turns weak signals into structured candidate problems. Each candidate names the actor, the gap, the evidence, the assumptions, and the next test.

The important part is review. LENS ranks candidates, then shows source traces, separates value from confidence, records contradictions, and uses Challenger and Skeptic agents to attack weak claims. A killed candidate is a useful result because it saves the team from chasing a shallow idea.

The first proof point is YC Requests for Startups prediction. LENS uses only pre-cutoff material, generates RFS-style problem areas, then compares them against the later YC list while scoring provenance quality and false positives.

## 2-minute pitch

Startup studios, venture builders, and thesis-driven investors make one expensive decision again and again: which problem should be validated next?

Most teams answer that with scattered research, partner intuition, analyst memos, and a lot of untracked judgment. The evidence trail disappears. Teams forget why a candidate looked promising, why it was killed, which assumptions were never tested, and which weak signals came from independent sources.

LENS makes that workflow explicit.

The core object is a candidate problem. A candidate problem says: this actor has this gap, the gap matters for these reasons, these sources support it, these sources weaken it, and this is the validation path. That structure lets the system rank candidates without pretending that a score is truth.

The method combines decision theory and adversarial review. Multi-attribute utility handles tradeoffs like scale, urgency, tractability, neglectedness, and fit. Evidence confidence stays separate, so a large market with thin evidence still looks risky. Argument theory gives the system a place to store grounds, warrants, rebuttals, and missing support.

The architecture follows the product logic. Postgres is the source of truth for runs, scores, events, and lifecycle state. pgvector supports semantic retrieval. Apache AGE stores the claim-source-candidate graph, so reviewers can ask which sources support a candidate, which claims are contradicted, and which candidates share evidence. MinIO stores raw uploads. Fast live agents handle the investigation board, while deeper evidence work runs in the background as dossiers.

The user works from a board. Candidates appear, move, merge, get challenged, and sometimes die. Surviving candidates become opportunity briefs with traceable evidence and a clear next validation step.

The first benchmark is YC RFS. We feed LENS only material available before a YC request list was published, ask it to produce candidate problem areas, then measure matches, misses, unsupported predictions, and evidence quality. The stronger test is whether the system can produce excess predictions that are still grounded enough for a serious reviewer to inspect.

LENS wins if a reviewer can explain why one candidate survived, why another died, and what evidence would reverse either call.

### Problem

Opportunity selection is expensive, repeated, and poorly instrumented. Teams chase ideas with missing evidence, lose the trail behind earlier decisions, and spend validation time on candidates that should have died earlier.

### Product

LENS turns messy source material into evidence-backed candidate problems. It extracts signals, links claims to source traces, ranks candidates, attacks weak assumptions, and produces briefs with the next validation step.

### Why it is different

LENS treats killed candidates as output. It separates value from confidence, keeps provenance visible, and records adversarial review instead of hiding uncertainty behind a polished recommendation.

### Architecture

Fast agent orchestration powers the live board. Long-running dossier work runs in the background. Postgres stores state, pgvector retrieves source material, Apache AGE stores claim provenance, and MinIO keeps raw uploads.

### First proof

YC RFS prediction gives a clean benchmark: use pre-cutoff material, predict candidate problem areas, reveal the held-out YC list, and score matches, misses, excess predictions, and provenance quality.

### Closing line

LENS is the investigation layer for teams that need better problem selection before they commit people, interviews, and capital.
