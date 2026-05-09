"""Claude Agent SDK adapter.

Wraps ``claude-agent-sdk`` (Python) to conform to :class:`AgentFramework`.

Translation:
  * ``Tool`` instances → in-process MCP server via ``@tool`` decorator
    + ``create_sdk_mcp_server``
  * ``AgentDefinition`` → ``ClaudeAgentOptions`` (system_prompt, model,
    allowed_tools, max_turns, temperature, mcp_servers)
  * ``AgentRunInput.initial_prompt`` → ``query()`` argument
  * Streamed messages, MCP tool calls, and ``ResultMessage.total_cost_usd``
    → :class:`AgentRunOutput`

The SDK runs tool handlers itself once they're registered as @tool, so
we capture tool-call records inside a closure that wraps each handler.
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from typing import Any
from uuid import UUID, uuid4

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    ToolUseBlock,
    create_sdk_mcp_server,
    query,
    tool as sdk_tool,
)

from ..framework import AgentFramework
from ..tool import Tool
from ..types import (
    AgentDefinition,
    AgentMessage,
    AgentRunInput,
    AgentRunOutput,
    ToolCallRecord,
    ToolContext,
    ToolResult,
)


_MCP_SERVER_NAME = "lens"


class ClaudeAgentSDKAdapter(AgentFramework):
    name = "claude_agent_sdk"

    def __init__(
        self,
        api_key: str,
        default_cache_ttl_seconds: int = 3600,
    ) -> None:
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is required for ClaudeAgentSDKAdapter")
        self._api_key = api_key
        self._default_cache_ttl_seconds = default_cache_ttl_seconds

    async def run(
        self,
        agent: AgentDefinition,
        run_input: AgentRunInput,
        tools: Iterable[Tool],
    ) -> AgentRunOutput:
        run_id = uuid4()
        session_id = self._extract_session_id(run_input)

        ctx = ToolContext(
            session_id=session_id,
            parent_agent_name=agent.name,
            parent_run_id=run_id,
            cost_so_far_usd=0.0,
            storage=run_input.metadata.get("storage"),
        )

        allowed_by_name: dict[str, Tool] = {
            t.spec.name: t for t in tools if t.spec.name in agent.tool_names
        }

        # tool_calls_log is mutated by closures inside the wrapped tools.
        tool_calls_log: list[ToolCallRecord] = []

        sdk_handlers = [
            self._wrap_tool(t, ctx, tool_calls_log)
            for t in allowed_by_name.values()
        ]

        mcp_server = create_sdk_mcp_server(
            name=_MCP_SERVER_NAME,
            version="1.0.0",
            tools=sdk_handlers,
        )

        allowed_tool_uris = [
            f"mcp__{_MCP_SERVER_NAME}__{name}" for name in allowed_by_name
        ]

        options = ClaudeAgentOptions(
            system_prompt=agent.system_prompt,
            model=agent.model,
            allowed_tools=allowed_tool_uris,
            max_turns=agent.max_turns,
            temperature=agent.temperature,
            mcp_servers={_MCP_SERVER_NAME: mcp_server},
        )

        transcript: list[AgentMessage] = [
            AgentMessage(role="user", content=run_input.initial_prompt)
        ]
        final_text = ""
        cost_usd = 0.0
        framework_metadata: dict[str, Any] = {"adapter": self.name, "model": agent.model}
        start = time.monotonic()

        async for message in query(prompt=run_input.initial_prompt, options=options):
            if isinstance(message, AssistantMessage):
                blocks: list[dict] = []
                for block in message.content:
                    if isinstance(block, ToolUseBlock):
                        blocks.append(
                            {
                                "type": "tool_use",
                                "name": getattr(block, "name", ""),
                                "input": getattr(block, "input", {}),
                            }
                        )
                    else:
                        blocks.append(
                            {
                                "type": "text",
                                "text": getattr(block, "text", str(block)),
                            }
                        )
                transcript.append(AgentMessage(role="assistant", content=blocks))

            elif isinstance(message, ResultMessage):
                # The SDK's terminal message. Field names vary slightly
                # across versions; prefer the canonical ``result`` and
                # ``total_cost_usd`` if present, fall back gracefully.
                final_text = (
                    getattr(message, "result", None)
                    or getattr(message, "text", "")
                    or final_text
                )
                cost_usd = float(
                    getattr(message, "total_cost_usd", None)
                    or getattr(message, "cost_usd", None)
                    or 0.0
                )
                framework_metadata["session_id"] = getattr(message, "session_id", None)
                framework_metadata["subtype"] = getattr(message, "subtype", None)

        duration_ms = int((time.monotonic() - start) * 1000)
        return AgentRunOutput(
            run_id=run_id,
            final_message=final_text,
            transcript=transcript,
            tool_calls=tool_calls_log,
            cost_usd=cost_usd,
            duration_ms=duration_ms,
            framework_metadata=framework_metadata,
        )

    async def health_check(self) -> bool:
        # The SDK doesn't expose a separate health endpoint; we settle for
        # confirming the API key is present. A real health check would
        # exercise an end-to-end query against a no-op tool.
        return bool(self._api_key)

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _extract_session_id(run_input: AgentRunInput) -> UUID:
        sid = run_input.metadata.get("session_id")
        if isinstance(sid, UUID):
            return sid
        if isinstance(sid, str):
            try:
                return UUID(sid)
            except ValueError:
                pass
        return uuid4()

    @staticmethod
    def _wrap_tool(
        t: Tool,
        ctx: ToolContext,
        tool_calls_log: list[ToolCallRecord],
    ) -> Any:
        """Build an @sdk_tool-decorated handler that delegates to ``t.execute``
        while capturing the call into ``tool_calls_log``."""

        spec = t.spec

        @sdk_tool(spec.name, spec.description, spec.input_schema)
        async def handler(args: dict[str, Any]) -> dict[str, Any]:
            t0 = time.monotonic()
            try:
                result: ToolResult = await t.execute(args, ctx)
            except Exception as exc:  # noqa: BLE001
                result = ToolResult(content=f"Tool raised: {exc!r}", is_error=True)
            duration_ms = int((time.monotonic() - t0) * 1000)

            tool_calls_log.append(
                ToolCallRecord(
                    tool_name=spec.name,
                    arguments=args,
                    result=result,
                    duration_ms=duration_ms,
                )
            )

            if isinstance(result.content, str):
                content_blocks = [{"type": "text", "text": result.content}]
            else:
                # Already a list of content blocks (image/resource/text).
                content_blocks = result.content

            return {"content": content_blocks, "is_error": result.is_error}

        return handler
