"""Tests for ``LENS/templates/evidence_dossier.md`` + render helper.

These exercise the template + renderer that PR 4 part 2 (TICKET-045) will call
into when emitting evidence_dossier tickets.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[5]
LENS_DIR = REPO_ROOT / "LENS"
RENDER_PATH = LENS_DIR / "templates" / "render_evidence_dossier.py"


def _discover_car_lint_impl() -> Path | None:
    """Find CAR's portable ticket lint implementation.

    The lint impl is gitignored in the LENS worktree, so we search known
    sibling locations and fall back to the ``LENS_CAR_LINT_IMPL`` env var.
    """
    override = os.environ.get("LENS_CAR_LINT_IMPL")
    if override:
        path = Path(override)
        if path.exists():
            return path
    candidates = [
        REPO_ROOT
        / ".."
        / ".."
        / "hackathon"
        / "car-hub"
        / "lens"
        / ".codex-autorunner"
        / "bin"
        / "_ticket_lint_impl.py",
        Path.home()
        / "Neuryta"
        / "hackathon"
        / "car-hub"
        / "lens"
        / ".codex-autorunner"
        / "bin"
        / "_ticket_lint_impl.py",
    ]
    for c in candidates:
        c = c.resolve()
        if c.exists():
            return c
    return None


CAR_LINT_IMPL = _discover_car_lint_impl()


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, f"cannot load {path}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def render_mod():
    return _load_module("render_evidence_dossier", RENDER_PATH)


@pytest.fixture(scope="module")
def car_lint():
    if CAR_LINT_IMPL is None:
        pytest.skip(
            "CAR lint impl not found; set LENS_CAR_LINT_IMPL to enable lint test"
        )
    return _load_module("_car_ticket_lint_impl", CAR_LINT_IMPL)


def test_template_applies(render_mod, tmp_path):
    out = tmp_path / "TICKET-1003-evidence-dossier.md"
    result = render_mod.render_dossier_ticket(
        candidate_id="cand_demo123",
        claim_summary="AI agents will replace SaaS spreadsheets within 5 years.",
        lens_attribution="cross_domain_transfer",
        out_path=out,
    )

    assert result.out_path == out
    assert result.ticket_id.startswith("tkt_")
    body = out.read_text(encoding="utf-8")

    # Frontmatter present and lint-relevant fields populated.
    assert body.startswith("---\n")
    assert "agent: hermes" in body
    assert "done: false" in body
    assert f'ticket_id: "{result.ticket_id}"' in body
    assert 'candidate_id: "cand_demo123"' in body
    assert 'lens_attribution: "cross_domain_transfer"' in body
    assert "model: claude-sonnet-4-6" in body

    # All section markers present.
    for section in (
        "context",
        "search_plan",
        "sources",
        "claims",
        "confidence",
        "run_record",
    ):
        assert f"<!-- BEGIN: {section} -->" in body
        assert f"<!-- END: {section} -->" in body

    # No raw placeholders remain.
    assert "{candidate_id}" not in body
    assert "{claim_summary}" not in body
    assert "{lens_attribution}" not in body
    assert "{ticket_id}" not in body
    assert "{claim_summary_short}" not in body


def test_lint_clean(render_mod, car_lint, tmp_path):
    tickets_dir = tmp_path / ".codex-autorunner" / "tickets"
    tickets_dir.mkdir(parents=True)

    render_mod.render_dossier_ticket(
        candidate_id="cand_lint_check",
        claim_summary="A specific testable claim about a real phenomenon.",
        lens_attribution="contradiction_surfacing",
        out_path=tickets_dir / "TICKET-1004-evidence-dossier.md",
    )

    rc = car_lint.run_ticket_lint(tickets_dir)
    assert rc == 0


def test_short_summary_truncation(render_mod):
    long_text = "x" * 200
    short = render_mod._short_summary(long_text, max_len=80)
    assert len(short) <= 80
    assert short.endswith("…")


def test_render_rejects_empty_inputs(render_mod):
    with pytest.raises(ValueError):
        render_mod.render_dossier_content(
            candidate_id="",
            claim_summary="ok",
            lens_attribution="lens",
        )
    with pytest.raises(ValueError):
        render_mod.render_dossier_content(
            candidate_id="cand",
            claim_summary="   ",
            lens_attribution="lens",
        )
    with pytest.raises(ValueError):
        render_mod.render_dossier_content(
            candidate_id="cand",
            claim_summary="ok",
            lens_attribution="",
        )


def test_quotes_in_claim_summary_dont_break_yaml(render_mod, car_lint, tmp_path):
    tickets_dir = tmp_path / ".codex-autorunner" / "tickets"
    tickets_dir.mkdir(parents=True)
    render_mod.render_dossier_ticket(
        candidate_id="cand_quotes",
        claim_summary='He said "hello \\ world" — done.',
        lens_attribution="lens_with_special_chars_!@",
        out_path=tickets_dir / "TICKET-1005-evidence-dossier.md",
    )
    assert car_lint.run_ticket_lint(tickets_dir) == 0
