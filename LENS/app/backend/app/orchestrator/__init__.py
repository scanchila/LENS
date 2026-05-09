"""Orchestrator-side glue: demo stage replay, dirty-set re-eval, lens runner.

The replay subsystem lets the prediction board run the §11.1 demo arc
end-to-end against a real Postgres + SSE pipeline — every candidate
that appears on the board is persisted, every animation is driven by
a real NOTIFY, and the YC reveal scores against the real fixture.

Real lens execution lives alongside; the orchestrator picks the
appropriate path per stage (stub vs. live) based on env config.
"""

from .demo_stages import DEMO_STAGES, apply_stage

__all__ = ["DEMO_STAGES", "apply_stage"]
