"""Cappe tenant billing — plan catalog, subscribe, portal, add-ons, cancel.

Charges land on OUR platform Stripe account (this is our revenue), never on the
tenant's connected account — that one is only for their own storefront sales.
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import (
    CappeAccount,
    CappeAddon,
    CappeAddonQuantityRequest,
    CappeCancelRequest,
    CappeChangePlanRequest,
    CappeCatalog,
    CappeCheckoutRequest,
    CappeCheckoutResponse,
    CappePlan,
    CappePlanPrice,
    CappePortalRequest,
    CappePortalResponse,
    CappeSubscription,
    CappeSubscriptionAddon,
)
from ..services import billing as billing_svc
from ..services.entitlements import decode_features, mailbox_quota
from ..services.stripe_connect import CappeStripeError, get_cappe_stripe

logger = logging.getLogger(__name__)

router = APIRouter()


def _prices_for(rows, code: str) -> list[CappePlanPrice]:
    return [
        CappePlanPrice(
            interval=r["interval"],
            unit_amount_cents=r["unit_amount_cents"],
            currency=r["currency"],
            # Nothing is purchasable until the seed script mints the Stripe
            # Price; surfacing that beats a checkout that 400s.
            purchasable=bool(r["stripe_price_id"]),
        )
        for r in rows
        if r["product_code"] == code and r["role"] == "standard"
    ]


@router.get("/billing/catalog", response_model=CappeCatalog)
async def get_catalog(account: CappeAccount = Depends(require_cappe_account)):
    """The purchasable lineup, plus whether THIS account can still claim the $1."""
    async with get_connection() as conn:
        products = await conn.fetch(
            "SELECT * FROM cappe_billing_products WHERE status = 'active' ORDER BY sort_order, code"
        )
        prices = await conn.fetch(
            "SELECT * FROM cappe_billing_prices WHERE is_current AND active"
        )
        intro_ok = await billing_svc.intro_eligible(conn, account.id)

    intro_by_code = {
        r["product_code"]: r for r in prices if r["role"] == "intro"
    }
    plans, addons = [], []
    for p in products:
        if p["kind"] == "plan":
            # Only surface the intro if its Stripe Price actually exists —
            # `_prices_for` already withholds `purchasable` for un-minted
            # standard prices, but intro_price_cents/intro_days carried no such
            # flag. Before the seed script has run, the catalog would advertise
            # "$1 for 30 days" while start_checkout silently drops the intro
            # (its own stripe_price_id check) and charges full price — the
            # customer sees a different amount on Stripe's page than the one
            # they clicked.
            intro_row = intro_by_code.get(p["code"])
            intro = intro_row if intro_row and intro_row["stripe_price_id"] else None
            plans.append(CappePlan(
                code=p["code"], name=p["name"], description=p["description"],
                status=p["status"], sort_order=p["sort_order"],
                can_sell=p["can_sell"], platform_fee_bps=p["platform_fee_bps"],
                allowed_fulfillment=list(p["allowed_fulfillment"] or []),
                site_limit=p["site_limit"],
                mailbox_quota_included=p["mailbox_quota_included"],
                features=decode_features(p["features"]),
                prices=_prices_for(prices, p["code"]),
                intro_price_cents=intro["unit_amount_cents"] if intro else None,
                intro_days=intro["intro_days"] if intro else None,
            ))
        else:
            addons.append(CappeAddon(
                code=p["code"], name=p["name"], description=p["description"],
                unit_label=p["unit_label"], max_quantity=p["max_quantity"],
                prices=_prices_for(prices, p["code"]),
            ))
    return CappeCatalog(plans=plans, addons=addons, intro_available=intro_ok)


async def _subscription_response(account_id) -> CappeSubscription | None:
    """The tenant-facing view of a subscription. One builder, because three
    endpoints return this shape and they must not drift."""
    async with get_connection() as conn:
        sub = await billing_svc.current_subscription(conn, account_id)
        if not sub:
            return None
        addons = await billing_svc.subscription_addons(conn, sub["id"])
        quota = await mailbox_quota(account_id, conn=conn)
    return CappeSubscription(
        plan_code=sub["plan_code"], plan_name=sub.get("plan_name"),
        interval=sub["interval"], status=sub["status"], source=sub["source"],
        current_period_end=sub["current_period_end"], trial_end=sub["trial_end"],
        cancel_at_period_end=sub["cancel_at_period_end"],
        comped_until=sub["comped_until"],
        mailbox_quota=quota,
        addons=[
            CappeSubscriptionAddon(
                code=a["product_code"], name=a["name"],
                unit_label=a["unit_label"], quantity=a["quantity"],
            )
            for a in addons
        ],
    )


@router.get("/billing/subscription", response_model=CappeSubscription | None)
async def get_subscription(account: CappeAccount = Depends(require_cappe_account)):
    return await _subscription_response(account.id)


async def _subscription_response_or_409(account_id) -> CappeSubscription:
    """For the two mutating endpoints below, whose `response_model` is the
    non-Optional `CappeSubscription` — they just applied a real, billed Stripe
    mutation, so returning `null` (or letting FastAPI's own `ResponseValidation
    Error` 500 the request) would report a failure for a change that actually
    succeeded and was already charged.

    A live subscription can genuinely be gone here — an add-on change that
    pushes the subscription to `canceled`, or a `customer.subscription.deleted`
    landing between the mutation and this read — so surface that explicitly as
    409 rather than a validation crash.
    """
    result = await _subscription_response(account_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "The change was applied, but the subscription is no longer active — "
                "it may have just been cancelled. Refresh and check your billing status."
            ),
        )
    return result


@router.post("/billing/checkout", response_model=CappeCheckoutResponse)
async def start_checkout(
    body: CappeCheckoutRequest, account: CappeAccount = Depends(require_cappe_account)
):
    """Subscribe to a plan. The $1 intro is applied by the SERVER when the
    account has never had a subscription — never on client request."""
    async with get_connection() as conn:
        product = await conn.fetchrow(
            "SELECT code, name, status, kind FROM cappe_billing_products WHERE code = $1",
            body.plan_code,
        )
        if product is None or product["kind"] != "plan":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown plan")
        if product["status"] != "active":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="That plan is no longer available.",
            )

        existing = await billing_svc.current_subscription(conn, account.id)
        if existing and existing["source"] == "stripe":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "You already have an active subscription. "
                    "Use POST /billing/change-plan to switch plan or interval."
                ),
            )

        price = await billing_svc.resolve_price(conn, body.plan_code, body.interval)
        if price is None or not price["stripe_price_id"]:
            # The catalog row exists but its Stripe Price was never minted.
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Billing is not configured for this plan yet.",
            )

        intro_applied = False
        intro_price_id = None
        intro_days = None
        if await billing_svc.intro_eligible(conn, account.id):
            intro = await billing_svc.resolve_price(
                conn, body.plan_code, "once", role="intro"
            )
            if intro and intro["stripe_price_id"]:
                intro_applied = True
                intro_price_id = intro["stripe_price_id"]
                intro_days = intro["intro_days"]

    # Outside the connection block on purpose — this may create a Stripe
    # Customer, and holding a pooled connection across that network call pins
    # one of ten for its whole duration.
    customer_id = await billing_svc.get_or_create_customer(account.id, account.email)

    try:
        session = await get_cappe_stripe().create_subscription_checkout_session(
            customer_id=customer_id,
            price_id=price["stripe_price_id"],
            intro_price_id=intro_price_id,
            trial_days=intro_days,
            success_url=body.success_url,
            cancel_url=body.cancel_url,
            metadata={
                "type": "cappe_subscription",
                "account_id": str(account.id),
                "plan_code": body.plan_code,
                "intro": "1" if intro_applied else "0",
            },
        )
    except CappeStripeError as exc:
        logger.error("cappe: subscription checkout failed for %s: %s", account.id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Could not start checkout"
        ) from exc

    url = session.get("url")
    if not url:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Could not start checkout"
        )
    return CappeCheckoutResponse(checkout_url=url, intro_applied=intro_applied)


@router.post("/billing/portal", response_model=CappePortalResponse)
async def open_portal(
    body: CappePortalRequest, account: CappeAccount = Depends(require_cappe_account)
):
    """Stripe's hosted portal for cards, invoices and receipts."""
    async with get_connection() as conn:
        customer_id = await conn.fetchval(
            "SELECT stripe_customer_id FROM cappe_accounts WHERE id = $1", account.id
        )
    if not customer_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No billing account yet — subscribe first.",
        )
    try:
        session = await get_cappe_stripe().create_billing_portal_session(
            customer_id=customer_id, return_url=body.return_url
        )
    except CappeStripeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Could not open billing portal"
        ) from exc
    return CappePortalResponse(portal_url=session["url"])


@router.post("/billing/addons", response_model=CappeSubscription)
async def set_addon_quantity(
    body: CappeAddonQuantityRequest, account: CappeAccount = Depends(require_cappe_account)
):
    """Set how many units of an add-on (e.g. private-email mailboxes) to carry.

    The add-on rides the SAME subscription as an extra item, so there is one
    invoice and one dunning state. Its interval must match the parent's, which
    is why the price is resolved from the subscription's own interval.
    """
    async with get_connection() as conn:
        sub = await billing_svc.current_subscription(conn, account.id)
        if not sub or sub["source"] != "stripe":
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="Add-ons require an active paid subscription.",
            )
        addon = await conn.fetchrow(
            "SELECT code, name, max_quantity FROM cappe_billing_products "
            "WHERE code = $1 AND kind = 'addon' AND status = 'active'",
            body.addon_code,
        )
        if addon is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown add-on")
        if body.quantity > addon["max_quantity"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Maximum {addon['max_quantity']} per account.",
            )

        item = await conn.fetchrow(
            "SELECT stripe_item_id, quantity FROM cappe_subscription_items "
            "WHERE subscription_id = $1 AND product_code = $2",
            sub["id"], body.addon_code,
        )
        price = await billing_svc.resolve_price(conn, body.addon_code, sub["interval"])
        if price is None or not price["stripe_price_id"]:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Billing is not configured for this add-on yet.",
            )
        stripe_sub_id = sub["stripe_subscription_id"]

    cs = get_cappe_stripe()
    try:
        if item is None:
            if body.quantity > 0:
                await cs.add_subscription_item(
                    subscription_id=stripe_sub_id,
                    price_id=price["stripe_price_id"],
                    quantity=body.quantity,
                )
        elif body.quantity == 0:
            await cs.remove_subscription_item(item["stripe_item_id"])
        else:
            await cs.set_item_quantity(
                item_id=item["stripe_item_id"],
                quantity=body.quantity,
                # Only bill immediately when they're buying MORE; a decrease
                # credits the next invoice instead of issuing a negative one.
                invoice_now=body.quantity > int(item["quantity"]),
            )
        fresh = await cs.retrieve_subscription(stripe_sub_id)
    except CappeStripeError as exc:
        logger.error("cappe: add-on change failed for %s: %s", account.id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Could not update add-on"
        ) from exc

    async with get_connection() as conn:
        async with conn.transaction():
            await billing_svc.sync_subscription(
                conn, account_id=account.id, subscription=fresh
            )
    return await _subscription_response_or_409(account.id)


@router.post("/billing/change-plan", response_model=CappeSubscription)
async def change_plan(
    body: CappeChangePlanRequest, account: CappeAccount = Depends(require_cappe_account)
):
    """Move a live subscription to a different plan and/or billing interval.

    Prorated immediately in both directions. Entitlements follow Stripe's own
    view of the subscription rather than this response: the sync below re-reads
    it, and `payment_behavior='pending_if_incomplete'` means an upgrade whose
    proration charge fails does not silently grant the higher tier.
    """
    async with get_connection() as conn:
        sub = await billing_svc.current_subscription(conn, account.id)
        if not sub or sub["source"] != "stripe" or not sub["stripe_subscription_id"]:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active subscription to change. Subscribe first.",
            )
        product = await conn.fetchrow(
            "SELECT code, status, kind FROM cappe_billing_products WHERE code = $1",
            body.plan_code,
        )
        if product is None or product["kind"] != "plan":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown plan")
        if product["status"] != "active":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="That plan is no longer available.",
            )
        if sub["plan_code"] == body.plan_code and sub["interval"] == body.interval:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You are already on that plan and interval.",
            )

        price = await billing_svc.resolve_price(conn, body.plan_code, body.interval)
        if price is None or not price["stripe_price_id"]:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Billing is not configured for this plan yet.",
            )
        plan_item = await conn.fetchrow(
            """
            SELECT i.stripe_item_id
              FROM cappe_subscription_items i
              JOIN cappe_billing_products p ON p.code = i.product_code
             WHERE i.subscription_id = $1 AND p.kind = 'plan'
             LIMIT 1
            """,
            sub["id"],
        )
        if plan_item is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Subscription is still syncing — try again in a moment.",
            )
        stripe_sub_id = sub["stripe_subscription_id"]
        interval_changed = sub["interval"] != body.interval
        was_trialing = sub["status"] == "trialing"

    try:
        await get_cappe_stripe().change_subscription_price(
            subscription_id=stripe_sub_id,
            item_id=plan_item["stripe_item_id"],
            new_price_id=price["stripe_price_id"],
            # Re-anchor only when the billing cadence itself changed; a same-
            # interval tier change should keep the customer's existing renewal
            # date rather than silently moving it.
            anchor_now=interval_changed,
            # Someone upgrading mid-intro starts paying now rather than riding
            # the $1 trial at the higher tier.
            end_trial=was_trialing,
        )
        fresh = await get_cappe_stripe().retrieve_subscription(stripe_sub_id)
    except CappeStripeError as exc:
        logger.error("cappe: plan change failed for %s: %s", account.id, exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Could not change plan"
        ) from exc

    async with get_connection() as conn:
        async with conn.transaction():
            await billing_svc.sync_subscription(
                conn, account_id=account.id, subscription=fresh
            )
    return await _subscription_response_or_409(account.id)


@router.post("/billing/cancel")
async def cancel(
    body: CappeCancelRequest, account: CappeAccount = Depends(require_cappe_account)
):
    """Cancel at the period boundary by default — they keep what they paid for
    until it runs out, and that path stays webhook-driven (entitlements drop
    when Stripe sends the deletion event, not here).

    An IMMEDIATE cancel (`at_period_end=False`) is different: Stripe deletes
    the subscription synchronously, so local state drops the tier right here
    too, rather than waiting on webhook delivery to catch up — see
    `billing_svc.cancel_immediately`.
    """
    async with get_connection() as conn:
        sub = await billing_svc.current_subscription(conn, account.id)
    if not sub or sub["source"] != "stripe" or not sub["stripe_subscription_id"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No active subscription"
        )
    try:
        await get_cappe_stripe().cancel_subscription(
            sub["stripe_subscription_id"], at_period_end=body.at_period_end
        )
    except CappeStripeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Could not cancel"
        ) from exc

    async with get_connection() as conn:
        async with conn.transaction():
            if body.at_period_end:
                await conn.execute(
                    "UPDATE cappe_subscriptions SET cancel_at_period_end = true, "
                    "updated_at = NOW() WHERE id = $1",
                    sub["id"],
                )
            else:
                await billing_svc.cancel_immediately(
                    conn, subscription_id=sub["id"], account_id=account.id
                )
    return {"status": "ok", "at_period_end": body.at_period_end}
