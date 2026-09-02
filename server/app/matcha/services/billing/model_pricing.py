"""Per-model pricing config and cost calculator for dollar-based billing.

Gemini prices: https://ai.google.dev/pricing. OpenAI Luna prices:
https://developers.openai.com/api/docs/models/gpt-5.6-luna.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_UP

# Price per 1M tokens (input / output) for each supported model
MODEL_PRICING: dict[str, dict[str, Decimal]] = {
    # OpenAI GPT-5.6 Luna — Huume's Responses API tool loop. This table is
    # used only for Matcha-work's internal usage-event accounting; the admin
    # AI ledger leaves OpenAI cost NULL and treats provider billing as the
    # dollar source of truth.
    "gpt-5.6-luna": {
        "input_per_1m": Decimal("0.20"),
        "cached_input_per_1m": Decimal("0.02"),
        "output_per_1m": Decimal("1.20"),
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
    cached_tokens: int | None = None,
) -> Decimal:
    """Calculate the dollar cost of a single AI call based on model and token counts.

    Returns a Decimal with 6 decimal places, floored at MINIMUM_COST_PER_CALL.
    """
    pricing = MODEL_PRICING.get(model, DEFAULT_PRICING)

    prompt_count = max(prompt_tokens or 0, 0)
    cached_count = min(max(cached_tokens or 0, 0), prompt_count)
    cached_price = pricing.get("cached_input_per_1m", pricing["input_per_1m"])
    input_cost = (
        Decimal(prompt_count - cached_count) * pricing["input_per_1m"]
        + Decimal(cached_count) * cached_price
    ) / Decimal("1000000")
    # Responses output_tokens already includes its reasoning-token breakdown.
    # Gemini candidates_token_count excludes thoughts_token_count, so only the
    # Gemini-shaped rows need the separate thinking counter added.
    output_count = completion_tokens or 0
    if model != "gpt-5.6-luna":
        output_count += thinking_tokens or 0
    output_cost = Decimal(output_count) * pricing["output_per_1m"] / Decimal("1000000")

    total = (input_cost + output_cost).quantize(Decimal("0.000001"), rounding=ROUND_UP)

    return max(total, MINIMUM_COST_PER_CALL)
