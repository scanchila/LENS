"""Problem-finder agent runtime.

Subpackages:
- ``types``: data classes for tools, agents, runs, and tool calls
- ``tool``: Tool abstract base class
- ``framework``: AgentFramework abstract base class + FrameworkRegistry
- ``adapters``: concrete framework adapters (Claude Agent SDK, Direct Anthropic, ...)
- ``tools``: concrete Tool implementations (search_user_corpus, ask_user, note, ...)
- ``lenses``: lens-specific agent definitions (cross-domain transfer, ...)

The orchestrator and tool code never imports from ``adapters`` directly;
all framework dispatch goes through the FrameworkRegistry. Switching
frameworks is therefore a configuration change, not a code change.
"""

from .framework import AgentFramework, FrameworkRegistry
from .tool import Tool
from .types import (
    AgentDefinition,
    AgentMessage,
    AgentRunInput,
    AgentRunOutput,
    ToolCallRecord,
    ToolContext,
    ToolResult,
    ToolSpec,
)

__all__ = [
    "AgentDefinition",
    "AgentFramework",
    "AgentMessage",
    "AgentRunInput",
    "AgentRunOutput",
    "FrameworkRegistry",
    "Tool",
    "ToolCallRecord",
    "ToolContext",
    "ToolResult",
    "ToolSpec",
]
