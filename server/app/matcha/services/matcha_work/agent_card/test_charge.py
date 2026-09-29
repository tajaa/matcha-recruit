"""Stripe **test-mode** charge for an approved agent-card purchase.

Proves the approve → pay path end to end with no real money: when a purchase
is approved in chat and has a verified total, the server creates and confirms
a Stripe PaymentIntent for exactly that amount and currency.

Safety rails:
  * Test keys only. The key (`AGENT_PURCHASE_STRIPE_KEY`, else
    `STRIPE_SECRET_KEY`) must start with `sk_test_` / `rk_test_`; a live key
    means no charge at all, never a live one.
  * The saved card's number is never sent to Stripe. Stripe's built-in test
    payment method for the card's brand (`pm_card_visa`, …) stands in for it.
  * One charge per purchase: the purchase id is the idempotency key.

`AGENT_PURCHASE_MODE=handoff` turns it off (link only); the default is
`stripe_test`.
"""
from __future__ import annotations

import asyncio
import logging
import os
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

logger = logging.getLogger(__name__)

MODE_ENV = "AGENT_PURCHASE_MODE"
KEY_ENV = "AGENT_PURCHASE_STRIPE_KEY"
_TEST_KEY_PREFIXES = ("sk_test_", "rk_test_")
_TEST_PAYMENT_METHODS = {
    "visa": "pm_card_visa",
    "mastercard": "pm_card_mastercard",
    "amex": "pm_card_amex",
    "discover": "pm_card_discover",
}
# Stripe amounts are in the currency's minor unit; these have none.
_ZERO_DECIMAL = {
    "bif", "clp", "djf", "gnf", "jpy", "kmf", "krw", "mga", "pyg", "rwf",
    "ugx", "vnd", "vuv", "xaf", "xof", "xpf",
}


def test_key() -> str | None:
    """The Stripe test key to charge with, or None (mode off, or not a test key)."""
    if (os.getenv(MODE_ENV) or "stripe_test").strip().lower() != "stripe_test":
        return None
    key = (os.getenv(KEY_ENV) or os.getenv("STRIPE_SECRET_KEY") or "").strip()
    return key if key.startswith(_TEST_KEY_PREFIXES) else None


def minor_units(amount, currency: str) -> int:
    value = Decimal(str(amount))
    if currency.lower() not in _ZERO_DECIMAL:
        value *= 100
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _create(key: str, *, purchase_id: UUID, amount: int, currency: str, payment_method: str,
            description: str, metadata: dict):
    import stripe

    return stripe.PaymentIntent.create(
        api_key=key,
        idempotency_key=f"agent-purchase-{purchase_id}",
        amount=amount,
        currency=currency,
        payment_method=payment_method,
        confirm=True,
        automatic_payment_methods={"enabled": True, "allow_redirects": "never"},
        description=description[:200],
        metadata=metadata,
    )


async def charge(
    key: str, *, purchase_id: UUID, amount, currency: str, brand: str | None, description: str,
    metadata: dict,
) -> dict:
    """{"status": "test_charged" | "test_failed", "payment_intent_id", "error"}."""
    import stripe

    try:
        intent = await asyncio.to_thread(
            _create, key,
            purchase_id=purchase_id,
            amount=minor_units(amount, currency),
            currency=currency.lower(),
            payment_method=_TEST_PAYMENT_METHODS.get(brand or "", "pm_card_visa"),
            description=description,
            metadata={k: str(v) for k, v in metadata.items()},
        )
    except stripe.StripeError as exc:
        logger.warning("agent purchase test charge failed purchase=%s: %s", purchase_id, exc)
        return {
            "status": "test_failed",
            "payment_intent_id": None,
            "error": (getattr(exc, "user_message", None) or "Stripe refused the test charge.")[:300],
        }
    succeeded = getattr(intent, "status", None) == "succeeded"
    return {
        "status": "test_charged" if succeeded else "test_failed",
        "payment_intent_id": intent.id,
        "error": None if succeeded else f"Stripe left the test charge {intent.status}.",
    }
