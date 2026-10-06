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
import time
from typing import Any, Optional

try:
    import stripe
except ImportError:  # pragma: no cover - handled at runtime
    stripe = None

from ...config import get_settings


class CappeStripeError(Exception):
    """Raised when Cappe Stripe operations fail or are misconfigured."""


class CappeStripeCardError(CappeStripeError):
    """The CARD was refused — declined, expired, or it needs the cardholder
    present (authentication_required) — or there is no card to charge.

    Kept apart from `CappeStripeError` because the two demand opposite
    responses. A refused card is the customer's to fix: tell them, and
    eventually lapse what they are not paying for. An outage, a bad key or a
    malformed request is OURS: retry later and never punish the customer for
    it. The renewal sweep used to treat both as "could not collect" and expired
    a paid-up tenant's domain on any Stripe error at all.
    """

    def __init__(self, message: str, *, code: Optional[str] = None):
        super().__init__(message)
        self.code = code


def _is_card_error(exc: BaseException) -> bool:
    card_error = getattr(stripe, "CardError", None) if stripe is not None else None
    return isinstance(card_error, type) and isinstance(exc, card_error)


def platform_fee_cents(amount_cents: int) -> int:
    """FALLBACK take rate from the global setting (2% by default, floored).

    The live rate is per-plan and comes from the billing catalog — see
    `services/entitlements.fee_cents`. This remains only for callers with no
    account context and as the degraded path when the catalog is unreadable.
    """
    bps = get_settings().cappe_platform_fee_bps
    return max(0, (amount_cents * bps) // 10_000)


# Where Stripe takes a shipping address when the caller names no country.
# Callers pass the order's ship-to country (services/shipping.py); this is the
# old US-only default for anything that doesn't.
CAPPE_SHIPPING_COUNTRIES = ["US"]

# How long a storefront payment page stays payable: Stripe's 30-minute minimum
# plus a minute, so a slightly fast clock here can never produce a rejected
# `expires_at`.
CONNECT_CHECKOUT_TTL_SECONDS = 31 * 60


def build_shipping_options(shipping_option: Optional[dict], currency: str) -> Optional[list[dict]]:
    """Translate {label, amount_cents} into Stripe's shipping_options shape.
    A 0-amount option is still emitted so the buyer sees the 'Free shipping' row."""
    if shipping_option is None:
        return None
    return [{
        "shipping_rate_data": {
            "type": "fixed_amount",
            "display_name": (shipping_option.get("label") or "Shipping")[:100],
            "fixed_amount": {
                "amount": max(0, int(shipping_option["amount_cents"])),
                "currency": (currency or "usd").lower(),
            },
        }
    }]


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
        customer_id: Optional[str] = None,
        collect_shipping_address: bool = False,
        shipping_option: Optional[dict] = None,
        expires_in_seconds: Optional[int] = None,
        ship_countries: Optional[list[str]] = None,
    ):
        """Create a Checkout Session ON the connected account (direct charge),
        taking a platform `application_fee_amount`. Returns the Session.

        The fee is passed in, never recomputed here. It used to be derived from
        an `amount_cents` argument, which meant the caller computed the fee once
        for persistence (`cappe_orders.platform_fee_cents`) and this method
        computed it again for the actual charge. Both read the same global
        setting, so they agreed by luck; with a per-plan rate they could
        diverge, and the persisted number would be a lie about money.

        With `collect_shipping_address`, Stripe collects the buyer's address
        in one of `ship_countries` (the country the order was priced for) and
        `shipping_option` renders as a real shipping row included in
        amount_total; the fee stays on the goods subtotal.

        `expires_in_seconds` shortens Stripe's default 24h session lifetime. The
        order behind a session holds stock from the moment it is created, so an
        abandoned page would otherwise keep those units off the shelf for a day.
        Stripe refuses anything under 30 minutes; `CONNECT_CHECKOUT_TTL_SECONDS`
        leaves a minute of clock-skew margin above that.
        """
        self._ensure_key()
        fee = max(0, int(application_fee_cents))

        def _create():
            extra: dict[str, Any] = {}
            if customer_id:
                extra["customer"] = customer_id
                if collect_shipping_address:
                    extra["customer_update"] = {"shipping": "auto"}
            else:
                extra["customer_email"] = customer_email or None
            if collect_shipping_address:
                extra["shipping_address_collection"] = {
                    "allowed_countries": list(ship_countries or CAPPE_SHIPPING_COUNTRIES),
                }
                opts = build_shipping_options(shipping_option, currency)
                if opts:
                    extra["shipping_options"] = opts
            if expires_in_seconds:
                extra["expires_at"] = int(time.time()) + max(
                    CONNECT_CHECKOUT_TTL_SECONDS, int(expires_in_seconds)
                )
            return stripe.checkout.Session.create(
                mode="payment",
                success_url=success_url,
                cancel_url=cancel_url,
                line_items=line_items,
                metadata=metadata,
                payment_intent_data={
                    "application_fee_amount": fee,
                    "metadata": metadata,
                },
                # stripe_account header → the charge happens on the business's
                # connected account; the fee is swept to the platform.
                stripe_account=account_id,
                **extra,
            )

        try:
            return await asyncio.to_thread(_create)
        except Exception as exc:  # noqa: BLE001
            raise CappeStripeError(f"Failed to create checkout session: {exc}") from exc

    async def ensure_connected_customer(self, *, account_id, email, name=None, shipping=None,
                                        customer_id=None, idempotency_key=None):
        self._ensure_key()
        def save():
            values = {"email": email, "name": name, "stripe_account": account_id}
            if shipping:
                values["shipping"] = shipping
            if customer_id:
                return stripe.Customer.modify(customer_id, **values)
            return stripe.Customer.create(**values, idempotency_key=idempotency_key)
        try:
            return (await asyncio.to_thread(save))["id"]
        except Exception as exc:
            raise CappeStripeError("Could not prepare customer checkout") from exc

    async def create_subscription_checkout(self, *, account_id, customer_id, line_items,
                                           application_fee_percent, success_url, cancel_url,
                                           metadata, collect_shipping, idempotency_key,
                                           ship_countries=None):
        self._ensure_key()
        def create():
            extra = {}
            if collect_shipping:
                extra = {"shipping_address_collection": {
                             "allowed_countries": list(ship_countries or CAPPE_SHIPPING_COUNTRIES)},
                         "customer_update": {"shipping": "auto"}}
            return stripe.checkout.Session.create(
                mode="subscription", customer=customer_id, line_items=line_items,
                subscription_data={"metadata": metadata, "application_fee_percent": application_fee_percent},
                metadata=metadata, success_url=success_url, cancel_url=cancel_url,
                stripe_account=account_id, idempotency_key=idempotency_key, **extra,
            )
        try:
            return await asyncio.to_thread(create)
        except Exception as exc:
            raise CappeStripeError("Could not start subscription checkout") from exc

    async def connected_invoice_payment_intent(self, account_id: str, invoice: dict) -> Optional[str]:
        """The PaymentIntent that paid an invoice on a connected account.

        A renewal order needs it: refunds (`refund_connected_charge`), the
        `charge.refunded` sync and disputes all find an order by its payment
        intent, and a subscription order used to store none — so it could not
        be refunded from the dashboard, a refund in Stripe never reached it,
        and a chargeback on it was invisible.

        Older API versions put `payment_intent` on the invoice; current ones
        list it under InvoicePayment. Both are read. Returns None rather than
        raising: the order is recorded either way.
        """
        legacy = invoice.get("payment_intent")
        if isinstance(legacy, str) and legacy:
            return legacy
        if isinstance(legacy, dict) and isinstance(legacy.get("id"), str):
            return legacy["id"]
        invoice_id = invoice.get("id")
        if not invoice_id:
            return None
        self._ensure_key()

        def _lookup():
            lister = getattr(stripe, "InvoicePayment", None)
            if lister is None:
                return None
            for pay in (lister.list(invoice=invoice_id, limit=10, stripe_account=account_id).get("data") or []):
                intent = (pay.get("payment") or {}).get("payment_intent")
                if pay.get("status") == "paid" and isinstance(intent, str):
                    return intent
            return None

        try:
            return await asyncio.to_thread(_lookup)
        except Exception:  # noqa: BLE001 — best-effort; the order still records
            return None

    async def retrieve_connected_subscription(self, account_id, subscription_id):
        self._ensure_key()
        try:
            return await asyncio.to_thread(stripe.Subscription.retrieve, subscription_id, stripe_account=account_id)
        except Exception as exc:
            raise CappeStripeError("Could not retrieve subscription") from exc

    async def modify_connected_subscription(self, *, account_id, subscription_id, cancel_at_period_end):
        self._ensure_key()
        try:
            return await asyncio.to_thread(stripe.Subscription.modify, subscription_id,
                                          stripe_account=account_id, cancel_at_period_end=cancel_at_period_end)
        except Exception as exc:
            raise CappeStripeError("Could not update subscription") from exc

    async def cancel_connected_subscription(self, account_id, subscription_id):
        self._ensure_key()
        try:
            return await asyncio.to_thread(stripe.Subscription.delete, subscription_id, stripe_account=account_id)
        except Exception as exc:
            raise CappeStripeError("Could not cancel subscription") from exc

    async def retrieve_checkout_session(self, account_id: str, session_id: str):
        """Fetch a Checkout Session from the connected account (webhook fallback
        when the event payload omits shipping details)."""
        self._ensure_key()

        def _get():
            return stripe.checkout.Session.retrieve(session_id, stripe_account=account_id)

        try:
            return await asyncio.to_thread(_get)
        except Exception as exc:  # noqa: BLE001
            raise CappeStripeError(f"Failed to retrieve checkout session: {exc}") from exc

    async def expire_checkout_session(self, account_id: str, session_id: str) -> str:
        """Close a Checkout Session so it can no longer be paid, and report where
        it ended up: 'expired' (we closed it, or it already was), or 'complete'
        (the buyer finished checkout — the money is either in or settling, and
        the order must NOT be released).

        A Checkout Session stays payable for 24h by default. Cancelling the
        order underneath an open session is how a buyer gets charged for an
        order we already threw away, so the session is closed FIRST and the
        order only released once Stripe confirms nobody can pay it.
        """
        self._ensure_key()

        def _expire():
            sess = stripe.checkout.Session.retrieve(session_id, stripe_account=account_id)
            state = str(sess.get("status") or "")
            if state == "open":
                sess = stripe.checkout.Session.expire(session_id, stripe_account=account_id)
                state = str(sess.get("status") or "")
            return state

        try:
            return await asyncio.to_thread(_expire)
        except Exception as exc:  # noqa: BLE001
            raise CappeStripeError(f"Failed to expire checkout session: {exc}") from exc

    async def refund_connected_charge(
        self, *, account_id: str, payment_intent: str, idempotency_key: Optional[str] = None,
    ):
        """Refund, in full, a DIRECT charge that lives on a connected account —
        a storefront order or a collab installment.

        `refund()` below cannot do this: it runs on the platform account, where
        a connected account's PaymentIntent does not exist. The `stripe_account`
        header is what reaches it. `refund_application_fee=True` hands our
        platform fee back too — keeping a fee on a sale that was undone would
        make the merchant pay us for a refund.

        The idempotency key makes a retried or double-clicked refund return the
        first refund rather than attempting a second.
        """
        self._ensure_key()

        def _refund():
            kwargs: dict[str, Any] = {"idempotency_key": idempotency_key} if idempotency_key else {}
            return stripe.Refund.create(
                payment_intent=payment_intent,
                refund_application_fee=True,
                stripe_account=account_id,
                **kwargs,
            )

        try:
            return await asyncio.to_thread(_refund)
        except Exception as exc:  # noqa: BLE001
            if getattr(exc, "code", None) == "charge_already_refunded":
                # Refunded already — in the Stripe dashboard, or by an earlier
                # attempt whose response we never saw. The money IS back with
                # the customer, which is what the caller needs to know; failing
                # here would leave the order un-refundable from our side for
                # ever.
                return {"id": None, "already_refunded": True}
            raise CappeStripeError(f"Failed to refund: {exc}") from exc

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
        expires_in_seconds: Optional[int] = None,
    ):
        """Checkout Session on OUR platform account (we keep 100%). Used for
        domain registration and plan billing — no connected account, no fee.
        With save_card, create a Customer + store the card off-session so renewals
        can charge it later.

        `expires_in_seconds` shortens Stripe's default 24h session lifetime
        (minimum 30 minutes). A domain purchase holds a claim on the name while
        its session is payable, so the shorter the better."""
        self._ensure_key()

        def _create():
            pi_data: dict[str, Any] = {"metadata": metadata}
            kwargs: dict[str, Any] = {}
            if save_card:
                pi_data["setup_future_usage"] = "off_session"
                kwargs["customer_creation"] = "always"
            if expires_in_seconds:
                kwargs["expires_at"] = int(time.time()) + max(1800, int(expires_in_seconds))
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

    async def expire_platform_checkout_session(self, session_id: str) -> str:
        """Close a PLATFORM Checkout Session; returns 'expired' or 'complete'.
        Same contract as `expire_checkout_session`, minus the connected account."""
        self._ensure_key()

        def _expire():
            sess = stripe.checkout.Session.retrieve(session_id)
            state = str(sess.get("status") or "")
            if state == "open":
                sess = stripe.checkout.Session.expire(session_id)
                state = str(sess.get("status") or "")
            return state

        try:
            return await asyncio.to_thread(_expire)
        except Exception as exc:  # noqa: BLE001
            raise CappeStripeError(f"Failed to expire checkout session: {exc}") from exc

    async def retrieve_platform_checkout_session(self, session_id: str):
        self._ensure_key()
        try:
            return await asyncio.to_thread(stripe.checkout.Session.retrieve, session_id)
        except Exception as exc:  # noqa: BLE001
            raise CappeStripeError(f"Failed to retrieve checkout session: {exc}") from exc

    async def payment_method_for_intent(self, payment_intent: str) -> Optional[str]:
        """The PaymentMethod id a platform PaymentIntent was paid with.

        Read at purchase time and stored, because it is the only thing an
        off-session charge can use: a PaymentIntent does NOT fall back to "the
        customer's card". `setup_future_usage` attaches the card to the Customer
        but nothing ever made it a default, so a renewal that passed only the
        customer id had nothing to charge.
        """
        self._ensure_key()
        try:
            pi = await asyncio.to_thread(stripe.PaymentIntent.retrieve, payment_intent)
        except Exception as exc:  # noqa: BLE001
            raise CappeStripeError(f"Failed to retrieve payment intent: {exc}") from exc
        pm = pi.get("payment_method")
        if isinstance(pm, dict):
            pm = pm.get("id")
        return pm if isinstance(pm, str) and pm else None

    async def card_fingerprint(self, payment_method_id: str) -> Optional[str]:
        """Stripe's stable per-card fingerprint for a platform PaymentMethod —
        the same physical card yields the same value across customers."""
        self._ensure_key()
        try:
            pm = await asyncio.to_thread(stripe.PaymentMethod.retrieve, payment_method_id)
        except Exception as exc:  # noqa: BLE001
            raise CappeStripeError(f"Failed to retrieve payment method: {exc}") from exc
        fingerprint = (pm.get("card") or {}).get("fingerprint")
        return fingerprint if isinstance(fingerprint, str) and fingerprint else None

    async def saved_card_for_customer(self, customer_id: str) -> Optional[str]:
        """Most recently attached card PaymentMethod on a platform Customer, or
        None. The fallback for rows written before the payment method id was
        stored at purchase."""
        self._ensure_key()

        def _list():
            return stripe.PaymentMethod.list(customer=customer_id, type="card", limit=1)

        try:
            listed = await asyncio.to_thread(_list)
        except Exception as exc:  # noqa: BLE001
            raise CappeStripeError(f"Failed to list payment methods: {exc}") from exc
        data = listed.get("data") or []
        return data[0].get("id") if data else None

    async def charge_off_session(
        self, *, customer_id: str, payment_method_id: str, amount_cents: int, currency: str,
        metadata: dict[str, str], idempotency_key: Optional[str] = None,
    ):
        """Charge a Customer's saved card off-session (e.g. a domain renewal).

        `payment_method_id` is required — see `payment_method_for_intent`.

        Raises `CappeStripeCardError` when the CARD is the problem (declined,
        expired, authentication required) and plain `CappeStripeError` for
        everything else, so the caller can dun the customer for the first and
        simply retry the second. The idempotency key keeps a retrying cron from
        double-charging."""
        self._ensure_key()

        def _charge():
            kwargs = {"idempotency_key": idempotency_key} if idempotency_key else {}
            return stripe.PaymentIntent.create(
                amount=amount_cents,
                currency=currency,
                customer=customer_id,
                payment_method=payment_method_id,
                off_session=True,
                confirm=True,
                metadata=metadata,
                **kwargs,
            )

        try:
            return await asyncio.to_thread(_charge)
        except Exception as exc:  # noqa: BLE001
            if _is_card_error(exc):
                raise CappeStripeCardError(
                    f"Card was refused: {exc}", code=getattr(exc, "code", None)
                ) from exc
            raise CappeStripeError(f"Off-session charge failed: {exc}") from exc

    async def refund(self, payment_intent: str, *, idempotency_key: Optional[str] = None):
        """Refund a platform charge in full (e.g. domain registration failed
        after the customer paid). The idempotency key makes a retried refund
        return the first one instead of failing as already-refunded."""
        self._ensure_key()

        def _refund():
            kwargs = {"idempotency_key": idempotency_key} if idempotency_key else {}
            return stripe.Refund.create(payment_intent=payment_intent, **kwargs)

        try:
            return await asyncio.to_thread(_refund)
        except Exception as exc:  # noqa: BLE001
            if getattr(exc, "code", None) == "charge_already_refunded":
                return {"id": None, "already_refunded": True}  # see refund_connected_charge
            raise CappeStripeError(f"Failed to refund: {exc}") from exc

    async def refund_invoice(self, invoice_id: str) -> list[str]:
        """Refund every paid payment on a platform invoice; returns refund ids.

        For a subscription that should never have existed (the double-checkout
        race): cancelling it stops future billing but leaves the invoice it
        already collected in our account.

        `Invoice.payment_intent` was removed from recent API versions in favour
        of the InvoicePayment list, so both shapes are read.
        """
        self._ensure_key()

        def _refund_all():
            intents: list[str] = []
            lister = getattr(stripe, "InvoicePayment", None)
            if lister is not None:
                for pay in (lister.list(invoice=invoice_id, limit=10).get("data") or []):
                    intent = (pay.get("payment") or {}).get("payment_intent")
                    if pay.get("status") == "paid" and isinstance(intent, str):
                        intents.append(intent)
            if not intents:
                legacy = stripe.Invoice.retrieve(invoice_id).get("payment_intent")
                if isinstance(legacy, str):
                    intents.append(legacy)
            return [
                stripe.Refund.create(payment_intent=pi, idempotency_key=f"cappe-invoice-refund-{pi}")["id"]
                for pi in intents
            ]

        try:
            return await asyncio.to_thread(_refund_all)
        except Exception as exc:  # noqa: BLE001
            raise CappeStripeError(f"Failed to refund invoice: {exc}") from exc

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
                # Without this the item is added even when the proration
                # invoice's payment fails, and the add-on is provisioned unpaid.
                # With it, a failed payment leaves the subscription untouched
                # and parks the change in `pending_update`.
                payment_behavior="pending_if_incomplete",
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
            kwargs: dict[str, Any] = {}
            if invoice_now:
                # An INCREASE is only real once its invoice is paid — see
                # add_subscription_item.
                kwargs["payment_behavior"] = "pending_if_incomplete"
            return stripe.SubscriptionItem.modify(
                item_id,
                quantity=int(quantity),
                proration_behavior="always_invoice" if invoice_now else "create_prorations",
                **kwargs,
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
