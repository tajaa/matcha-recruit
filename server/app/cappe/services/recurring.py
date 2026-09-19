"""Connected-account subscriptions; each paid invoice becomes one order."""
import json
from datetime import datetime, timezone
from uuid import UUID
from urllib.parse import urlsplit

from fastapi import HTTPException

from app.database import get_connection
from .cart import cart_totals, price_cart
from .common import loads_list, site_origins, url_within_origins
from .entitlements import resolve_entitlements, require_can_sell
from .options import fetch_option_groups
from .shopper_customers import connected_customer
from .stripe_connect import get_cappe_stripe, CappeStripeError


async def validate_product_subscription(conn, plan, product, *, changed=True):
    intervals = product.get("subscription_intervals")
    discount = product.get("subscription_discount_bps")
    if intervals is None or discount is None:
        raise HTTPException(422, "Subscription settings cannot be null")
    if len(intervals) != len(set(intervals)):
        raise HTTPException(422, "Select each subscription interval at most once")
    if not intervals and discount:
        raise HTTPException(422, "A subscription discount requires an interval")
    if intervals and (product["fulfillment"] not in ("physical", "digital") or product.get("requires_approval")):
        raise HTTPException(422, "Subscriptions require physical or digital products without approval")
    if changed and (intervals or discount):
        ent = await resolve_entitlements(plan, conn=conn)
        if not ent.has("recurring_orders"):
            raise HTTPException(402, "Recurring orders are not enabled on this plan")


def build_subscription_lines(products, items, interval, site):
    quoted = price_cart(products, items, site)
    snapshot = []
    for item, line in zip(items, quoted["lines"]):
        product = products.get(item.product_id)
        if not product or not line["available"]:
            raise HTTPException(409, "A subscription product is unavailable")
        if interval not in product.get("subscription_intervals", []) or product["fulfillment"] not in ("physical", "digital") or product.get("requires_approval"):
            raise HTTPException(422, "Product does not support this subscription interval")
        unit = line["unit_price_cents"] * (10000 - product["subscription_discount_bps"]) // 10000
        snapshot.append({**line, "unit_price_cents": unit,
                         "selected_option_ids": [str(v) for v in item.selected_option_ids]})
    totals = cart_totals(snapshot, site)
    if totals["total_cents"] <= 0:
        raise HTTPException(422, "Subscriptions must have a positive total")
    currency = quoted["currency"]
    def stripe_line(name, amount, quantity):
        return {"price_data": {"currency": currency.lower(), "unit_amount": amount,
                               "recurring": {"interval": interval}, "product_data": {"name": name[:250]}},
                "quantity": quantity}
    lines = [stripe_line(row["title"], row["unit_price_cents"], row["quantity"]) for row in snapshot]
    for label, key in (("Tax", "tax_cents"), ("Shipping", "shipping_cents")):
        if totals[key]:
            lines.append(stripe_line(label, totals[key], 1))
    if len(lines) > 20:
        raise HTTPException(422, "Subscriptions support at most 20 billed line items")
    return lines, snapshot, {**totals, "currency": currency}


async def checkout(site, shopper, body):
    origins = site_origins(site)
    success, cancel = url_within_origins(body.success_url, origins), url_within_origins(body.cancel_url, origins)
    if not success or not cancel:
        raise HTTPException(422, "Checkout returns must use this store's origin")
    async with get_connection() as conn:
        owner = await conn.fetchrow("SELECT stripe_account_id,stripe_charges_enabled,plan FROM cappe_accounts WHERE id=$1 AND status='active'", site["account_id"])
        ent = await resolve_entitlements(owner["plan"] if owner else None, conn=conn)
        require_can_sell(ent)
        if not ent.has("recurring_orders"):
            raise HTTPException(402, "Recurring orders are not enabled")
        if not owner or not owner["stripe_account_id"] or not owner["stripe_charges_enabled"]:
            raise HTTPException(409, "This store has not enabled card payments")
        products = await conn.fetch("SELECT * FROM cappe_products WHERE site_id=$1 AND id=ANY($2::uuid[])", site["id"], [i.product_id for i in body.items])
        groups = await fetch_option_groups(conn, [r["id"] for r in products])
        stripe_lines, snapshot, totals = build_subscription_lines(
            {r["id"]: {**dict(r), "option_groups": groups.get(r["id"], [])} for r in products}, body.items, body.interval, site,
        )
    customer_id = await connected_customer(shopper, owner["stripe_account_id"])
    async with get_connection() as conn, conn.transaction():
        live = await conn.fetchrow("SELECT deleting FROM cappe_shoppers WHERE id=$1 AND site_id=$2 FOR UPDATE", shopper["id"], site["id"])
        if not live or live["deleting"]:
            raise HTTPException(409, "Account deletion is in progress")
        pending = await conn.fetchval("SELECT count(*) FROM cappe_shopper_subscriptions WHERE shopper_id=$1 AND status='incomplete'", shopper["id"])
        if pending >= 10:
            raise HTTPException(409, "Too many pending checkouts; cancel an existing checkout first")
        row = await conn.fetchrow(
            "INSERT INTO cappe_shopper_subscriptions(site_id,shopper_id,stripe_account_id,interval,items,subtotal_cents,tax_cents,shipping_cents,total_cents,currency) "
            "VALUES($1,$2,$3,$4,$5::jsonb,$6,$7,$8,$9,$10) RETURNING *",
            site["id"], shopper["id"], owner["stripe_account_id"], body.interval, json.dumps(snapshot),
            totals["subtotal_cents"], totals["tax_cents"], totals["shipping_cents"], totals["total_cents"], totals["currency"],
        )
    def callback(url, result):
        parsed = urlsplit(url)
        if parsed.path == "/__cappe/app-return":
            return f"{parsed.scheme}://{parsed.netloc}/__cappe/app-return?o={row['checkout_token']}&r={result}"
        return url
    try:
        session = await get_cappe_stripe().create_subscription_checkout(
            account_id=owner["stripe_account_id"], customer_id=customer_id, line_items=stripe_lines,
            application_fee_percent=ent.platform_fee_bps / 100,
            success_url=callback(success, "success"), cancel_url=callback(cancel, "cancel"),
            metadata={"cappe_shopper_subscription_id": str(row["id"]), "site_id": str(site["id"])},
            collect_shipping=any(line["fulfillment"] == "physical" for line in snapshot),
            idempotency_key=f"shopper-sub:{row['id']}",
        )
    except CappeStripeError as exc:
        # The Stripe request may have succeeded before a timeout. Keep this row
        # so metadata on a later webhook can recover the paid subscription.
        raise HTTPException(503, "Checkout could not be confirmed. Check subscriptions before retrying.") from exc
    async with get_connection() as conn:
        await conn.execute("UPDATE cappe_shopper_subscriptions SET stripe_checkout_session_id=$1,updated_at=NOW() WHERE id=$2", session["id"], row["id"])
    return {"checkout_url": session["url"], "subscription_id": str(row["id"]), "order_token": row["checkout_token"]}


def invoice_subscription_id(invoice):
    return invoice.get("subscription") or ((invoice.get("parent") or {}).get("subscription_details") or {}).get("subscription")


async def sync_subscription(conn, row, subscription, event_at):
    items = (subscription.get("items") or {}).get("data") or []
    period = subscription.get("current_period_end") or (items[0].get("current_period_end") if items else None)
    values = (
        row["id"], subscription["id"], subscription["status"],
        bool(subscription.get("cancel_at_period_end")), period,
    )
    if event_at is None:
        # An interactive cancel/resume response has no Stripe event timestamp.
        # Do not advance the webhook watermark using local wall-clock time: the
        # corresponding Stripe event was created slightly earlier and would be
        # rejected as stale, leaving a concurrent response permanently in DB.
        await conn.execute(
            "UPDATE cappe_shopper_subscriptions SET stripe_subscription_id=$2,status=$3,"
            "cancel_at_period_end=$4,current_period_end=to_timestamp($5),updated_at=NOW() "
            "WHERE id=$1 AND (status NOT IN ('canceled','incomplete_expired') "
            "OR $3 IN ('canceled','incomplete_expired'))",
            *values,
        )
    else:
        await conn.execute(
            "UPDATE cappe_shopper_subscriptions SET stripe_subscription_id=$2,status=$3,cancel_at_period_end=$4,"
            "current_period_end=to_timestamp($5),stripe_event_at=GREATEST(stripe_event_at,$6),updated_at=NOW() "
            "WHERE id=$1 AND (stripe_event_at IS NULL OR stripe_event_at<=$6) "
            "AND (status NOT IN ('canceled','incomplete_expired') OR $3 IN ('canceled','incomplete_expired'))",
            *values, event_at,
        )


async def record_invoice_order(conn, row, invoice):
    """Caller holds subscription lock/transaction. Unique invoice prevents replay."""
    shopper = await conn.fetchrow("SELECT email,name FROM cappe_shoppers WHERE id=$1 AND site_id=$2", row["shopper_id"], row["site_id"]) if row["shopper_id"] else None
    shipping = invoice.get("customer_shipping")
    order = await conn.fetchrow(
        "INSERT INTO cappe_orders(site_id,shopper_id,subscription_id,stripe_invoice_id,status,paid_at,customer_email,customer_name,"
        "subtotal_cents,tax_cents,shipping_cents,total_cents,currency,shipping_address) "
        "VALUES($1,$2,$3,$4,'paid',NOW(),$5,$6,$7,$8,$9,$10,$11,$12::jsonb) "
        "ON CONFLICT(stripe_invoice_id) WHERE stripe_invoice_id IS NOT NULL DO NOTHING RETURNING id",
        row["site_id"], row["shopper_id"], row["id"], invoice["id"],
        shopper["email"] if shopper else None, shopper["name"] if shopper else None,
        row["subtotal_cents"], row["tax_cents"], row["shipping_cents"], invoice.get("total", row["total_cents"]),
        row["currency"], json.dumps(shipping) if shipping else None,
    )
    if not order:
        return None, False
    for item in loads_list(row["items"]):
        pid = await conn.fetchval("SELECT id FROM cappe_products WHERE id=$1 AND site_id=$2", UUID(item["product_id"]), row["site_id"])
        await conn.execute(
            "INSERT INTO cappe_order_items(order_id,site_id,product_id,title,unit_price_cents,quantity,fulfillment,selected_options,selected_option_ids) "
            "VALUES($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9::uuid[])",
            order["id"], row["site_id"], pid, item["title"], item["unit_price_cents"], item["quantity"], item["fulfillment"],
            json.dumps(item.get("selected_options", [])), [UUID(v) for v in item.get("selected_option_ids", [])],
        )
    # Paid goods are owed even when stock is short. Match Cappe's existing late
    # payment recovery: negative inventory records the debt and refunds reverse
    # exactly this decrement. A guarded no-op would over-credit on refund.
    from .inventory import retake_order_stock
    await retake_order_stock(conn, site_id=row["site_id"], order_id=order["id"])
    short = await conn.fetchval(
        "SELECT EXISTS(SELECT 1 FROM cappe_order_items i LEFT JOIN cappe_products p ON p.id=i.product_id "
        "WHERE i.order_id=$1 AND i.fulfillment='physical' AND (p.id IS NULL OR p.inventory<0 "
        "OR EXISTS(SELECT 1 FROM cappe_product_options o WHERE o.id=ANY(i.selected_option_ids) AND o.inventory<0)))", order["id"],
    )
    await conn.execute("UPDATE cappe_orders SET metadata=metadata || $2::jsonb WHERE id=$1", order["id"],
                       json.dumps({"stock_shortfall": bool(short), "invoice_total_changed": invoice.get("total", row["total_cents"]) != row["total_cents"]}))
    return order["id"], bool(short)


async def handle_event(etype, obj, event, background):
    account_id = event.get("account")
    if not account_id:
        return {"received": True}
    sid = obj.get("id") if etype.startswith("customer.subscription.") else (
        invoice_subscription_id(obj) if etype.startswith("invoice.") else obj.get("subscription"))
    metadata = obj.get("metadata") or {}
    local_id = metadata.get("cappe_shopper_subscription_id")
    if not sid and not local_id:
        return {"received": True}
    # Event creation timestamps have only second precision, so two updates in
    # the same second cannot be ordered reliably from their payloads. Fetch the
    # current Stripe state outside the DB transaction. Deleted events retain an
    # authoritative terminal payload and may no longer be retrievable.
    subscription = (
        obj if etype == "customer.subscription.deleted" else
        await get_cappe_stripe().retrieve_connected_subscription(account_id, sid) if sid else None
    )
    local_id = local_id or ((subscription or {}).get("metadata") or {}).get("cappe_shopper_subscription_id")
    try:
        local_uuid = UUID(local_id) if local_id else None
    except (ValueError, TypeError):
        return {"received": True}
    event_at = datetime.fromtimestamp(event.get("created") or 0, timezone.utc)
    order_id = None
    stock_shortfall = False
    async with get_connection() as conn, conn.transaction():
        row = await conn.fetchrow(
            "SELECT sub.* FROM cappe_shopper_subscriptions sub JOIN cappe_sites s ON s.id=sub.site_id "
            "JOIN cappe_accounts a ON a.id=s.account_id WHERE (sub.id=$1 OR sub.stripe_subscription_id=$2) "
            "AND sub.stripe_account_id=$3 AND a.stripe_account_id=$3 FOR UPDATE OF sub",
            local_uuid, sid, account_id,
        )
        if not row:
            return {"received": True}
        if subscription:
            await sync_subscription(conn, row, subscription, event_at)
        if etype == "checkout.session.expired":
            await conn.execute("UPDATE cappe_shopper_subscriptions SET status='incomplete_expired' WHERE id=$1 AND status='incomplete' AND stripe_subscription_id IS NULL", row["id"])
        if etype == "invoice.paid" and obj.get("paid") and obj.get("billing_reason") in ("subscription_create", "subscription_cycle"):
            order_id, stock_shortfall = await record_invoice_order(conn, row, obj)
    if order_id:
        from .receipt import issue_receipt_for_paid_order
        from .push import notify_order_event
        background.add_task(issue_receipt_for_paid_order, order_id, row["site_id"])
        background.add_task(notify_order_event, order_id, "paid")
        if stock_shortfall:
            async with get_connection() as conn:
                owner = await conn.fetchrow(
                    "SELECT a.email,a.name,s.name AS site_name FROM cappe_sites s "
                    "JOIN cappe_accounts a ON a.id=s.account_id WHERE s.id=$1", row["site_id"],
                )
                shortages = await conn.fetch(
                    "SELECT COALESCE(p.name,i.title) AS name,COALESCE(p.inventory,-1) AS balance "
                    "FROM cappe_order_items i LEFT JOIN cappe_products p ON p.id=i.product_id "
                    "WHERE i.order_id=$1 AND i.fulfillment='physical' AND (p.id IS NULL OR p.inventory<0 "
                    "OR EXISTS(SELECT 1 FROM cappe_product_options o "
                    "WHERE o.id=ANY(i.selected_option_ids) AND o.inventory<0))",
                    order_id,
                )
            if owner and owner["email"]:
                from .email import dashboard_url, send_cappe_low_stock_email
                background.add_task(
                    send_cappe_low_stock_email, owner["email"], owner["name"], owner["site_name"],
                    [(item["name"], item["balance"]) for item in shortages],
                    dashboard_url(f"/sites/{row['site_id']}/shop"),
                )
    elif (etype == "invoice.payment_failed" and row["shopper_id"] and subscription
          and subscription.get("status") in ("incomplete", "past_due", "unpaid")):
        from .push import send_to_shopper
        background.add_task(send_to_shopper, row["shopper_id"], row["site_id"], "Subscription payment failed",
                            "Please update your payment method with the store.", {"type": "subscription", "subscription_id": str(row["id"])})
    return {"received": True}


async def change_subscription(row, cancel):
    if not row["stripe_subscription_id"]:
        if not cancel:
            raise HTTPException(409, "Checkout has not completed")
        if not row["stripe_checkout_session_id"]:
            # Stripe never returned a session URL, so the shopper could not have
            # opened or completed this Checkout Session. Make the local attempt
            # terminal so failed preparation cannot block account deletion or
            # consume the pending-checkout allowance forever.
            async with get_connection() as conn:
                await conn.execute(
                    "UPDATE cappe_shopper_subscriptions SET status='incomplete_expired',updated_at=NOW() "
                    "WHERE id=$1 AND stripe_subscription_id IS NULL AND stripe_checkout_session_id IS NULL",
                    row["id"],
                )
            return {"status": "incomplete_expired"}
        state = await get_cappe_stripe().expire_checkout_session(row["stripe_account_id"], row["stripe_checkout_session_id"])
        if state == "complete":
            raise HTTPException(409, "Payment is settling; retry after it completes")
        async with get_connection() as conn:
            await conn.execute("UPDATE cappe_shopper_subscriptions SET status='incomplete_expired' WHERE id=$1 AND stripe_subscription_id IS NULL", row["id"])
        return {"status": "incomplete_expired"}
    subscription = await get_cappe_stripe().modify_connected_subscription(
        account_id=row["stripe_account_id"], subscription_id=row["stripe_subscription_id"], cancel_at_period_end=cancel,
    )
    async with get_connection() as conn, conn.transaction():
        await conn.fetchval("SELECT id FROM cappe_shopper_subscriptions WHERE id=$1 FOR UPDATE", row["id"])
        await sync_subscription(conn, row, subscription, None)
    return {"status": subscription["status"], "cancel_at_period_end": subscription["cancel_at_period_end"]}


async def delete_shopper_subscriptions(site, shopper):
    # A durable deletion flag blocks concurrent new checkouts. On failure the
    # shopper remains present and can retry deletion with the same session.
    async with get_connection() as conn, conn.transaction():
        await conn.execute("UPDATE cappe_shoppers SET deleting=TRUE WHERE id=$1 AND site_id=$2", shopper["id"], site["id"])
        rows = await conn.fetch("SELECT * FROM cappe_shopper_subscriptions WHERE shopper_id=$1 AND site_id=$2 AND status NOT IN ('canceled','incomplete_expired')",
                                shopper["id"], site["id"])
    for row in rows:
        if row["stripe_subscription_id"]:
            subscription = await get_cappe_stripe().cancel_connected_subscription(row["stripe_account_id"], row["stripe_subscription_id"])
            async with get_connection() as conn:
                await sync_subscription(conn, row, subscription, None)
        else:
            await change_subscription(row, True)
