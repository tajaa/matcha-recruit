"""Per-model pricing config and cost calculator for dollar-based billing."""

from __future__ import annotations

from decimal import Decimal, ROUND_UP

# Price per 1M tokens (input / output) for each supported model
MODEL_PRICING: dict[str, dict[str, Decimal]] = {
    "gemini-3-flash-preview": {
        "input_per_1m": Decimal("0.10"),
        "output_per_1m": Decimal("0.40"),
    },
    "gemini-3.1-pro-preview": {
        "input_per_1m": Decimal("1.25"),
        "output_per_1m": Decimal("10.00"),
    },
}

# Fallback pricing for unknown models (use flash pricing)
DEFAULT_PRICING: dict[str, Decimal] = {
    "input_per_1m": Decimal("0.10"),
    "output_per_1m": Decimal("0.40"),
}

# Minimum cost per call — prevents free rides on tiny requests
MINIMUM_COST_PER_CALL = Decimal("0.0001")


def calculate_call_cost(
    model: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
) -> Decimal:
    """Calculate the dollar cost of a single AI call based on model and token counts.

    Returns a Decimal with 6 decimal places, floored at MINIMUM_COST_PER_CALL.
    """
    pricing = MODEL_PRICING.get(model, DEFAULT_PRICING)

    input_cost = Decimal(prompt_tokens or 0) * pricing["input_per_1m"] / Decimal("1000000")
    output_cost = Decimal(completion_tokens or 0) * pricing["output_per_1m"] / Decimal("1000000")

    total = (input_cost + output_cost).quantize(Decimal("0.000001"), rounding=ROUND_UP)

    return max(total, MINIMUM_COST_PER_CALL)
