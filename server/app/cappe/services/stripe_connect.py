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

    # ── Platform checkout (our own revenue — domains, plans; NO Connect) ───
    async def create_platform_checkout_session(
        self,
        *,
        currency: str,
        line_items: list[dict[str, Any]],
        success_url: str,
        cancel_url: str,
        metadata: dict[str, str],
        customer_email: Optional[str] = None,
        save_card: bool = False,
    ):
        """Checkout Session on OUR platform account (we keep 100%). Used for
        domain registration and plan billing — no connected account, no fee.
        With save_card, create a Customer + store the card off-session so renewals
        can charge it later."""
        self._ensure_key()

        def _create():
            pi_data: dict[str, Any] = {"metadata": metadata}
            kwargs: dict[str, Any] = {}
            if save_card:
                pi_data["setup_future_usage"] = "off_session"
                kwargs["customer_creation"] = "always"
            return stripe.checkout.Session.create(
                mode="payment",
                success_url=success_url,
                cancel_url=cancel_url,
                line_items=line_items,
                customer_email=customer_email or None,
                metadata=metadata,
                payment_intent_data=pi_data,
                **kwargs,
            )

        try:
            return await asyncio.to_thread(_create)
        except Exception as exc:  # noqa: BLE001
            raise CappeStripeError(f"Failed to create checkout session: {exc}") from exc

    async def charge_off_session(
        self, *, customer_id: str, amount_cents: int, currency: str, metadata: dict[str, str],
        idempotency_key: Optional[str] = None,
    ):
        """Charge a saved-card Customer off-session (e.g. a domain renewal).
        Raises CappeStripeError on decline so the caller can dun/lapse. The
        idempotency key (24h replay) keeps a retrying cron from double-charging
        or re-hammering a declined card within a renewal window."""
        self._ensure_key()

        def _charge():
            kwargs = {"idempotency_key": idempotency_key} if idempotency_key else {}
            return stripe.PaymentIntent.create(
                amount=amount_cents,
                currency=currency,
                customer=customer_id,
                off_session=True,
                confirm=True,
                metadata=metadata,
                **kwargs,
            )

        try:
            return await asyncio.to_thread(_charge)
        except Exception as exc:  # noqa: BLE001
            raise CappeStripeError(f"Off-session charge failed: {exc}") from exc

    async def refund(self, payment_intent: str):
        """Refund a platform charge in full (e.g. domain registration failed
        after the customer paid)."""
        self._ensure_key()

        def _refund():
            return stripe.Refund.create(payment_intent=payment_intent)

        try:
            return await asyncio.to_thread(_refund)
        except Exception as exc:  # noqa: BLE001
            raise CappeStripeError(f"Failed to refund: {exc}") from exc

    async def verify_platform_webhook(self, payload: bytes, signature: str):
        """Verify a PLATFORM webhook (domain/plan checkout). Distinct endpoint +
        secret from the Connect storefront webhook."""
        self._ensure_key()
        secret = self.settings.cappe_platform_webhook_secret
        if not secret:
            raise CappeStripeError("Cappe platform webhook secret is not configured")

        def _construct():
            return stripe.Webhook.construct_event(payload, signature, secret)

        try:
            return await asyncio.to_thread(_construct)
        except Exception as exc:  # noqa: BLE001
            raise CappeStripeError(f"Invalid Stripe webhook: {exc}") from exc

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
