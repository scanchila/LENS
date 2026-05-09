#!/usr/bin/env python3
"""Phase 0 smoke test — adapter parity.

Runs the same simple agent (using echo + note tools) through both the
DirectAnthropicAdapter and the ClaudeAgentSDKAdapter, then prints a
side-by-side comparison.

Usage:
    ANTHROPIC_API_KEY=sk-... python -m scripts.phase0_smoke

Exit codes:
    0  — both adapters produced output successfully
    1  — config error (e.g. missing API key)
    2  — adapter error during run
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# Ensure ``app`` is importable when running from the backend directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents import (  # noqa: E402
    AgentDefinition,
    AgentRunInput,
    AgentRunOutput,
    FrameworkRegistry,
)
from app.agents.adapters import (  # noqa: E402
    ClaudeAgentSDKAdapter,
    DirectAnthropicAdapter,
)
from app.agents.tools import EchoTool, InMemoryNoteSink, NoteTool  # noqa: E402


SMOKE_AGENT_PROMPT = """\
You are testing a multi-agent runtime.

Use the `echo` tool exactly once with the text 'PHASE_0_PROBE'.
Then use the `note` tool to record one observation with text='echo round-tripped successfully' and kind='finding'.
Then return a one-sentence final message confirming both calls happened.

Do not call any other tool. Do not call echo or note more than once.
"""


def build_agent(model: str) -> AgentDefinition:
    return AgentDefinition(
        name="phase0_probe",
        role="lens_proposer",
        system_prompt=SMOKE_AGENT_PROMPT,
        tool_names=["echo", "note"],
        model=model,
        max_turns=6,
        temperature=0.0,
    )


async def run_one(adapter_name: str, registry: FrameworkRegistry, model: str) -> AgentRunOutput:
    # Smoke test uses an in-memory note sink so it does not require a
    # running database. The DB-bound path is exercised by the integration
    # tests under tests/test_note_tool.py.
    note_sink = InMemoryNoteSink()
    tools = [EchoTool(), NoteTool(sink=note_sink)]
    agent = build_agent(model=model)

    framework = registry.get(adapter_name)
    output = await framework.run(
        agent=agent,
        run_input=AgentRunInput(
            initial_prompt="Please run the probe sequence as described in the system prompt.",
            metadata={"budget_cap_usd": 0.50},
        ),
        tools=tools,
    )
    output.framework_metadata.setdefault("note_buffer_size", len(note_sink.notes))
    return output


def summarize(label: str, output: AgentRunOutput) -> None:
    print(f"\n=== {label} ===")
    print(f"  cost_usd       : ${output.cost_usd:.6f}")
    print(f"  duration_ms    : {output.duration_ms}")
    print(f"  tool_calls     : {len(output.tool_calls)}")
    for call in output.tool_calls:
        is_err = "ERR" if call.result.is_error else "OK "
        content = call.result.content
        if isinstance(content, list):
            content = "<list>"
        content_str = (str(content) or "").replace("\n", " ")[:80]
        print(f"     [{is_err}] {call.tool_name}({call.arguments}) -> {content_str}")
    final = (output.final_message or "").strip().replace("\n", " ")
    print(f"  final_message  : {final[:200]}")
    note_size = output.framework_metadata.get("note_buffer_size")
    if note_size is not None:
        print(f"  notes recorded : {note_size}")


def parity_check(a: AgentRunOutput, b: AgentRunOutput) -> list[str]:
    """Return a list of mismatches (empty list = parity)."""
    mismatches: list[str] = []
    if {c.tool_name for c in a.tool_calls} != {c.tool_name for c in b.tool_calls}:
        mismatches.append(
            "tool sets differ: "
            f"{sorted(c.tool_name for c in a.tool_calls)} vs "
            f"{sorted(c.tool_name for c in b.tool_calls)}"
        )
    if not a.final_message.strip() or not b.final_message.strip():
        mismatches.append("at least one adapter returned an empty final message")
    return mismatches


async def main() -> int:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print(
            "ERROR: ANTHROPIC_API_KEY is not set. "
            "Set it in your environment (or .env) before running the smoke test.",
            file=sys.stderr,
        )
        return 1

    model = os.environ.get("PHASE0_SMOKE_MODEL", "claude-haiku-4-5")
    print(f"Smoke test using model: {model}")

    registry = FrameworkRegistry()
    registry.register(DirectAnthropicAdapter(api_key=api_key))
    registry.register(ClaudeAgentSDKAdapter(api_key=api_key))
    registry.set_default("direct_anthropic")

    try:
        direct_out = await run_one("direct_anthropic", registry, model)
    except Exception as exc:  # noqa: BLE001
        print(f"DirectAnthropicAdapter failed: {exc!r}", file=sys.stderr)
        return 2

    try:
        sdk_out = await run_one("claude_agent_sdk", registry, model)
    except Exception as exc:  # noqa: BLE001
        print(f"ClaudeAgentSDKAdapter failed: {exc!r}", file=sys.stderr)
        summarize("DirectAnthropicAdapter", direct_out)
        return 2

    summarize("DirectAnthropicAdapter", direct_out)
    summarize("ClaudeAgentSDKAdapter", sdk_out)

    mismatches = parity_check(direct_out, sdk_out)
    if mismatches:
        print("\nPARITY CHECK: mismatches found")
        for m in mismatches:
            print(f"  - {m}")
        # Mismatches at this level (tool-set differences, empty messages)
        # signal real adapter divergence; surface but don't fail — small
        # variation across adapters is expected and informative.
    else:
        print("\nPARITY CHECK: passed")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
