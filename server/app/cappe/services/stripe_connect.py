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
    """FALLBACK take rate from the global setting (2% by default, floored).

    The live rate is per-plan and comes from the billing catalog — see
    `services/entitlements.fee_cents`. This remains only for callers with no
    account context and as the degraded path when the catalog is unreadable.
    """
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
        application_fee_cents: int,
        success_url: str,
        cancel_url: str,
        metadata: dict[str, str],
        customer_email: Optional[str] = None,
    ):
        """Create a Checkout Session ON the connected account (direct charge),
        taking a platform `application_fee_amount`. Returns the Session.

        The fee is passed in, never recomputed here. It used to be derived from
        an `amount_cents` argument, which meant the caller computed the fee once
        for persistence (`cappe_orders.platform_fee_cents`) and this method
        computed it again for the actual charge. Both read the same global
        setting, so they agreed by luck; with a per-plan rate they could
        diverge, and the persisted number would be a lie about money.
        """
        self._ensure_key()
        fee = max(0, int(application_fee_cents))

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

    # ── Catalog: Products + Prices on the PLATFORM account ────────────────
    async def ensure_product(self, *, code: str, name: str, description: Optional[str] = None) -> str:
        """Create the Stripe Product backing a plan/add-on. Returns its id."""
        self._ensure_key()

        def _create():
            return stripe.Product.create(
                name=name,
                description=description or None,
                metadata={"product": "cappe", "cappe_code": code},
            )

        try:
            return (await asyncio.to_thread(_create))["id"]
        except Exception as exc:  # noqa: BLE001
            raise CappeStripeError(f"Failed to create Stripe product: {exc}") from exc

    async def ensure_price(
        self,
        *,
        product_id: str,
        unit_amount_cents: int,
        currency: str,
        interval: str,
        lookup_key: Optional[str] = None,
    ) -> str:
        """Create a Price. `interval` is 'month' | 'year' | 'once'.

        Stripe Prices are IMMUTABLE in `unit_amount`, so changing a price means
        creating a new one — never editing. `lookup_key` is unique per account
        on Stripe's side, which makes a re-run of the seed script error rather
        than silently minting a duplicate.
        """
        self._ensure_key()

        def _create():
            kwargs: dict[str, Any] = {
                "product": product_id,
                "unit_amount": int(unit_amount_cents),
                "currency": (currency or "usd").lower(),
                "metadata": {"product": "cappe"},
            }
            if interval in ("month", "year"):
                kwargs["recurring"] = {"interval": interval}
            if lookup_key:
                kwargs["lookup_key"] = lookup_key
            return stripe.Price.create(**kwargs)

        try:
            return (await asyncio.to_thread(_create))["id"]
        except Exception as exc:  # noqa: BLE001
            raise CappeStripeError(f"Failed to create Stripe price: {exc}") from exc

    async def archive_price(self, price_id: str) -> None:
        """Deactivate a superseded Price. Best-effort: an orphaned active Price
        charges nobody, so a failure here must not fail the admin's edit."""
        self._ensure_key()

        def _archive():
            return stripe.Price.modify(price_id, active=False)

        try:
            await asyncio.to_thread(_archive)
        except Exception as exc:  # noqa: BLE001
            raise CappeStripeError(f"Failed to archive price: {exc}") from exc

    # ── Customers + subscription checkout ─────────────────────────────────
    async def ensure_customer(self, *, email: str, account_id: str) -> str:
        """Create a Stripe Customer for a Cappe account. Returns its id."""
        self._ensure_key()

        def _create():
            return stripe.Customer.create(
                email=email or None,
                metadata={"product": "cappe", "cappe_account_id": account_id},
            )

        try:
            return (await asyncio.to_thread(_create))["id"]
        except Exception as exc:  # noqa: BLE001
            raise CappeStripeError(f"Failed to create Stripe customer: {exc}") from exc

    async def create_subscription_checkout_session(
        self,
        *,
        customer_id: str,
        price_id: str,
        success_url: str,
        cancel_url: str,
        metadata: dict[str, str],
        intro_price_id: Optional[str] = None,
        trial_days: Optional[int] = None,
    ):
        """Subscription Checkout on OUR platform account.

        The $1-for-30-days intro is `trial_period_days` + the one-time $1 as
        `subscription_data.add_invoice_items`. It cannot be an extra entry in
        `line_items`: Checkout REJECTS non-recurring prices in subscription
        mode. It is also not a coupon — a coupon's `amount_off` is itself
        immutable and derived from the standard price, so every admin price edit
        would force a matching new coupon.

        `customer_creation` is deliberately absent: it is not valid in
        subscription mode (Stripe always creates/uses a Customer), which is why
        the caller resolves `customer_id` first.
        """
        self._ensure_key()

        def _create():
            sub_data: dict[str, Any] = {"metadata": metadata}
            if trial_days and intro_price_id:
                sub_data["trial_period_days"] = int(trial_days)
                sub_data["add_invoice_items"] = [{"price": intro_price_id}]
                # No card on file at trial end ⇒ cancel rather than silently
                # leaving an unpaid subscription entitled.
                sub_data["trial_settings"] = {
                    "end_behavior": {"missing_payment_method": "cancel"}
                }
            return stripe.checkout.Session.create(
                mode="subscription",
                customer=customer_id,
                line_items=[{"price": price_id, "quantity": 1}],
                subscription_data=sub_data,
                payment_method_collection="always",
                success_url=success_url,
                cancel_url=cancel_url,
                metadata=metadata,
                allow_promotion_codes=False,
            )

        try:
            return await asyncio.to_thread(_create)
        except Exception as exc:  # noqa: BLE001
            raise CappeStripeError(f"Failed to create subscription checkout: {exc}") from exc

    async def retrieve_subscription(self, subscription_id: str):
        """Fetch a subscription with its items+prices expanded. Subscription
        state is always read back from Stripe rather than inferred from a
        Checkout Session — the session alone does not carry item ids."""
        self._ensure_key()

        def _get():
            return stripe.Subscription.retrieve(
                subscription_id, expand=["items.data.price"]
            )

        try:
            return await asyncio.to_thread(_get)
        except Exception as exc:  # noqa: BLE001
            raise CappeStripeError(f"Failed to retrieve subscription: {exc}") from exc

    async def change_subscription_price(
        self,
        *,
        subscription_id: str,
        item_id: str,
        new_price_id: str,
        proration_behavior: str = "always_invoice",
        anchor_now: bool = False,
        end_trial: bool = False,
    ):
        """Move the plan item to a different Price (tier or interval change)."""
        self._ensure_key()

        def _modify():
            kwargs: dict[str, Any] = {
                "items": [{"id": item_id, "price": new_price_id}],
                "proration_behavior": proration_behavior,
                "payment_behavior": "pending_if_incomplete",
            }
            if anchor_now:
                kwargs["billing_cycle_anchor"] = "now"
            if end_trial:
                # Upgrading mid-intro should start paying now, not ride the $1
                # trial at the higher tier.
                kwargs["trial_end"] = "now"
            return stripe.Subscription.modify(subscription_id, **kwargs)

        try:
            return await asyncio.to_thread(_modify)
        except Exception as exc:  # noqa: BLE001
            raise CappeStripeError(f"Failed to change subscription price: {exc}") from exc

    async def add_subscription_item(
        self, *, subscription_id: str, price_id: str, quantity: int
    ):
        """Add an add-on item. Invoices immediately so provisioning is paid for
        before it happens."""
        self._ensure_key()

        def _create():
            return stripe.SubscriptionItem.create(
                subscription=subscription_id,
                price=price_id,
                quantity=int(quantity),
                proration_behavior="always_invoice",
            )

        try:
            return await asyncio.to_thread(_create)
        except Exception as exc:  # noqa: BLE001
            raise CappeStripeError(f"Failed to add subscription item: {exc}") from exc

    async def set_item_quantity(self, *, item_id: str, quantity: int, invoice_now: bool):
        """Change an add-on quantity.

        Increases invoice now; decreases only create prorations — billing a
        decrease immediately generates a $0/negative invoice that confuses
        people, so the credit sits on the customer balance instead.
        """
        self._ensure_key()

        def _modify():
            return stripe.SubscriptionItem.modify(
                item_id,
                quantity=int(quantity),
                proration_behavior="always_invoice" if invoice_now else "create_prorations",
            )

        try:
            return await asyncio.to_thread(_modify)
        except Exception as exc:  # noqa: BLE001
            raise CappeStripeError(f"Failed to set item quantity: {exc}") from exc

    async def remove_subscription_item(self, item_id: str):
        self._ensure_key()

        def _delete():
            return stripe.SubscriptionItem.delete(
                item_id, proration_behavior="create_prorations"
            )

        try:
            return await asyncio.to_thread(_delete)
        except Exception as exc:  # noqa: BLE001
            raise CappeStripeError(f"Failed to remove subscription item: {exc}") from exc

    async def cancel_subscription(self, subscription_id: str, *, at_period_end: bool = True):
        """Cancel at the period boundary (default) or immediately."""
        self._ensure_key()

        def _cancel():
            if at_period_end:
                return stripe.Subscription.modify(
                    subscription_id, cancel_at_period_end=True
                )
            return stripe.Subscription.delete(subscription_id)

        try:
            return await asyncio.to_thread(_cancel)
        except Exception as exc:  # noqa: BLE001
            raise CappeStripeError(f"Failed to cancel subscription: {exc}") from exc

    async def create_billing_portal_session(self, *, customer_id: str, return_url: str):
        """Hosted portal for card updates, invoices and receipts — rather than
        rebuilding those surfaces. Plan switching stays on our own endpoints so
        the catalog remains authoritative."""
        self._ensure_key()

        def _create():
            return stripe.billing_portal.Session.create(
                customer=customer_id, return_url=return_url
            )

        try:
            return await asyncio.to_thread(_create)
        except Exception as exc:  # noqa: BLE001
            raise CappeStripeError(f"Failed to create portal session: {exc}") from exc


_cappe_stripe: Optional[CappeStripe] = None


def get_cappe_stripe() -> CappeStripe:
    global _cappe_stripe
    if _cappe_stripe is None:
        _cappe_stripe = CappeStripe()
    return _cappe_stripe
