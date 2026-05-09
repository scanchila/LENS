"""Pure-function tests for ``app.workers.dossier_parser``.

No DB or AGE involvement; runs under the LENS-local conftest that no-ops
the parent backend's autouse Postgres fixture.
"""

from __future__ import annotations

import pytest

from app.workers.dossier_parser import (
    DossierParseError,
    parse_dossier_text,
)

SAMPLE = """---
title: "Evidence dossier — synthetic"
agent: hermes
done: true
ticket_id: "tkt_abc123"
candidate_id: "11111111-2222-3333-4444-555555555555"
lens_attribution: "cross_domain_transfer"
model: claude-sonnet-4-6
---

## Context

<!-- BEGIN: context -->
ctx
<!-- END: context -->

## Search plan

<!-- BEGIN: search_plan -->
plan
<!-- END: search_plan -->

## Sources found

<!-- BEGIN: sources -->
1. [Paper A](https://example.com/a) — paper — Strong support.
2. [HN Thread](https://news.ycombinator.com/x) — forum — Mixed signal.
3. [Blog post](https://example.com/b) — blog — Direct refutation.
<!-- END: sources -->

## Claims extracted

<!-- BEGIN: claims -->
- Adoption is accelerating. — supports — based on sources [1, 2]
- Cost is prohibitive at scale. — refutes — based on sources [3]
<!-- END: claims -->

## Confidence note

<!-- BEGIN: confidence -->
note
<!-- END: confidence -->

## Run record

<!-- BEGIN: run_record -->
- Termination: completed
<!-- END: run_record -->
"""


def test_parses_full_template() -> None:
    parsed = parse_dossier_text(SAMPLE)
    assert parsed.candidate_id == "11111111-2222-3333-4444-555555555555"
    assert parsed.ticket_id == "tkt_abc123"
    assert parsed.done is True
    assert len(parsed.sources) == 3
    assert parsed.sources[0].url == "https://example.com/a"
    assert parsed.sources[0].kind == "paper"
    assert len(parsed.claims) == 2
    assert parsed.claims[0].valence == "supports"
    assert parsed.claims[0].source_indices == (1, 2)
    assert parsed.claims[1].valence == "refutes"


def test_payload_hash_is_stable_across_reorder() -> None:
    a = parse_dossier_text(SAMPLE)
    swapped = SAMPLE.replace(
        "1. [Paper A](https://example.com/a) — paper — Strong support.\n"
        "2. [HN Thread](https://news.ycombinator.com/x) — forum — Mixed signal.",
        "1. [HN Thread](https://news.ycombinator.com/x) — forum — Mixed signal.\n"
        "2. [Paper A](https://example.com/a) — paper — Strong support.",
    )
    b = parse_dossier_text(swapped)
    assert a.payload_hash == b.payload_hash


def test_missing_required_section_raises() -> None:
    broken = SAMPLE.replace("<!-- BEGIN: sources -->", "<!-- omitted -->")
    with pytest.raises(DossierParseError):
        parse_dossier_text(broken)


def test_missing_frontmatter_raises() -> None:
    with pytest.raises(DossierParseError):
        parse_dossier_text("no frontmatter here")


def test_done_false_is_parsed() -> None:
    body = SAMPLE.replace("done: true", "done: false")
    parsed = parse_dossier_text(body)
    assert parsed.done is False


def test_neutral_valence_kept() -> None:
    body = SAMPLE.replace(
        "- Adoption is accelerating. — supports — based on sources [1, 2]",
        "- Things are stable. — neutral — based on sources [1]",
    )
    parsed = parse_dossier_text(body)
    valences = {c.valence for c in parsed.claims}
    assert "neutral" in valences


def test_empty_sources_section_yields_no_sources() -> None:
    body = SAMPLE.replace(
        "1. [Paper A](https://example.com/a) — paper — Strong support.\n"
        "2. [HN Thread](https://news.ycombinator.com/x) — forum — Mixed signal.\n"
        "3. [Blog post](https://example.com/b) — blog — Direct refutation.",
        "_No sources found._",
    )
    parsed = parse_dossier_text(body)
    assert parsed.sources == []
