"""Tests for ``LENS/scripts/gather_evidence.py``.

The live test (``test_basic_run``) requires real network access + an
``ANTHROPIC_API_KEY``, so it is gated on ``LENS_LIVE_API=1``.

The budget-abort test mocks both the search backends and the LLM client.
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
GATHER_PATH = LENS_DIR / "scripts" / "gather_evidence.py"


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
def gather_mod():
    return _load_module("gather_evidence", GATHER_PATH)


def _make_ticket(render_mod, tmp_path: Path) -> Path:
    out = tmp_path / "TICKET-1010-evidence-dossier.md"
    render_mod.render_dossier_ticket(
        candidate_id="cand_test",
        claim_summary="Test claim about a measurable phenomenon.",
        lens_attribution="test_lens",
        out_path=out,
    )
    return out


class _FakeLLM:
    """Stub LLM that returns canned text + reports a fixed token usage."""

    def __init__(
        self,
        *,
        per_call_input_tokens: int = 10_000,
        per_call_output_tokens: int = 1_000,
        summary_text: str = "A canned one-sentence summary about the source.",
        claims_text: str = (
            '{"claims": [{"text":"Synthetic claim A","valence":"supports","sources":[1]},'
            '{"text":"Synthetic claim B","valence":"refutes","sources":[2]}]}'
        ),
    ) -> None:
        self.calls = 0
        self.per_call_input_tokens = per_call_input_tokens
        self.per_call_output_tokens = per_call_output_tokens
        self.summary_text = summary_text
        self.claims_text = claims_text

    def messages_create(self, *, system: str, user: str, max_tokens: int = 256):
        self.calls += 1
        text = (
            self.claims_text
            if "Extract 5–10 ATOMIC sub-claims" in user
            else self.summary_text
        )
        usage = {
            "input_tokens": self.per_call_input_tokens,
            "output_tokens": self.per_call_output_tokens,
        }
        return text, usage


def _fake_extract_text(_source) -> str:
    return "Stub raw text body for testing."


@pytest.mark.skipif(
    os.environ.get("LENS_LIVE_API") != "1",
    reason="live API gated behind LENS_LIVE_API=1",
)
def test_basic_run(render_mod, gather_mod, tmp_path):
    ticket = _make_ticket(render_mod, tmp_path)
    cfg = gather_mod.GatherConfig(
        candidate_id="cand_test",
        claim="AI agents will replace SaaS spreadsheets within 5 years",
        ticket_path=ticket,
        cost_cap_usd=1.00,
    )
    result = gather_mod.gather_evidence(cfg)
    assert result.termination in {"completed", "budget_aborted"}
    assert len(result.sources) >= 5
    assert len(result.claims) >= 3
    body = ticket.read_text(encoding="utf-8")
    assert "<!-- BEGIN: sources -->" in body
    assert "<!-- END: sources -->" in body
    assert result.ledger.spend_usd <= 1.00


def test_budget_abort(render_mod, gather_mod, tmp_path):
    ticket = _make_ticket(render_mod, tmp_path)

    def fake_search_with_hits(_claim):
        return [
            gather_mod.Source(
                title=f"Source {i}",
                url=f"https://example.com/src{i}",
                kind="web",
                backend="fake",
                raw_text="Excerpt body about the test claim.",
            )
            for i in range(3)
        ]

    backends = [("fake", fake_search_with_hits)]
    # Pricing math: 10k in @ $3/Mtok + 1k out @ $15/Mtok = $0.045/call.
    # Cap at $0.05 → first call passes, second call must trip budget guard.
    llm = _FakeLLM(per_call_input_tokens=10_000, per_call_output_tokens=1_000)
    cfg = gather_mod.GatherConfig(
        candidate_id="cand_budget",
        claim="A claim",
        ticket_path=ticket,
        cost_cap_usd=0.05,
    )
    result = gather_mod.gather_evidence(
        cfg,
        backends=backends,
        llm=llm,
        extract_text_fn=_fake_extract_text,
    )

    assert result.termination == "budget_aborted"
    assert result.ledger.spend_usd > 0
    body = ticket.read_text(encoding="utf-8")
    assert "Termination: **budget_aborted**" in body
    assert "<!-- BEGIN: run_record -->" in body


def test_replace_section_idempotent(gather_mod, render_mod, tmp_path):
    ticket = _make_ticket(render_mod, tmp_path)
    body = ticket.read_text(encoding="utf-8")
    body2 = gather_mod.replace_section(body, "sources", "FIRST")
    body3 = gather_mod.replace_section(body2, "sources", "SECOND")
    assert "SECOND" in body3
    assert "FIRST" not in body3
    # Markers preserved
    assert "<!-- BEGIN: sources -->" in body3
    assert "<!-- END: sources -->" in body3


def test_replace_section_missing_marker_raises(gather_mod):
    with pytest.raises(ValueError):
        gather_mod.replace_section("no markers here", "sources", "x")


def test_parse_claims_handles_fenced_json(gather_mod):
    raw = '```json\n{"claims":[{"text":"x","valence":"supports","sources":[1,2]}]}\n```'
    out = gather_mod._parse_claims_json(raw)
    assert len(out) == 1
    assert out[0].text == "x"
    assert out[0].valence == "supports"
    assert out[0].source_indices == [1, 2]


def test_parse_claims_normalizes_invalid_valence(gather_mod):
    raw = '{"claims":[{"text":"x","valence":"bogus","sources":[]}]}'
    out = gather_mod._parse_claims_json(raw)
    assert out[0].valence == "neutral"


def test_no_backends_yields_empty_dossier(render_mod, gather_mod, tmp_path):
    ticket = _make_ticket(render_mod, tmp_path)
    result = gather_mod.gather_evidence(
        gather_mod.GatherConfig(
            candidate_id="cand_empty",
            claim="A claim",
            ticket_path=ticket,
            cost_cap_usd=1.00,
        ),
        backends=[],
        llm=_FakeLLM(),
        extract_text_fn=_fake_extract_text,
    )
    assert result.termination == "completed"
    assert result.sources == []
    body = ticket.read_text(encoding="utf-8")
    assert "_No sources found._" in body
