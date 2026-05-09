---
title: "Evidence dossier — {claim_summary_short}"
agent: hermes
done: false
ticket_id: {ticket_id}
candidate_id: {candidate_id}
lens_attribution: {lens_attribution}
model: claude-sonnet-4-6
---

## Context

<!-- BEGIN: context -->
**Candidate:** {candidate_id}
**Lens attribution:** {lens_attribution}

**Claim summary:**

{claim_summary}
<!-- END: context -->

## Search plan

<!-- BEGIN: search_plan -->
Plan queries across the configured backends in the order Tavily → Semantic Scholar → HN Algolia → Reddit. Capture top 10 hits per backend, dedupe by URL, then rank by topical relevance to the claim summary above.

The script `lens/scripts/gather_evidence.py` executes this plan when invoked with `--ticket-path <this file>`. Hermes inspects the script output and may extend the plan if coverage looks thin (e.g. single-source claim, no academic citations).
<!-- END: search_plan -->

## Sources found

<!-- BEGIN: sources -->
_Populated by `gather_evidence.py`._
<!-- END: sources -->

## Claims extracted

<!-- BEGIN: claims -->
_Populated by `gather_evidence.py`._
<!-- END: claims -->

## Confidence note

<!-- BEGIN: confidence -->
_Hermes fills this in after reviewing sources and extracted claims. Comment on coverage breadth, source quality, agreement vs disagreement across sources, and any gaps that warrant follow-up._
<!-- END: confidence -->

## Run record

<!-- BEGIN: run_record -->
_Populated by `gather_evidence.py` with timing, per-backend hit counts, model spend, and termination state (completed | budget_aborted | error)._
<!-- END: run_record -->
