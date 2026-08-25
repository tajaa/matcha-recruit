"""Per-model pricing config and cost calculator for dollar-based billing.

Prices sourced from https://ai.google.dev/pricing (Feb 2026).
"""

from __future__ import annotations

from decimal import Decimal, ROUND_UP

# Price per 1M tokens (input / output) for each supported model
MODEL_PRICING: dict[str, dict[str, Decimal]] = {
    # OpenAI GPT-5.6 Luna — Huume's Responses API tool loop. Must stay in
    # sync with core.services.ai_usage.PRICING so saved Huume-run cost and
    # the admin AI ledger never disagree.
    "gpt-5.6-luna": {
        "input_per_1m": Decimal("1.00"),
        "output_per_1m": Decimal("6.00"),
    },
    # Gemini 3.5 Flash — pricing TBD (placeholder = prior 3-flash-preview
    # tier of $0.50 in / $3.00 out; revisit when Google publishes 3.5 GA pricing).
    "gemini-3-flash-preview": {
        "input_per_1m": Decimal("0.50"),
        "output_per_1m": Decimal("3.00"),
    },
    # Gemini 3.1 Pro — $2.00 input (≤200k), $12.00 output (≤200k)
    "gemini-3.1-pro-preview": {
        "input_per_1m": Decimal("2.00"),
        "output_per_1m": Decimal("12.00"),
    },
    # Gemini 3.7 Flash — the fleet quality-tier model (model_catalog.GEMINI_FLASH,
    # aliased by huume/agent.py _MODEL etc.). Price mirrors 3.6-flash until
    # Google's 3.7 GA rate is confirmed — an unpriced row would fall to
    # DEFAULT_PRICING. Must match ai_usage.PRICING's row.
    "gemini-3.7-flash": {
        "input_per_1m": Decimal("1.50"),
        "output_per_1m": Decimal("7.50"),
    },
    # Gemini 3.6 Flash — kept for already-logged usage rows; the fleet moved
    # to 3.7-flash.
    "gemini-3.6-flash": {
        "input_per_1m": Decimal("1.50"),
        "output_per_1m": Decimal("7.50"),
    },
    # Gemini 3.1 Flash Lite — flash-lite tier (kept for already-logged rows)
    "gemini-3.1-flash-lite": {
        "input_per_1m": Decimal("0.10"),
        "output_per_1m": Decimal("0.40"),
    },
    # Gemini 3.7 Flash Lite — kept for already-logged rows. The active fleet
    # alias uses 3.5-flash-lite because 3.7-flash-lite is unavailable for the
    # current API account.
    "gemini-3.7-flash-lite": {
        "input_per_1m": Decimal("0.30"),
        "output_per_1m": Decimal("2.50"),
    },
    # Gemini 3.5 Flash Lite — active fleet cheap tier.
    "gemini-3.5-flash-lite": {
        "input_per_1m": Decimal("0.30"),
        "output_per_1m": Decimal("2.50"),
    },
    # Gemini 3.1 Flash Image — image output tokens are billed at the image
    # rate (~$30/1M ≈ $0.039 per 1290-token image). GA landed 2026-06-25 as
    # "gemini-3.1-flash-image" (Nano Banana 2); the "-preview" name it
    # shipped under is now shut down. Both rows priced — "-preview" for any
    # already-logged rows that still carry it.
    "gemini-3.1-flash-image": {
        "input_per_1m": Decimal("0.30"),
        "output_per_1m": Decimal("30.00"),
    },
    "gemini-3.1-flash-image-preview": {
        "input_per_1m": Decimal("0.30"),
        "output_per_1m": Decimal("30.00"),
    },
    # Gemini 2.5 Flash — kept for any legacy references
    "gemini-2.5-flash": {
        "input_per_1m": Decimal("0.30"),
        "output_per_1m": Decimal("2.50"),
    },
    # Gemini 2.0 Flash
    "gemini-2.0-flash": {
        "input_per_1m": Decimal("0.10"),
        "output_per_1m": Decimal("0.40"),
    },
}

# Fallback pricing for unknown models (use flash pricing)
DEFAULT_PRICING: dict[str, Decimal] = {
    "input_per_1m": Decimal("0.50"),
    "output_per_1m": Decimal("3.00"),
}

# Minimum cost per call — prevents free rides on tiny requests
MINIMUM_COST_PER_CALL = Decimal("0.0001")


def calculate_call_cost(
    model: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    thinking_tokens: int | None = None,
) -> Decimal:
    """Calculate the dollar cost of a single AI call based on model and token counts.

    Returns a Decimal with 6 decimal places, floored at MINIMUM_COST_PER_CALL.
    """
    pricing = MODEL_PRICING.get(model, DEFAULT_PRICING)

    input_cost = Decimal(prompt_tokens or 0) * pricing["input_per_1m"] / Decimal("1000000")
    # Thinking tokens bill at the output rate (matches ai_usage.compute_cost).
    output_cost = (
        Decimal((completion_tokens or 0) + (thinking_tokens or 0))
        * pricing["output_per_1m"] / Decimal("1000000")
    )

    total = (input_cost + output_cost).quantize(Decimal("0.000001"), rounding=ROUND_UP)

    return max(total, MINIMUM_COST_PER_CALL)
