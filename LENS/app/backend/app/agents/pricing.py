"""Per-model pricing for cost tracking.

The DirectAnthropic adapter computes costs from token counts because the
raw Messages API doesn't return a USD figure. The Claude Agent SDK
adapter reads cost from the ``ResultMessage`` directly (more accurate)
and falls back to this table only on missing fields.

Pricing here is in USD per million tokens (MTok). Numbers are
approximate; verify against the live Anthropic pricing page before
trusting cost-cap enforcement in production.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPricing:
    input_per_mtok: float
    output_per_mtok: float
    cache_write_per_mtok: float | None = None
    cache_read_per_mtok: float | None = None


# Verify against https://www.anthropic.com/pricing before trusting these
# for hard cost caps. Numbers below are approximate.
_PRICING: dict[str, ModelPricing] = {
    "claude-opus-4-7": ModelPricing(
        input_per_mtok=15.0,
        output_per_mtok=75.0,
        cache_write_per_mtok=18.75,
        cache_read_per_mtok=1.50,
    ),
    "claude-sonnet-4-6": ModelPricing(
        input_per_mtok=3.0,
        output_per_mtok=15.0,
        cache_write_per_mtok=3.75,
        cache_read_per_mtok=0.30,
    ),
    "claude-haiku-4-5": ModelPricing(
        input_per_mtok=0.80,
        output_per_mtok=4.0,
        cache_write_per_mtok=1.0,
        cache_read_per_mtok=0.08,
    ),
}


def cost_for_usage(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0,
) -> float:
    """Compute USD cost for one API call's usage.

    Unknown models default to Sonnet pricing; callers should consider
    that a soft warning rather than a hard failure.
    """
    pricing = _PRICING.get(model) or _PRICING["claude-sonnet-4-6"]

    cost = (
        input_tokens * pricing.input_per_mtok / 1_000_000
        + output_tokens * pricing.output_per_mtok / 1_000_000
    )
    if pricing.cache_write_per_mtok is not None:
        cost += cache_creation_input_tokens * pricing.cache_write_per_mtok / 1_000_000
    if pricing.cache_read_per_mtok is not None:
        cost += cache_read_input_tokens * pricing.cache_read_per_mtok / 1_000_000
    return cost
