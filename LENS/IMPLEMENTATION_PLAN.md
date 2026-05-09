# `problem_finder` Implementation Plan

A buildable plan for the multi-agent problem-discovery system. The plan is structured as: framework decision → multi-agent role taxonomy → tool catalog → storage layer → full-loop architecture → framework abstraction interface → phased build plan → framework comparison.

The architectural commitments behind this plan come from earlier design conversations and are encoded in `~/.claude/projects/.../memory/`. Re-read those before substantial revisions.

---

## 1. Framework deep-dive — what we have to work with

### Claude Agent SDK (`claude-agent-sdk`)

Anthropic's official agent SDK in Python and TypeScript. Architecturally sound for our pattern, with several features that map directly to what we need:

- **Sub-agents** (via the `Agent` tool / `AgentDefinition`) have isolated context, tool restrictions, separate system prompts, dynamic model overrides. Multiple sub-agents run concurrently. Parent receives only the final message — intermediate scratch doesn't accumulate. This is the proposer/challenger/synthesizer pattern, native.
- **Tools** via `@tool` decorator wrapping into in-process MCP servers. JSON-schema validation automatic. External MCP servers for cross-process / shared / authenticated tools.
- **Hooks** (`PreToolUse`, `PostToolUse`, `SubagentStart/Stop`, `PreCompact`, etc.) — usable for cost tracking, validation, audit logging, sub-agent fan-out monitoring.
- **Sessions**: capture `session_id`, resume, fork. Local JSONL transcripts on disk.
- **Prompt caching**: automatic, 5-minute TTL default, 1-hour configurable. Critical for multi-agent runs that re-read large user corpora.
- **Cost tracking**: `total_cost_usd` per call, `model_usage` per-model breakdown. No hard budget cap (we build that ourselves).

**Limitations to design around:**
- No nested sub-agents (sub-agent can't spawn sub-sub-agents). Our orchestration is therefore one level deep.
- No central agent coordinator / scheduler / message router — we write that.
- No built-in debate framework — we encode it.
- No distributed session store — fine for MVP; address later.
- No retry semantics for sub-agent timeouts.

### PI / `pi-mono`

Layered TypeScript toolkit (Mario Zechner). Packages:
- `pi-ai`: unified LLM API across Anthropic / OpenAI / Google / xAI / Groq / Cerebras / OpenRouter / any OpenAI-compatible endpoint. Streaming, tool calls (TypeBox schemas), thinking-tokens, cross-provider context handoffs, token+cost tracking.
- `pi-agent-core`: thin wrapper turning pi-ai into an agent loop.
- `pi-coding-agent`: full coding-agent runtime with file tools, JSONL session persistence, context compaction, skills, extension system. Four run modes: interactive, print/JSON, RPC, SDK.
- `pi-tui`: terminal UI library (differential rendering, autocomplete, spinners).

PI's strength is **provider neutrality**. If we want the system to run against Claude, GPT, Gemini, or local models with minimal change, PI's abstraction is the closest off-the-shelf fit. Its weakness is youth — smaller community, fewer production references than Claude Agent SDK or LangGraph.

### LangGraph

LangChain's stateful graph-based agent framework. Models agents as directed graphs with typed state, conditional edges, checkpointing. Built-in patterns for multi-agent debate, supervisor, swarm. LangSmith provides observability. Strongest production maturity of any agent framework in 2026.

For our use case, LangGraph maps onto the orchestration layer cleanly — the agent loop is a state machine over agent transitions. Cost: more conceptual overhead (state schemas, node typing) for the small win in built-in checkpointing.

### Microsoft Agent Framework / AutoGen v0.7.x / AG2

AutoGen split in 2026 into three forks. Microsoft Agent Framework is the production-grade successor (merging AutoGen orchestration with Semantic Kernel's enterprise stack). AutoGen v0.7.x is maintenance. AG2 is community-led continuation. Strong for debate / group-chat patterns specifically; less control over individual agent definition than Claude SDK or LangGraph.

### Direct (Anthropic SDK + hand-rolled tool loop)

The lowest-level option — implement the agent loop ourselves on top of the Anthropic Messages API. Full control, no abstraction overhead, but reinvents what every framework above gives us. Useful as a *fallback* abstraction so we can verify our wrapper layer works in the absence of any framework.

### CAR (codex-autorunner)

**Not a competitor to the above; a complementary subsystem at a different layer.** CAR is a meta-harness for ACP-compatible coding agents (Codex, Hermes, OpenCode). Tickets in markdown+frontmatter are the control plane; agents grind through them sequentially as walk-away background work, with notifications via Telegram/Discord on stuck tickets. Filesystem state is source of truth. Native targets: `ticket_flow` (deterministic multi-step delivery) and `pma` (durable conversation threads).

**Where CAR does NOT fit:** the in-process orchestration runtime. Lens-Proposers, Challenger, Synthesizer, Critic need real-time concurrent execution feeding a streaming UI; CAR's sequential walk-away model conflicts with that.

**Where CAR DOES fit:**
1. **Runtime deep-search subsystem.** When the Orchestrator surfaces a high-V̂ candidate, it emits an `evidence_dossier` CAR ticket. The configured ACP agent (Hermes preferred — durable threads carry context across related investigations) grinds through web/academic/messy sources over minutes, producing a structured Markdown dossier on disk. A `dossier_ingest_worker` parses the dossier and writes evidence relations into Postgres+AGE. This replaces the in-process Evidence Gatherer agent role from the original plan.
2. **Build-time agent harness.** During implementation, CAR drives Codex/Hermes through a ticket spine sourced from this plan. Free-running execution while the human focuses on prompt engineering, demo polish, and the visual layer.

The split exploits each tool's design center: Claude Agent SDK for fast in-process reasoning, CAR for slow multi-step external research, Postgres+AGE for the graph queries that compose them.

### Recommendation

**Default framework: Claude Agent SDK** (Python). Reasons:
1. Direct first-class support from Anthropic, the model provider this product will lean on heaviest
2. Sub-agent + tool primitives map cleanly to our role-separation pattern
3. Prompt caching automatic — critical for cost on repeated context across sub-agents
4. Hooks give us observability and cost-tracking insertion points

**Companion runtime subsystem: CAR + Hermes** for deep-search dossier work (see CAR section above). Not a framework swap; a different layer.

**Second framework (parity verification): PI**. Reasons:
1. Provider-neutral — proves the abstraction works across model families
2. TypeScript, so we exercise both language ecosystems
3. Smaller, simpler — easier to map our abstraction onto without framework opinions getting in the way

**Third option (later): LangGraph**, if we hit scale or observability limits with Claude Agent SDK.

---

## 2. Multi-agent role taxonomy

Eight roles. Not all instantiated at once — the orchestrator decides which to spin up per session.

| Role | Job | Tools (typical) | Model |
|---|---|---|---|
| **Orchestrator** | Top-level coordinator. Plans the run, dispatches sub-agents, decides stop conditions, presents results | All tools, but mostly invokes sub-agents | Opus 4.7 |
| **Lens-Proposer** | Applies one specific lens (cross-domain transfer, counterfactual, etc.). Generates candidate problems | `search_user_corpus`, `search_curated_catalog`, `search_academic`, `search_messy`, `note` | Sonnet 4.6 |
| **Evidence Gatherer** *(CAR-mediated; see §1 CAR subsection)* | Deep-retrieval specialist. Given a candidate, finds supporting/refuting evidence across all sources. **Implementation:** Orchestrator emits an `evidence_dossier` CAR ticket; Hermes runs the multi-step research; `dossier_ingest_worker` writes results into Postgres+AGE. Not an in-process Claude Agent SDK agent. | All search tools, `read_url` | Sonnet 4.6 (configured on Hermes side) |
| **Challenger** | Adversarial. Argues *against* each candidate. Surfaces weaknesses, hidden assumptions, counterexamples | `search_messy`, `search_academic`, `read_url` | Opus 4.7 (worth the cost — challenger quality is decisive) |
| **Skeptic** | Distinct from challenger. Checks groundedness — does every claim trace to a source? Hallucination audit | `inspect_provenance`, `search_user_corpus` | Haiku 4.5 (cheap, focused) |
| **Synthesizer** | Merges candidates across lenses. De-duplicates, identifies cross-lens reinforcements, ranks | `note`, `critique` (sub-agent dispatch) | Opus 4.7 |
| **Critic / Judge** | Scores final candidates against criteria: non-obviousness, groundedness, actionability, V̂/Ĉ confidence | `critique` template prompts | Sonnet 4.6 |
| **User Liaison** | Formulates clarifying / validating questions to the user. Presents results in NL | `ask_user` | Sonnet 4.6 |

**Model assignment rationale** is a per-role decision. The principle: spend Opus on roles where reasoning quality directly affects output quality (Orchestrator, Challenger, Synthesizer); use Sonnet on routine roles; use Haiku for narrow checking tasks.

**Adversarial structure:** Challenger + Skeptic are both adversarial but at different layers. Challenger contests the *claim* — "is this even a problem worth solving?". Skeptic contests the *evidence* — "does the system's reasoning trace to its sources?". Running both is cheap insurance against a class of errors single-pass agents make.

---

## 3. Tool catalog

Tools are framework-agnostic. Each implements a clean async interface; the framework adapter exposes them in framework-native form (in-process MCP for Claude SDK, TypeBox-schema function for PI, LangGraph node, etc.).

| Tool | Purpose | Implementation notes |
|---|---|---|
| `search_user_corpus` | Semantic + keyword search over user-uploaded documents | pgvector (semantic) + Postgres FTS (keyword). Returns ranked chunks with provenance |
| `search_curated_catalog` | Query the CS/AI principles catalog | Vector DB over catalog embeddings + graph DB traversal for related principles |
| `search_academic` | Semantic Scholar / OpenAlex / arXiv | API client; cached responses; structured citation metadata returned |
| `search_messy` | Web + targeted social/blog | Tavily or Exa for general web; PRAW for Reddit; HN Algolia API; RSS aggregation for niche blogs |
| `read_url` | Deep-fetch a specific URL | Headless browser (Playwright) for JS-heavy sites; trafilatura for clean extraction |
| `ask_user` | Pose a question to the user, wait for response | Mediated by orchestrator's UX layer |
| `note` | Persist intermediate finding to session memory | Append-only structured log per session |
| `critique` | Spawn a Critic sub-agent run on an in-progress output | Returns score + structured feedback |
| `inspect_provenance` | Trace claim → source map for an output | Reads the provenance ledger built up during the session |
| `queue_evidence_dossier` | Emit a CAR `evidence_dossier` ticket for a high-V̂ candidate | Writes a markdown ticket file into `.codex-autorunner/tickets/` per CAR's filesystem-as-truth contract; returns ticket id. Caller is typically the Orchestrator after Lens-Proposer + Synthesizer have produced a candidate above a confidence threshold. Async — does not block the main loop |
| `read_dossier` | Fetch a completed CAR dossier (Markdown + extracted graph relations) | Reads from disk by ticket id; only returns if ticket is `done: true`. Pairs with the `dossier_ingest_worker` which is responsible for AGE writes |

Each tool has:
- A NL `description` that the agent reads to decide when to use it
- A JSON schema for arguments
- An async handler
- Cost / latency tracking
- A retry policy

---

## 4. Storage layer

**Decision (2026-05-05):** unified Postgres-centric stack. Production-ready from day one rather than zero-config-local-first.

| Component | Choice | Stores |
|---|---|---|
| **Relational + Vector + Graph** | **Postgres + pgvector + Apache AGE** (one DB, three extensions) | Sessions, runs, transcripts, scoring history, calibration; user-doc embeddings, catalog embeddings, retrieved content; catalog principle relationships, provenance graph, problem-dependency graph |
| **Object store** | **MinIO** (S3-compatible, local Docker) | Raw user uploads (PDFs, docs, images) |
| **Cache** | Postgres-backed (initially); optionally Redis later | Deduplicated LLM calls, search results, embeddings |

**Why Apache AGE over Neo4j / Memgraph / Kuzu:**
- Top-Level Apache Project (since 2022); active development; production deployments cited in 2026
- Inherits Postgres ACID + MVCC + Postgres ecosystem (Alembic migrations, psycopg, etc.)
- OSI-licensed (Apache 2.0); no commercial licensing trap
- Single database for all three workloads — operational simplicity is large
- Cypher-style query support (openCypher subset)
- Trade: not as fast as Memgraph for pure graph workloads, but at our expected scale (catalog: thousands of nodes, not millions) AGE is well within its operating envelope

**Ruled out:**
- *Neo4j*: separate service to operate, license complexity, and we don't need its scale
- *Memgraph*: fast but BSL 1.1 (not OSI), ~$25k/yr commercial, documented stability issues
- *Kuzu*: acquired by Apple and archived October 2025 — abandonment risk

**Why graph storage matters here.** Once we have:
- A catalog of CS/AI principles with `parent`, `prerequisite`, `application_of`, `analog_of` edges
- A provenance graph (claim → source → support_relation)
- A problem-dependency graph (problem → sub-problem, problem → related-problem)

…some of the most valuable queries are graph-shaped: *"What principles are structurally analogous to X?"* / *"What sources support both claim A and claim B?"* / *"What problems share a sub-problem with this candidate?"* These aren't natively expressible in vector search. With AGE, both vector search and graph traversal happen in the same database, joinable via SQL.

---

## 5. Full-loop architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  USER SESSION                                                         │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │ INGESTION                                                        │  │
│  │   - Document parsing (PDF, MD, HTML, plain text)                  │  │
│  │   - Chunking (semantic, sliding-window)                           │  │
│  │   - Embedding (Voyage / OpenAI / local)                           │  │
│  │   - Indexing into Vector DB                                       │  │
│  │   - Entity + relation extraction → Graph DB                       │  │
│  └─────────────────────────────────────────────────────────────────┘  │
│                                ↓                                       │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │ ORCHESTRATOR (Claude Agent SDK; in-process; real-time)            │  │
│  │                                                                    │  │
│  │   Plans:                                                            │  │
│  │     - Which lenses to apply (default: all enabled, per-config)     │  │
│  │     - Resource budget (cost cap, time cap)                         │  │
│  │     - Whether to ask the user clarifying questions first            │  │
│  │                                                                    │  │
│  │   Dispatches in parallel:                                          │  │
│  │     ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐ │  │
│  │     │ Lens-Proposer:   │ │ Lens-Proposer:   │ │ Lens-Proposer:   │ │  │
│  │     │ Cross-domain     │ │ Counterfactual   │ │ Contradiction    │ │  │
│  │     │   transfer       │ │  perturbation    │ │  surfacing       │ │  │
│  │     └────────┬─────────┘ └────────┬─────────┘ └────────┬─────────┘ │  │
│  │              ↓                    ↓                    ↓           │  │
│  │           [N candidate problems with provenance per lens]            │  │
│  │                                  ↓                                     │  │
│  │     ┌──────────────────────────────────────────────────────────┐    │  │
│  │     │ Triage: candidates with V̂ ≥ threshold                      │    │  │
│  │     │   → tool: queue_evidence_dossier(candidate_id)             │    │  │
│  │     │   (async fan-out to CAR; main loop continues)               │    │  │
│  │     └────────────────────────────┬───────────────────────────────┘    │  │
│  │                                  ↓                                     │  │
│  │     ┌──────────────────────────────────────────────────────────┐    │  │
│  │     │ Challenger (per candidate)                                 │    │  │
│  │     │   Argues against; surfaces hidden assumptions               │    │  │
│  │     │   For dossiered candidates: reads AGE evidence subgraph     │    │  │
│  │     └────────────────────────────┬───────────────────────────────┘    │  │
│  │                                  ↓                                     │  │
│  │     ┌──────────────────────────────────────────────────────────┐    │  │
│  │     │ Skeptic (per candidate)                                    │    │  │
│  │     │   Provenance audit via AGE Cypher traversal                 │    │  │
│  │     └────────────────────────────┬───────────────────────────────┘    │  │
│  │                                  ↓                                     │  │
│  │     ┌──────────────────────────────────────────────────────────┐    │  │
│  │     │ Synthesizer                                                │    │  │
│  │     │   Cross-candidate AGE queries: "candidates sharing sources" │    │  │
│  │     │   Merge across lenses, dedupe, identify reinforcements      │    │  │
│  │     └────────────────────────────┬───────────────────────────────┘    │  │
│  │                                  ↓                                     │  │
│  │     ┌──────────────────────────────────────────────────────────┐    │  │
│  │     │ Critic / Judge                                             │    │  │
│  │     │   Score on: non-obviousness, groundedness, actionability,   │    │  │
│  │     │             V̂/Ĉ confidence (rewards dossier-grounded)        │    │  │
│  │     └────────────────────────────┬───────────────────────────────┘    │  │
│  │                                  ↓                                     │  │
│  │     ┌──────────────────────────────────────────────────────────┐    │  │
│  │     │ User Liaison                                               │    │  │
│  │     │   Present top K with provenance and dossier badges          │    │  │
│  │     │   Optionally ask clarifying questions                        │    │  │
│  │     └──────────────────────────────────────────────────────────┘    │  │
│  └─────────────────────────────────────────────────────────────────┘  │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │ CAR DEEP-SEARCH SUBSYSTEM (async; runs in parallel to orchestrator)│  │
│  │                                                                    │  │
│  │   .codex-autorunner/tickets/  ← queue_evidence_dossier writes here │  │
│  │              ↓                                                      │  │
│  │     ┌──────────────────────────────────────────────────────────┐  │  │
│  │     │ CAR engine picks ticket → dispatches to Hermes (ACP)       │  │  │
│  │     └────────────────────────────┬───────────────────────────────┘  │  │
│  │                                  ↓                                   │  │
│  │     ┌──────────────────────────────────────────────────────────┐  │  │
│  │     │ Hermes (durable thread per investigation domain)            │  │  │
│  │     │   Multi-step deep research:                                  │  │  │
│  │     │     - Tavily / web                                           │  │  │
│  │     │     - Semantic Scholar / OpenAlex / arXiv                    │  │  │
│  │     │     - Reddit / HN / niche blogs                              │  │  │
│  │     │     - read_url for deep fetch                                │  │  │
│  │     │   Output: dossiers/<ticket_id>.md (structured Markdown)      │  │  │
│  │     └────────────────────────────┬───────────────────────────────┘  │  │
│  │                                  ↓                                   │  │
│  │     ┌──────────────────────────────────────────────────────────┐  │  │
│  │     │ dossier_ingest_worker (watches tickets/*.md for done)      │  │  │
│  │     │   Parses dossier → writes to Postgres + AGE:                 │  │  │
│  │     │     - source nodes (URL, arxiv id, etc.)                     │  │  │
│  │     │     - claim → source `supports`/`refutes` edges              │  │  │
│  │     │     - candidate ←→ source edges                              │  │  │
│  │     │   Emits Postgres NOTIFY → triggers dirty-set re-eval         │  │  │
│  │     │   in the orchestrator (Challenger/Synth/Critic re-run on    │  │  │
│  │     │   affected candidates with the new evidence)                 │  │  │
│  │     └──────────────────────────────────────────────────────────┘  │  │
│  └─────────────────────────────────────────────────────────────────┘  │
│                                ↓                                       │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │ FEEDBACK LOOP                                                      │  │
│  │   User accept/reject/elaborate → updates:                         │  │
│  │     - Vector DB (added user content)                               │  │
│  │     - Graph DB (new relationships)                                 │  │
│  │     - Calibration data (was V̂, was Ĉ correct?)                     │  │
│  │     - Lens weights (which lens produced accepted candidates)        │  │
│  │     - Dossier reuse statistics (was the CAR investment worth it?)   │  │
│  └─────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 6. Framework abstraction interface

The interface that lets us swap Claude Agent SDK ↔ PI ↔ LangGraph ↔ direct-Anthropic without changing orchestrator or tool code.

### Core types

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

# ----- Tools -----

@dataclass
class ToolSpec:
    name: str                      # canonical name across frameworks
    description: str               # what the agent reads to decide use
    input_schema: dict             # JSON Schema for arguments
    output_schema: dict | None     # optional; for typed tool returns

class Tool(ABC):
    spec: ToolSpec

    @abstractmethod
    async def execute(self, args: dict, ctx: "ToolContext") -> "ToolResult":
        ...

@dataclass
class ToolContext:
    session_id: str
    parent_agent: str
    cost_so_far_usd: float
    storage: "StorageClients"

@dataclass
class ToolResult:
    content: str | list[dict]  # NL or structured
    is_error: bool = False
    metadata: dict = field(default_factory=dict)

# ----- Agents -----

@dataclass
class AgentDefinition:
    name: str                      # "cross_domain_proposer"
    role: str                      # "proposer" | "challenger" | "synthesizer" | ...
    system_prompt: str
    tool_names: list[str]          # subset of registered tools
    model: str                     # "claude-opus-4-7" | "gpt-5" | ...
    max_turns: int = 10
    temperature: float = 0.7
    context_strategy: Literal["fresh", "shared", "summarized"] = "fresh"

@dataclass
class AgentRunInput:
    initial_prompt: str
    shared_context: list[dict] = field(default_factory=list)  # for "shared" strategy
    metadata: dict = field(default_factory=dict)

@dataclass
class AgentRunOutput:
    final_message: str
    transcript: list[dict]
    tool_calls: list[dict]
    cost_usd: float
    duration_ms: int
    framework_metadata: dict       # framework-specific telemetry

# ----- Framework adapter -----

class AgentFramework(ABC):
    @abstractmethod
    async def run(
        self,
        agent: AgentDefinition,
        run_input: AgentRunInput,
        tools: list[Tool],
    ) -> AgentRunOutput: ...

    @abstractmethod
    async def health_check(self) -> bool: ...

# ----- Registry -----

class FrameworkRegistry:
    """Configurable per-agent framework selection."""

    def __init__(self):
        self._frameworks: dict[str, AgentFramework] = {}
        self._role_assignments: dict[str, str] = {}  # role → framework name

    def register(self, name: str, framework: AgentFramework): ...
    def assign(self, role: str, framework_name: str): ...
    def get(self, role: str) -> AgentFramework: ...
```

### Concrete adapter examples

```python
class ClaudeAgentSDKAdapter(AgentFramework):
    """Wraps anthropic-claude-agent-sdk."""

    async def run(self, agent, run_input, tools):
        from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions
        # Convert Tool list → in-process MCP server
        # Convert AgentDefinition → ClaudeAgentOptions
        # Run query, accumulate transcript and cost
        # Return AgentRunOutput

class PIAgentAdapter(AgentFramework):
    """Wraps pi-agent-core via subprocess or via Python bindings."""
    async def run(self, agent, run_input, tools):
        # Convert Tool list → TypeBox JSON schemas
        # Convert AgentDefinition → pi-ai system prompt + tool spec
        # Execute via pi-agent-core
        # Map output → AgentRunOutput

class DirectAnthropicAdapter(AgentFramework):
    """Hand-rolled tool-use loop on the Anthropic Messages API.
    Useful as a fallback and as a parity test."""
    async def run(self, agent, run_input, tools):
        # Standard tool-use loop with explicit budget tracking
```

### Configuration

```yaml
# problem_finder.yaml
default_framework: claude_agent_sdk

framework_assignments:
  orchestrator: claude_agent_sdk
  cross_domain_proposer: claude_agent_sdk
  challenger: claude_agent_sdk     # can swap to pi_agent for cross-vendor verification
  synthesizer: claude_agent_sdk

frameworks:
  claude_agent_sdk:
    api_key_env: ANTHROPIC_API_KEY
    default_model: claude-sonnet-4-6
    cache_ttl: 3600
  pi_agent:
    binary_path: /usr/local/bin/pi
    transport: rpc
  direct_anthropic:
    api_key_env: ANTHROPIC_API_KEY
```

---

## 7. Phased build plan

### Phase 0 — Foundation (ambitious scope) (target: ~1.5–2 weeks)

**Goal:** scaffolding + framework abstraction + storage + one full lens running end-to-end on the YC RFS prediction test.

**Scaffolding:**
- Clone [`fastapi/full-stack-fastapi-template`](https://github.com/fastapi/full-stack-fastapi-template); strip the example items CRUD; keep the auth/user model, Docker Compose, Alembic, pytest skeleton
- Add Postgres extensions: `pgvector`, Apache `AGE` (init via Alembic migration)
- Add `MinIO` service to docker-compose (S3-compatible local)
- Add a separate `agent-runner` service container for long-running agent loops
- Repo Python package layout (uv for deps); ESLint/Prettier kept from the React frontend

**Core code:**
- Define `Tool`, `AgentDefinition`, `AgentFramework`, `AgentRunOutput` interfaces (Section 6)
- Implement `ClaudeAgentSDKAdapter`
- Implement `DirectAnthropicAdapter` (parity baseline, also useful when Claude API has incidents)
- `FrameworkRegistry` with config-driven role assignment
- Cost tracking from day one; per-run budget cap (hard stop, not soft signal)

**Tools:**
- `search_user_corpus` (pgvector + Postgres FTS for hybrid search)
- `note` (writes to session table)
- `ask_user` (mediated by web UI)

**Catalog (initial):**
- 5–10 hand-curated CS/AI principles with full schema (description, structural signature, canonical examples, cross-domain examples)
- Stored as AGE graph nodes with `analog_of`, `prerequisite_for` edges where applicable

**Agent:**
- One `cross_domain_proposer` Lens-Proposer agent
- Tools allowed: `search_user_corpus`, `note`, `ask_user`
- System prompt encoding the cross-domain transfer methodology

**Web UI (minimal):**
- Document upload (PDFs, plain text, MD) with parse + chunk + embed pipeline
- "Run a problem-finding session" button with status streaming
- Results display: ranked candidates with provenance pointers
- Login (kept from the FastAPI template)

**Test target:** YC RFS prediction (Section 8 below)

**Exit criterion:** end-to-end run produces ≥10 NL problem candidates against the YC test corpus, each with traceable provenance, with full cost reported and under a configurable budget cap.

### Phase 1 — Single lens, properly (target: ~2 weeks)

**Goal:** demonstrate the value claim on one lens.

- Hand-curate the catalog of CS/AI principles (~20–50 entries)
- Implement `search_curated_catalog` (vector + graph traversal)
- Refine the cross-domain Lens-Proposer prompts and tool-use sequencing
- Add `note` tool and session memory
- Add provenance ledger
- Pick one test domain (yours or a collaborator's); build a 50–200 document corpus
- Hand-evaluate 30–50 outputs against the criteria (non-obviousness, groundedness, actionability)

**Exit criterion:** ≥30% of outputs rated as "non-obvious AND grounded AND actionable" by you.

### Phase 2 — External search + adversarial agents (target: ~2 weeks)

**Goal:** add the messy-source channel and the adversarial pair.

- Implement `search_academic` (Semantic Scholar API)
- Implement `search_messy` (Tavily for web + Reddit + HN)
- Implement `read_url`
- Define Challenger agent (with prompt encouraging strong adversarial stance)
- Define Skeptic agent (focused on provenance audit)
- A/B compare: outputs with vs. without the adversarial pass

**Exit criterion:** measurable lift in groundedness scores when adversarial pass is enabled. Cost per successful candidate comes back tractable.

### Phase 3 — Full multi-lens (target: ~3 weeks)

**Goal:** lens count goes from 1 to 4–5; synthesizer emerges as a real component.

- Implement Counterfactual Perturbation lens
- Implement Contradiction Surfacing lens
- Implement Distance-from-Focus lens
- Synthesizer agent: dedupe, cross-lens reinforcement detection
- Critic agent: formal scoring with calibration
- Lens weighting based on observed downstream success

**Exit criterion:** Synthesizer's top-3 outputs, on a held-out evaluation set, hit 50%+ "valuable" rating.

### Phase 4 — Graph queries first-class (target: ~2 weeks)

**Goal:** graph-shaped queries used at scale; AGE schema and indices tuned.

- Expand the AGE catalog graph (was minimal in Phase 0): full set of edges (`analog_of`, `prerequisite_for`, `application_of`, `composes_with`)
- Build out the provenance graph (claim → source → support_relation, queryable across runs)
- Build the problem-dependency graph (problem → sub-problem, problem → related-problem)
- New tool: `inspect_provenance` — walks the graph from a claim to all supporting evidence
- AGE index tuning (label indices, property indices) based on Phase 1–3 query patterns

**Exit criterion:** the system can answer "what other principles share structural signature with X?" via a single AGE Cypher query, and `inspect_provenance` returns a complete reasoning trace for any claim in any output.

### Phase 5 — Framework swap (target: ~1 week)

**Goal:** verify the abstraction layer is real.

- Implement `PIAgentAdapter`
- Run a regression suite: same inputs through Claude SDK adapter and PI adapter, compare outputs (modulo per-run noise)
- Document any abstraction leaks; fix them

**Exit criterion:** swapping `default_framework` in config produces identical-quality outputs (within calibration tolerance) without code changes.

### Phase 6 — Productization (open-ended)

UI surface, multi-tenant auth, billing, deployment, observability stack, etc. Out of scope for this plan.

---

## 8. Framework comparison summary

| Dimension | Claude Agent SDK | PI / pi-mono | LangGraph | Direct Anthropic | CAR (codex-autorunner) |
|---|---|---|---|---|---|
| **Maturity** | High (Anthropic-supported) | Medium (active, smaller community) | Highest (production references) | N/A — we own it | Medium (active, single-maintainer + community) |
| **Multi-agent native** | Sub-agents, isolated context | Manual (via pi-agent-core composition) | Native (graph nodes) | Manual | No — sequential ticket flow; concurrency is across tickets, not within |
| **Provider flexibility** | Claude only | Anthropic / OpenAI / Google / xAI / Groq / Cerebras / OpenRouter | Via LangChain integrations (broad) | Anthropic only | Backend-agent flexible (Codex, Hermes, OpenCode, any ACP) — but tied to coding-agent runtimes |
| **Tool definition** | `@tool` decorator → MCP | TypeBox schema → function | LangChain Tools | Hand-roll on Messages API | Tickets describe work; backend agent brings its own tools |
| **Hooks / observability** | Rich (PreToolUse, PostToolUse, etc.) | Simple | LangSmith integration | We build it | Web UI + logs + Telegram/Discord notifications when stuck |
| **Prompt caching** | Automatic | Manual | Manual (provider-dependent) | Manual | Backend-agent dependent |
| **Session / resume** | Built-in (JSONL local) | Built-in (JSONL local) | Built-in (checkpointing) | We build it | Yes — durable threads in Hermes; ticket retry/resume in CAR engine |
| **Cost tracking** | Per-call + per-model | Per-call + per-provider | Via LangSmith | We build it | Per-ticket via `/api/usage` and `/api/usage/series` |
| **Ecosystem fit** | Best with Claude-centric stack | Best for cross-provider | Best with LangChain stack | Lowest abstraction overhead | Best for long-running, walk-away, multi-step work that fits "ticket" shape |
| **Recommended role** | **Default orchestration** | **Parity verification** | Future option for graph orchestration | Fallback / regression baseline | **Runtime deep-search subsystem + build-time harness** (NOT orchestration) |

---

## 9. Decisions resolved

### 2026-05-05

| # | Decision | Resolution |
|---|---|---|
| 1 | Default framework | **Claude Agent SDK (Python)**, with `DirectAnthropicAdapter` as parity baseline. PI in Phase 5 for cross-vendor verification. |
| 2 | Storage stack | **Postgres + pgvector + Apache AGE** (single DB), **MinIO** for object storage. Production-ready from day one. |
| 3 | Test domain | **YC Requests for Startups prediction.** See Section 10 for methodology. |
| 4 | Catalog seeding | **Hand-write ~20–50 entries**, expand later via system-proposed-then-validated. |
| 5 | Phase 0 scope | **Ambitious** — scaffolding + cross-domain lens + first end-to-end run on YC test |
| 6 | UX surface | **Lightweight web UI** built on `fastapi/full-stack-fastapi-template` |

### 2026-05-09

| # | Decision | Resolution |
|---|---|---|
| 7 | CAR (codex-autorunner) integration | **Two-role split.** (a) **Runtime deep-search subsystem:** the in-process Evidence Gatherer agent role from Section 2 dissolves into CAR `evidence_dossier` tickets executed by Hermes (durable threads); a `dossier_ingest_worker` writes results back into Postgres+AGE. (b) **Build-time agent harness:** CAR drives Codex/Hermes through the implementation ticket spine for the hackathon scaffold. CAR is *not* the orchestration runtime — Lens-Proposers, Challenger, Synthesizer, Critic stay in-process under Claude Agent SDK because the streaming demo requires real-time concurrent execution. |
| 8 | Lenses for hackathon | **Cross-domain transfer + Contradiction surfacing + Distance-from-focus.** Counterfactual perturbation deferred to Phase 3. Selection optimizes for visible surprise in the demo (cross-domain) and breadth of input signal (the other two). |
| 9 | Demo architecture | **Streaming/incremental flow** with dirty-set partial re-eval. Each new doc invalidates affected candidates; orchestrator re-runs Challenger/Synthesizer on the dirty subset. Postgres `LISTEN/NOTIFY` → SSE → frontend diff feed. CAR ticket panel embedded in the demo board shows pending → running → complete dossier work in real time. |
| 10 | Demo benchmark anchor | **YC RFS Summer 2026 prediction as headline; founder/investor use case as 30-sec interactive coda.** See Section 11 for the stage-by-stage demo arc. |

---

## 10. Test methodology — YC RFS prediction

**Why this test:** YC publishes Requests-for-Startups lists every cycle (~3 per year), with each list naming 10–20 specific opportunity areas YC would fund. This gives us a *labeled, repeating, public* benchmark — uncommon in problem-finding research. It tests the core value claim: *can the system anticipate where high-leverage opportunities are surfacing in a domain it has only indirect access to?*

**Cycle to predict:**
- **Primary target: Summer 2026 RFS** (published ~May 4 2026). Today is 2026-05-05; the list is public. We simulate prediction by restricting all ingested data to ≤ 2026-05-03 (the day before publication).
- **Secondary target (forward prediction): Fall 2026 RFS.** Run again after Phase 1 with all currently-available data; compare predictions to the actual list when it publishes (~September 2026).
- **Backtest targets** (no waiting, useful for tuning): Spring 2026 RFS (cutoff 2026-02-05), Winter 2025 RFS, etc.

**Inputs (all restricted to pre-cutoff):**
- Prior YC RFS lists (we already have these in `research/tier3_practitioner/`)
- YC blog posts and podcast / Garry Tan / partner public statements
- Hacker News discussions, especially around new technologies and unmet needs
- Tech news (TechCrunch, The Information, Stratechery, etc.)
- AI / ML research trends from arXiv and select Twitter/X accounts
- Founder commentary and forums (IndieHackers, Reddit r/startups)
- Macro tech / industry signals
- Our hand-curated CS/AI principles catalog

**Output:**
- A predicted RFS-style list: 15–20 NL areas the system thinks YC is likely to fund this cycle
- Each entry includes the full output schema: NL statement, evidence, V̂/Ĉ confidence, pipeline (suggested first moves a founder might take), provenance, lens attribution

**Evaluation:**
- **Conceptual overlap** with actual published RFS — manual scoring at 3 levels per actual RFS item: *direct match* (system predicted this exact area), *adjacent* (system predicted something tangentially related), *missed* (no system output addresses this area)
- **Precision** — fraction of system predictions that conceptually match an actual RFS item
- **Recall** — fraction of actual RFS items that have a corresponding system prediction
- **Excess** — predictions the system made that don't match any actual RFS item; manually inspect — are they YC-style ideas YC just didn't publish? Are they nonsense? Are they ahead of YC?
- **Provenance quality** — for a sample of predictions, can a human follow the reasoning chain back to source documents?

**Why this is genuinely diagnostic:**
- *Direct match precision/recall* tests cross-domain transfer accuracy directly
- *Excess analysis* tests whether the system is producing valuable outputs YC missed (the most interesting case for a real product) vs. hallucinations
- *Provenance quality* tests whether the deep-tech rigor commitment is being earned

**Cycle of repeated evaluation:**
- Phase 0 exit: hit 1 backtest cycle (Spring 2026 or earlier)
- Phase 1 exit: backtest on 3 cycles, plus simulated-prediction on Summer 2026
- Phase 3 exit: forward-prediction on Fall 2026 (when its RFS publishes)

This gives us a credible benchmark to defend the "deep tech, rigorous" positioning externally and a calibration signal internally.

---

## 11. Hackathon execution plan (3 days)

This section is the consolidated hackathon-scope cut of the long-term plan above. The long-term plan is canonical for design intent; this section is canonical for what we ship in the next 72 hours.

### 11.1 Demo arc — "watch it get smarter"

The hackathon's signature surprise is a live, streaming prediction board where the system visibly improves as data flows in. The demo runs the YC RFS Summer 2026 prediction with all ingested data restricted to ≤ 2026-05-03, then reveals the actual published list at the end and scores the curve.

| t | Action on stage | What audience sees |
|---|---|---|
| 0:00 | **Cold start.** Seed = YC's prior RFS history + the curated CS/AI principles catalog | 10 generic predictions. Low V̂, high Ĉ uncertainty. No dossier badges. Flat board. |
| 0:30 | **Drop HN top posts (last 90 days, ≤cutoff).** | Board churns. Contradiction-surfacing lens fires — surfaces "everyone's complaining about X" predictions. Confidence bars shift live. |
| 1:15 | **Drop arXiv recent + Stratechery archives.** | Cross-domain transfer lens fires — surfaces a *structurally analogous* prediction. Visible 💡 chip. First high-V̂ candidate emerges. |
| 1:20 | **Orchestrator fires `queue_evidence_dossier`** for the high-V̂ candidate | Diff feed: `→ CAR queued evidence_dossier #1`. CAR ticket appears in the side-panel: `pending`. |
| 1:45 | **Drop 200 founder-interview transcripts** (synthetic but plausible blob) | Synthesizer detects 3-way reinforcement; second high-V̂ candidate emerges; second CAR ticket queued. |
| 2:00 | **First CAR dossier completes** (pre-warmed against the demo corpus to fit timing) | Side panel: ticket flips `complete`. Candidate gets `📚 12 sources` badge. V̂ jumps 0.78 → 0.91. AGE graph traversal becomes live in subsequent agent calls. |
| 2:30 | **Synthesizer re-runs over populated graph** | Cross-candidate AGE query reveals two candidates share 4 evidence sources. They merge into one stronger prediction. |
| 2:45 | **Challenger pass live.** | Three weak (non-dossiered) candidates get red-struck. Skeptic flags one for unsourced claim. One dossiered candidate earns `✓ challenged & held` badge. |
| 3:15 | **Reveal: actual YC Summer 2026 RFS.** | Side-by-side. Score precision/recall at each stage. Curve: 20% → 35% → 55% → 70% as data and dossiers grew. |
| 3:45 | **The kicker — "ahead of YC" excess.** | Highlight 2–3 predictions the system made that *weren't* on YC's list but match emerging signals. Frame as leading indicators, not noise. |
| 4:00 | **Interactive coda** — judge persona ("indie hacker into climate") drops a personal interest doc | Same board re-instances. Runs the loop in 30 seconds against the persona's interest. Shows the YC benchmark is one instance, not a parlor trick. |

The visual surprise is the **diff feed** (Twitter-like stream of state changes) and the **CAR side panel** (the system visibly outsourcing deep work). Together they make the system's reasoning legible — and demonstrate judgment about *when* to invest deeply.

### 11.2 Architectural additions for the demo

The long-term plan (Section 5) is one-shot: ingest → run pipeline → return ranked list. The demo requires an incremental, streaming flow. Three additions:

1. **Dirty-set partial re-eval orchestrator.** Each new doc invalidates only candidates whose evidence overlaps. Re-runs Challenger / Synthesizer / Critic on the dirty subset, not the full pipeline. Avoids the "looks like a batch rerun" anti-feel.
2. **Postgres `LISTEN/NOTIFY` → SSE diff feed.** Every state change (candidate added, V̂ updated, killed, merged, dossier ready) publishes to a Postgres channel. Frontend subscribes via Server-Sent Events. Drives both the prediction board and the diff feed.
3. **CAR ticket panel embed.** The demo board reserves a side panel that mirrors `.codex-autorunner/tickets/` state — pending / running / complete. Users see the system queueing and completing deep-research tickets in real time. Architecturally, this is just CAR's existing web UI in an iframe, plus a tiny shim that filters to the current session's tickets.

### 11.3 Cuts from the long-term plan

What we drop for hackathon scope (and pick up later):
- **Phase 4 (graph-queries-first-class)** — keep AGE schema minimal, only the edges the dossier worker needs. Defer index tuning.
- **Phase 5 (PI parity)** — single framework (Claude Agent SDK + CAR/Hermes). Cross-vendor verification deferred.
- **Counterfactual perturbation lens** — keep cross-domain, contradiction surfacing, distance-from-focus. The fourth lens lands in Phase 3.
- **Skeptic as separate agent** — fold provenance audit into Challenger via AGE traversal. Keep the badge visual ("✓ provenance audited") so audience sees the function happening.
- **Multi-tenancy, auth, billing** — single hardcoded session.
- **Backtesting on 3 cycles** — backtest only Spring 2026 in dev for tuning. Demo runs against Summer 2026.

### 11.4 Build ticket spine

Driven by CAR + Hermes during the build. Numbers leave gaps for follow-ups per CAR's ticket-skill convention. Each ticket is independently completable; lower numbers strictly precede higher. Per `docs/car-ticket-skill.md`, frontmatter requires `ticket_id`, `agent`, `done`.

| # | Title | Notes |
|---|---|---|
| 001 | Scaffold from `fastapi/full-stack-fastapi-template`; strip items CRUD; keep auth | One-shot |
| 010 | Add Postgres + pgvector via Alembic migration | |
| 011 | Add Apache AGE extension + minimal catalog graph schema | Keep minimal for hackathon |
| 015 | MinIO docker-compose service for raw uploads | |
| 020 | Document ingestion pipeline: PDF/MD/HTML → chunks → Voyage embeddings → pgvector | |
| 030 | `Tool`, `AgentDefinition`, `AgentFramework`, `AgentRunOutput` interfaces (Section 6) | Pin IMPLEMENTATION_PLAN.md as `contextspace/` |
| 031 | `ClaudeAgentSDKAdapter` implementation | |
| 032 | `DirectAnthropicAdapter` parity baseline | |
| 040 | `search_user_corpus` tool (pgvector + FTS hybrid) | |
| 041 | `note` tool (session table append) | |
| 042 | `ask_user` tool (web-mediated) | |
| 045 | `queue_evidence_dossier` tool — writes ticket file into `.codex-autorunner/tickets/` | New per Section 3 |
| 046 | `dossier_ingest_worker` — watches done tickets; parses MD; writes to Postgres+AGE; emits NOTIFY | Single write-point to AGE from CAR output |
| 047 | `evidence_dossier` ticket template (the canonical body Hermes executes against) | |
| 048 | Evidence-gathering Python script invoked from CAR ticket; uses Tavily/Semantic Scholar/HN; writes structured MD | Replaces in-process Evidence Gatherer |
| 050 | Cross-domain transfer Lens-Proposer prompt + system message | Bundles 5–10 hand-curated catalog entries |
| 051 | Contradiction-surfacing Lens-Proposer | |
| 052 | Distance-from-focus Lens-Proposer | |
| 060 | Challenger agent (folds Skeptic logic; reads from AGE for provenance audit) | |
| 061 | Synthesizer agent (cross-candidate AGE queries for shared-source detection) | |
| 062 | Critic / Judge agent — V̂/Ĉ scoring with dossier-grounding bonus | |
| 070 | **Dirty-set partial re-eval orchestrator** — invalidates affected candidates per ingestion event | The demo's load-bearing architectural piece |
| 080 | `LISTEN/NOTIFY` channel + SSE endpoint for diff feed | |
| 090 | Prediction board frontend: V̂/Ĉ bars, lens chips, diff feed, ranking | |
| 091 | YC live benchmark scoring widget (precision/recall against held-out RFS) | |
| 092 | CAR side-panel embed in demo board | iframe + filter shim |
| 100 | Pre-bake 4–5 corpus bundles (YC history, HN top, arXiv, Stratechery, founder transcripts) | Pre-chunked, pre-embedded |
| 105 | Pre-warm CAR dossiers on demo corpus before live run | So Stage 2:00 timing works |
| 110 | YC Summer 2026 RFS ground truth fixture + evaluation script | |
| 200 | Demo dry-run rehearsal + recorded fallback video | `agent: user` — final human signoff |

### 11.5 Day-by-day

| Day | Output |
|---|---|
| **Day 1 AM** | CAR hub init (`car init --mode hub` in `/home/santiago/Neuryta/hackathon/car-hub/`). Configure Hermes as backend. Pin IMPLEMENTATION_PLAN.md to contextspace. Smoke-test one trivial ticket. |
| **Day 1 PM → night** | Tickets 001–048 (scaffold, storage, framework abstraction, basic tools, CAR integration plumbing). CAR runs overnight. |
| **Day 2 AM** | Review what shipped. Hand-tune Lens-Proposer prompts. |
| **Day 2 day** | Tickets 050–062 (the three Lens-Proposers, Challenger, Synthesizer, Critic). |
| **Day 2 night** | Tickets 070–092 (the architectural punchline — dirty-set re-eval + diff feed + UI). |
| **Day 3 AM** | Tickets 100–110 (pre-baked corpora, CAR dossier pre-warm, YC ground truth). Demo dry-runs. |
| **Day 3 PM** | Polish visual surprise moments (cross-domain 💡 chip, dossier badges, "ahead of YC" badge). Record fallback video. |

### 11.6 Risks and mitigations

| Risk | Mitigation |
|---|---|
| Codex/Hermes makes architectural decisions in early CAR tickets that conflict with the plan | Pin IMPLEMENTATION_PLAN.md as a `contextspace/` doc — every CAR run gives the agent that file as context. Babysit ticket 030 (the framework abstraction layer is opinionated). |
| Live ingestion is too slow for a 4-min demo | Pre-bake the 4–5 corpus bundles (chunked, embedded, ready to drop in with one click). Pre-warm CAR dossiers against the demo corpus the night before. |
| Dirty-set re-eval has subtle correctness bugs | Ship it with an explicit "full re-eval" fallback button. If demo goes sideways, switch modes and absorb the slower feel. |
| CAR side-panel iframe feels disconnected from the main board | Style the panel to match the prediction board's design language. Animate transitions in/out. Have a recorded fallback that shows the same flow without the iframe. |
| Ahead-of-YC excess predictions are pure hallucinations on the day | Pre-vet excess predictions during dry-runs. Have 2–3 hand-picked excess predictions queued as "if the live run produces these, lean into them; else fall back to these prepared examples." |
| Hermes setup is fragile | Codex is the safe fallback — JSON-RPC stable, well-documented in CAR. Reconfigure if needed; lose memory continuity but keep delivery. |

### 11.7 Demo success criteria

The demo succeeds if all of the following are true:
1. Audience sees ≥3 distinct prediction-board state changes in real time per data drop (new candidate, V̂ update, kill, merge, dossier-ready).
2. At least one candidate visibly survives Challenger after dossier completion — demonstrating the deep-search investment paid off.
3. The precision/recall curve against actual Summer 2026 RFS climbs monotonically across stages, ending ≥60% precision on top-10 predictions.
4. At least one "ahead of YC" excess prediction is defensible — the audience can be shown a real-world signal supporting it.
5. The interactive coda for a judge persona produces at least one prediction the judge finds genuinely interesting (subjective, but the moment that converts skeptics).
