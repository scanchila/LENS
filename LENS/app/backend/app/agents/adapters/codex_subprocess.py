"""Codex CLI subprocess adapter.

Runs the user's local ``codex`` CLI as the LLM engine — same pattern CAR
uses for synchronous one-shot prompts (see
``codex_autorunner/integrations/github/service.py::_run_codex_sync_agent``).

For pure LLM inference (no shell tool execution by the agent itself):

    codex exec \\
      --skip-git-repo-check --ephemeral \\
      --sandbox read-only \\
      --color never \\
      --output-last-message <file> \\
      [--output-schema <file>] \\
      [-m <model>] \\
      "<prompt>" \\
      < /dev/null

The agent loop runs internally to Codex; we read the final assistant
message from the ``--output-last-message`` file. If the prompt asks for
structured JSON and an ``--output-schema`` is supplied, the model
responds in the schema's shape, which we parse.

This adapter is suitable for lens proposers, the synthesizer, and the
critic, all of which produce structured outputs and don't need their
own external-search tool calls during a single Codex run.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterable
from typing import Any
from uuid import UUID, uuid4

from ..framework import AgentFramework
from ..tool import Tool
from ..types import (
    AgentDefinition,
    AgentMessage,
    AgentRunInput,
    AgentRunOutput,
    ToolCallRecord,
    ToolResult,
)

logger = logging.getLogger(__name__)


class CodexInvocationError(RuntimeError):
    """Raised when the codex CLI fails or returns malformed output."""


class CodexSubprocessAdapter(AgentFramework):
    """Drives the codex CLI as a one-shot LLM engine.

    Tools are not exposed to Codex's agent loop in this adapter — the
    LLM produces a single structured message in response to the
    prompt. Lens runners that need retrieval call our tools directly
    (server-side) and inject the results into the prompt before
    invoking the model. This keeps cost predictable and the audit
    trail simple.
    """

    name = "codex_subprocess"

    def __init__(
        self,
        binary: str | None = None,
        model: str | None = None,
        timeout_seconds: int = 600,
        extra_args: list[str] | None = None,
    ) -> None:
        self._binary = binary or shutil.which("codex") or "codex"
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._extra_args = list(extra_args or [])

    async def run(
        self,
        agent: AgentDefinition,
        run_input: AgentRunInput,
        tools: Iterable[Tool],  # noqa: ARG002 — adapter ignores per-call tools
    ) -> AgentRunOutput:
        run_id = uuid4()
        session_id = self._extract_session_id(run_input)
        start = time.monotonic()

        # Compose final prompt from system + user. Codex `exec` accepts a
        # single prompt argument; we surface the system rules at the top
        # so the model still sees them.
        prompt_text = self._compose_prompt(agent, run_input)

        # Optional JSON schema (set via run_input.metadata["output_schema"]).
        output_schema = run_input.metadata.get("output_schema")
        # Per-call model override (e.g. ``gpt-5.5``) wins over instance default
        model_override = (
            run_input.metadata.get("model_override")
            or agent.model
            or self._model
        )

        with tempfile.TemporaryDirectory(prefix="lens-codex-") as tmpdir:
            last_message_path = os.path.join(tmpdir, "last.txt")
            schema_path: str | None = None
            if isinstance(output_schema, dict):
                schema_path = os.path.join(tmpdir, "schema.json")
                with open(schema_path, "w") as fh:
                    json.dump(output_schema, fh)

            cmd = self._build_command(
                prompt_text=prompt_text,
                model=model_override,
                last_message_path=last_message_path,
                schema_path=schema_path,
            )

            logger.info(
                "codex.run agent=%s session=%s model=%s",
                agent.name,
                session_id,
                model_override,
            )

            stdout, stderr, returncode = await self._spawn(cmd)

            if returncode != 0:
                detail = (stderr or stdout or "").strip()[-1500:]
                raise CodexInvocationError(
                    f"codex exit={returncode}: {detail or '<no output>'}"
                )

            final_message = ""
            if os.path.exists(last_message_path):
                final_message = open(last_message_path).read().strip()
            if not final_message:
                # Fallback: parse stdout. Codex prints the final reply to
                # stdout near the end; we just use the whole stdout if
                # output-last-message is empty for any reason.
                final_message = stdout.strip()

        duration_ms = int((time.monotonic() - start) * 1000)

        transcript: list[AgentMessage] = [
            AgentMessage(role="user", content=run_input.initial_prompt),
            AgentMessage(role="assistant", content=final_message),
        ]
        return AgentRunOutput(
            run_id=run_id,
            final_message=final_message,
            transcript=transcript,
            tool_calls=[],
            cost_usd=0.0,  # Codex CLI doesn't currently surface per-call cost
            duration_ms=duration_ms,
            framework_metadata={
                "adapter": self.name,
                "model": model_override or "<codex-default>",
                "binary": self._binary,
            },
        )

    async def health_check(self) -> bool:
        try:
            proc = await asyncio.create_subprocess_exec(
                self._binary,
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.wait(), timeout=10)
            return proc.returncode == 0
        except (FileNotFoundError, asyncio.TimeoutError, Exception):  # noqa: BLE001
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
    def _compose_prompt(agent: AgentDefinition, run_input: AgentRunInput) -> str:
        # Codex exec takes a single prompt argument; we prepend the system
        # prompt as a clearly delimited preamble. The LLM treats it as the
        # rules-of-the-game even though Codex itself doesn't have a separate
        # system role for this CLI surface.
        return (
            f"# System\n{agent.system_prompt.strip()}\n\n"
            f"# Task\n{run_input.initial_prompt.strip()}\n"
        )

    def _build_command(
        self,
        *,
        prompt_text: str,
        model: str | None,
        last_message_path: str,
        schema_path: str | None,
    ) -> list[str]:
        cmd: list[str] = [
            self._binary,
            "exec",
            "--skip-git-repo-check",
            "--ephemeral",
            "--sandbox",
            "read-only",
            "--color",
            "never",
            "--output-last-message",
            last_message_path,
        ]
        if model:
            cmd.extend(["-m", model])
        if schema_path:
            cmd.extend(["--output-schema", schema_path])
        cmd.extend(self._extra_args)
        cmd.append(prompt_text)
        return cmd

    async def _spawn(self, cmd: list[str]) -> tuple[str, str, int]:
        # Use asyncio.create_subprocess_exec so we don't block the event
        # loop while Codex thinks. Stdin must be /dev/null because codex
        # exec reads stdin if it's a TTY.
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=self._timeout_seconds
            )
        except asyncio.TimeoutError as exc:
            with contextlib_suppress():
                proc.kill()
                await proc.wait()
            raise CodexInvocationError(
                f"codex timed out after {self._timeout_seconds}s"
            ) from exc

        return (
            (stdout_b or b"").decode("utf-8", errors="replace"),
            (stderr_b or b"").decode("utf-8", errors="replace"),
            proc.returncode or 0,
        )


def parse_json_response(text: str) -> Any:
    """Best-effort parse of a JSON blob from a Codex final message.

    Codex with ``--output-schema`` is supposed to return a single JSON
    document, but in practice the model can prepend a thought line.
    Strip common prefixes / fences and try again.
    """
    text = text.strip()
    # Strip code fences.
    if text.startswith("```"):
        # ``` or ```json ... ```
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Attempt to find a JSON object/array anywhere in the text.
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if 0 <= start < end:
            slice_ = text[start : end + 1]
            try:
                return json.loads(slice_)
            except json.JSONDecodeError:
                continue
    raise ValueError("could not parse JSON from codex response")


class contextlib_suppress:
    """Tiny stand-in for ``contextlib.suppress`` to keep the import surface
    minimal here (this module is imported by the lens runner)."""

    def __enter__(self) -> "contextlib_suppress":
        return self

    def __exit__(self, exc_type: type[BaseException] | None, *_: Any) -> bool:
        # Suppress everything for the brief kill/wait fallback.
        return exc_type is not None
