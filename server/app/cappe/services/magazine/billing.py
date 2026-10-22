"""A reader's paid subscription to a magazine (cappemag05).

It is a `cappe_shopper_subscriptions` row with `kind='magazine'`, so it gets
everything the store's recurring orders already have: the hardened Stripe
Checkout handshake (`recurring._attach_checkout_session`), cancel and resume,
the card-update portal, the account page, deletion of the reader or the site,
and the webhook's state sync. What differs:

  * one monthly line at the magazine's price — no tax or shipping lines; the
    price is what the reader pays;
  * Gummfit's cut is `magazine_fee_bps` (`cappe_marketplace_settings`, 30%
    unless an admin changes it), never the plan's store fee;
  * a paid invoice is a `cappe_magazine_payments` row, not an order: no
    stock, no receipt, no order alert (`record_magazine_payment`).

The subscription is on the writer's own Stripe account (Connect, direct
charges), so Stripe's processing fee comes out of the writer's balance.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import HTTPException

from app.database import get_connection
from ..common import site_origins, url_within_origins
from ..entitlements import resolve_entitlements
from ..shopper_customers import connected_customer
from ..stripe_connect import CappeStripeError, get_cappe_stripe
from .access import has_paid_access
from .magazines import live_magazine

logger = logging.getLogger(__name__)

DEFAULT_FEE_BPS = 3000
MAX_FEE_BPS = 5000
_OPEN = ("preparing", "incomplete", "cancel_requested")


async def fee_bps(conn) -> int:
    """Gummfit's share of a reader's payment, in basis points. A missing,
    unreadable or out-of-range setting is the default, never the plan's store
    fee."""
    from ..collab import resolve_marketplace_int

    bps = await resolve_marketplace_int(conn, "magazine_fee_bps", "bps", DEFAULT_FEE_BPS)
    return bps if 0 <= bps <= MAX_FEE_BPS else DEFAULT_FEE_BPS


def subscription_title(mag: dict, site: dict) -> str:
    return f"{mag.get('name') or site.get('name') or 'Magazine'} subscription"[:250]


async def paid_ready(conn, site: dict) -> tuple[Optional[dict], Optional[dict]]:
    """(magazine, owner) when the magazine can take a new subscriber now, or
    raises with the reason it can't."""
    mag = await live_magazine(conn, site)
    if not mag or not mag.get("paid_enabled") or not mag.get("price_cents"):
        raise HTTPException(409, "This magazine isn't taking subscriptions.")
    owner = await conn.fetchrow(
        "SELECT stripe_account_id, stripe_charges_enabled, plan FROM cappe_accounts WHERE id = $1 AND status = 'active'",
        site["account_id"],
    )
    ent = await resolve_entitlements(owner["plan"] if owner else None, conn=conn)
    if not owner or not ent.has("magazine_paid"):
        raise HTTPException(402, "This magazine isn't taking subscriptions right now.")
    if not owner["stripe_account_id"] or not owner["stripe_charges_enabled"]:
        raise HTTPException(409, "This magazine isn't taking card payments yet.")
    return mag, dict(owner)


async def checkout(site: dict, shopper: dict, body, *, return_origins: Optional[list[str]] = None) -> dict[str, Any]:
    """Start a reader's subscription: a `preparing` row under the reader's lock,
    then Stripe Checkout on the writer's account, then the session attached
    (or expired, if the reader's account was deleted meanwhile). Checkout
    returns to the magazine's own address, or to `return_origins` (the
    reader's dashboard on gummfit.com)."""
    from .. import recurring

    origins = return_origins or site_origins(site)
    success, cancel = url_within_origins(body.success_url, origins), url_within_origins(body.cancel_url, origins)
    if not success or not cancel:
        raise HTTPException(422, "Checkout returns must use this magazine's own address")
    async with get_connection() as conn:
        mag, owner = await paid_ready(conn, site)
        bps = await fee_bps(conn)
    customer_id = await connected_customer(shopper, owner["stripe_account_id"])
    price = int(mag["price_cents"])
    currency = (site.get("currency") or "USD").upper()
    title = subscription_title(mag, site)
    async with get_connection() as conn, conn.transaction():
        live = await conn.fetchrow(
            "SELECT deleting FROM cappe_shoppers WHERE id = $1 AND site_id = $2 FOR UPDATE", shopper["id"], site["id"],
        )
        if not live or live["deleting"]:
            raise HTTPException(409, "Account deletion is in progress")
        if await has_paid_access(conn, site["id"], shopper["id"]):
            raise HTTPException(409, "You already subscribe to this magazine.")
        # Checkouts this reader opened and never finished. They are closed
        # once the lock is released (closing one calls Stripe), so a reader
        # who clicks Subscribe twice can't end up paying twice.
        stale = await conn.fetch(
            "SELECT * FROM cappe_shopper_subscriptions WHERE site_id = $1 AND shopper_id = $2 "
            "AND kind = 'magazine' AND status = ANY($3::text[])",
            site["id"], shopper["id"], list(_OPEN),
        )
        row = await conn.fetchrow(
            "INSERT INTO cappe_shopper_subscriptions (site_id, shopper_id, stripe_account_id, status, interval, items, "
            "subtotal_cents, tax_cents, shipping_cents, total_cents, currency, tax_included, shipping_tax_cents, kind) "
            "VALUES ($1, $2, $3, 'preparing', 'month', $4::jsonb, $5, 0, 0, $5, $6, true, 0, 'magazine') RETURNING *",
            site["id"], shopper["id"], owner["stripe_account_id"],
            json.dumps([{"title": title, "quantity": 1, "unit_price_cents": price, "fulfillment": "magazine"}]),
            price, currency,
        )
    for old in stale:
        try:
            await recurring.change_subscription(old, True)
        except HTTPException as exc:
            # It may be paid with its webhook still on the way (Stripe won't
            # close a completed checkout): a new one could charge the reader
            # twice, so none opens until that one settles or expires.
            logger.info("magazine checkout %s not closed yet: %s", old["id"], exc.detail)
            async with get_connection() as conn:
                await conn.execute(
                    "DELETE FROM cappe_shopper_subscriptions WHERE id = $1 AND status = 'preparing'", row["id"],
                )
            raise HTTPException(409, "Your last checkout is still being confirmed. Give it a minute, "
                                     "then check your subscription.") from exc
    line = {"price_data": {"currency": currency.lower(), "unit_amount": price, "recurring": {"interval": "month"},
                           "product_data": {"name": title}}, "quantity": 1}
    try:
        session = await get_cappe_stripe().create_subscription_checkout(
            account_id=owner["stripe_account_id"], customer_id=customer_id, line_items=[line],
            application_fee_percent=round(bps / 100, 2), success_url=success, cancel_url=cancel,
            metadata={"cappe_shopper_subscription_id": str(row["id"]), "site_id": str(site["id"]),
                      "cappe_kind": "magazine"},
            collect_shipping=False, idempotency_key=f"mag-sub:{row['id']}",
        )
    except CappeStripeError as exc:
        # Kept: a session Stripe made before a timeout reaches us by webhook.
        raise HTTPException(503, "Checkout could not be confirmed. Check your subscription before trying again.") from exc
    if not await recurring._attach_checkout_session(row, shopper, session["id"]):
        await recurring._expire_checkout_session(row, session["id"])
        raise HTTPException(409, "Checkout was canceled before it could open")
    return {"checkout_url": session["url"], "subscription_id": str(row["id"])}


def _paid_at(invoice: dict) -> datetime:
    stamp = ((invoice.get("status_transitions") or {}).get("paid_at")) or invoice.get("created")
    try:
        return datetime.fromtimestamp(int(stamp), timezone.utc)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)


async def record_magazine_payment(conn, row, invoice: dict, payment_intent: Optional[str]) -> Optional[UUID]:
    """One paid invoice of a reader's subscription, into the ledger. The caller
    holds the subscription's lock and transaction; the invoice id is unique,
    so a replayed event records nothing (returns None)."""
    fee = invoice.get("application_fee_amount")
    amount = invoice.get("amount_paid")
    if not isinstance(amount, int):
        amount = invoice.get("total", row["total_cents"])
    return await conn.fetchval(
        "INSERT INTO cappe_magazine_payments (site_id, subscription_id, shopper_id, stripe_account_id, "
        "stripe_invoice_id, stripe_payment_intent, amount_cents, fee_cents, currency, billing_reason, paid_at) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11) "
        "ON CONFLICT (stripe_invoice_id) DO NOTHING RETURNING id",
        row["site_id"], row["id"], row["shopper_id"], row["stripe_account_id"], invoice["id"], payment_intent,
        int(amount or 0), int(fee) if isinstance(fee, int) else None,
        str(invoice.get("currency") or row["currency"]).upper()[:3], invoice.get("billing_reason"), _paid_at(invoice),
    )


async def sync_refund(conn, *, account_id: str, payment_intent: Optional[str], invoice_id: Optional[str],
                      refunded_cents: int) -> Optional[UUID]:
    """`charge.refunded` for a reader's payment: the ledger takes Stripe's
    total refunded (never less than it already had — events can arrive out of
    order). Returns the payment's id, or None when it isn't a magazine one."""
    if not payment_intent and not invoice_id:
        return None
    return await conn.fetchval(
        "UPDATE cappe_magazine_payments SET refunded_cents = GREATEST(refunded_cents, LEAST(amount_cents, $4)) "
        "WHERE stripe_account_id = $1 AND ((stripe_payment_intent = $2 AND $2 IS NOT NULL) "
        "OR (stripe_invoice_id = $3 AND $3 IS NOT NULL)) RETURNING id",
        account_id, payment_intent, invoice_id, max(0, int(refunded_cents or 0)),
    )
