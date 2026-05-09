"""Ask-user tool — pose a clarifying question to the human.

Implementation strategy: the tool itself is a thin shell around an
injectable async callable ``UserPrompter``. The orchestrator decides
how to wire that callable: in a CLI smoke test it reads from stdin;
in the web UI it sends a WebSocket message to the active session and
awaits the response; in batch mode it can return a fixed answer.

This keeps the agent runtime decoupled from any specific UX layer.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from ..tool import Tool
from ..types import ToolContext, ToolResult, ToolSpec

# Signature of the function that delivers a user's answer back.
UserPrompter = Callable[[str], Awaitable[str]]


class AskUserTool(Tool):
    spec = ToolSpec(
        name="ask_user",
        description=(
            "Pose a clarifying or validating question to the user and wait for "
            "their answer. Use sparingly — only when the answer would meaningfully "
            "change the rest of the run. Each call blocks the agent until the user "
            "responds, so questions should be specific and minimal."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The question to ask the user, in natural language.",
                },
                "expected_answer_kind": {
                    "type": "string",
                    "description": (
                        "Optional hint about the expected answer shape "
                        "(e.g. 'one of A/B/C', 'short phrase', 'yes/no')."
                    ),
                },
            },
            "required": ["question"],
        },
    )

    def __init__(self, prompter: UserPrompter) -> None:
        self._prompter = prompter

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        question = str(args.get("question", "")).strip()
        if not question:
            return ToolResult(content="Empty question; nothing asked.", is_error=True)
        try:
            answer = await self._prompter(question)
        except Exception as exc:  # noqa: BLE001 — surface to the agent
            return ToolResult(
                content=f"User-prompt mechanism failed: {exc!r}", is_error=True
            )
        return ToolResult(content=str(answer), is_error=False)
