"""Direct-Anthropic adapter.

Hand-rolled tool-use loop on the Anthropic Messages API. Useful as:
  * a parity baseline against :class:`ClaudeAgentSDKAdapter` to verify
    the abstraction layer is honest (same input/tools → equivalent
    outputs modulo per-run noise)
  * a fallback when the SDK has incidents or schema drift
  * a reference implementation of what an adapter must do at the
    lowest level

This module deliberately avoids any ``claude_agent_sdk`` import.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterable
from uuid import UUID, uuid4

from anthropic import AsyncAnthropic
from anthropic.types import Message

from ..framework import AgentFramework
from ..pricing import cost_for_usage
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


_DEFAULT_MAX_TOKENS = 4096


class DirectAnthropicAdapter(AgentFramework):
    name = "direct_anthropic"

    def __init__(
        self,
        api_key: str,
        max_tokens_per_call: int = _DEFAULT_MAX_TOKENS,
    ) -> None:
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is required for DirectAnthropicAdapter")
        self._client = AsyncAnthropic(api_key=api_key)
        self._max_tokens = max_tokens_per_call

    async def run(
        self,
        agent: AgentDefinition,
        run_input: AgentRunInput,
        tools: Iterable[Tool],
    ) -> AgentRunOutput:
        run_id = uuid4()
        session_id = self._extract_session_id(run_input)
        budget_cap_usd = self._extract_budget_cap(run_input)

        ctx = ToolContext(
            session_id=session_id,
            parent_agent_name=agent.name,
            parent_run_id=run_id,
            cost_so_far_usd=0.0,
            storage=run_input.metadata.get("storage"),
        )

        # Filter to the tools this agent is allowed to call. Granting more
        # is silently dropped — the agent only sees what its definition
        # permits, which mirrors how the SDK adapter handles allowed_tools.
        allowed_by_name: dict[str, Tool] = {
            t.spec.name: t for t in tools if t.spec.name in agent.tool_names
        }
        api_tools = [
            {
                "name": t.spec.name,
                "description": t.spec.description,
                "input_schema": t.spec.input_schema,
            }
            for t in allowed_by_name.values()
        ]

        # Conversation state. We carry the SDK message format directly so
        # we can pass `messages` straight back into messages.create on each
        # turn; we mirror it into our framework-agnostic transcript.
        messages: list[dict] = [
            {"role": "user", "content": run_input.initial_prompt}
        ]
        transcript: list[AgentMessage] = [
            AgentMessage(role="user", content=run_input.initial_prompt)
        ]
        tool_calls: list[ToolCallRecord] = []
        cost_usd = 0.0
        final_text: str | None = None
        start = time.monotonic()

        for _turn in range(agent.max_turns):
            response: Message = await self._client.messages.create(
                model=agent.model,
                max_tokens=self._max_tokens,
                temperature=agent.temperature,
                system=agent.system_prompt,
                messages=messages,
                tools=api_tools or None,  # type: ignore[arg-type]
            )

            cost_usd += self._cost_of(response, agent.model)
            ctx = ctx.model_copy(update={"cost_so_far_usd": cost_usd})

            assistant_blocks = [self._block_to_dict(b) for b in response.content]
            transcript.append(AgentMessage(role="assistant", content=assistant_blocks))
            messages.append({"role": "assistant", "content": response.content})

            if budget_cap_usd is not None and cost_usd >= budget_cap_usd:
                final_text = self._collect_text(response)
                final_text = (final_text or "") + (
                    f"\n\n[budget cap hit: ${cost_usd:.4f} >= ${budget_cap_usd:.4f}]"
                )
                break

            if response.stop_reason == "end_turn":
                final_text = self._collect_text(response)
                break

            if response.stop_reason == "tool_use":
                tool_results = await self._execute_tool_calls(
                    response, allowed_by_name, ctx, tool_calls
                )
                messages.append({"role": "user", "content": tool_results})
                transcript.append(AgentMessage(role="tool", content=tool_results))
                continue

            # Other stop reasons: max_tokens, stop_sequence, refusal, etc.
            final_text = self._collect_text(response)
            break
        else:
            # for/else: the loop fell off the end without hitting break.
            final_text = (
                self._collect_text_from_messages(messages)
                + f"\n\n[reached max_turns={agent.max_turns} without end_turn]"
            )

        duration_ms = int((time.monotonic() - start) * 1000)
        return AgentRunOutput(
            run_id=run_id,
            final_message=final_text or "",
            transcript=transcript,
            tool_calls=tool_calls,
            cost_usd=cost_usd,
            duration_ms=duration_ms,
            framework_metadata={"adapter": self.name, "model": agent.model},
        )

    async def health_check(self) -> bool:
        try:
            # Lightest available call: list models.
            await self._client.models.list(limit=1)
            return True
        except Exception:  # noqa: BLE001
            return False

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
    def _extract_budget_cap(run_input: AgentRunInput) -> float | None:
        cap = run_input.metadata.get("budget_cap_usd")
        if isinstance(cap, (int, float)):
            return float(cap)
        return None

    @staticmethod
    def _cost_of(response: Message, model: str) -> float:
        usage = response.usage
        return cost_for_usage(
            model=model,
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
            cache_creation_input_tokens=getattr(
                usage, "cache_creation_input_tokens", 0
            )
            or 0,
            cache_read_input_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
        )

    @staticmethod
    def _block_to_dict(block: object) -> dict:
        # anthropic content blocks have ``.type``; convert to our generic
        # transcript shape.
        btype = getattr(block, "type", "unknown")
        if btype == "text":
            return {"type": "text", "text": getattr(block, "text", "")}
        if btype == "tool_use":
            return {
                "type": "tool_use",
                "id": getattr(block, "id", ""),
                "name": getattr(block, "name", ""),
                "input": getattr(block, "input", {}),
            }
        # Fallbacks: thinking, refusal, etc. Best-effort serialization.
        return {
            "type": btype,
            "raw": getattr(block, "model_dump", lambda: {"repr": repr(block)})(),
        }

    @staticmethod
    def _collect_text(response: Message) -> str:
        return "\n".join(
            getattr(b, "text", "") for b in response.content if getattr(b, "type", "") == "text"
        ).strip()

    @staticmethod
    def _collect_text_from_messages(messages: list[dict]) -> str:
        # Used when we hit max_turns and need to surface whatever
        # cumulative text the assistant has produced.
        out: list[str] = []
        for m in messages:
            if m.get("role") != "assistant":
                continue
            content = m.get("content")
            if isinstance(content, list):
                for b in content:
                    btype = getattr(b, "type", None) or (
                        b.get("type") if isinstance(b, dict) else None
                    )
                    if btype == "text":
                        out.append(getattr(b, "text", None) or b.get("text", ""))
        return "\n\n".join(out).strip()

    async def _execute_tool_calls(
        self,
        response: Message,
        tools_by_name: dict[str, Tool],
        ctx: ToolContext,
        tool_calls_log: list[ToolCallRecord],
    ) -> list[dict]:
        tool_results: list[dict] = []
        for block in response.content:
            if getattr(block, "type", "") != "tool_use":
                continue
            tool_name = getattr(block, "name", "")
            tool_use_id = getattr(block, "id", "")
            tool_input = getattr(block, "input", {}) or {}

            tool = tools_by_name.get(tool_name)
            if tool is None:
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": f"Tool {tool_name!r} is not available to this agent.",
                        "is_error": True,
                    }
                )
                continue

            t0 = time.monotonic()
            try:
                result: ToolResult = await tool.execute(tool_input, ctx)
            except Exception as exc:  # noqa: BLE001 — surface to the model
                result = ToolResult(content=f"Tool raised: {exc!r}", is_error=True)
            duration_ms = int((time.monotonic() - t0) * 1000)

            tool_calls_log.append(
                ToolCallRecord(
                    tool_name=tool_name,
                    arguments=tool_input,
                    result=result,
                    duration_ms=duration_ms,
                )
            )

            content_for_api: str | list[dict]
            if isinstance(result.content, str):
                content_for_api = result.content
            else:
                # Anthropic accepts either a string or a list of content
                # blocks for tool_result.content. Coerce list-of-dicts as-is.
                try:
                    content_for_api = result.content
                except Exception:  # noqa: BLE001
                    content_for_api = json.dumps(result.content)

            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": content_for_api,
                    "is_error": result.is_error,
                }
            )
        return tool_results
