"""Cappe subscription billing — persistence, Stripe sync, and event handling.

Stripe is the source of truth for subscription state; this module projects it
onto `cappe_subscriptions` / `cappe_subscription_items` and materializes the
resulting tier onto `cappe_accounts.plan`, which is what every read path
actually gates on.

Two rules that are easy to get wrong and expensive to get wrong:

1. **Subscription state is always read back from Stripe**, never inferred from a
   Checkout Session. The session does not carry subscription item ids, and the
   add-on quantity lives on the items.
2. **Every write is guarded by an event watermark.** Stripe delivers
   `customer.subscription.updated` out of order. Without the guard a stale
   `trialing` event landing after an `active` one silently downgrades a paying
   account, and nothing in the logs says so.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from app.core.services.stripe_service import extract_current_period_end

from .entitlements import ENTITLED_SUBSCRIPTION_STATUSES, invalidate_catalog_cache
from .stripe_connect import CappeStripeError, get_cappe_stripe

logger = logging.getLogger(__name__)

# Statuses that mean "this account no longer has the tier it paid for".
TERMINAL_STATUSES = frozenset({"canceled", "unpaid", "incomplete_expired"})

FREE_PLAN_CODE = "free"


def _as_dict(obj: Any) -> dict:
    """Stripe SDK objects are not plain dicts; normalize."""
    if isinstance(obj, dict):
        return obj
    to_dict = getattr(obj, "to_dict", None)
    return to_dict() if callable(to_dict) else dict(obj)


def _ts(value: Optional[int]) -> Optional[datetime]:
    if not value:
        return None
    return datetime.fromtimestamp(int(value), tz=timezone.utc)


# ── Customer ──────────────────────────────────────────────────────────────

async def get_or_create_customer(conn, account_id: UUID, email: str) -> str:
    """The account's Stripe Customer, creating one if needed.

    Account-level, unlike the pre-existing per-domain `cappe_domains.
    stripe_customer_id` — a tenant who bought a domain and then subscribed used
    to end up with two unrelated Customers and no single billing identity.
    """
    existing = await conn.fetchval(
        "SELECT stripe_customer_id FROM cappe_accounts WHERE id = $1", account_id
    )
    if existing:
        return existing

    customer_id = await get_cappe_stripe().ensure_customer(
        email=email, account_id=str(account_id)
    )
    # Only claim it if nobody raced us; the partial unique index would reject a
    # second account taking the same customer anyway.
    await conn.execute(
        "UPDATE cappe_accounts SET stripe_customer_id = $1, updated_at = NOW() "
        "WHERE id = $2 AND stripe_customer_id IS NULL",
        customer_id, account_id,
    )
    return await conn.fetchval(
        "SELECT stripe_customer_id FROM cappe_accounts WHERE id = $1", account_id
    ) or customer_id


# ── Reads ─────────────────────────────────────────────────────────────────

async def current_subscription(conn, account_id: UUID) -> Optional[dict]:
    row = await conn.fetchrow(
        """
        SELECT s.*, p.name AS plan_name
          FROM cappe_subscriptions s
          LEFT JOIN cappe_billing_products p ON p.code = s.plan_code
         WHERE s.account_id = $1
           AND s.status IN ('trialing','active','past_due','incomplete','unpaid','paused')
         ORDER BY s.created_at DESC
         LIMIT 1
        """,
        account_id,
    )
    return dict(row) if row else None


async def subscription_addons(conn, subscription_id) -> list[dict]:
    rows = await conn.fetch(
        """
        SELECT i.product_code, i.quantity, i.stripe_item_id, p.name, p.unit_label
          FROM cappe_subscription_items i
          JOIN cappe_billing_products p ON p.code = i.product_code
         WHERE i.subscription_id = $1 AND p.kind = 'addon'
         ORDER BY p.sort_order, p.code
        """,
        subscription_id,
    )
    return [dict(r) for r in rows]


async def intro_eligible(conn, account_id: UUID) -> bool:
    """The $1 offer is once per account, ever.

    Checked against ANY prior subscription row — not just live ones — so a
    customer who subscribed and cancelled cannot come back for a second $1. The
    redemption table is the durable record; the subscription history is the
    belt-and-braces check for rows predating it.
    """
    redeemed = await conn.fetchval(
        "SELECT 1 FROM cappe_intro_redemptions WHERE account_id = $1", account_id
    )
    if redeemed:
        return False
    prior = await conn.fetchval(
        "SELECT 1 FROM cappe_subscriptions WHERE account_id = $1 LIMIT 1", account_id
    )
    return not prior


async def resolve_price(conn, product_code: str, interval: str, role: str = "standard"):
    """The current Price row for a product/interval, or None."""
    return await conn.fetchrow(
        """
        SELECT id, stripe_price_id, unit_amount_cents, currency, intro_days
          FROM cappe_billing_prices
         WHERE product_code = $1 AND interval = $2 AND role = $3 AND is_current
         ORDER BY created_at DESC
         LIMIT 1
        """,
        product_code, interval, role,
    )


# ── Plan materialization ──────────────────────────────────────────────────

def effective_plan_code(status: str, plan_code: str) -> str:
    """The tier an account should actually hold, given its subscription status.

    `incomplete` maps to free: the customer started checkout but no money has
    settled, and handing out the tier before `invoice.paid` is how you give away
    a paid plan to an abandoned card.
    """
    if status in ENTITLED_SUBSCRIPTION_STATUSES:
        return plan_code
    return FREE_PLAN_CODE


async def _materialize_plan(conn, account_id: UUID, plan_code: str) -> None:
    await conn.execute(
        "UPDATE cappe_accounts SET plan = $1, updated_at = NOW() "
        "WHERE id = $2 AND plan IS DISTINCT FROM $1",
        plan_code, account_id,
    )


# ── Sync from Stripe ──────────────────────────────────────────────────────

async def sync_subscription(
    conn,
    *,
    account_id: UUID,
    subscription: Any,
    event_at: Optional[datetime] = None,
) -> Optional[UUID]:
    """Upsert a Stripe Subscription (and its items) and materialize the plan.

    Returns the local subscription id, or None if a newer event already applied
    (the watermark rejected this one).
    """
    sub = _as_dict(subscription)
    stripe_sub_id = sub.get("id")
    if not stripe_sub_id:
        return None

    status = str(sub.get("status") or "incomplete")
    items = (sub.get("items") or {}).get("data") or []

    # The plan item is the one whose price maps to a catalog row of kind 'plan'.
    plan_code = None
    plan_price_row_id = None
    interval = "month"
    for item in items:
        price = _as_dict(item.get("price") or {})
        row = await conn.fetchrow(
            """
            SELECT pr.id AS price_id, pr.product_code, pr.interval, p.kind
              FROM cappe_billing_prices pr
              JOIN cappe_billing_products p ON p.code = pr.product_code
             WHERE pr.stripe_price_id = $1
            """,
            price.get("id"),
        )
        if row and row["kind"] == "plan":
            plan_code = row["product_code"]
            plan_price_row_id = row["price_id"]
            interval = row["interval"]
            break

    if plan_code is None:
        # A subscription on this platform account whose price we don't own —
        # almost certainly a Matcha subscription. Not ours to record.
        logger.info("cappe: ignoring subscription %s with no cappe plan item", stripe_sub_id)
        return None

    period_end = None
    try:
        period_end = _ts(extract_current_period_end(sub))
    except Exception:  # noqa: BLE001
        pass

    existing = await conn.fetchrow(
        "SELECT id, stripe_event_at FROM cappe_subscriptions WHERE stripe_subscription_id = $1",
        stripe_sub_id,
    )

    # Out-of-order guard. Stripe does not promise ordering; an older event
    # arriving late must not overwrite newer state.
    if existing and event_at and existing["stripe_event_at"] and existing["stripe_event_at"] > event_at:
        logger.info(
            "cappe: dropping stale subscription event for %s (%s < %s)",
            stripe_sub_id, event_at, existing["stripe_event_at"],
        )
        return existing["id"]

    values = dict(
        account_id=account_id,
        stripe_subscription_id=stripe_sub_id,
        stripe_customer_id=sub.get("customer"),
        plan_code=plan_code,
        price_id=plan_price_row_id,
        interval=interval,
        status=status,
        current_period_end=period_end,
        trial_end=_ts(sub.get("trial_end")),
        cancel_at_period_end=bool(sub.get("cancel_at_period_end")),
        canceled_at=_ts(sub.get("canceled_at")),
        latest_invoice_id=sub.get("latest_invoice") if isinstance(sub.get("latest_invoice"), str) else None,
        stripe_event_at=event_at,
    )

    if existing:
        sub_id = existing["id"]
        await conn.execute(
            """
            UPDATE cappe_subscriptions
               SET plan_code = $2, price_id = $3, interval = $4, status = $5,
                   current_period_end = $6, trial_end = $7, cancel_at_period_end = $8,
                   canceled_at = $9, latest_invoice_id = $10,
                   stripe_customer_id = COALESCE($11, stripe_customer_id),
                   stripe_event_at = COALESCE($12, stripe_event_at),
                   updated_at = NOW()
             WHERE id = $1
            """,
            sub_id, values["plan_code"], values["price_id"], values["interval"],
            values["status"], values["current_period_end"], values["trial_end"],
            values["cancel_at_period_end"], values["canceled_at"],
            values["latest_invoice_id"], values["stripe_customer_id"],
            values["stripe_event_at"],
        )
    else:
        sub_id = await conn.fetchval(
            """
            INSERT INTO cappe_subscriptions
                (account_id, stripe_subscription_id, stripe_customer_id, plan_code,
                 price_id, interval, status, current_period_end, trial_end,
                 cancel_at_period_end, canceled_at, latest_invoice_id, stripe_event_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
            RETURNING id
            """,
            values["account_id"], values["stripe_subscription_id"],
            values["stripe_customer_id"], values["plan_code"], values["price_id"],
            values["interval"], values["status"], values["current_period_end"],
            values["trial_end"], values["cancel_at_period_end"], values["canceled_at"],
            values["latest_invoice_id"], values["stripe_event_at"],
        )

    # Items are a pure projection — rebuild wholesale so a removed add-on
    # disappears and a quantity change cannot drift from what Stripe bills.
    await conn.execute("DELETE FROM cappe_subscription_items WHERE subscription_id = $1", sub_id)
    for item in items:
        price = _as_dict(item.get("price") or {})
        row = await conn.fetchrow(
            "SELECT id, product_code FROM cappe_billing_prices WHERE stripe_price_id = $1",
            price.get("id"),
        )
        if not row:
            continue
        await conn.execute(
            """
            INSERT INTO cappe_subscription_items
                (subscription_id, stripe_item_id, product_code, price_id,
                 stripe_price_id, quantity)
            VALUES ($1,$2,$3,$4,$5,$6)
            ON CONFLICT (stripe_item_id) DO UPDATE
               SET quantity = EXCLUDED.quantity, updated_at = NOW()
            """,
            sub_id, item.get("id"), row["product_code"], row["id"],
            price.get("id"), int(item.get("quantity") or 1),
        )

    await _materialize_plan(conn, account_id, effective_plan_code(status, plan_code))
    return sub_id


async def _account_for_subscription(conn, stripe_sub_id: str) -> Optional[UUID]:
    return await conn.fetchval(
        "SELECT account_id FROM cappe_subscriptions WHERE stripe_subscription_id = $1",
        stripe_sub_id,
    )


# ── Webhook handlers ──────────────────────────────────────────────────────

async def handle_checkout_completed(conn, session: dict, event_at: Optional[datetime]) -> dict:
    """A subscription Checkout finished. Read the subscription back from Stripe
    (the session alone lacks item ids) and record it."""
    account_id = session.get("metadata", {}).get("account_id") or session.get("client_reference_id")
    stripe_sub_id = session.get("subscription")
    if not account_id or not stripe_sub_id:
        return {"status": "ignored"}

    account_uuid = UUID(str(account_id))
    if session.get("customer"):
        await conn.execute(
            "UPDATE cappe_accounts SET stripe_customer_id = COALESCE(stripe_customer_id, $1), "
            "updated_at = NOW() WHERE id = $2",
            session["customer"], account_uuid,
        )

    try:
        sub = await get_cappe_stripe().retrieve_subscription(stripe_sub_id)
    except CappeStripeError as exc:
        logger.error("cappe: could not retrieve subscription %s: %s", stripe_sub_id, exc)
        raise

    await sync_subscription(conn, account_id=account_uuid, subscription=sub, event_at=event_at)

    if str(session.get("metadata", {}).get("intro")) == "1":
        # PK makes this idempotent under Stripe retries.
        await conn.execute(
            """
            INSERT INTO cappe_intro_redemptions (account_id, stripe_subscription_id)
            VALUES ($1, $2) ON CONFLICT (account_id) DO NOTHING
            """,
            account_uuid, stripe_sub_id,
        )
    return {"status": "ok"}


async def handle_subscription_event(conn, subscription: dict, event_at: Optional[datetime]) -> dict:
    """`customer.subscription.created|updated|deleted`."""
    stripe_sub_id = subscription.get("id")
    account_id = await _account_for_subscription(conn, stripe_sub_id) if stripe_sub_id else None
    if account_id is None:
        # Not a Cappe subscription (core/Matcha owns it, or we never saw the
        # checkout). Ignoring is correct — and is why this dispatcher must not
        # route on metadata, which Stripe does not reliably inherit onto every
        # downstream object.
        return {"status": "ignored"}

    await sync_subscription(
        conn, account_id=account_id, subscription=subscription, event_at=event_at
    )
    return {"status": "ok"}


async def handle_invoice_event(
    conn, invoice: dict, *, paid: bool, event_at: Optional[datetime]
) -> dict:
    """`invoice.paid` / `invoice.payment_failed`.

    A failed payment does NOT revoke access here: Stripe retries a failed card
    over days, and `past_due` stays entitled. Access ends only when Stripe moves
    the subscription itself to `unpaid`/`canceled`, which arrives as a
    subscription event.
    """
    stripe_sub_id = invoice.get("subscription")
    if not isinstance(stripe_sub_id, str):
        return {"status": "ignored"}
    account_id = await _account_for_subscription(conn, stripe_sub_id)
    if account_id is None:
        return {"status": "ignored"}

    try:
        sub = await get_cappe_stripe().retrieve_subscription(stripe_sub_id)
    except CappeStripeError as exc:
        logger.error("cappe: could not retrieve subscription %s: %s", stripe_sub_id, exc)
        raise

    await sync_subscription(conn, account_id=account_id, subscription=sub, event_at=event_at)
    await conn.execute(
        "UPDATE cappe_subscriptions SET latest_invoice_id = $1, updated_at = NOW() "
        "WHERE stripe_subscription_id = $2",
        invoice.get("id"), stripe_sub_id,
    )
    logger.info(
        "cappe: invoice %s for %s (paid=%s)", invoice.get("id"), stripe_sub_id, paid
    )
    return {"status": "ok"}


async def dispatch_billing_event(conn, event_type: str, obj: dict, event_at: Optional[datetime]) -> dict:
    """Route a platform Stripe event to the right subscription handler.

    Returns `{"status": "ignored"}` for anything that isn't ours, so the caller
    can 200 rather than retrying an event that belongs to another product on the
    same Stripe account.
    """
    if event_type == "checkout.session.completed":
        if obj.get("mode") == "subscription" or (obj.get("metadata") or {}).get("type") == "cappe_subscription":
            return await handle_checkout_completed(conn, obj, event_at)
        return {"status": "ignored"}
    if event_type.startswith("customer.subscription."):
        return await handle_subscription_event(conn, obj, event_at)
    if event_type in ("invoice.paid", "invoice.payment_failed"):
        return await handle_invoice_event(
            conn, obj, paid=(event_type == "invoice.paid"), event_at=event_at
        )
    return {"status": "ignored"}


# ── Comps (admin-granted plans, no Stripe subscription) ───────────────────

async def grant_comp(conn, *, account_id: UUID, plan_code: str, until, reason: str) -> None:
    """Grant a plan with no Stripe subscription behind it.

    Modeled explicitly rather than by just setting `cappe_accounts.plan` so a
    comp stays visible and revocable — otherwise comped accounts are
    indistinguishable from paying ones in every report.
    """
    await conn.execute(
        "UPDATE cappe_subscriptions SET status = 'canceled', canceled_at = NOW(), "
        "updated_at = NOW() WHERE account_id = $1 AND source = 'comp' "
        "AND status IN ('trialing','active','past_due','incomplete','unpaid','paused')",
        account_id,
    )
    await conn.execute(
        """
        INSERT INTO cappe_subscriptions
            (account_id, plan_code, interval, status, source, comped_until, comp_reason)
        VALUES ($1, $2, 'month', 'active', 'comp', $3, $4)
        """,
        account_id, plan_code, until, reason,
    )
    await _materialize_plan(conn, account_id, plan_code)
    invalidate_catalog_cache()
