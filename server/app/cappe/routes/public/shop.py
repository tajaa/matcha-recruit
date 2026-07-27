"""Cappe public surface — shop (products, orders, receipts)."""
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status

from ....core.services.redis_cache import check_rate_limit, client_ip
from ....database import get_connection
from ...models.cappe import CappeCheckoutRequest, CappeOrderReceipt, CappeProduct
from ...services.commerce import create_public_order
from ...services.discounts import apply_discount_cents, best_discount_percent, fetch_active_discounts, site_today
from .._shared import fetch_option_groups, loads_list
from ._common import _published_site, _read_rate_limit, _reject_reserved

router = APIRouter()

# Public product listing exposes everything EXCEPT digital_file_url (the gated
# deliverable — released only via the order receipt once paid/fulfilled).
_PUBLIC_PRODUCT_COLS = (
    "id, site_id, name, description, price_cents, currency, image_url, sku, "
    "inventory, status, sort_order, fulfillment, booking_type_id, requires_approval, "
    "intake_fields, category, created_at, updated_at"
)


@router.get("/public/sites/{slug}/products", response_model=list[CappeProduct])
async def public_products(slug: str, request: Request):
    await _read_rate_limit(request)
    async with get_connection() as conn:
        site = await _published_site(conn, slug)
        rows = await conn.fetch(
            f"SELECT {_PUBLIC_PRODUCT_COLS} FROM cappe_products "
            "WHERE site_id = $1 AND status = 'active' ORDER BY sort_order, created_at",
            site["id"],
        )
        discounts = await fetch_active_discounts(conn, site["id"])
        now_utc = await conn.fetchval("SELECT NOW()")
        groups = await fetch_option_groups(conn, [r["id"] for r in rows])
    today = site_today(now_utc, site["timezone"])
    out = []
    for r in rows:
        pct = best_discount_percent(discounts, kind="product", target_id=str(r["id"]), on_date=today)
        out.append({
            **dict(r),
            "intake_fields": loads_list(r["intake_fields"]),
            "option_groups": groups.get(r["id"], []),
            "discount_percent": pct,
            "discounted_price_cents": apply_discount_cents(r["price_cents"], pct) if pct else None,
        })
    return out


@router.post("/public/sites/{slug}/orders", status_code=status.HTTP_201_CREATED)
async def public_create_order(slug: str, body: CappeCheckoutRequest, request: Request, background: BackgroundTasks):
    """Create a pending order for a mixed cart (physical / digital / service /
    booking). Prices + totals are recomputed server-side from the live product
    rows; payment is stubbed (order lands `pending`). Inventory is decremented
    only for physical lines; booking lines create a scheduled booking; service
    lines validate intake answers. All in one transaction — see
    `services/commerce.py:create_public_order`."""
    ip = client_ip(request)
    await check_rate_limit(ip, "cappe_order", 10, 60)
    await check_rate_limit(ip, "cappe_order_hr", 50, 3600)
    _reject_reserved(str(body.customer_email).strip().lower())

    async with get_connection() as conn:
        site = await _published_site(conn, slug)
    return await create_public_order(site, body, background)


@router.get("/public/orders/{token}/receipt.pdf")
async def public_order_receipt_pdf(token: str, request: Request):
    """Customer-downloadable PDF receipt — released once the order is paid/fulfilled."""
    from fastapi import Response
    from ...services.receipt import render_order_receipt_pdf

    await check_rate_limit(client_ip(request), "cappe_receipt", 30, 60)
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT id, status FROM cappe_orders WHERE access_token = $1", token
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
        if row["status"] not in ("paid", "fulfilled"):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Your receipt will be available once payment completes.",
            )
        rendered = await render_order_receipt_pdf(conn, row["id"])
    if rendered is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    order, pdf = rendered
    fname = (order.get("receipt_number") or "receipt") + ".pdf"
    return Response(
        content=pdf, media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{fname}"'},
    )


@router.get("/public/orders/{token}", response_model=CappeOrderReceipt)
async def public_order_receipt(token: str, request: Request):
    """Buyer receipt + deliverables, resolved by the order's unguessable token.
    Digital downloads / service deliverables are released only once the seller
    marks the order paid or fulfilled (payment is stubbed)."""
    await check_rate_limit(client_ip(request), "cappe_receipt", 30, 60)
    async with get_connection() as conn:
        order = await conn.fetchrow(
            "SELECT id, status, customer_email, customer_name, subtotal_cents, currency, created_at "
            "FROM cappe_orders WHERE access_token = $1",
            token,
        )
        if order is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
        items = await conn.fetch(
            """SELECT oi.title, oi.quantity, oi.fulfillment, oi.unit_price_cents,
                      oi.selected_options, oi.deliverable_url, p.digital_file_url,
                      b.starts_at AS b_start, b.ends_at AS b_end, b.status AS b_status
               FROM cappe_order_items oi
               LEFT JOIN cappe_products p ON p.id = oi.product_id
               LEFT JOIN cappe_bookings b ON b.id = oi.booking_id
               WHERE oi.order_id = $1 ORDER BY oi.created_at""",
            order["id"],
        )
    released = order["status"] in ("paid", "fulfilled")
    return CappeOrderReceipt(
        order_id=order["id"],
        status=order["status"],
        customer_email=order["customer_email"],
        customer_name=order["customer_name"],
        subtotal_cents=order["subtotal_cents"],
        currency=order["currency"],
        created_at=order["created_at"],
        items=[
            {
                "title": it["title"],
                "quantity": it["quantity"],
                "fulfillment": it["fulfillment"],
                "unit_price_cents": it["unit_price_cents"],
                "selected_options": loads_list(it["selected_options"]),
                "download_url": it["digital_file_url"] if (it["fulfillment"] == "digital" and released) else None,
                "deliverable_url": it["deliverable_url"] if released else None,
                "booking_starts_at": it["b_start"],
                "booking_ends_at": it["b_end"],
                "booking_status": it["b_status"],
            }
            for it in items
        ],
    )
