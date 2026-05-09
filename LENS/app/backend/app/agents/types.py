"""Core data types for the agent runtime.

These types are framework-agnostic. Adapters translate to/from
framework-native representations (Claude Agent SDK options, PI tool
schemas, LangGraph state objects, etc.). The orchestrator and tool
code only ever sees these types.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Tool layer
# ---------------------------------------------------------------------------


class ToolSpec(BaseModel):
    """Framework-agnostic tool specification.

    Adapters convert ``input_schema`` (JSON Schema) into framework-native
    schema (Claude SDK ``@tool`` decorator inputs, TypeBox schemas for PI,
    LangChain ``Tool.args_schema`` for LangGraph, etc.).
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(..., description="Canonical tool name; must be unique within a registry")
    description: str = Field(..., description="What the agent reads to decide when to use this tool")
    input_schema: dict[str, Any] = Field(..., description="JSON Schema for arguments")
    output_schema: dict[str, Any] | None = Field(
        default=None, description="Optional JSON Schema for typed tool returns"
    )


class ToolContext(BaseModel):
    """Per-call context passed to a Tool.execute. Adapters populate this.

    Tools should treat fields as read-only; mutations belong in the result.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    session_id: UUID
    parent_agent_name: str
    parent_run_id: UUID
    cost_so_far_usd: float = 0.0
    # Storage handles, populated by the orchestrator at the start of a run.
    # Concrete type is ``app.agents.storage.StorageClients`` once that module
    # exists; held as Any here to avoid an import cycle with the agents package.
    storage: Any | None = None


class ToolResult(BaseModel):
    """What a Tool returns to the agent loop."""

    content: str | list[dict[str, Any]] = Field(
        ..., description="Either NL text the agent reads, or structured chunks"
    )
    is_error: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Agent layer
# ---------------------------------------------------------------------------


AgentRole = Literal[
    "orchestrator",
    "lens_proposer",
    "evidence_gatherer",
    "challenger",
    "skeptic",
    "synthesizer",
    "critic",
    "user_liaison",
]

ContextStrategy = Literal["fresh", "shared", "summarized"]


class AgentDefinition(BaseModel):
    """Static definition of an agent role.

    Instances are typically constructed once per role at startup and
    re-used across runs (the framework registry resolves which adapter
    actually executes each role).
    """

    name: str = Field(..., description="Unique agent name (e.g. 'cross_domain_proposer')")
    role: AgentRole
    system_prompt: str
    tool_names: list[str] = Field(
        default_factory=list,
        description="Tool names this agent is allowed to call; subset of registered tools",
    )
    model: str = Field(
        ...,
        description="Model identifier; meaning is adapter-specific (e.g. 'claude-opus-4-7', 'gpt-5')",
    )
    max_turns: int = 10
    temperature: float = 0.7
    context_strategy: ContextStrategy = "fresh"


class AgentMessage(BaseModel):
    """One message in an agent's transcript."""

    role: Literal["user", "assistant", "tool"]
    content: str | list[dict[str, Any]]
    timestamp: datetime = Field(default_factory=_utcnow)


class AgentRunInput(BaseModel):
    """Inputs to a single agent.run() call."""

    initial_prompt: str
    shared_context: list[AgentMessage] = Field(
        default_factory=list,
        description="Pre-existing conversation history for ``context_strategy='shared'``",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolCallRecord(BaseModel):
    """One tool call within an agent run, captured for replay and audit."""

    tool_name: str
    arguments: dict[str, Any]
    result: ToolResult
    duration_ms: int


class AgentRunOutput(BaseModel):
    """Result of a single agent.run() call."""

    run_id: UUID = Field(default_factory=uuid4)
    final_message: str
    transcript: list[AgentMessage]
    tool_calls: list[ToolCallRecord]
    cost_usd: float
    duration_ms: int
    framework_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Framework-specific telemetry (session ids, model usage breakdowns, etc.)",
    )
