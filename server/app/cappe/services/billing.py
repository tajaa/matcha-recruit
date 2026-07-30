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

from asyncpg.exceptions import UniqueViolationError

from app.core.services.stripe_service import extract_current_period_end

from app.database import get_connection

from .entitlements import ENTITLED_SUBSCRIPTION_STATUSES, invalidate_catalog_cache
from .stripe_connect import CappeStripeError, get_cappe_stripe

logger = logging.getLogger(__name__)

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

async def get_or_create_customer(account_id: UUID, email: str) -> str:
    """The account's Stripe Customer, creating one if needed.

    Account-level, unlike the pre-existing per-domain `cappe_domains.
    stripe_customer_id` — a tenant who bought a domain and then subscribed used
    to end up with two unrelated Customers and no single billing identity.

    Manages its own connections and takes none from the caller, deliberately:
    the `stripe.Customer.create` in the middle is a network call, and holding a
    pooled connection across it pins one of ten for the whole round-trip. This
    is the convention `commerce.create_public_order` already documents.
    """
    async with get_connection() as conn:
        existing = await conn.fetchval(
            "SELECT stripe_customer_id FROM cappe_accounts WHERE id = $1", account_id
        )
    if existing:
        return existing

    # No connection held here.
    customer_id = await get_cappe_stripe().ensure_customer(
        email=email, account_id=str(account_id)
    )

    async with get_connection() as conn:
        # Only claim it if nobody raced us; the partial unique index would reject
        # a second account taking the same customer anyway.
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

    Checked against any prior REAL (`source='stripe'`) subscription row — not
    just live ones — so a customer who subscribed and cancelled cannot come
    back for a second $1. The redemption table is the durable record; the
    subscription history is the belt-and-braces check for rows predating it.

    Scoped to `source='stripe'` deliberately: `cappe_subscriptions` also holds
    `source='comp'` rows from `grant_comp`, and comping is a sales motion whose
    whole point is converting the account to a paid plan. Counting a comp
    against intro eligibility would mean anyone ever given a goodwill trial —
    including one that has since lapsed — permanently loses the $1 offer with
    no way for an admin to restore it.
    """
    redeemed = await conn.fetchval(
        "SELECT 1 FROM cappe_intro_redemptions WHERE account_id = $1", account_id
    )
    if redeemed:
        return False
    prior = await conn.fetchval(
        "SELECT 1 FROM cappe_subscriptions WHERE account_id = $1 AND source = 'stripe' LIMIT 1",
        account_id,
    )
    return not prior


DEFAULT_CURRENCY = "USD"


async def resolve_price(
    conn,
    product_code: str,
    interval: str,
    role: str = "standard",
    currency: str = DEFAULT_CURRENCY,
):
    """The current Price row for a product/interval/currency, or None.

    `currency` is part of the lookup, not an afterthought: `uq_cappe_price_current`
    is keyed `(product_code, role, interval, currency) WHERE is_current`, so the
    schema explicitly permits one current price per currency. Filtering on
    product/interval/role alone and taking the newest row would silently start
    charging every customer in whichever currency was added last.
    """
    return await conn.fetchrow(
        """
        SELECT id, stripe_price_id, unit_amount_cents, currency, intro_days
          FROM cappe_billing_prices
         WHERE product_code = $1 AND interval = $2 AND role = $3
           AND currency = $4 AND is_current
         ORDER BY created_at DESC
         LIMIT 1
        """,
        product_code, interval, role, currency.upper(),
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
    """Write the effective tier onto the account.

    A downgrade to free defers to a live, unexpired comp. Without that, ANY
    later `customer.subscription.*` for an unrelated or long-cancelled Stripe
    subscription on the account would resolve to `free` and silently revoke an
    active comp, with nothing to notice it by.
    """
    if plan_code == FREE_PLAN_CODE:
        comp = await conn.fetchrow(
            """
            SELECT plan_code FROM cappe_subscriptions
             WHERE account_id = $1 AND source = 'comp'
               AND status IN ('trialing','active','past_due')
               AND (comped_until IS NULL OR comped_until > NOW())
             ORDER BY created_at DESC
             LIMIT 1
            """,
            account_id,
        )
        if comp is not None:
            plan_code = comp["plan_code"]

    await conn.execute(
        "UPDATE cappe_accounts SET plan = $1, updated_at = NOW() "
        "WHERE id = $2 AND plan IS DISTINCT FROM $1",
        plan_code, account_id,
    )


# ── Sync from Stripe ──────────────────────────────────────────────────────

async def _fetch_price_rows(conn, stripe_price_ids: list[str]) -> dict[str, dict]:
    """Batch-resolve Stripe Price ids to catalog rows, keyed by stripe_price_id.

    One query up front rather than one per subscription item — the plan-
    detection loop and the item-rebuild loop below both need this lookup, and a
    plan plus two add-ons used to cost 6 sequential round-trips inside a
    transaction that is holding row locks the whole time.
    """
    if not stripe_price_ids:
        return {}
    rows = await conn.fetch(
        """
        SELECT pr.stripe_price_id, pr.id AS price_id, pr.product_code,
               pr.interval, p.kind
          FROM cappe_billing_prices pr
          JOIN cappe_billing_products p ON p.code = pr.product_code
         WHERE pr.stripe_price_id = ANY($1::text[])
        """,
        list(stripe_price_ids),
    )
    return {r["stripe_price_id"]: dict(r) for r in rows}


async def _apply_subscription_row(conn, sub_id: UUID, values: dict) -> None:
    """The UPDATE shared by every path that already has a local subscription
    row to write onto — the normal update path and the concurrent-insert
    fallback in `sync_subscription` below. One statement, so they cannot drift."""
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


async def sync_subscription(
    conn,
    *,
    account_id: UUID,
    subscription: Any,
    event_at: Optional[datetime] = None,
) -> Optional[UUID]:
    """Upsert a Stripe Subscription (and its items) and materialize the plan.

    Returns the local subscription id, or None if a newer event already applied
    (the watermark rejected this one) or a duplicate-subscription race was
    resolved by cancelling this one.
    """
    sub = _as_dict(subscription)
    stripe_sub_id = sub.get("id")
    if not stripe_sub_id:
        return None

    status = str(sub.get("status") or "incomplete")
    items = (sub.get("items") or {}).get("data") or []
    item_prices = {item.get("id"): _as_dict(item.get("price") or {}) for item in items}
    price_rows = await _fetch_price_rows(
        conn, [p.get("id") for p in item_prices.values() if p.get("id")]
    )

    # The plan item is the one whose price maps to a catalog row of kind 'plan'.
    plan_code = None
    plan_price_row_id = None
    interval = "month"
    for price in item_prices.values():
        row = price_rows.get(price.get("id"))
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
        await _apply_subscription_row(conn, sub_id, values)
    else:
        # A real paid subscription supersedes any live comp on the account.
        # Without this the INSERT below violates `uq_cappe_sub_live` (one live
        # row per account, regardless of source) — and because that happens
        # inside the webhook, Stripe would retry the event forever while the
        # customer is billed and never receives the plan.
        #
        # This whole block runs inside a SAVEPOINT (every caller already holds
        # an outer transaction) so that a UniqueViolationError here rolls back
        # only to here, not the whole webhook transaction — a statement that
        # runs after sync_subscription returns (e.g. the intro-redemption
        # INSERT in handle_checkout_completed) would otherwise hit
        # InFailedSQLTransactionError on an already-aborted transaction.
        try:
            async with conn.transaction():
                await conn.execute(
                    """
                    UPDATE cappe_subscriptions
                       SET status = 'canceled', canceled_at = NOW(), updated_at = NOW()
                     WHERE account_id = $1 AND source = 'comp'
                       AND status IN ('trialing','active','past_due','incomplete','unpaid','paused')
                    """,
                    account_id,
                )
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
        except UniqueViolationError as exc:
            if exc.constraint_name == "uq_cappe_sub_live":
                # Another LIVE Stripe subscription already exists for this
                # account — the double-checkout race (two tabs both pass
                # start_checkout's guard, because that guard reads a row only
                # the webhook creates). Both subscriptions are real and the
                # customer is being billed twice.
                #
                # Cancel the one we are processing (the later arrival) and
                # report handled, so Stripe stops retrying. Raising instead
                # would leave the event retrying for days while the double
                # billing continues.
                logger.error(
                    "cappe: duplicate live subscription for account %s; cancelling %s",
                    account_id, stripe_sub_id,
                )
                try:
                    await get_cappe_stripe().cancel_subscription(
                        stripe_sub_id, at_period_end=False
                    )
                except CappeStripeError as cancel_exc:
                    logger.error(
                        "cappe: could not cancel duplicate subscription %s: %s — "
                        "MANUAL REFUND REQUIRED", stripe_sub_id, cancel_exc,
                    )
                return None

            # Any other violation on this table is `stripe_subscription_id`
            # (its only other UNIQUE constraint) — a concurrent delivery of the
            # SAME event (two webhook workers, a manual re-drive) inserted this
            # exact subscription first. This is NOT a duplicate subscription —
            # it is the SAME one — so cancelling it would hard-cancel the
            # customer's only real subscription. Re-read what the winner wrote
            # and fall through to the update path instead.
            logger.info(
                "cappe: concurrent insert for subscription %s, re-reading", stripe_sub_id
            )
            existing = await conn.fetchrow(
                "SELECT id FROM cappe_subscriptions WHERE stripe_subscription_id = $1",
                stripe_sub_id,
            )
            if existing is None:
                raise
            sub_id = existing["id"]
            await _apply_subscription_row(conn, sub_id, values)

    # Items are a pure projection — rebuild wholesale so a removed add-on
    # disappears and a quantity change cannot drift from what Stripe bills.
    # DELETE only removes THIS subscription's rows, but stripe_item_id is
    # globally unique — so the ON CONFLICT below could only ever fire against a
    # row belonging to a DIFFERENT subscription. Repointing subscription_id
    # (and product_code/price_id) on conflict, not just quantity, is what makes
    # that safe rather than silently corrupting another account's projection.
    await conn.execute("DELETE FROM cappe_subscription_items WHERE subscription_id = $1", sub_id)
    for item in items:
        price = item_prices.get(item.get("id"), {})
        row = price_rows.get(price.get("id"))
        if not row:
            continue
        await conn.execute(
            """
            INSERT INTO cappe_subscription_items
                (subscription_id, stripe_item_id, product_code, price_id,
                 stripe_price_id, quantity)
            VALUES ($1,$2,$3,$4,$5,$6)
            ON CONFLICT (stripe_item_id) DO UPDATE
               SET subscription_id = EXCLUDED.subscription_id,
                   product_code = EXCLUDED.product_code,
                   price_id = EXCLUDED.price_id,
                   stripe_price_id = EXCLUDED.stripe_price_id,
                   quantity = EXCLUDED.quantity,
                   updated_at = NOW()
            """,
            sub_id, item.get("id"), row["product_code"], row["price_id"],
            price.get("id"), int(item.get("quantity") or 1),
        )

    await _materialize_plan(conn, account_id, effective_plan_code(status, plan_code))
    return sub_id


async def cancel_immediately(conn, *, subscription_id: UUID, account_id: UUID) -> None:
    """Mark a subscription canceled and drop the account's tier right now.

    For an `at_period_end=False` cancel, Stripe deletes the subscription
    synchronously — but local state does not have to wait on the
    `customer.subscription.deleted` webhook to catch up with that. Webhook
    delivery can lag seconds to minutes, during which `resolve_entitlements`
    would keep granting the paid tier for a subscription Stripe has already
    torn down. Deferred (`at_period_end=True`) cancellation is unaffected —
    the customer keeps what they paid for until the period actually ends, so
    that path stays webhook-driven.
    """
    await conn.execute(
        "UPDATE cappe_subscriptions SET status = 'canceled', canceled_at = NOW(), "
        "cancel_at_period_end = false, updated_at = NOW() WHERE id = $1",
        subscription_id,
    )
    await _materialize_plan(conn, account_id, FREE_PLAN_CODE)


async def _account_for_subscription(conn, stripe_sub_id: str) -> Optional[UUID]:
    return await conn.fetchval(
        "SELECT account_id FROM cappe_subscriptions WHERE stripe_subscription_id = $1",
        stripe_sub_id,
    )


# ── Webhook handlers ──────────────────────────────────────────────────────

async def handle_checkout_completed(session: dict, event_at: Optional[datetime]) -> dict:
    """A subscription Checkout finished. Read the subscription back from Stripe
    (the session alone lacks item ids) and record it.

    Opens its own connections around the Stripe call rather than borrowing the
    webhook's, so a slow Stripe round-trip never pins a pooled connection.
    """
    # `.get("metadata", {})` is not a safe default: Stripe sends the key with an
    # explicit `null` on some session shapes, and `None.get(...)` is an
    # AttributeError, not a missing key. `(x or {})` handles both.
    meta = session.get("metadata") or {}
    account_id = meta.get("account_id") or session.get("client_reference_id")
    stripe_sub_id = session.get("subscription")
    if not account_id or not stripe_sub_id:
        return {"status": "ignored"}

    # This webhook receives every checkout.session.completed on the shared
    # platform account. A subscription-mode session from another product whose
    # account_id/client_reference_id isn't a UUID must be ignored, not crash —
    # an unguarded ValueError here 500s, releases the claim, and Stripe retries
    # the same non-Cappe event forever.
    try:
        account_uuid = UUID(str(account_id))
    except (ValueError, TypeError):
        logger.info(
            "cappe: checkout.session.completed with non-UUID account_id %r; ignoring "
            "(likely another product's session on this Stripe account)", account_id,
        )
        return {"status": "ignored"}

    if session.get("customer"):
        async with get_connection() as conn:
            await conn.execute(
                "UPDATE cappe_accounts SET stripe_customer_id = COALESCE(stripe_customer_id, $1), "
                "updated_at = NOW() WHERE id = $2",
                session["customer"], account_uuid,
            )

    # No connection held across this.
    try:
        sub = await get_cappe_stripe().retrieve_subscription(stripe_sub_id)
    except CappeStripeError as exc:
        logger.error("cappe: could not retrieve subscription %s: %s", stripe_sub_id, exc)
        raise

    async with get_connection() as conn:
        async with conn.transaction():
            await sync_subscription(
                conn, account_id=account_uuid, subscription=sub, event_at=event_at
            )
            if str(meta.get("intro")) == "1":
                # PK makes this idempotent under Stripe retries.
                await conn.execute(
                    """
                    INSERT INTO cappe_intro_redemptions (account_id, stripe_subscription_id)
                    VALUES ($1, $2) ON CONFLICT (account_id) DO NOTHING
                    """,
                    account_uuid, stripe_sub_id,
                )
    return {"status": "ok"}


async def handle_subscription_event(subscription: dict, event_at: Optional[datetime]) -> dict:
    """`customer.subscription.created|updated|deleted`."""
    stripe_sub_id = subscription.get("id")
    if not stripe_sub_id:
        return {"status": "ignored"}

    async with get_connection() as conn:
        account_id = await _account_for_subscription(conn, stripe_sub_id)
        if account_id is None:
            # Not a Cappe subscription (core/Matcha owns it, or we never saw the
            # checkout). Ignoring is correct — and is why this dispatcher must
            # not route on metadata, which Stripe does not reliably inherit onto
            # every downstream object.
            return {"status": "ignored"}
        async with conn.transaction():
            await sync_subscription(
                conn, account_id=account_id, subscription=subscription, event_at=event_at
            )
    return {"status": "ok"}


def _invoice_subscription_id(invoice: dict) -> Optional[str]:
    """The subscription id on an Invoice, across Stripe API versions.

    `Invoice.subscription` was a top-level field through API version
    2025-04-30; the pinned SDK (stripe 15.1.0) defaults to a LATER version
    (2026-04-22.dahlia) where it moved to
    `invoice.parent.subscription_details.subscription`. Reading only the old
    field means `isinstance(stripe_sub_id, str)` is always False on the
    installed SDK — this handler silently never fires for a single event,
    including the intro-trial → first-real-payment reconciliation it exists
    for — with no error anywhere. Both shapes are checked so this survives a
    future Stripe API version bump either direction.
    """
    legacy = invoice.get("subscription")
    if isinstance(legacy, str):
        return legacy
    parent = invoice.get("parent") or {}
    details = parent.get("subscription_details") or {}
    current = details.get("subscription")
    return current if isinstance(current, str) else None


async def handle_invoice_event(
    invoice: dict, *, paid: bool, event_at: Optional[datetime]
) -> dict:
    """`invoice.paid` / `invoice.payment_failed`.

    A failed payment does NOT revoke access here: Stripe retries a failed card
    over days, and `past_due` stays entitled. Access ends only when Stripe moves
    the subscription itself to `unpaid`/`canceled`, which arrives as a
    subscription event.
    """
    stripe_sub_id = _invoice_subscription_id(invoice)
    if stripe_sub_id is None:
        return {"status": "ignored"}

    async with get_connection() as conn:
        account_id = await _account_for_subscription(conn, stripe_sub_id)
    if account_id is None:
        return {"status": "ignored"}

    # No connection held across this.
    try:
        sub = await get_cappe_stripe().retrieve_subscription(stripe_sub_id)
    except CappeStripeError as exc:
        logger.error("cappe: could not retrieve subscription %s: %s", stripe_sub_id, exc)
        raise

    async with get_connection() as conn:
        async with conn.transaction():
            await sync_subscription(
                conn, account_id=account_id, subscription=sub, event_at=event_at
            )
            await conn.execute(
                "UPDATE cappe_subscriptions SET latest_invoice_id = $1, updated_at = NOW() "
                "WHERE stripe_subscription_id = $2",
                invoice.get("id"), stripe_sub_id,
            )
    logger.info(
        "cappe: invoice %s for %s (paid=%s)", invoice.get("id"), stripe_sub_id, paid
    )
    return {"status": "ok"}


async def dispatch_billing_event(event_type: str, obj: dict, event_at: Optional[datetime]) -> dict:
    """Route a platform Stripe event to the right subscription handler.

    Takes no connection: each handler opens its own around its Stripe calls, so
    the webhook never holds a pooled connection across a network round-trip.

    Returns `{"status": "ignored"}` for anything that isn't ours, so the caller
    can 200 rather than retrying an event that belongs to another product on the
    same Stripe account.
    """
    if event_type == "checkout.session.completed":
        if obj.get("mode") == "subscription" or (obj.get("metadata") or {}).get("type") == "cappe_subscription":
            return await handle_checkout_completed(obj, event_at)
        return {"status": "ignored"}
    if event_type.startswith("customer.subscription."):
        return await handle_subscription_event(obj, event_at)
    if event_type in ("invoice.paid", "invoice.payment_failed"):
        return await handle_invoice_event(
            obj, paid=(event_type == "invoice.paid"), event_at=event_at
        )
    return {"status": "ignored"}


# ── Comps (admin-granted plans, no Stripe subscription) ───────────────────

class LiveSubscriptionExists(Exception):
    """Raised when a comp would collide with a paying subscription."""


async def grant_comp(conn, *, account_id: UUID, plan_code: str, until, reason: str) -> None:
    """Grant a plan with no Stripe subscription behind it.

    Modeled explicitly rather than by just setting `cappe_accounts.plan` so a
    comp stays visible, expirable and revocable — otherwise comped accounts are
    indistinguishable from paying ones in every report.

    `uq_cappe_sub_live` allows at most one live row per account regardless of
    source, so this supersedes any live comp first and REFUSES outright when the
    account has a live Stripe subscription. Silently superseding a paying
    subscription would strand it: the Stripe side keeps billing while our row
    says comp. Cancel the subscription first, deliberately.
    """
    paying = await conn.fetchval(
        """
        SELECT stripe_subscription_id FROM cappe_subscriptions
         WHERE account_id = $1 AND source = 'stripe'
           AND status IN ('trialing','active','past_due','incomplete','unpaid','paused')
         LIMIT 1
        """,
        account_id,
    )
    if paying:
        raise LiveSubscriptionExists(
            "This account has a live Stripe subscription. Cancel it before comping, "
            "or the customer keeps being billed."
        )

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


async def expire_lapsed_comps(conn) -> int:
    """Drop accounts whose comp has run out back to free. Returns the count.

    Without this, `comped_until` is decorative: `_materialize_plan` wrote the
    comped tier onto `cappe_accounts.plan` permanently and nothing reads the
    expiry, so a comp "until March" is a comp forever.

    Set-based and idempotent, so it is safe to run on any cadence.
    """
    rows = await conn.fetch(
        """
        WITH lapsed AS (
            UPDATE cappe_subscriptions
               SET status = 'canceled', canceled_at = NOW(), updated_at = NOW()
             WHERE source = 'comp'
               AND status IN ('trialing','active','past_due')
               AND comped_until IS NOT NULL
               AND comped_until <= NOW()
            RETURNING account_id
        )
        UPDATE cappe_accounts a
           SET plan = $1, updated_at = NOW()
          FROM lapsed
         WHERE a.id = lapsed.account_id
           AND NOT EXISTS (
               SELECT 1 FROM cappe_subscriptions s
                WHERE s.account_id = a.id AND s.source = 'stripe'
                  AND s.status IN ('trialing','active','past_due')
           )
        RETURNING a.id
        """,
        FREE_PLAN_CODE,
    )
    return len(rows)
