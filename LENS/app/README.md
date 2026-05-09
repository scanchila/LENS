# `problem_finder` — application

Multi-agent problem-discovery system. Architectural rationale lives one level up in `../IMPLEMENTATION_PLAN.md`. This README is a quick map of the codebase.

The repository was bootstrapped from [`fastapi/full-stack-fastapi-template`](https://github.com/fastapi/full-stack-fastapi-template) on 2026-05-05; the example items CRUD has been stripped, and `problem_finder`-specific scaffolding has been layered on top.

## Stack

- **Backend:** FastAPI + SQLModel + Alembic (Python 3.10+, managed by uv)
- **Frontend:** React + TypeScript + Vite + Chakra UI (kept from the template; trimmed of items CRUD)
- **Database:** Custom Postgres 16 image bundling [pgvector](https://github.com/pgvector/pgvector) and [Apache AGE](https://age.apache.org/) → relational + vector + graph in one DB
- **Object storage:** [MinIO](https://min.io/) (S3-compatible, local) for raw user uploads
- **LLM providers:** Anthropic via both `claude-agent-sdk` and direct `anthropic` Messages API client
- **Orchestration:** Docker Compose (local dev); Traefik (production)

## Layout

```
app/
├── backend/                                Python service (FastAPI + agent runtime)
│   ├── app/
│   │   ├── agents/                         Agent runtime (framework-agnostic core)
│   │   │   ├── types.py                    Pydantic models for tools, agents, runs
│   │   │   ├── tool.py                     Tool ABC
│   │   │   ├── framework.py                AgentFramework ABC + FrameworkRegistry
│   │   │   ├── adapters/                   Concrete framework adapters
│   │   │   │   ├── claude_sdk.py           Wraps claude-agent-sdk           (stub)
│   │   │   │   └── direct_anthropic.py     Hand-rolled tool-use loop        (stub)
│   │   │   ├── tools/                      Concrete Tool implementations    (pending)
│   │   │   ├── lenses/                     Per-lens AgentDefinitions
│   │   │   │   └── cross_domain_transfer.py  First lens — proposer agent
│   │   │   └── data/
│   │   │       └── catalog_seed.json       8 seed CS/AI principles
│   │   ├── alembic/versions/
│   │   │   └── a1b2c3d4e5f6_…_extensions_and_drop_item.py    pgvector + AGE init
│   │   ├── api/                            FastAPI routes (auth, users, utils, private)
│   │   ├── core/                           Config, DB, security
│   │   ├── crud.py                         User CRUD only
│   │   ├── models.py                       User model only
│   │   └── main.py                         FastAPI app entry
│   ├── tests/                              pytest tests (item-related tests removed)
│   ├── pyproject.toml                      Adds pgvector, boto3, anthropic,
│   │                                       claude-agent-sdk, tiktoken, pypdf,
│   │                                       trafilatura
│   └── Dockerfile
├── frontend/                               React + TS UI (item routes/components removed)
├── postgres-extensions/
│   ├── Dockerfile                          Postgres 16 + pgvector + Apache AGE
│   └── init-extensions.sh                  CREATE EXTENSION on first init
├── compose.yml                             Production compose (db / minio / backend / frontend)
├── compose.override.yml                    Local-dev overrides (ports exposed)
├── .env                                    Local secrets (replace `changethis`)
└── README.md                               (this file)
```

## What Phase 0 has shipped

| Layer | Status | Notes |
|---|---|---|
| Repo scaffold (FastAPI template) | ✅ done | Items CRUD stripped, frontend item routes removed |
| Custom Postgres image (pgvector + AGE) | ✅ done | `postgres-extensions/Dockerfile` |
| MinIO service in compose | ✅ done | Console on `:9001`, S3 API on `:9000` |
| Alembic migration for extensions + graph | ✅ done | `a1b2c3d4e5f6` — drops `item`, creates extensions, creates `problem_finder` AGE graph |
| Backend dependencies | ✅ done | `pyproject.toml` updated |
| Core agent framework types | ✅ done | `agents/types.py`, `tool.py`, `framework.py` |
| FrameworkRegistry | ✅ done | Per-agent / per-role / default precedence |
| Adapter scaffolding | ✅ done | `ClaudeAgentSDKAdapter`, `DirectAnthropicAdapter` (interfaces only) |
| Adapter implementations | ✅ done | Both `DirectAnthropicAdapter.run` and `ClaudeAgentSDKAdapter.run` implemented |
| Pricing table | ✅ done | `agents/pricing.py` — per-model token rates for cost computation |
| `echo`, `note`, `ask_user` tools | ✅ done | `agents/tools/{echo,note,ask_user}.py` |
| `search_user_corpus` tool | ⏳ pending | pgvector + Postgres FTS hybrid (Phase 1) |
| Catalog seed | ✅ done | 8 principles in `agents/data/catalog_seed.json` |
| Catalog loader (JSON → Postgres + AGE) | ⏳ pending | (Phase 1) |
| Cross-domain proposer agent definition | ✅ done | `agents/lenses/cross_domain_transfer.py` |
| Adapter parity smoke test | ✅ done | `backend/scripts/phase0_smoke.py` — runs same agent through both adapters |
| YC RFS Spring 2026 backtest corpus | ⏳ pending | Cutoff 2026-02-05 (Phase 1) |
| YC end-to-end backtest | ⏳ pending | (Phase 1) |
| Web UI (upload + run + view) | ⏳ pending | Trim React frontend, add 3 screens (Phase 1) |

All 51 Python files in `backend/app/` and `backend/scripts/` pass `ast.parse`. The adapter parity smoke test exercises both adapters end-to-end against the real Anthropic API (requires `ANTHROPIC_API_KEY`).

### Running the adapter parity smoke test

```bash
cd app/backend
ANTHROPIC_API_KEY=sk-... python -m scripts.phase0_smoke

# Optional: pin a different model (default is claude-haiku-4-5 — cheapest)
PHASE0_SMOKE_MODEL=claude-sonnet-4-6 \
  ANTHROPIC_API_KEY=sk-... \
  python -m scripts.phase0_smoke
```

The smoke test runs the same trivial agent (one `echo` call + one `note` call) through both adapters and prints a side-by-side cost / tool-call / final-message comparison. Tool-set parity is asserted; cost may differ because the SDK reports authoritative cost from the `ResultMessage`, while the direct adapter computes from token counts.

## Local development (when adapters land)

```bash
# 1. Set required env vars in .env (replace 'changethis')
#    - ANTHROPIC_API_KEY
#    - POSTGRES_PASSWORD
#    - SECRET_KEY
#    - FIRST_SUPERUSER_PASSWORD
#    - MINIO_ROOT_PASSWORD

# 2. Build the custom Postgres image and bring everything up
docker compose up --build

# 3. Migrations are run automatically by the prestart container.
#    Run manually only when iterating on a new migration:
docker compose exec backend alembic upgrade head

# Endpoints (local dev):
#   Frontend:     http://localhost:5173
#   Backend docs: http://localhost:8000/docs
#   MinIO:        http://localhost:9001 (login with MINIO_ROOT_USER/PASSWORD)
#   Adminer:      http://localhost:8080
```

## What's next (next session, in priority order)

1. Implement `ClaudeAgentSDKAdapter.run`. Smallest body that satisfies the interface end-to-end against a trivial echo tool.
2. Implement `DirectAnthropicAdapter.run`. Use it as a parity baseline against (1) — same agent + tools must produce equivalent outputs.
3. Implement `search_user_corpus` (pgvector hybrid), `note`, `ask_user`.
4. Catalog loader — read `catalog_seed.json`, INSERT into Postgres + AGE.
5. YC Spring-2026 backtest corpus assembly script with cutoff 2026-02-05.
6. End-to-end smoke test: orchestrator dispatches `cross_domain_proposer` against the YC corpus, surfaces ≥10 candidates with provenance, under budget.
7. Trim the React frontend: upload screen, run-session screen, results screen.
