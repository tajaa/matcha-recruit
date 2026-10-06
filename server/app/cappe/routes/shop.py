"""Cappe shop — products CRUD + order management (owner side).

Public checkout lives in routes/public/shop.py. Card payment is real: a
storefront order with Stripe Connect ready goes through Checkout and the paid
webhook (routes/payments.py) flips it to 'paid'. Orders that take no card — a
site without Connect, an approval-gated cart — are created 'pending' and the
owner advances status by hand here.
"""
import json
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status

from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import (
    CappeAccount,
    CappeApprovalDecline,
    CappeDeliverableUpdate,
    CappeInventoryAdjustment,
    CappeOrder,
    CappeOrderItem,
    CappeOrderStatusUpdate,
    CappeProduct,
    CappeProductCreate,
    CappeProductUpdate,
    CappeRefundRequest,
    CappeStockAdjust,
)
from ._shared import build_patch, fetch_option_groups, get_owned_site, loads, loads_list
from ..services.options import match_prior_rows
from ..services.common import order_page_url, receipt_filename as _receipt_filename
from ..services.email import (
    build_order_items_summary,
    send_cappe_order_approved_email,
    send_cappe_order_declined_email,
    send_cappe_order_shipped_email,
)
from ..services.directory import refresh_site_search
from ..services.inventory import log_adjustment, release_order_bookings, restock_order
from ..services.entitlements import require_fulfillment, resolve_entitlements
from ..services.order_lifecycle import REFUNDABLE_STATUSES, mark_order_refunded, transition_error
from ..services.receipt import issue_receipt_for_paid_order
from ..services.stripe_connect import CappeStripeError, get_cappe_stripe

# Order statuses that reflect a physical decrement having happened, and the
# statuses that reverse it. A status TRANSITION between these two sets is what
# triggers a restock — not the destination status alone — so cancelling an
# already-cancelled/declined order (nothing to reverse) or an already-restocked
# one (double-click) is a no-op rather than a double-credit.
_RESTOCK_FROM_STATUSES = {"pending", "paid", "fulfilled"}
_RESTOCK_TO_STATUSES = {"cancelled", "refunded"}


def should_restock(current_status: str, new_status: str | None) -> bool:
    """A restock reverses a stock decrement, so it depends on the transition,
    not the destination. `new_status=None` is a tracking-only PATCH — it never
    touches stock."""
    return (
        new_status is not None
        and current_status in _RESTOCK_FROM_STATUSES
        and new_status in _RESTOCK_TO_STATUSES
    )


router = APIRouter()

# How long a buyer has to pay for an order the owner approved.
PAY_WINDOW_DAYS = 3


def _items_summary(items) -> str:
    return build_order_items_summary([{"title": i["title"], "quantity": i["quantity"]} for i in items])


async def _order_token(order_id, conn=None):
    """The order's access token — for the order-page link, never returned
    to the owner's dashboard (`_ORDER_COLS` leaves it out on purpose)."""
    if conn is not None:
        return await conn.fetchval("SELECT access_token FROM cappe_orders WHERE id = $1", order_id)
    async with get_connection() as own:
        return await own.fetchval("SELECT access_token FROM cappe_orders WHERE id = $1", order_id)


async def _close_open_checkout(
    site_id: UUID, order_id: UUID, account_id: UUID, *, then: str = "refund it",
) -> None:
    """Close a pending order's Stripe Checkout Session before it is released.

    A Checkout Session stays payable for 24 hours. Cancelling or declining the
    order underneath an open one leaves a live payment page pointing at an order
    we have thrown away: the buyer pays, and the webhook has to resurrect an
    order whose stock and slots are already gone. So the session is closed
    FIRST — the same rule the abandoned-order reaper follows — and the release
    only proceeds once Stripe confirms nobody can pay it.

    Opens and closes its own connection around the lookup so no pooled
    connection is held across the Stripe round-trip. No-op for orders that never
    went to Stripe or are no longer pending.
    """
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """SELECT o.status, o.stripe_session_id, a.stripe_account_id
                 FROM cappe_orders o
                 JOIN cappe_sites s ON s.id = o.site_id
                 JOIN cappe_accounts a ON a.id = s.account_id
                WHERE o.id = $1 AND o.site_id = $2 AND s.account_id = $3""",
            order_id, site_id, account_id,
        )
    if (
        row is None
        or row["status"] != "pending"
        or not row["stripe_session_id"]
        or not row["stripe_account_id"]
    ):
        return
    try:
        state = await get_cappe_stripe().expire_checkout_session(
            row["stripe_account_id"], row["stripe_session_id"]
        )
    except CappeStripeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Couldn't close the customer's payment page, so the order was left as is: {exc}",
        )
    if state != "expired":
        # 'complete': the buyer finished checkout. The money is in, or a delayed
        # method (ACH, SEPA) is still settling; the webhook decides this order.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The customer has already completed checkout and the payment is settling. "
                   f"Wait for it to be marked paid, then {then}.",
        )

_PRODUCT_COLS = (
    "subscription_intervals, subscription_discount_bps, "
    "id, site_id, name, description, price_cents, currency, image_url, sku, "
    "inventory, low_stock_threshold, status, sort_order, fulfillment, digital_file_url, "
    "booking_type_id, requires_approval, intake_fields, category, created_at, updated_at"
)
_ORDER_COLS = (
    "subscription_id, "
    "id, site_id, customer_email, customer_name, status, subtotal_cents, "
    "tax_cents, shipping_cents, total_cents, receipt_number, "
    "shipping_address, carrier, tracking_number, "
    "currency, payment_ref, note, requires_approval, approved_at, decline_reason, "
    "refunded_at, refunded_cents, dispute_status, disputed_at, "
    "pay_by, shipped_notified_at, platform_fee_cents, "
    "metadata, created_at, updated_at"
)
_ITEM_COLS = (
    "id, product_id, title, unit_price_cents, quantity, fulfillment, "
    "intake_answers, selected_options, deliverable_url, booking_id"
)


def _product_row(row, groups=None) -> dict:
    d = dict(row)
    d["intake_fields"] = loads_list(row["intake_fields"])
    d["option_groups"] = groups or []
    return d


def _item_row(row) -> dict:
    d = dict(row)
    d["intake_answers"] = loads(row["intake_answers"])
    d["selected_options"] = loads_list(row["selected_options"])
    return d


def _stock_conflict(now: int | None) -> HTTPException:
    """The stock the editor was showing is not the stock on the shelf any more."""
    state = "is no longer tracked" if now is None else f"is now {now}"
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"Stock changed while you were editing — it {state} (a sale, a return or another "
               "edit). Reload the product and set the stock again.",
    )


async def _replace_option_groups(conn, site_id, product_id, groups) -> None:
    """Bring a product's option groups + options in line with `groups`
    (None = leave as-is, [] = clear), keeping the id of everything that
    survives.

    This used to delete every group and insert the set again, so each save
    minted new option ids. Order lines (`selected_option_ids`), subscription
    snapshots and the stock ledger all point at option ids: after any edit a
    cancelled or refunded order no longer restocked its variant, renewals
    stopped decrementing it, and a shopper with the product open was told
    "Unknown product option". Rows are now matched (`match_prior_rows`) and
    updated in place.

    Option stock is tri-state on an existing option — omitted leaves it alone,
    a number sets it (with a ledger row), null stops tracking — so an edit that
    is not about stock cannot write a stale count over sales made since the
    form loaded. MUST run inside the caller's transaction, after it has locked
    the product row (products before options, the order `lock_stock_rows` uses).
    """
    if groups is None:
        return
    prior_groups = await conn.fetch(
        "SELECT id, name FROM cappe_product_option_groups "
        "WHERE product_id = $1 AND site_id = $2 ORDER BY sort_order, created_at",
        product_id, site_id,
    )
    prior_options = await conn.fetch(
        "SELECT o.id, o.group_id, o.name, o.inventory FROM cappe_product_options o "
        "JOIN cappe_product_option_groups g ON g.id = o.group_id "
        "WHERE g.product_id = $1 AND o.site_id = $2 ORDER BY o.id FOR UPDATE OF o",
        product_id, site_id,
    )
    options_by_group: dict = {}
    for row in prior_options:
        options_by_group.setdefault(row["group_id"], []).append(row)

    group_pairs, groups_gone = match_prior_rows(list(prior_groups), groups)
    for gi, (g, was) in enumerate(zip(groups, group_pairs)):
        # Position is the order unless the caller pinned one: rows keep their
        # created_at now, so it can no longer stand in for "the order sent".
        g_sort = g.sort_order if "sort_order" in g.model_fields_set else gi
        if was is None:
            gid = await conn.fetchval(
                """INSERT INTO cappe_product_option_groups
                       (site_id, product_id, name, select_type, required, sort_order)
                   VALUES ($1, $2, $3, $4, $5, $6) RETURNING id""",
                site_id, product_id, g.name, g.select_type, g.required, g_sort,
            )
            stored = []
        else:
            gid = was["id"]
            await conn.execute(
                "UPDATE cappe_product_option_groups "
                "SET name = $1, select_type = $2, required = $3, sort_order = $4 WHERE id = $5",
                g.name, g.select_type, g.required, g_sort, gid,
            )
            stored = options_by_group.get(gid, [])

        incoming = g.options or []
        option_pairs, options_gone = match_prior_rows(stored, incoming)
        for oi, (o, owas) in enumerate(zip(incoming, option_pairs)):
            o_sort = o.sort_order if "sort_order" in o.model_fields_set else oi
            if owas is None:
                new_oid = await conn.fetchval(
                    """INSERT INTO cappe_product_options
                           (site_id, group_id, name, price_delta_cents, sort_order, inventory)
                       VALUES ($1, $2, $3, $4, $5, $6) RETURNING id""",
                    site_id, gid, o.name, o.price_delta_cents, o_sort, o.inventory,
                )
                if o.inventory is not None:
                    await log_adjustment(
                        conn, site_id=site_id, product_id=product_id, option_id=new_oid,
                        delta=o.inventory, balance_after=o.inventory,
                        reason="adjustment", note="Opening stock",
                    )
                continue
            sets = "name = $1, price_delta_cents = $2, sort_order = $3"
            args = [o.name, o.price_delta_cents, o_sort]
            if "inventory" in o.model_fields_set and o.inventory != owas["inventory"]:
                if "expected_inventory" in o.model_fields_set and o.expected_inventory != owas["inventory"]:
                    raise _stock_conflict(owas["inventory"])
                sets += ", inventory = $4"
                args.append(o.inventory)
                if o.inventory is not None:
                    await log_adjustment(
                        conn, site_id=site_id, product_id=product_id, option_id=owas["id"],
                        delta=o.inventory - (owas["inventory"] or 0), balance_after=o.inventory,
                        reason="adjustment", note="Set in the product editor",
                    )
            args.append(owas["id"])
            await conn.execute(
                f"UPDATE cappe_product_options SET {sets} WHERE id = ${len(args)}", *args,
            )
        if options_gone:
            await conn.execute(
                "DELETE FROM cappe_product_options WHERE id = ANY($1::uuid[]) AND site_id = $2",
                [row["id"] for row in options_gone], site_id,
            )
    if groups_gone:
        await conn.execute(
            "DELETE FROM cappe_product_option_groups WHERE id = ANY($1::uuid[]) AND site_id = $2",
            [row["id"] for row in groups_gone], site_id,
        )


def _subscription_changed(body, existing) -> bool:
    """Whether an edit actually changes the product's subscription settings.

    The editor sends them on every save, so "the field is present" used to
    count as a change — and a plan without recurring orders got a 402 for
    fixing a typo. Only a different value is a change.
    """
    fields = body.model_fields_set
    if "subscription_intervals" in fields and (
        sorted(body.subscription_intervals or []) != sorted(existing["subscription_intervals"] or [])
    ):
        return True
    return (
        "subscription_discount_bps" in fields
        and body.subscription_discount_bps != existing["subscription_discount_bps"]
    )


def _order_row(row, items=None) -> dict:
    d = dict(row)
    d["metadata"] = loads(row["metadata"])
    d["shipping_address"] = loads(row["shipping_address"]) or None  # loads() maps NULL→{}; keep None
    d["items"] = items or []
    return d


async def _guard_subscribers(site_id, product_id, end_subscriptions: bool) -> None:
    """A product shoppers subscribe to can't silently leave the shop.

    Deleting or archiving it used to leave every subscription renewing: the
    shopper kept being charged for a product the store no longer sold (and
    after a delete, its renewal order lines pointed at nothing). The owner now
    has to say so — `end_subscriptions=true` stops those subscriptions renewing
    after the period already paid for; without it the change is refused with
    the count, so the dashboard can ask."""
    from ..services.recurring import end_subscriptions_at_period_end, live_subscriptions_for_product

    async with get_connection() as conn:
        rows = await live_subscriptions_for_product(conn, site_id, product_id)
    if not rows:
        return
    if not end_subscriptions:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "has_subscriptions",
                "count": len(rows),
                "message": f"{len(rows)} customer subscription{'s' if len(rows) != 1 else ''} include this product. "
                           "Ending them stops their renewals after the period already paid for.",
            },
        )
    await end_subscriptions_at_period_end(rows)


async def _validate_booking_type(conn, site_id, booking_type_id) -> None:
    """Ensure a referenced booking type belongs to this site (or 400)."""
    if booking_type_id is None:
        return
    ok = await conn.fetchval(
        "SELECT 1 FROM cappe_booking_types WHERE id = $1 AND site_id = $2",
        booking_type_id, site_id,
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown booking type")


# --- Products ---------------------------------------------------------------

@router.get("/sites/{site_id}/products", response_model=list[CappeProduct])
async def list_products(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        rows = await conn.fetch(
            f"SELECT {_PRODUCT_COLS} FROM cappe_products WHERE site_id = $1 ORDER BY sort_order, created_at",
            site_id,
        )
        groups = await fetch_option_groups(conn, [r["id"] for r in rows])
    return [_product_row(r, groups.get(r["id"])) for r in rows]


@router.post("/sites/{site_id}/products", response_model=CappeProduct, status_code=status.HTTP_201_CREATED)
async def create_product(
    site_id: UUID, body: CappeProductCreate, account: CappeAccount = Depends(require_cappe_account)
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        # What a plan may sell is data (`allowed_fulfillment` on the catalog
        # row), not a hardcoded Creator-vs-Business branch — so the lineup can
        # change from the admin UI without a deploy.
        require_fulfillment(
            await resolve_entitlements(account.plan, conn=conn), body.fulfillment
        )
        await _validate_booking_type(conn, site_id, body.booking_type_id)
        from ..services.recurring import validate_product_subscription
        await validate_product_subscription(conn, account.plan, body.model_dump())
        async with conn.transaction():
            row = await conn.fetchrow(
                f"""INSERT INTO cappe_products
                        (site_id, name, description, price_cents, currency, image_url, sku, inventory,
                         low_stock_threshold, status, sort_order, fulfillment, digital_file_url,
                         booking_type_id, requires_approval, intake_fields, category, subscription_intervals, subscription_discount_bps)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19)
                    RETURNING {_PRODUCT_COLS}""",
                site_id, body.name, body.description, body.price_cents, body.currency,
                body.image_url, body.sku, body.inventory, body.low_stock_threshold, body.status,
                body.sort_order, body.fulfillment, body.digital_file_url, body.booking_type_id,
                body.requires_approval, json.dumps(body.intake_fields), body.category,
                body.subscription_intervals, body.subscription_discount_bps,
            )
            if body.inventory is not None:
                await log_adjustment(
                    conn, site_id=site_id, product_id=row["id"], delta=body.inventory,
                    balance_after=body.inventory, reason="adjustment", note="Opening stock",
                )
            await _replace_option_groups(conn, site_id, row["id"], body.option_groups)
        groups = await fetch_option_groups(conn, [row["id"]])
        # Product names are indexed at weight D, so "cold brew" finds the cafe
        # that sells it even when its name and blurb say neither word.
        await refresh_site_search(conn, site_id)
    return _product_row(row, groups.get(row["id"]))


@router.get("/sites/{site_id}/products/{product_id}", response_model=CappeProduct)
async def get_product(
    site_id: UUID, product_id: UUID, account: CappeAccount = Depends(require_cappe_account)
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        row = await conn.fetchrow(
            f"SELECT {_PRODUCT_COLS} FROM cappe_products WHERE id = $1 AND site_id = $2",
            product_id, site_id,
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
        groups = await fetch_option_groups(conn, [product_id])
    return _product_row(row, groups.get(product_id))


@router.put("/sites/{site_id}/products/{product_id}", response_model=CappeProduct)
async def update_product(
    site_id: UUID, product_id: UUID, body: CappeProductUpdate,
    account: CappeAccount = Depends(require_cappe_account),
    end_subscriptions: bool = Query(False),
):
    if body.status in ("archived", "draft"):
        async with get_connection() as conn:
            await get_owned_site(conn, site_id, account.id)
        await _guard_subscribers(site_id, product_id, end_subscriptions)
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        existing = await conn.fetchrow("SELECT * FROM cappe_products WHERE id=$1 AND site_id=$2", product_id, site_id)
        if not existing:
            raise HTTPException(404, "Product not found")
        from ..services.recurring import validate_product_subscription
        await validate_product_subscription(conn, account.plan, {**dict(existing), **body.model_dump(exclude_unset=True)},
                                            changed=_subscription_changed(body, existing))
        # Only when the caller is actually changing fulfillment — an unrelated
        # edit (a price tweak, a rename) to a product that predates the gate
        # must not start 403-ing.
        if "fulfillment" in body.model_fields_set:
            require_fulfillment(
                await resolve_entitlements(account.plan, conn=conn), body.fulfillment
            )
        await _validate_booking_type(conn, site_id, body.booking_type_id)
        async with conn.transaction():
            # Stock is read under the row lock, not from `existing` above: the
            # number that matters is the one on the shelf when this writes.
            shelf = await conn.fetchrow(
                "SELECT inventory FROM cappe_products WHERE id = $1 AND site_id = $2 FOR UPDATE",
                product_id, site_id,
            )
            if shelf is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
            stock_edit = "inventory" in body.model_fields_set and body.inventory != shelf["inventory"]
            if (
                stock_edit
                and "expected_inventory" in body.model_fields_set
                and body.expected_inventory != shelf["inventory"]
            ):
                raise _stock_conflict(shelf["inventory"])
            sets, args = build_patch(body, (
                "name", "description", "price_cents", "currency", "image_url",
                "sku", "inventory", "low_stock_threshold", "status", "sort_order",
                "fulfillment", "digital_file_url", "booking_type_id", "requires_approval",
                "category",
                "subscription_intervals", "subscription_discount_bps",
            ), nullable={"description", "image_url", "sku", "inventory", "low_stock_threshold",
                         "digital_file_url", "booking_type_id", "category"})
            # intake_fields is JSONB NOT NULL DEFAULT '[]' — a `null` PATCH value
            # has no sensible SQL NULL to clear to, so this stays on the plain
            # `is not None` idiom rather than build_patch's model_fields_set.
            if body.intake_fields is not None:  # JSONB column needs explicit serialization
                args.append(json.dumps(body.intake_fields))
                sets.append(f"intake_fields = ${len(args)}")
            if sets:
                sets.append("updated_at = NOW()")
                args.extend([product_id, site_id])
                row = await conn.fetchrow(
                    f"UPDATE cappe_products SET {', '.join(sets)} "
                    f"WHERE id = ${len(args) - 1} AND site_id = ${len(args)} RETURNING {_PRODUCT_COLS}",
                    *args,
                )
            else:
                row = await conn.fetchrow(
                    f"SELECT {_PRODUCT_COLS} FROM cappe_products WHERE id = $1 AND site_id = $2",
                    product_id, site_id,
                )
            if row is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
            if stock_edit and body.inventory is not None:
                # A stock number typed into the product form is a stock change
                # like any other, and used to be the one kind with no record.
                await log_adjustment(
                    conn, site_id=site_id, product_id=product_id,
                    delta=body.inventory - (shelf["inventory"] or 0), balance_after=body.inventory,
                    reason="adjustment", note="Set in the product editor",
                )
            await _replace_option_groups(conn, site_id, product_id, body.option_groups)
        groups = await fetch_option_groups(conn, [product_id])
        await refresh_site_search(conn, site_id)
    return _product_row(row, groups.get(product_id))


@router.delete("/sites/{site_id}/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    site_id: UUID, product_id: UUID, account: CappeAccount = Depends(require_cappe_account),
    end_subscriptions: bool = Query(False),
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
    await _guard_subscribers(site_id, product_id, end_subscriptions)
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        result = await conn.execute(
            "DELETE FROM cappe_products WHERE id = $1 AND site_id = $2", product_id, site_id
        )
        if not result.endswith(" 0"):
            await refresh_site_search(conn, site_id)
    if result.endswith(" 0"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")


@router.post("/sites/{site_id}/products/{product_id}/adjust", response_model=CappeProduct)
async def adjust_stock(
    site_id: UUID, product_id: UUID, body: CappeStockAdjust,
    account: CappeAccount = Depends(require_cappe_account),
):
    """Manually change stock for a product or one of its variants (restock,
    damage, correction). Writes an audit row. Only tracked stock can be adjusted."""
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        async with conn.transaction():
            if body.option_id is not None:
                vrow = await conn.fetchrow(
                    "SELECT o.id, o.inventory FROM cappe_product_options o "
                    "JOIN cappe_product_option_groups g ON g.id = o.group_id "
                    "WHERE o.id = $1 AND g.product_id = $2 AND o.site_id = $3 FOR UPDATE",
                    body.option_id, product_id, site_id,
                )
                if vrow is None:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Variant not found")
                if vrow["inventory"] is None:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="That variant isn't tracking stock — set a stock number on it first.",
                    )
                new_bal = max(0, vrow["inventory"] + body.delta)
                await conn.execute(
                    "UPDATE cappe_product_options SET inventory = $1 WHERE id = $2", new_bal, body.option_id
                )
                await log_adjustment(
                    conn, site_id=site_id, product_id=product_id, option_id=body.option_id,
                    delta=new_bal - vrow["inventory"], balance_after=new_bal, reason=body.reason, note=body.note,
                )
            else:
                prow = await conn.fetchrow(
                    "SELECT inventory FROM cappe_products WHERE id = $1 AND site_id = $2 FOR UPDATE",
                    product_id, site_id,
                )
                if prow is None:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
                if prow["inventory"] is None:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="This product isn't tracking stock — set a stock number first.",
                    )
                new_bal = max(0, prow["inventory"] + body.delta)
                await conn.execute(
                    "UPDATE cappe_products SET inventory = $1, updated_at = NOW() WHERE id = $2",
                    new_bal, product_id,
                )
                await log_adjustment(
                    conn, site_id=site_id, product_id=product_id,
                    delta=new_bal - prow["inventory"], balance_after=new_bal,
                    reason=body.reason, note=body.note,
                )
            row = await conn.fetchrow(
                f"SELECT {_PRODUCT_COLS} FROM cappe_products WHERE id = $1 AND site_id = $2",
                product_id, site_id,
            )
        groups = await fetch_option_groups(conn, [product_id])
    return _product_row(row, groups.get(product_id))


@router.get(
    "/sites/{site_id}/products/{product_id}/inventory-log",
    response_model=list[CappeInventoryAdjustment],
)
async def inventory_log(
    site_id: UUID, product_id: UUID, account: CappeAccount = Depends(require_cappe_account)
):
    """Recent stock changes for a product (newest first)."""
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        rows = await conn.fetch(
            "SELECT id, product_id, option_id, delta, balance_after, reason, note, created_at "
            "FROM cappe_inventory_adjustments WHERE site_id = $1 AND product_id = $2 "
            "ORDER BY created_at DESC LIMIT 100",
            site_id, product_id,
        )
    return [dict(r) for r in rows]


# --- Orders -----------------------------------------------------------------

@router.get("/sites/{site_id}/orders", response_model=list[CappeOrder])
async def list_orders(
    site_id: UUID,
    account: CappeAccount = Depends(require_cappe_account),
    order_status: Annotated[Optional[str], Query(alias="status", max_length=20)] = None,
    q: Annotated[Optional[str], Query(max_length=120)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    """A page of orders, newest first, optionally narrowed by status and by a
    customer / receipt search. This returned every order the store had ever
    taken on every load. Each row carries a count and a short summary of its
    lines (the list has no `items`), so orders can be told apart at a glance."""
    where, args = ["site_id = $1"], [site_id]
    if order_status:
        args.append(order_status)
        where.append(f"status = ${len(args)}")
    needle = (q or "").strip()
    if needle:
        # Escape LIKE wildcards: a search for "50%" is a literal, not a pattern.
        args.append("%" + needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
        where.append(
            f"(customer_email ILIKE ${len(args)} OR customer_name ILIKE ${len(args)} "
            f"OR receipt_number ILIKE ${len(args)})"
        )
    args.extend([limit, offset])
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        rows = await conn.fetch(
            f"""SELECT {_ORDER_COLS},
                       (SELECT COALESCE(SUM(i.quantity), 0) FROM cappe_order_items i
                         WHERE i.order_id = o.id) AS item_count,
                       (SELECT string_agg(
                                   t.title || CASE WHEN t.quantity > 1 THEN ' × ' || t.quantity ELSE '' END,
                                   ', ' ORDER BY t.created_at)
                          FROM (SELECT title, quantity, created_at FROM cappe_order_items i
                                 WHERE i.order_id = o.id ORDER BY i.created_at LIMIT 3) t) AS items_summary
                  FROM cappe_orders o
                 WHERE {' AND '.join(where)}
                 ORDER BY created_at DESC
                 LIMIT ${len(args) - 1} OFFSET ${len(args)}""",
            *args,
        )
    return [_order_row(r) for r in rows]


@router.get("/sites/{site_id}/orders/{order_id}", response_model=CappeOrder)
async def get_order(
    site_id: UUID, order_id: UUID, account: CappeAccount = Depends(require_cappe_account)
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        order = await conn.fetchrow(
            f"SELECT {_ORDER_COLS} FROM cappe_orders WHERE id = $1 AND site_id = $2",
            order_id, site_id,
        )
        if order is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
        items = await conn.fetch(
            f"SELECT {_ITEM_COLS} FROM cappe_order_items WHERE order_id = $1 ORDER BY created_at",
            order_id,
        )
    return _order_row(order, [_item_row(i) for i in items])


@router.get("/sites/{site_id}/orders/{order_id}/receipt.pdf")
async def owner_order_receipt_pdf(
    site_id: UUID, order_id: UUID, account: CappeAccount = Depends(require_cappe_account)
):
    """Owner-facing printable/exportable PDF receipt for one of their orders."""
    from fastapi import Response
    from ..services.receipt import render_order_receipt_pdf

    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        owns = await conn.fetchval(
            "SELECT 1 FROM cappe_orders WHERE id = $1 AND site_id = $2", order_id, site_id
        )
        if not owns:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
        rendered = await render_order_receipt_pdf(conn, order_id)
    if rendered is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    _order, pdf = rendered
    fname = _receipt_filename(_order.get("receipt_number"))
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{fname}"'},
    )


@router.patch("/sites/{site_id}/orders/{order_id}", response_model=CappeOrder)
async def update_order_status(
    site_id: UUID, order_id: UUID, body: CappeOrderStatusUpdate,
    background: BackgroundTasks,
    account: CappeAccount = Depends(require_cappe_account),
):
    """Advance an order by hand, and/or edit its tracking.

    Status changes follow `order_lifecycle.ALLOWED_TRANSITIONS` — this used to
    accept any status after any other. `refunded` is refused here outright: it
    is only reachable through POST …/refund, which actually returns the money.
    """
    # Cheap pre-check, so a refused transition never closes the buyer's
    # payment page as a side effect. The locked read below is the authority.
    if body.status is not None:
        async with get_connection() as conn:
            await get_owned_site(conn, site_id, account.id)
            pre = await conn.fetchval(
                "SELECT status FROM cappe_orders WHERE id = $1 AND site_id = $2", order_id, site_id,
            )
        if pre is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
        refusal = transition_error(pre, body.status)
        if refusal:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=refusal)
        if pre == "pending" and body.status == "cancelled":
            await _close_open_checkout(site_id, order_id, account.id)
        elif pre == "pending" and body.status == "paid":
            # Marking an order paid by hand while its Stripe page is still open
            # is how a customer gets charged for an order already settled in
            # cash. Close the page first; if they finished checkout, the
            # webhook is what marks it paid, not this.
            await _close_open_checkout(
                site_id, order_id, account.id, then="it needs no manual change",
            )
    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)
        async with conn.transaction():
            # Lock + read the CURRENT status first: whether this transition
            # reverses a stock decrement depends on what it's transitioning
            # FROM, and locking makes a concurrent double-click restock once.
            current = await conn.fetchrow(
                "SELECT status,tracking_number FROM cappe_orders WHERE id = $1 AND site_id = $2 FOR UPDATE",
                order_id, site_id,
            )
            if current is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
            refusal = transition_error(current["status"], body.status)
            if refusal:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=refusal)
            became_paid = current["status"] == "pending" and body.status == "paid"
            sets, args = build_patch(body, ("status", "carrier", "tracking_number"),
                                     nullable={"carrier", "tracking_number"})
            if became_paid:
                sets.append("paid_at = COALESCE(paid_at, NOW())")
            sets.append("updated_at = NOW()")
            args.extend([order_id, site_id])
            order = await conn.fetchrow(
                f"""UPDATE cappe_orders SET {', '.join(sets)}
                    WHERE id = ${len(args) - 1} AND site_id = ${len(args)}
                    RETURNING {_ORDER_COLS}""",
                *args,
            )
            if should_restock(current["status"], body.status):
                await restock_order(conn, site_id=site_id, order_id=order_id, reason="restock")
                await release_order_bookings(conn, order_id=order_id)
            items = await conn.fetch(
                f"SELECT {_ITEM_COLS} FROM cappe_order_items WHERE order_id = $1 ORDER BY created_at",
                order_id,
            )
            # Tell the buyer it shipped (or is ready): once when it is
            # fulfilled, and again only for a NEW tracking number.
            tracking_changed = bool(
                "tracking_number" in getattr(body, "model_fields_set", set()) and body.tracking_number
                and body.tracking_number != current["tracking_number"]
            )
            notify_ship = False
            if order.get("customer_email") and order.get("status") in ("paid", "fulfilled"):
                if tracking_changed:
                    await conn.execute(
                        "UPDATE cappe_orders SET shipped_notified_at = NOW() WHERE id = $1", order_id,
                    )
                    notify_ship = True
                elif body.status == "fulfilled" and current["status"] != "fulfilled":
                    notify_ship = bool(await conn.fetchval(
                        "UPDATE cappe_orders SET shipped_notified_at = NOW() "
                        "WHERE id = $1 AND shipped_notified_at IS NULL RETURNING id",
                        order_id,
                    ))
    if became_paid:
        # The webhook path issues the receipt for a card payment; an order paid
        # offline used to get none at all.
        background.add_task(issue_receipt_for_paid_order, order_id, site_id)
    if notify_ship:
        background.add_task(
            send_cappe_order_shipped_email, order["customer_email"], order["customer_name"], site["name"],
            _items_summary(items), order["carrier"], order["tracking_number"],
            order_page_url(site, await _order_token(order_id)),
            any(i["fulfillment"] == "physical" for i in items),
        )
    from ..services.push import schedule_push
    body_fields = getattr(body, "model_fields_set", set())
    if body.status == "fulfilled" and current["status"] != "fulfilled":
        schedule_push(order_id, "fulfilled")
    elif ("tracking_number" in body_fields and body.tracking_number
          and body.tracking_number != current["tracking_number"]
          and (body.status or current["status"]) not in _RESTOCK_TO_STATUSES):
        schedule_push(order_id, "shipped")
    return _order_row(order, [_item_row(i) for i in items])


@router.post("/sites/{site_id}/orders/{order_id}/refund", response_model=CappeOrder)
async def refund_order(
    site_id: UUID, order_id: UUID, body: Optional[CappeRefundRequest] = None,
    account: CappeAccount = Depends(require_cappe_account),
):
    """Refund a paid order in full — the money first, then the record.

    `restock` says whether the goods go back on the shelf. Left out, they do
    unless the order was already fulfilled: a refund for a parcel that was lost
    or kept used to add stock that was never coming back.

    A card order is refunded on the business's own connected Stripe account
    (the charge lives there, not on the platform), platform fee included. Only
    once Stripe has accepted the refund is the order marked `refunded` and its
    stock and booking slots handed back. If Stripe refuses, nothing changes
    and the owner is told why.

    An order paid OUTSIDE Stripe (marked paid by hand) has no charge to
    reverse: it is recorded as refunded and the owner returns the money the
    way they took it. The dashboard says which case it is before confirming.

    Idempotent: a repeat call on an already-refunded order returns it, and the
    Stripe idempotency key means a double-click cannot refund twice.
    """
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        row = await conn.fetchrow(
            """SELECT o.status, o.stripe_payment_intent, o.stripe_invoice_id,
                      a.stripe_account_id
                 FROM cappe_orders o
                 JOIN cappe_sites s ON s.id = o.site_id
                 JOIN cappe_accounts a ON a.id = s.account_id
                WHERE o.id = $1 AND o.site_id = $2""",
            order_id, site_id,
        )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    if row["status"] != "refunded" and row["status"] not in REFUNDABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only a paid order can be refunded.",
        )

    restock = (
        body.restock if body is not None and body.restock is not None
        else row["status"] != "fulfilled"
    )
    refund_id = None
    if row["status"] != "refunded":
        if row["stripe_payment_intent"]:
            if not row["stripe_account_id"]:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This order was paid by card, but your Stripe account is no longer "
                           "connected. Reconnect it, or refund the payment from your Stripe dashboard.",
                )
            # No connection is held across the Stripe round-trip.
            try:
                refund = await get_cappe_stripe().refund_connected_charge(
                    account_id=row["stripe_account_id"],
                    payment_intent=row["stripe_payment_intent"],
                    idempotency_key=f"cappe-order-refund-{order_id}",
                )
            except CappeStripeError as exc:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Stripe did not accept the refund, so the order was left as is: {exc}",
                )
            refund_id = refund.get("id")
        elif row["stripe_invoice_id"]:
            # A subscription order: its charge belongs to a Stripe invoice we
            # hold no payment intent for. Refunding it in Stripe is synced back
            # by the charge.refunded webhook.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This order was billed by a subscription. Refund its invoice from your "
                       "Stripe dashboard — it will show as refunded here once Stripe confirms.",
            )

    async with get_connection() as conn:
        async with conn.transaction():
            await mark_order_refunded(
                conn, order_id=order_id, site_id=site_id,
                refunded_cents=None, stripe_refund_id=refund_id, restock=restock,
            )
            order = await conn.fetchrow(
                f"SELECT {_ORDER_COLS} FROM cappe_orders WHERE id = $1 AND site_id = $2",
                order_id, site_id,
            )
            items = await conn.fetch(
                f"SELECT {_ITEM_COLS} FROM cappe_order_items WHERE order_id = $1 ORDER BY created_at",
                order_id,
            )
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return _order_row(order, [_item_row(i) for i in items])


@router.post("/sites/{site_id}/orders/{order_id}/accept", response_model=CappeOrder)
async def accept_order(
    site_id: UUID, order_id: UUID, background: BackgroundTasks,
    account: CappeAccount = Depends(require_cappe_account),
):
    """Approve an order that was held for review. Stays 'pending' — approval is
    not payment — but is stamped approved and leaves the requests queue.

    The buyer is emailed. If the store takes cards, the email carries a link
    to pay on the order page, open for `PAY_WINDOW_DAYS`; an approval order is
    never charged before this (it used to be charged at checkout, which made
    the approval meaningless).

    Its booking lines are approved with it. A booking bought through the shop
    that needs approval lands `pending`; accepting the order used to leave it
    there, so the appointment the owner had just said yes to sat in the
    booking queue waiting for a second yes."""
    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)
        takes_cards = bool(await conn.fetchval(
            "SELECT stripe_account_id IS NOT NULL AND stripe_charges_enabled FROM cappe_accounts WHERE id = $1",
            account.id,
        ))
        async with conn.transaction():
            # A store that takes cards gives the buyer a window to pay from the
            # emailed link; the reaper releases the order (and its stock) after.
            order = await conn.fetchrow(
                f"""UPDATE cappe_orders
                    SET requires_approval = false, approved_at = NOW(), updated_at = NOW(),
                        pay_by = CASE WHEN $3 AND subtotal_cents > 0
                                      THEN NOW() + interval '{PAY_WINDOW_DAYS} days' END
                    WHERE id = $1 AND site_id = $2 AND status = 'pending' AND requires_approval = true
                    RETURNING {_ORDER_COLS}""",
                order_id, site_id, takes_cards,
            )
            if order is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No pending order to accept")
            await conn.execute(
                """UPDATE cappe_bookings
                      SET status = 'confirmed', approved_at = NOW(), updated_at = NOW()
                    WHERE site_id = $2 AND status = 'pending'
                      AND id IN (SELECT booking_id FROM cappe_order_items
                                  WHERE order_id = $1 AND booking_id IS NOT NULL)""",
                order_id, site_id,
            )
        items = await conn.fetch(
            f"SELECT {_ITEM_COLS} FROM cappe_order_items WHERE order_id = $1 ORDER BY created_at",
            order_id,
        )
        token = await _order_token(order_id, conn)
    if order.get("customer_email"):
        from ..services.email import format_when
        background.add_task(
            send_cappe_order_approved_email, order["customer_email"], order["customer_name"], site["name"],
            _items_summary(items), order["total_cents"] or order["subtotal_cents"], order["currency"],
            order_page_url(site, token),
            format_when(order["pay_by"], site["timezone"]) if order["pay_by"] else None,
        )
    return _order_row(order, [_item_row(i) for i in items])


@router.post("/sites/{site_id}/orders/{order_id}/decline", response_model=CappeOrder)
async def decline_order(
    site_id: UUID, order_id: UUID, body: CappeApprovalDecline, background: BackgroundTasks,
    account: CappeAccount = Depends(require_cappe_account),
):
    """Decline an order held for review → 'declined' with an optional reason.
    Restocks any physical inventory the pending order had decremented, and
    frees its booking slots — after closing the buyer's payment page, because an
    approval-held cart still goes to Stripe Checkout."""
    await _close_open_checkout(site_id, order_id, account.id)
    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)
        async with conn.transaction():
            order = await conn.fetchrow(
                f"""UPDATE cappe_orders
                    SET status = 'declined', decline_reason = $3, updated_at = NOW()
                    WHERE id = $1 AND site_id = $2 AND status = 'pending'
                    RETURNING {_ORDER_COLS}""",
                order_id, site_id, body.reason,
            )
            if order is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No pending order to decline")
            await restock_order(conn, site_id=site_id, order_id=order_id, reason="decline_restock")
            # Shared release: frees `pending` AND `confirmed` holds. The inline
            # version this replaced freed only `pending`, so a confirmed booking
            # in a declined cart kept its slot off the calendar.
            await release_order_bookings(conn, order_id=order_id)
            items = await conn.fetch(
                f"SELECT {_ITEM_COLS} FROM cappe_order_items WHERE order_id = $1 ORDER BY created_at",
                order_id,
            )
    from ..services.push import schedule_push
    schedule_push(order_id, "declined")
    if order.get("customer_email"):
        background.add_task(
            send_cappe_order_declined_email, order["customer_email"], order["customer_name"], site["name"],
            _items_summary(items), body.reason,
        )
    return _order_row(order, [_item_row(i) for i in items])


@router.patch("/sites/{site_id}/orders/{order_id}/items/{item_id}", response_model=CappeOrderItem)
async def attach_deliverable(
    site_id: UUID, order_id: UUID, item_id: UUID, body: CappeDeliverableUpdate,
    account: CappeAccount = Depends(require_cappe_account),
):
    """Attach a delivered result (uploaded file URL) to a service/digital line."""
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        row = await conn.fetchrow(
            f"""UPDATE cappe_order_items SET deliverable_url = $1
                WHERE id = $2 AND order_id = $3 AND site_id = $4
                RETURNING {_ITEM_COLS}""",
            body.deliverable_url, item_id, order_id, site_id,
        )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order item not found")
    return _item_row(row)
