"""``queue_evidence_dossier`` tool — emit a CAR evidence_dossier ticket.

The Orchestrator calls this when a candidate crosses the V̂/Ĉ threshold that
warrants slow deep research. The tool writes a markdown ticket file into
the configured CAR ticket directory using the TICKET-047 template and
records a ``dossier_jobs`` row so :mod:`app.workers.dossier_ingest_worker`
can correlate the ticket with its candidate when CAR finishes the run.

The tool returns immediately. CAR's actual deep research happens
out-of-band; downstream callers poll via ``read_dossier`` (PR 5+) or
listen on the ``dossier_ready`` Postgres NOTIFY channel.

Build vs. runtime ticket numbering convention:
    - 001-999  : build tickets (the implementation spine; static)
    - 1000+    : runtime evidence dossiers (dynamic; one per candidate)

The runtime range starts at 1000 even when no runtime tickets exist yet.
"""

from __future__ import annotations

import importlib.util
import logging
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from sqlmodel import Session

from app.core.config import settings
from app.core.db import engine
from app.models import DossierJob

from ..tool import Tool
from ..types import ToolContext, ToolResult, ToolSpec

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# The first runtime ticket index. Build tickets occupy 1-999; runtime
# evidence dossiers start at 1000 so the two ranges never collide.
_RUNTIME_TICKET_FLOOR = 1000

# Match TICKET-NNNN- where NNNN is at least 3 digits. We accept any number
# of digits >= 3 because some legacy tickets may be 3- or 4-digit.
_TICKET_FILENAME_RE = re.compile(r"^TICKET-(\d{3,})-")

# Repo-relative path to the CAR linter; resolved relative to the
# *parent* of the ticket directory (the ``.codex-autorunner/`` root).
_LINT_SCRIPT_RELATIVE = Path("bin") / "lint_tickets.py"


# ---------------------------------------------------------------------------
# Renderer import (vendored at LENS/templates/render_evidence_dossier.py)
# ---------------------------------------------------------------------------


def _import_renderer() -> Any:
    """Import the LENS render_evidence_dossier module via filesystem path.

    The renderer lives under ``LENS/templates/`` (a sibling of the backend
    package), not on the importable package path. We load it via
    ``importlib.util.spec_from_file_location`` so the agent runtime does not
    need a fragile sys.path mutation at startup.
    """
    backend_root = Path(__file__).resolve().parents[3]
    repo_root = backend_root.parent.parent.parent  # backend -> app -> LENS -> repo
    candidate = repo_root / "LENS" / "templates" / "render_evidence_dossier.py"
    if not candidate.exists():
        raise FileNotFoundError(
            f"Could not locate render_evidence_dossier.py at {candidate}"
        )
    name = "lens_render_evidence_dossier"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, candidate)
    if spec is None or spec.loader is None:
        raise ImportError(f"failed to load render_evidence_dossier from {candidate}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_ticket_dir(override: str | Path | None = None) -> Path:
    """Resolve the configured CAR ticket directory to an absolute path.

    Relative paths are resolved against the repo root (the LENS folder's
    parent). Tests pass ``override`` to point at an isolated tmp dir.
    """
    if override is not None:
        return Path(override).resolve()
    configured = Path(settings.LENS_CAR_TICKET_DIR)
    if configured.is_absolute():
        return configured.resolve()
    backend_root = Path(__file__).resolve().parents[3]
    repo_root = backend_root.parent.parent.parent
    return (repo_root / configured).resolve()


def _next_runtime_index(ticket_dir: Path) -> int:
    """Return the next available runtime ticket index (>= 1000)."""
    if not ticket_dir.exists():
        return _RUNTIME_TICKET_FLOOR
    runtime_indices: list[int] = []
    for entry in ticket_dir.iterdir():
        if not entry.is_file() or entry.suffix != ".md":
            continue
        match = _TICKET_FILENAME_RE.match(entry.name)
        if not match:
            continue
        idx = int(match.group(1))
        if idx >= _RUNTIME_TICKET_FLOOR:
            runtime_indices.append(idx)
    if not runtime_indices:
        return _RUNTIME_TICKET_FLOOR
    return max(runtime_indices) + 1


def _short_candidate(candidate_id: str) -> str:
    """First 8 chars of the candidate UUID (no dashes), for filenames."""
    return candidate_id.replace("-", "")[:8] or "anon"


def _run_lint(ticket_dir: Path) -> tuple[bool, str]:
    """Run CAR's lint_tickets.py against the ticket dir's parent.

    Returns (ok, combined_output). Degrades to ok=True if the lint script
    is absent (test environments without CAR installed).
    """
    ca_root = ticket_dir.parent  # the ``.codex-autorunner/`` directory
    lint_path = ca_root / _LINT_SCRIPT_RELATIVE
    if not lint_path.exists():
        logger.info(
            "lint_tickets.py not found at %s; skipping lint (likely test env)",
            lint_path,
        )
        return True, ""
    python = shutil.which("python3") or shutil.which("python") or sys.executable
    try:
        result = subprocess.run(
            [python, str(lint_path)],
            cwd=str(ca_root),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except Exception as exc:  # subprocess failed to spawn
        return False, f"lint subprocess failed: {exc}"
    combined = (result.stdout or "") + (result.stderr or "")
    return (result.returncode == 0), combined


def _insert_dossier_job(
    *,
    ticket_id: str,
    candidate_id: str,
    lens_attribution: str,
    ticket_path: Path,
) -> None:
    job = DossierJob(
        ticket_id=ticket_id,
        candidate_id=uuid.UUID(candidate_id),
        status="queued",
        lens_attribution=lens_attribution,
        ticket_path=str(ticket_path),
    )
    with Session(engine) as session:
        session.add(job)
        session.commit()


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------


class QueueEvidenceDossierTool(Tool):
    spec = ToolSpec(
        name="queue_evidence_dossier",
        description=(
            "Emit a CAR evidence_dossier ticket for a high-V̂ candidate. "
            "Writes a markdown ticket file into the configured CAR ticket "
            "directory and records a dossier_jobs row. Returns immediately "
            "with the ticket_id; the caller polls or listens for "
            "'dossier_ready' to consume the result."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "candidate_id": {
                    "type": "string",
                    "format": "uuid",
                    "description": "UUID of the candidate this dossier supports.",
                },
                "claim_summary": {
                    "type": "string",
                    "description": (
                        "Concise statement of the claim Hermes should research."
                    ),
                },
                "lens_attribution": {
                    "type": "string",
                    "description": (
                        "Name of the lens that produced the candidate (e.g. "
                        "'cross_domain_transfer')."
                    ),
                },
            },
            "required": ["candidate_id", "claim_summary", "lens_attribution"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "ticket_id": {"type": "string"},
                "ticket_file": {"type": "string"},
                "status": {"type": "string", "enum": ["queued"]},
            },
            "required": ["ticket_id", "ticket_file", "status"],
        },
    )

    def __init__(self, *, ticket_dir_override: str | Path | None = None) -> None:
        # ``ticket_dir_override`` is a non-public seam for tests; production
        # code uses settings.LENS_CAR_TICKET_DIR.
        self._ticket_dir_override = ticket_dir_override

    async def execute(self, args: dict[str, Any], ctx: ToolContext) -> ToolResult:
        candidate_id = str(args.get("candidate_id") or "").strip()
        claim_summary = str(args.get("claim_summary") or "").strip()
        lens_attribution = str(args.get("lens_attribution") or "").strip()

        if not candidate_id:
            return ToolResult(
                content="candidate_id is required",
                is_error=True,
                metadata={"reason": "missing_candidate_id"},
            )
        if not claim_summary:
            return ToolResult(
                content="claim_summary is required",
                is_error=True,
                metadata={"reason": "missing_claim_summary"},
            )
        if not lens_attribution:
            return ToolResult(
                content="lens_attribution is required",
                is_error=True,
                metadata={"reason": "missing_lens_attribution"},
            )
        try:
            uuid.UUID(candidate_id)
        except (ValueError, TypeError):
            return ToolResult(
                content=f"candidate_id is not a valid UUID: {candidate_id!r}",
                is_error=True,
                metadata={"reason": "invalid_candidate_id"},
            )

        ticket_dir = _resolve_ticket_dir(self._ticket_dir_override)
        ticket_dir.mkdir(parents=True, exist_ok=True)

        renderer = _import_renderer()
        index = _next_runtime_index(ticket_dir)
        short_id = _short_candidate(candidate_id)
        out_path = ticket_dir / f"TICKET-{index:04d}-evidence-{short_id}.md"

        try:
            result = renderer.render_dossier_ticket(
                candidate_id=candidate_id,
                claim_summary=claim_summary,
                lens_attribution=lens_attribution,
                out_path=out_path,
            )
        except Exception as exc:
            return ToolResult(
                content=f"render failed: {exc}",
                is_error=True,
                metadata={"reason": "render_failed"},
            )

        ok, lint_output = _run_lint(ticket_dir)
        if not ok:
            try:
                out_path.unlink()
            except FileNotFoundError:
                pass
            return ToolResult(
                content=f"lint_tickets.py failed:\n{lint_output}",
                is_error=True,
                metadata={"reason": "lint_failed", "lint_output": lint_output},
            )

        try:
            _insert_dossier_job(
                ticket_id=result.ticket_id,
                candidate_id=candidate_id,
                lens_attribution=lens_attribution,
                ticket_path=out_path,
            )
        except Exception as exc:
            try:
                out_path.unlink()
            except FileNotFoundError:
                pass
            return ToolResult(
                content=f"dossier_jobs insert failed: {exc}",
                is_error=True,
                metadata={"reason": "db_insert_failed"},
            )

        return ToolResult(
            content=(f"Queued evidence dossier {result.ticket_id} ({out_path.name})."),
            is_error=False,
            metadata={
                "ticket_id": result.ticket_id,
                "ticket_file": str(out_path),
                "status": "queued",
            },
        )
