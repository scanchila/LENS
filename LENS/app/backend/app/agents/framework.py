"""Agent framework abstraction + per-role registry.

The whole point of this layer is that the orchestrator never imports a
specific framework. Switching from Claude Agent SDK to PI to LangGraph
is config-only; see ``lens.yaml`` for assignments.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable

from .tool import Tool
from .types import AgentDefinition, AgentRunInput, AgentRunOutput


class AgentFramework(ABC):
    """Abstract base class for agentic-framework adapters.

    Each adapter wraps one underlying framework (Claude Agent SDK,
    PI / pi-mono, LangGraph, direct Anthropic Messages API, ...) and
    exposes a uniform ``run`` interface.

    Subclasses must:
      * set the class attribute ``name`` to a unique string
      * implement :meth:`run` and :meth:`health_check`
    """

    #: Unique framework identifier (e.g. "claude_agent_sdk", "pi_agent",
    #: "langgraph", "direct_anthropic"). Used as the registry key.
    name: str

    @abstractmethod
    async def run(
        self,
        agent: AgentDefinition,
        run_input: AgentRunInput,
        tools: Iterable[Tool],
    ) -> AgentRunOutput:
        """Execute one agent.run().

        Adapters MUST:
          * Translate ``tools`` to framework-native tool definitions
          * Apply ``agent.max_turns`` and any ``cost_cap`` from run_input.metadata
          * Track cost, accumulate transcript and tool calls
          * Return a fully-populated :class:`AgentRunOutput`
        """
        raise NotImplementedError

    @abstractmethod
    async def health_check(self) -> bool:
        """Lightweight liveness check; e.g. an API ping. Used by the orchestrator
        to fail fast if a configured framework cannot be reached."""
        raise NotImplementedError


class FrameworkRegistry:
    """Maps agent roles to the framework adapter that should execute them.

    Lookup precedence (most specific wins):
      1. Per-agent override (registered with :meth:`assign_agent`)
      2. Per-role assignment (registered with :meth:`assign_role`)
      3. Default framework (set with :meth:`set_default`)

    Adapters are registered once at startup; assignments come from the
    application config (``lens.yaml``).
    """

    def __init__(self) -> None:
        self._frameworks: dict[str, AgentFramework] = {}
        self._role_assignments: dict[str, str] = {}
        self._agent_assignments: dict[str, str] = {}
        self._default: str | None = None

    def register(self, framework: AgentFramework) -> None:
        if not framework.name:
            raise ValueError(
                f"AgentFramework subclass {type(framework).__name__} has empty name"
            )
        self._frameworks[framework.name] = framework

    def set_default(self, framework_name: str) -> None:
        self._require_registered(framework_name)
        self._default = framework_name

    def assign_role(self, role: str, framework_name: str) -> None:
        self._require_registered(framework_name)
        self._role_assignments[role] = framework_name

    def assign_agent(self, agent_name: str, framework_name: str) -> None:
        self._require_registered(framework_name)
        self._agent_assignments[agent_name] = framework_name

    def for_agent(self, agent: AgentDefinition) -> AgentFramework:
        """Return the framework that should execute this agent definition."""
        if agent.name in self._agent_assignments:
            return self._frameworks[self._agent_assignments[agent.name]]
        if agent.role in self._role_assignments:
            return self._frameworks[self._role_assignments[agent.role]]
        if self._default is not None:
            return self._frameworks[self._default]
        raise LookupError(
            f"No framework assigned for agent {agent.name!r} (role {agent.role!r}) "
            "and no default registered"
        )

    def get(self, framework_name: str) -> AgentFramework:
        self._require_registered(framework_name)
        return self._frameworks[framework_name]

    def _require_registered(self, name: str) -> None:
        if name not in self._frameworks:
            raise LookupError(
                f"Framework {name!r} is not registered. "
                f"Registered: {sorted(self._frameworks)!r}"
            )
