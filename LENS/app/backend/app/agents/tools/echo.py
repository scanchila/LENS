"""Echo tool — trivial Tool used for adapter parity testing.

Returns its ``text`` argument as the result content. Useful to verify
that an adapter correctly:
  1. Translates ToolSpec into framework-native form
  2. Routes the model's tool call to our handler
  3. Surfaces the handler's return value back to the model
  4. Records the call into AgentRunOutput.tool_calls

If two adapters produce the same final transcript and tool-call list
when given the same agent and the same EchoTool, the abstraction is
honest at this layer.
"""

from __future__ import annotations

from typing import Any

from ..tool import Tool
from ..types import ToolContext, ToolResult, ToolSpec


class EchoTool(Tool):
    spec = ToolSpec(
        name="echo",
        description="Echo a string back. Useful only for testing the agent loop.",
        input_schema={
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The text to echo back.",
                }
            },
            "required": ["text"],
        },
    )

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        text = args.get("text", "")
        return ToolResult(content=str(text), is_error=False)
