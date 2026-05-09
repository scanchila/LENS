"""Note tool — append a finding to the session's note buffer.

The orchestrator owns the note buffer (a plain list) and constructs one
NoteTool instance per session, passing the buffer in. Each tool call
appends; the orchestrator can read the buffer back at any point to
produce intermediate UX or include in subsequent agent-run prompts.

The buffer is intentionally not stored on ToolContext: notes are a
lens-proposer-style scratchpad, not cross-tool shared state.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..tool import Tool
from ..types import ToolContext, ToolResult, ToolSpec


class NoteEntry(dict[str, Any]):
    """Loosely-typed note entry. Keys: ``timestamp``, ``content``,
    ``tags``, ``agent_name``."""


class NoteTool(Tool):
    spec = ToolSpec(
        name="note",
        description=(
            "Persist an intermediate finding into the session's note buffer. "
            "Use during the SCAN phase to track candidate patterns and during "
            "later phases to leave breadcrumbs for the synthesizer. Notes "
            "are visible across the rest of this run."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The note content. One observation per call.",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional tags for later filtering (e.g. 'pattern', 'candidate', 'gap').",
                },
            },
            "required": ["content"],
        },
    )

    def __init__(self, buffer: list[NoteEntry]) -> None:
        # Buffer is a reference shared with the orchestrator. Mutating it
        # here is intentional and visible to the rest of the run.
        self._buffer = buffer

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        entry: NoteEntry = NoteEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            content=str(args.get("content", "")),
            tags=list(args.get("tags") or []),
            agent_name=ctx.parent_agent_name,
        )
        self._buffer.append(entry)
        return ToolResult(
            content=f"Noted ({len(self._buffer)} note(s) in buffer).",
            is_error=False,
            metadata={"index": len(self._buffer) - 1},
        )
