#!/usr/bin/env python3
"""Render the ``evidence_dossier.md`` template with concrete params.

CAR's ``car templates apply`` does not do parameter substitution (it can only
override the ``agent:`` frontmatter field and inject provenance). LENS therefore
ships its own thin renderer that produces a lint-clean ticket file from
``LENS/templates/evidence_dossier.md`` and a small set of params.

Usage as a library (will be the call site for TICKET-045's
``queue_evidence_dossier`` tool once PR 1 lands):

    from lens.templates.render_evidence_dossier import render_dossier_ticket

    render_dossier_ticket(
        candidate_id="cand_abc123",
        claim_summary="AI agents will replace SaaS spreadsheets within 5 years.",
        lens_attribution="cross_domain_transfer",
        out_path=Path(".codex-autorunner/tickets/TICKET-1003-evidence-dossier.md"),
    )

Usage from the shell:

    python3 lens/templates/render_evidence_dossier.py \\
        --candidate-id cand_abc123 \\
        --claim-summary "AI agents will replace SaaS spreadsheets" \\
        --lens-attribution cross_domain_transfer \\
        --out tickets/TICKET-1003-evidence-dossier.md
"""

from __future__ import annotations

import argparse
import re
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

TEMPLATE_PATH = Path(__file__).resolve().parent / "evidence_dossier.md"

_PLACEHOLDER_RE = re.compile(r"\{([a-z_][a-z0-9_]*)\}")
_TICKET_ID_RE = re.compile(r"^[A-Za-z0-9._-]{6,128}$")
_CLAIM_SUMMARY_SHORT_MAX = 80


@dataclass(frozen=True)
class RenderResult:
    content: str
    ticket_id: str
    out_path: Path | None


def _short_summary(text: str, *, max_len: int = _CLAIM_SUMMARY_SHORT_MAX) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 1].rstrip() + "…"


def _quote_yaml_scalar(value: str) -> str:
    """Quote a YAML scalar value so it survives the CAR linter's loader."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{escaped}"'


def _new_ticket_id() -> str:
    return f"tkt_{uuid.uuid4().hex}"


def _validate_ticket_id(ticket_id: str) -> str:
    if not _TICKET_ID_RE.match(ticket_id):
        raise ValueError(
            f"ticket_id {ticket_id!r} does not match {_TICKET_ID_RE.pattern}"
        )
    return ticket_id


def render_dossier_content(
    *,
    candidate_id: str,
    claim_summary: str,
    lens_attribution: str,
    ticket_id: str | None = None,
    template_path: Path = TEMPLATE_PATH,
) -> RenderResult:
    """Render the template body with the given params. Does not write to disk."""
    if not candidate_id.strip():
        raise ValueError("candidate_id must be a non-empty string")
    if not claim_summary.strip():
        raise ValueError("claim_summary must be a non-empty string")
    if not lens_attribution.strip():
        raise ValueError("lens_attribution must be a non-empty string")

    resolved_ticket_id = _validate_ticket_id(ticket_id or _new_ticket_id())

    raw = template_path.read_text(encoding="utf-8")

    substitutions = {
        "candidate_id": candidate_id,
        "claim_summary": claim_summary,
        "claim_summary_short": _short_summary(claim_summary),
        "lens_attribution": lens_attribution,
        "ticket_id": resolved_ticket_id,
    }

    # YAML scalars where the placeholder is the *entire* value of the key.
    # These get wrapped in double quotes so arbitrary user text can't break the
    # YAML parser.
    bare_yaml_scalar_keys = {
        "ticket_id",
        "candidate_id",
        "lens_attribution",
    }

    # Embedded YAML scalars: the placeholder lives inside an already-quoted
    # string (the title field). The value must be escaped for inclusion
    # *without* adding outer quotes.
    embedded_yaml_keys = {
        "claim_summary_short",
    }

    def _yaml_inner_escape(text: str) -> str:
        return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in substitutions:
            raise KeyError(f"Unknown placeholder {{{key}}} in template")
        value = substitutions[key]
        line_start = raw.rfind("\n", 0, match.start()) + 1
        line_end = raw.find("\n", match.end())
        if line_end == -1:
            line_end = len(raw)
        line = raw[line_start:line_end]
        stripped = line.lstrip()
        if key in bare_yaml_scalar_keys and stripped.startswith(f"{key}:"):
            return _quote_yaml_scalar(value)
        if key in embedded_yaml_keys and stripped.startswith("title:"):
            return _yaml_inner_escape(value)
        return value

    rendered = _PLACEHOLDER_RE.sub(replace, raw)

    leftover = _PLACEHOLDER_RE.search(rendered)
    if leftover:
        raise RuntimeError(
            f"Unsubstituted placeholder remained after render: {leftover.group(0)}"
        )

    return RenderResult(content=rendered, ticket_id=resolved_ticket_id, out_path=None)


def render_dossier_ticket(
    *,
    candidate_id: str,
    claim_summary: str,
    lens_attribution: str,
    out_path: Path,
    ticket_id: str | None = None,
    template_path: Path = TEMPLATE_PATH,
    overwrite: bool = False,
) -> RenderResult:
    """Render and write the ticket file to ``out_path``."""
    result = render_dossier_content(
        candidate_id=candidate_id,
        claim_summary=claim_summary,
        lens_attribution=lens_attribution,
        ticket_id=ticket_id,
        template_path=template_path,
    )

    out_path = Path(out_path)
    if out_path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing ticket: {out_path}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(result.content, encoding="utf-8")

    return RenderResult(
        content=result.content, ticket_id=result.ticket_id, out_path=out_path
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--claim-summary", required=True)
    parser.add_argument("--lens-attribution", required=True)
    parser.add_argument(
        "--ticket-id", default=None, help="Override the generated tkt_<hex> id"
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Path to write the rendered ticket markdown",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite the output file if it already exists",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    try:
        result = render_dossier_ticket(
            candidate_id=args.candidate_id,
            claim_summary=args.claim_summary,
            lens_attribution=args.lens_attribution,
            ticket_id=args.ticket_id,
            out_path=args.out,
            overwrite=args.overwrite,
        )
    except (FileExistsError, ValueError, KeyError, RuntimeError) as exc:
        print(f"render_evidence_dossier: {exc}", file=sys.stderr)
        return 2
    print(f"Wrote {result.out_path} (ticket_id={result.ticket_id})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
