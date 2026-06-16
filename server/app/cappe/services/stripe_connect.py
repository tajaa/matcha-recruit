"""Stripe Connect for Cappe storefronts.

Each business connects its OWN Stripe account (Connect **Standard**). Customer
card payments are **direct charges** created on the connected account, with a
small platform fee (`application_fee_amount`, default 2% — see
`settings.cappe_platform_fee_bps`) routed to the Gummfit platform account.

This is intentionally separate from `core/services/stripe_service.StripeService`
(which handles the platform's own subscription billing): Cappe is its own product
and uses a distinct webhook endpoint/secret. Both share the same Stripe SDK +
platform secret key.

All Stripe calls run in a worker thread (`asyncio.to_thread`) — the SDK is sync.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

try:
    import stripe
except ImportError:  # pragma: no cover - handled at runtime
    stripe = None

from ...config import get_settings


class CappeStripeError(Exception):
    """Raised when Cappe Stripe operations fail or are misconfigured."""


def platform_fee_cents(amount_cents: int) -> int:
    """The platform's cut of a sale, in cents (2% by default, floored)."""
    bps = get_settings().cappe_platform_fee_bps
    return max(0, (amount_cents * bps) // 10_000)


class CappeStripe:
    def __init__(self):
        self.settings = get_settings()

    def _ensure_key(self) -> None:
        if stripe is None:
            raise CappeStripeError("Stripe SDK is not installed. Run `pip install stripe`.")
        if not self.settings.stripe_secret_key:
            raise CappeStripeError("Stripe is not configured for this environment")
        stripe.api_key = self.settings.stripe_secret_key

    # ── Connect onboarding ────────────────────────────────────────────────
    async def create_connected_account(self, email: str) -> str:
        """Create a Connect Standard account for a business; return its id."""
        self._ensure_key()

        def _create():
            return stripe.Account.create(
                type="standard",
                email=email or None,
                metadata={"product": "cappe"},
            )

        try:
            acct = await asyncio.to_thread(_create)
            return acct["id"]
        except Exception as exc:  # noqa: BLE001
            raise CappeStripeError(f"Failed to create Stripe account: {exc}") from exc

    async def create_account_link(self, account_id: str, refresh_url: str, return_url: str):
        """Hosted onboarding link the business completes to enable charges."""
        self._ensure_key()

        def _create():
            return stripe.AccountLink.create(
                account=account_id,
                refresh_url=refresh_url,
                return_url=return_url,
                type="account_onboarding",
            )

        try:
            return await asyncio.to_thread(_create)
        except Exception as exc:  # noqa: BLE001
            raise CappeStripeError(f"Failed to create account link: {exc}") from exc

    async def retrieve_account(self, account_id: str):
        """Fetch a connected account (for charges_enabled / details_submitted)."""
        self._ensure_key()

        def _get():
            return stripe.Account.retrieve(account_id)

        try:
            return await asyncio.to_thread(_get)
        except Exception as exc:  # noqa: BLE001
            raise CappeStripeError(f"Failed to retrieve account: {exc}") from exc

    # ── Storefront checkout (direct charge on the connected account) ───────
    async def create_checkout_session(
        self,
        *,
        account_id: str,
        currency: str,
        line_items: list[dict[str, Any]],
        amount_cents: int,
        success_url: str,
        cancel_url: str,
        metadata: dict[str, str],
        customer_email: Optional[str] = None,
    ):
        """Create a Checkout Session ON the connected account (direct charge),
        taking a platform `application_fee_amount`. Returns the Session."""
        self._ensure_key()
        fee = platform_fee_cents(amount_cents)

        def _create():
            return stripe.checkout.Session.create(
                mode="payment",
                success_url=success_url,
                cancel_url=cancel_url,
                line_items=line_items,
                customer_email=customer_email or None,
                metadata=metadata,
                payment_intent_data={
                    "application_fee_amount": fee,
                    "metadata": metadata,
                },
                # stripe_account header → the charge happens on the business's
                # connected account; the fee is swept to the platform.
                stripe_account=account_id,
            )

        try:
            return await asyncio.to_thread(_create)
        except Exception as exc:  # noqa: BLE001
            raise CappeStripeError(f"Failed to create checkout session: {exc}") from exc

    # ── Webhook (Connect endpoint; events arrive with event.account set) ───
    async def verify_webhook(self, payload: bytes, signature: str):
        self._ensure_key()
        secret = self.settings.cappe_stripe_webhook_secret
        if not secret:
            raise CappeStripeError("Cappe Stripe webhook secret is not configured")

        def _construct():
            return stripe.Webhook.construct_event(payload, signature, secret)

        try:
            return await asyncio.to_thread(_construct)
        except Exception as exc:  # noqa: BLE001
            raise CappeStripeError(f"Invalid Stripe webhook: {exc}") from exc


_cappe_stripe: Optional[CappeStripe] = None


def get_cappe_stripe() -> CappeStripe:
    global _cappe_stripe
    if _cappe_stripe is None:
        _cappe_stripe = CappeStripe()
    return _cappe_stripe
