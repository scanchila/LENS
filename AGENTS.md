# LENS Agent Instructions

LENS is a multi-agent problem-discovery system for turning messy source material into evidence-backed opportunity briefs. Treat it as a decision-support product, not an idea generator. The most important product qualities are provenance, adversarial review, clear assumptions, and the ability to kill weak candidates early.

These instructions apply to the repository root unless a more specific instruction file overrides them.

## Product Principles

- Preserve the core thesis: LENS should surface non-obvious but grounded opportunities from weak signals across corpora, not produce generic brainstorm lists.
- Optimize for user trust. Every candidate, score, status change, and recommendation should be explainable from source traces, lens attribution, and review history.
- Treat killed or downgraded candidates as first-class outcomes. A system that saves validation time by rejecting weak claims is working.
- Keep workflows centered on investigation: corpus selection, agent runs, candidate ranking, evidence dossiers, contradiction notes, and next validation steps.
- Avoid hiding uncertainty. Prefer explicit confidence, missing evidence, open assumptions, and challenger findings over polished but unsupported conclusions.

## Architecture Decisions

- The app is a full-stack system with a FastAPI backend, SQLModel/Alembic persistence, a React/TypeScript/Vite frontend, and Docker Compose orchestration.
- Postgres is the source of truth. Use relational tables for durable application state, pgvector for semantic retrieval, Apache AGE for graph-shaped claim/source/candidate relationships, and MinIO for raw object storage.
- Keep the agent runtime framework-agnostic. Orchestration code should depend on shared agent, tool, run, and transcript abstractions; provider or framework details belong in adapters.
- Maintain adapter parity. SDK-backed and direct-provider adapters should expose equivalent behavior for tools, transcripts, cost accounting, budget caps, and failure handling.
- Separate fast interactive orchestration from slow evidence gathering. Live runs should remain responsive; long-running dossier work should be queued, resumable, auditable, and ingestible as structured evidence.
- Generated frontend API clients are the boundary between backend OpenAPI contracts and UI code. Regenerate clients after backend schema changes instead of hand-writing duplicate request types.
- Database changes belong in migrations. Do not rely on implicit schema creation or local-only state for behavior that must survive deployment.
- Local research corpora, CAR hub state, generated reports, secrets, and runtime artifacts are not application source. Do not modify or commit them unless the task explicitly targets them.

## Production-Grade Code Guidelines

- Make changes that are small, coherent, and aligned with existing architecture. Avoid broad rewrites unless the task requires them.
- Prefer typed, explicit boundaries: Pydantic/SQLModel models on the backend, TypeScript types and generated OpenAPI clients on the frontend, JSON-schema tool inputs for agents.
- Validate inputs at the edge. Reject malformed IDs, unsafe uploads, invalid pagination, unsupported tool names, and impossible run states before they reach core logic.
- Model failures deliberately. Use clear domain errors, HTTP status codes, retry boundaries, and user-visible states instead of swallowing exceptions or returning ambiguous success.
- Keep operations idempotent where retries are plausible: ingestion, migrations, dossier import, background jobs, agent run finalization, and external API callbacks.
- Use transactions for multi-step persistence changes. Do not persist partial candidate/evidence/run state unless it is explicitly modeled as partial.
- Never log secrets, raw access tokens, API keys, private corpus contents, or full provider payloads that may contain sensitive user data. Redact aggressively.
- Track cost, model, latency, tool calls, and run metadata for agent work. Budget caps and audit trails are product requirements, not optional telemetry.
- Keep provider-specific behavior behind adapters. Do not leak Anthropic SDK types, direct Messages API details, or future framework-specific state into orchestration or tool code.
- Tools should be deterministic where possible, have narrow permissions, return structured metadata, and avoid hidden side effects.
- Prefer boring dependencies already in the stack. Add new libraries only when they replace meaningful complexity or provide a proven domain capability.
- Keep frontend state server-driven where practical. TanStack Query should own remote state; local component state should be limited to UI concerns and in-progress form interactions.
- Build operational UI, not marketing UI. Prioritize dense, scannable investigation views, accessible controls, visible status changes, and clear recovery from loading/error/empty states.
- Preserve accessibility basics: semantic elements, keyboard navigation, focus states, labels, readable contrast, and no text overlap on responsive layouts.
- Treat generated code as generated. Do not manually edit generated clients or route artifacts unless the generator itself is the target.
- Keep comments sparse and useful. Explain non-obvious tradeoffs, invariants, and provider quirks; do not narrate straightforward code.

## Testing And Verification

- Match tests to risk. Unit-test pure domain logic, adapter/tool contracts, permission checks, ingestion transforms, and scoring. Integration-test persistence, migrations, and API contracts. Use Playwright for critical user workflows.
- When changing backend behavior, run the focused pytest target first, then broader tests when the change touches shared contracts.
- When changing frontend behavior, run type checking/build and the relevant browser tests. Verify responsive layouts for workflows that users will inspect repeatedly.
- When changing OpenAPI schemas, regenerate the frontend client and verify the UI compiles against the generated types.
- When changing agent adapters or tools, include parity or contract checks that prove transcript shape, tool calls, cost accounting, and error paths remain stable.
- When changing storage, verify migrations from an existing database state, not only a fresh database.
- Do not mark work complete if tests could not run. State exactly what was and was not verified.

## Security And Data Handling

- Treat uploaded corpora and generated dossiers as private customer data.
- Keep secrets in environment configuration, never in source or test fixtures.
- Sanitize filenames, content types, object keys, and any text rendered back into the UI.
- Enforce authorization on every user, corpus, run, candidate, and dossier access path. Avoid relying on frontend filtering for security.
- Prefer least privilege for tools, storage clients, service credentials, and background workers.
- Make destructive actions explicit, audited, and reversible where possible.

## Collaboration Rules For Agents

- Read the existing implementation before changing architecture. Follow local patterns unless there is a concrete reason to improve them.
- Respect a dirty worktree. Do not revert or overwrite changes you did not make.
- Keep documentation in sync with behavior when changing commands, architecture, setup, or product semantics.
- Avoid committing local state, generated reports, secret files, dependency caches, or temporary experiments.
- If a request is ambiguous, make the smallest reasonable assumption that preserves the product architecture and explain it in the final response.
