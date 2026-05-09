"""Tool abstract base class.

Tools are framework-agnostic. Each adapter handles the translation from
this base class into framework-native tool definitions (e.g. registering
as in-process MCP servers for Claude Agent SDK).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .types import ToolContext, ToolResult, ToolSpec


class Tool(ABC):
    """Abstract base class for tools the agent can call.

    Concrete tools must:
      * set ``spec`` (a :class:`ToolSpec`) at class or instance level
      * implement :meth:`execute` as an async coroutine

    Implementation note: tools should validate their own arguments against
    ``spec.input_schema`` only if the framework adapter does not already
    do so. The Claude Agent SDK's ``@tool`` decorator validates inputs
    automatically; the DirectAnthropic adapter does not, so it adds a
    validation step before calling :meth:`execute`.
    """

    spec: ToolSpec

    @abstractmethod
    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        """Execute the tool. Must be coroutine-safe.

        Args:
            args: arguments matching ``spec.input_schema``
            ctx:  per-call context (session id, parent agent, storage handles)

        Returns:
            :class:`ToolResult` with content and optional metadata.
            Set ``is_error=True`` on recoverable errors; raise on unrecoverable.
        """
        raise NotImplementedError

    @property
    def name(self) -> str:
        return self.spec.name
