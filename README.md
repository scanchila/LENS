# LENS

LENS is a multi-agent problem-discovery system for finding non-obvious, grounded, actionable opportunities from messy source material.

The name expands to **Latent Evidence and Need Scanner**. The core idea is that important problems often show up first as weak signals scattered across research papers, founder conversations, forums, technical shifts, and adjacent domains. LENS applies several reasoning lenses to those signals, challenges the resulting candidates, and builds a provenance trail so users can see why a problem is worth attention.

The product thesis is deliberately narrower than "AI idea generation": LENS helps venture builders, startup studios, and thesis-driven investors turn messy public and private signals into evidence-backed opportunity briefs. The user still makes the judgment call; LENS compresses the research loop, exposes weak assumptions, and helps decide which problems deserve validation time.

This repository is currently a hackathon-stage implementation. The code is real, but the product surface is still moving quickly.

## What LENS Does

LENS is designed to answer questions like:

- What problems are emerging before they become obvious?
- Which opportunities are supported by evidence across independent sources?
- Which candidate problems collapse under adversarial review?
- Which ideas are merely interesting, and which are grounded enough to pursue?

The first benchmark domain is **YC Requests for Startups prediction**. YC periodically publishes areas it wants founders to pursue. LENS uses only pre-cutoff public material, generates RFS-style predictions, and scores precision, recall, excess predictions, and provenance quality against the later published list.

## Theoretical Frame

LENS treats opportunity discovery as an evidence-ranking and falsification workflow.

The basic unit is a **candidate problem**: a hypothesis that a specific actor experiences a costly gap between a current state and a desired state, and that the gap may be tractable, neglected, non-obvious, and worth validating now. Candidates are not accepted as opportunities until they survive source tracing, scoring, adversarial review, and explicit assumption checks.

The local research corpus grounds this framing in seven source traditions:

- Hamming on important problems, prepared minds, and plausible attacks
- Paul Graham on organic startup ideas, urgent users, and noticing gaps
- 80,000 Hours on scale, neglectedness, solvability, and fit
- Rittel and Webber on wicked problems and unstable formulations
- Lehman and Stanley on novelty search and deceptive objectives
- Lakatos on progressive versus degenerating research programs
- DARPA's Heilmeier catechism and Wing's computational thinking as proposal-review and cross-domain-transfer scaffolds

See [LENS theoretical framework](LENS/THEORY.md) for formal definitions of sources, traces, claims, signals, candidate problems, scoring components, candidate lifecycle states, lenses, opportunity briefs, and benchmark metrics.

The scoring model keeps LENS's own candidate-problem definition primary. Its deeper base is multi-attribute utility theory, value-focused thinking, Bayesian value of information, exploration/exploitation, entrepreneurial opportunity theory, creativity assessment, and argument/evidence structure. Applied models such as ITN/SNT, Outcome-Driven Innovation, GRADE, RICE, CHNRI, TRL, and the Heilmeier Catechism are used only as operational adapters.

## Customer and User Thesis

The primary customer hypothesis is a **startup studio or venture builder**: a partner, studio lead, or head of incubation with budget responsibility for deciding which opportunities deserve team and capital allocation.

The primary user is a **venture analyst, founder-in-residence, EIR, or thesis researcher** who operates the investigation board, uploads or selects corpora, reviews evidence, challenges candidates, and turns surviving candidates into briefs for partner review.

Secondary customer hypotheses are early-stage VC funds, corporate innovation teams, accelerators, and solo founders. They are plausible, but the startup studio wedge is the cleanest because opportunity selection is repeated, expensive, and close to the organization's core workflow.

LENS is valuable if it is perceived as a decision-support system that reduces wasted exploration and improves thesis quality. It is weak if it is perceived as a polished AI brainstormer.

The core paid artifacts are:

- Evidence-backed opportunity briefs
- Candidate status changes: speculative, supported, challenged, killed, or ready to validate
- Source traces, contradiction notes, and adversarial review history
- Recommended next validation steps
- A reusable private corpus that compounds over repeated runs

## Product Shape

The intended user experience is a streaming investigation board:

1. A user uploads or selects a corpus.
2. The orchestrator chooses relevant lenses and dispatches proposer agents.
3. Candidate problems appear with confidence, source traces, and lens attribution.
4. High-value candidates trigger deeper evidence dossiers.
5. Challenger and Skeptic agents attack weak claims and provenance gaps.
6. A synthesizer merges duplicates and surfaces reinforced opportunities.
7. The user sees a ranked set of problem candidates plus the reasoning path.
8. Surviving candidates can be exported as opportunity briefs with open assumptions and next validation steps.

The demo version emphasizes live state changes: candidates added, scores updated, candidates killed, dossiers completed, and evidence graphs becoming available.

The paid workflow should emphasize killed candidates as much as promising ones. A candidate that dies early saves founder, analyst, and partner time; that is part of the ROI.

## Architecture

LENS separates fast reasoning from slow evidence gathering.

### Real-Time Orchestration

The in-process agent runtime handles interactive work:

- Orchestrator
- Lens-Proposers
- Challenger
- Skeptic
- Synthesizer
- Critic / Judge
- User Liaison

The default framework target is Claude Agent SDK, with a direct Anthropic adapter as a parity baseline. The adapter layer is intentionally framework-agnostic so later phases can test PI, LangGraph, or other runtimes without rewriting tools and orchestration logic.

### Deep Evidence Work

CAR, codex-autorunner, is used as a complementary subsystem, not as the real-time orchestrator.

When a candidate crosses a value threshold, LENS can emit an `evidence_dossier` ticket. CAR dispatches a long-running coding/research agent such as Hermes or Codex to gather web, academic, and messy-source evidence. A dossier ingest worker then parses the structured Markdown dossier into Postgres and Apache AGE.

This split keeps the live UI responsive while still allowing slow, multi-step investigations to run in the background.

### Storage

The storage plan is Postgres-centric:

- Postgres for relational state, sessions, runs, users, and calibration data
- pgvector for semantic search over uploaded and curated documents
- Apache AGE for graph-shaped queries over principles, sources, claims, and candidates
- MinIO for raw uploads and object storage

Graph queries matter because the most useful questions are relational:

- Which sources support both candidate A and candidate B?
- Which claims are unsupported or contradicted?
- Which CS/AI principles are structurally analogous to this domain?
- Which problems share a subproblem or dependency chain?

## Current Status

The current codebase is a Phase 0 scaffold.

Implemented or scaffolded:

- FastAPI backend, React frontend, Docker Compose stack
- Auth/user scaffold from the FastAPI full-stack template
- Custom Postgres image with pgvector and Apache AGE
- MinIO service for local object storage
- Alembic migration for database extensions and initial graph setup
- Agent runtime interfaces: tools, agent definitions, framework adapters, run outputs
- Claude Agent SDK adapter
- Direct Anthropic adapter
- Basic tools: `echo`, `note`, `ask_user`
- Pricing/cost tracking scaffolding
- Cross-domain transfer proposer definition
- Seed catalog of CS/AI principles
- Phase 0 adapter parity smoke script

Still in progress:

- User corpus ingestion with chunking and embeddings
- Hybrid `search_user_corpus` over pgvector and Postgres full-text search
- Curated catalog loader into Postgres and AGE
- Contradiction and distance-from-focus lenses
- Challenger, Skeptic, Synthesizer, and Critic runtime integration
- CAR evidence dossier ticket template and ingest worker
- Streaming demo board and diff feed
- YC RFS benchmark fixtures and scoring UI

## Repository Layout

```text
.
├── README.md                     Project overview
├── LENS/
│   ├── THEORY.md                  Formal definitions and source-grounded theory
│   ├── IMPLEMENTATION_PLAN.md     Detailed architecture and phased plan
│   ├── DEMO_PLAN.md               Demo narrative, runbook, and product thesis
│   ├── app/                       Full-stack application
│   │   ├── README.md              App-specific map and Phase 0 status
│   │   ├── backend/               FastAPI service and agent runtime
│   │   ├── frontend/              React + TypeScript frontend
│   │   ├── postgres-extensions/   Postgres 16 + pgvector + Apache AGE image
│   │   ├── compose.yml            Production-oriented compose file
│   │   └── compose.override.yml   Local development overrides
│   └── research/                  Local research corpus, intentionally ignored
└── car-hub/                       Local CAR hub state, intentionally ignored
```

The GitHub repository intentionally excludes local runtime state, research corpus files, `.env` files, the CAR hub, and local virtual environments.

## Local Development

Requirements:

- Docker
- Python 3.10+
- uv for backend Python dependency management
- Bun or Node.js for frontend work
- Anthropic API key for real agent adapter runs

Start the full local stack:

```bash
cd LENS/app
docker compose up --build
```

Local URLs:

- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- Backend docs: http://localhost:8000/docs
- Adminer: http://localhost:8080
- MinIO console: http://localhost:9001
- Mailcatcher: http://localhost:1080

For watch-mode development:

```bash
cd LENS/app
docker compose watch
```

Run backend tests:

```bash
cd LENS/app/backend
bash ./scripts/test.sh
```

Run the Phase 0 adapter parity smoke test:

```bash
cd LENS/app/backend
ANTHROPIC_API_KEY=sk-... python -m scripts.phase0_smoke
```

Use a different smoke-test model:

```bash
cd LENS/app/backend
PHASE0_SMOKE_MODEL=claude-sonnet-4-6 \
  ANTHROPIC_API_KEY=sk-... \
  python -m scripts.phase0_smoke
```

## Configuration

Local secrets live in `LENS/app/.env`, which is not committed.

Important settings include:

- `ANTHROPIC_API_KEY`
- `POSTGRES_PASSWORD`
- `SECRET_KEY`
- `FIRST_SUPERUSER`
- `FIRST_SUPERUSER_PASSWORD`
- `MINIO_ROOT_USER`
- `MINIO_ROOT_PASSWORD`

The compose files also use image, domain, CORS, SMTP, and deployment settings inherited from the FastAPI full-stack template.

## Benchmark Direction

The first rigorous evaluation target is YC RFS prediction.

LENS produces a predicted list of startup opportunity areas using only material available before a cutoff date. Outputs are then evaluated against the actual YC list after publication:

- Direct matches
- Adjacent matches
- Misses
- Precision
- Recall
- Excess predictions
- Provenance quality

The interesting case is not only matching YC. It is also finding defensible "ahead of YC" opportunities: predictions absent from the published list but supported by real signals.

## Roadmap

Near-term:

- Finish corpus ingestion
- Implement hybrid user-corpus search
- Load the CS/AI principle catalog into Postgres and AGE
- Wire the cross-domain lens into an end-to-end run
- Build the minimal upload, run, and results screens
- Add provenance display for candidate problems

Hackathon demo:

- Streaming candidate board
- Diff feed driven by backend state changes
- CAR side panel showing evidence dossier tickets
- YC RFS prediction benchmark
- Challenger pass that visibly kills weak candidates
- Dossier-backed candidates that survive adversarial review

Later:

- More lenses
- Stronger graph queries
- Framework swap tests
- Multi-tenant product surface
- Better observability and cost controls
- Public benchmark reports

## Core Documents

- [Implementation plan](LENS/IMPLEMENTATION_PLAN.md)
- [Application README](LENS/app/README.md)
- [Development guide](LENS/app/development.md)
- [Backend guide](LENS/app/backend/README.md)
- [Frontend guide](LENS/app/frontend/README.md)

## Working Principles

- Evidence before polish.
- Keep agent roles separate and inspectable.
- Treat provenance as a first-class product feature.
- Prefer graph-shaped explanations over opaque rankings.
- Use CAR for slow, durable evidence work, not for the real-time orchestration loop.
- Keep the benchmark honest by enforcing cutoff dates and preserving excess predictions for review.
