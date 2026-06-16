"""Cappe public surface — anonymous, by site slug.

Everything here is unauthenticated and reachable by any visitor, so each write
endpoint is (a) rate-limited per IP (layered minute+hour buckets), (b) guards
every email field against reserved/test domains, and (c) never trusts
client-supplied money/time — prices, order totals, and booking end-times are all
recomputed server-side. A site must be `published` to expose any public surface.
"""
import json
import os
from datetime import date, timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, status

from ...core.services.email._shared import _is_reserved_test_domain
from ...core.services.redis_cache import check_rate_limit, client_ip
from ...database import get_connection
from ..services.commerce import booking_quote_cents, booking_times, order_subtotal
from ..services.discounts import apply_discount_cents, best_discount_percent
from ..services.options import validate_and_price_options
from ..services.slots import generate_slots, merge_any_staff_slots
from ..models.cappe import (
    CappeBookingQuote,
    CappeBookingQuoteRequest,
    CappeBookingRequest,
    CappeBookingReschedule,
    CappeBookingType,
    CappeCheckoutRequest,
    CappeForm,
    CappeMessageCreate,
    CappeOrderReceipt,
    CappePost,
    CappeProduct,
    CappePublicBooking,
    CappePublicLocation,
    CappePublicReview,
    CappePublicSite,
    CappePublicStaff,
    CappePublicThread,
    CappeReviewCreate,
    CappeSubscribeRequest,
)
from ..services.email import (
    booking_manage_url,
    build_order_items_summary,
    dashboard_url,
    format_when,
    send_cappe_booking_alert_email,
    send_cappe_booking_cancelled_email,
    send_cappe_booking_received_email,
    send_cappe_form_alert_email,
    send_cappe_message_email,
    send_cappe_order_alert_email,
    send_cappe_order_receipt_email,
)
from ._shared import _site_owner, fetch_option_groups, loads, loads_list, page_row_to_dict

# Public product listing exposes everything EXCEPT digital_file_url (the gated
# deliverable — released only via the order receipt once paid/fulfilled).
_PUBLIC_PRODUCT_COLS = (
    "id, site_id, name, description, price_cents, currency, image_url, sku, "
    "inventory, status, sort_order, fulfillment, booking_type_id, requires_approval, "
    "intake_fields, category, created_at, updated_at"
)

router = APIRouter()


async def _site_rate_rules(conn, site_id, booking_type_id, location_id=None) -> list[dict]:
    """Rate rules in effect for a booking type at a location (its own + site-wide
    NULL ones; this location's + shared NULL-location ones)."""
    rows = await conn.fetch(
        """SELECT weekday, start_time, end_time, multiplier FROM cappe_rate_rules
           WHERE site_id = $1 AND (booking_type_id IS NULL OR booking_type_id = $2)
             AND (location_id IS NULL OR location_id = $3)""",
        site_id, booking_type_id, location_id,
    )
    return [dict(r) for r in rows]


async def _location_ctx(conn, site, location_id):
    """Validate `location_id` belongs to the published site (and is active) and
    return (location_id, tz). None → site timezone. Raises 400 on a bad id."""
    if location_id is None:
        return None, site["timezone"]
    row = await conn.fetchrow(
        "SELECT timezone FROM cappe_locations WHERE id = $1 AND site_id = $2 AND active = true",
        location_id, site["id"],
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown location")
    return location_id, (row["timezone"] or site["timezone"])


async def _site_rider(conn, site_id) -> list[dict]:
    rows = await conn.fetch(
        "SELECT label, detail, is_required FROM cappe_rider_items WHERE site_id = $1 "
        "ORDER BY sort_order, created_at",
        site_id,
    )
    return [dict(r) for r in rows]


async def _active_discounts(conn, site_id) -> list[dict]:
    """Active discounts for a site, shaped for services.discounts."""
    rows = await conn.fetch(
        "SELECT percent_off, scope, target_id, active, starts_on, ends_on "
        "FROM cappe_discounts WHERE site_id = $1 AND active = true",
        site_id,
    )
    return [
        {
            "percent_off": r["percent_off"], "scope": r["scope"],
            "target_id": str(r["target_id"]) if r["target_id"] else None,
            "active": r["active"], "starts_on": r["starts_on"], "ends_on": r["ends_on"],
        }
        for r in rows
    ]


def _site_today(now_utc, tz_name) -> date:
    """Today's date in the site's timezone — discount eligibility is judged on
    when the booking/order is *made*, not the appointment date."""
    try:
        return now_utc.astimezone(ZoneInfo(tz_name or "UTC")).date()
    except Exception:
        return now_utc.astimezone(timezone.utc).date()


async def _published_site(conn, slug: str):
    """Resolve a published site by slug, or 404. Returns the row (incl. id, timezone)."""
    row = await conn.fetchrow(
        "SELECT id, name, slug, theme_config, meta_config, timezone, status "
        "FROM cappe_sites WHERE slug = $1",
        slug,
    )
    if row is None or row["status"] != "published":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found")
    return row


def _reject_reserved(email: str | None):
    if email and _is_reserved_test_domain(email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reserved/test email domains are not accepted",
        )


# --- Site render data -------------------------------------------------------

async def _read_rate_limit(request: Request) -> None:
    """Shared per-IP budget for anonymous read endpoints. Generous — a page
    load fires 2-3 widget fetches — but stops scripted scraping/enumeration."""
    await check_rate_limit(client_ip(request), "cappe_pub_read", 120, 60)


@router.get("/public/sites/{slug}", response_model=CappePublicSite)
async def get_public_site(slug: str, request: Request):
    await _read_rate_limit(request)
    async with get_connection() as conn:
        site = await _published_site(conn, slug)
        pages = await conn.fetch(
            "SELECT id, site_id, title, slug, content, sort_order, status, created_at, updated_at "
            "FROM cappe_pages WHERE site_id = $1 AND status = 'published' ORDER BY sort_order, created_at",
            site["id"],
        )
    return CappePublicSite(
        name=site["name"],
        slug=site["slug"],
        theme_config=loads(site["theme_config"]),
        meta_config=loads(site["meta_config"]),
        pages=[page_row_to_dict(p) for p in pages],
    )


# --- Shop -------------------------------------------------------------------

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
        discounts = await _active_discounts(conn, site["id"])
        now_utc = await conn.fetchval("SELECT NOW()")
        groups = await fetch_option_groups(conn, [r["id"] for r in rows])
    today = _site_today(now_utc, site["timezone"])
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


def _validate_intake(intake_fields: list, answers: dict) -> None:
    """Reject a service/booking purchase whose required intake answers are
    missing. Answers are anonymous client input — keep it bounded + don't trust."""
    if len(json.dumps(answers)) > 8000:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Intake answers too large")
    for field in intake_fields or []:
        if isinstance(field, dict) and field.get("required"):
            key = field.get("key")
            val = answers.get(key) if isinstance(answers, dict) else None
            if val is None or (isinstance(val, str) and not val.strip()):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Missing required answer: {field.get('label') or key}",
                )


def _anchor_local(dt, tz_name):
    """A naive datetime from the widget is the visitor's pick in the SITE's
    timezone (availability is site-local) — anchor it there."""
    if dt.tzinfo is not None:
        return dt
    try:
        return dt.replace(tzinfo=ZoneInfo(tz_name or "UTC"))
    except Exception:
        return dt.replace(tzinfo=timezone.utc)


async def _resolve_booking_slot(
    conn, site, btype, starts_at, ends_at_override=None, exclude_booking_id=None, staff_id=None,
    location_id=None, tz=None,
):
    """Validate availability + overlap and price a booking window. Returns
    {s_utc, e_utc, quote_cents, requires_approval, booking_status}; raises 4xx on
    a bad/taken slot. `exclude_booking_id` skips one booking from the overlap
    check (for in-place reschedule). `staff_id` scopes availability + overlap to
    one staff member (None = the legacy shared calendar). MUST run inside a
    transaction.

    `btype` must carry duration_minutes, price_cents, pricing_mode,
    requires_approval. For an hourly type the buyer may pass `ends_at_override`
    to book a variable-length window; otherwise the type's duration is used.
    `location_id`/`tz` scope availability + overlap + pricing to one location and
    use that location's timezone (None → site timezone)."""
    tz = tz or site["timezone"]
    starts_at = _anchor_local(starts_at, tz)
    pricing_mode = btype.get("pricing_mode", "flat")

    if ends_at_override is not None and pricing_mode == "hourly":
        ends_at_override = _anchor_local(ends_at_override, tz)
        duration_min = (ends_at_override - starts_at).total_seconds() / 60
        if duration_min <= 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="End time must be after start")
        if duration_min > 1440:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Booking is too long")
    else:
        duration_min = btype["duration_minutes"]

    bt = booking_times(starts_at, duration_min, tz)
    s_utc, e_utc = bt["start_utc"], bt["end_utc"]

    now_utc = await conn.fetchval("SELECT NOW()")
    if s_utc <= now_utc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Choose a future time")
    if bt["spans_midnight"]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Booking can't span midnight")

    window = await conn.fetchval(
        """SELECT 1 FROM cappe_availability
           WHERE site_id = $1 AND weekday = $2
             AND start_time <= $3 AND end_time >= $4
             AND (booking_type_id IS NULL OR booking_type_id = $5)
             AND (staff_id IS NULL OR staff_id = $6)
             AND (location_id IS NULL OR location_id = $7)
           LIMIT 1""",
        site["id"], bt["weekday"], bt["local_start"].time(), bt["local_end"].time(),
        btype["id"], staff_id, location_id,
    )
    if not window:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Time is outside availability")

    # Overlap is scoped to this staff member AND location (both NULL-safe), so a
    # booking at a DIFFERENT location never blocks this one (must agree with the
    # double-book DB index). A buffer extends the window on both sides.
    buf_min = int(btype.get("buffer_minutes") or 0)
    overlap = await conn.fetchval(
        """SELECT 1 FROM cappe_bookings
           WHERE site_id = $1 AND booking_type_id = $2 AND status IN ('pending', 'confirmed')
             AND ($5::uuid IS NULL OR id <> $5)
             AND (staff_id IS NOT DISTINCT FROM $6)
             AND (location_id IS NOT DISTINCT FROM $8)
             AND tstzrange(starts_at, ends_at)
                 && tstzrange($3 - ($7 * interval '1 minute'), $4 + ($7 * interval '1 minute'))
           LIMIT 1""",
        site["id"], btype["id"], s_utc, e_utc, exclude_booking_id, staff_id, buf_min, location_id,
    )
    if overlap:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That slot is taken")

    # Price the booked window (flat → base; hourly → per-minute × rate rules),
    # then apply the best active discount judged on today (location timezone).
    rules = await _site_rate_rules(conn, site["id"], btype["id"], location_id)
    quote_cents = booking_quote_cents(
        btype.get("price_cents") or 0, pricing_mode, bt["local_start"], bt["local_end"], rules
    )
    discounts = await _active_discounts(conn, site["id"])
    pct = best_discount_percent(
        discounts, kind="booking_type", target_id=str(btype["id"]),
        on_date=_site_today(now_utc, tz),
    )
    quote_cents = apply_discount_cents(quote_cents, pct)

    requires_approval = bool(btype.get("requires_approval"))
    return {
        "s_utc": s_utc, "e_utc": e_utc, "quote_cents": quote_cents,
        "requires_approval": requires_approval,
        # Approval-required types land 'pending' (creator queue); others
        # auto-confirm so an open calendar books straight through.
        "booking_status": "pending" if requires_approval else "confirmed",
    }


async def _create_booking_in_tx(
    conn, site, btype, starts_at, customer_name, customer_email, note,
    ends_at_override=None, rider_acknowledged=False, rider_snapshot=None, staff_id=None,
    location_id=None, tz=None,
):
    """Validate + price + insert a booking. MUST run inside a transaction.
    Shared by the public booking intake and booking-fulfillment order lines."""
    slot = await _resolve_booking_slot(
        conn, site, btype, starts_at, ends_at_override, staff_id=staff_id, location_id=location_id, tz=tz,
    )
    try:
        return await conn.fetchrow(
            """INSERT INTO cappe_bookings
                   (site_id, booking_type_id, staff_id, location_id, customer_name, customer_email, starts_at, ends_at,
                    note, status, requires_approval, quoted_price_cents,
                    rider_acknowledged, rider_snapshot)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
               RETURNING id, status, starts_at, ends_at, quoted_price_cents, requires_approval, access_token""",
            site["id"], btype["id"], staff_id, location_id, customer_name, customer_email, slot["s_utc"], slot["e_utc"],
            note, slot["booking_status"], slot["requires_approval"], slot["quote_cents"],
            bool(rider_acknowledged), json.dumps(rider_snapshot or []),
        )
    except Exception as exc:
        if "idx_cappe_bookings_no_doublebook" in str(exc):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That slot is taken")
        raise


@router.post("/public/sites/{slug}/orders", status_code=status.HTTP_201_CREATED)
async def public_create_order(slug: str, body: CappeCheckoutRequest, request: Request, background: BackgroundTasks):
    """Create a pending order for a mixed cart (physical / digital / service /
    booking). Prices + totals are recomputed server-side from the live product
    rows; payment is stubbed (order lands `pending`). Inventory is decremented
    only for physical lines; booking lines create a scheduled booking; service
    lines validate intake answers. All in one transaction."""
    ip = client_ip(request)
    await check_rate_limit(ip, "cappe_order", 10, 60)
    await check_rate_limit(ip, "cappe_order_hr", 50, 3600)
    email = str(body.customer_email).strip().lower()
    _reject_reserved(email)

    async with get_connection() as conn:
        site = await _published_site(conn, slug)
        discounts = await _active_discounts(conn, site["id"])
        today = _site_today(await conn.fetchval("SELECT NOW()"), site["timezone"])
        async with conn.transaction():
            order_currency = None
            order_requires_approval = False  # any line needing creator review holds the whole order
            # (product_id, title, unit_price, qty, fulfillment, intake_answers, booking_id)
            line_rows = []
            for item in body.items:
                product = await conn.fetchrow(
                    "SELECT id, name, price_cents, currency, inventory, status, fulfillment, "
                    "booking_type_id, requires_approval, intake_fields "
                    "FROM cappe_products WHERE id = $1 AND site_id = $2 FOR UPDATE",
                    item.product_id, site["id"],
                )
                if product is None or product["status"] != "active":
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Product unavailable")
                if order_currency is None:
                    order_currency = product["currency"]
                elif product["currency"] != order_currency:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mixed currencies not supported")
                if product["requires_approval"]:
                    order_requires_approval = True

                f = product["fulfillment"]
                qty = item.quantity
                booking_id = None
                intake = item.intake_answers or {}

                if f == "physical":
                    if product["inventory"] is not None:
                        res = await conn.execute(
                            "UPDATE cappe_products SET inventory = inventory - $1, updated_at = NOW() "
                            "WHERE id = $2 AND inventory >= $1",
                            qty, item.product_id,
                        )
                        if res.endswith(" 0"):
                            raise HTTPException(
                                status_code=status.HTTP_409_CONFLICT,
                                detail=f"Insufficient stock for {product['name']}",
                            )
                elif f == "service":
                    _validate_intake(loads_list(product["intake_fields"]), intake)
                elif f == "digital":
                    pass  # delivered via the receipt download once paid/fulfilled
                elif f == "booking":
                    if product["booking_type_id"] is None:
                        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Booking not configured")
                    if item.starts_at is None:
                        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Pick a time for the booking")
                    btype = await conn.fetchrow(
                        "SELECT id, duration_minutes, status, price_cents, pricing_mode, requires_approval "
                        "FROM cappe_booking_types WHERE id = $1 AND site_id = $2",
                        product["booking_type_id"], site["id"],
                    )
                    if btype is None or btype["status"] != "active":
                        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Booking unavailable")
                    if btype["requires_approval"]:
                        order_requires_approval = True
                    _validate_intake(loads_list(product["intake_fields"]), intake)
                    booking = await _create_booking_in_tx(
                        conn, site, btype, item.starts_at, body.customer_name, email, body.note,
                    )
                    booking_id = booking["id"]

                # Server-authoritative option pricing: validate the selected
                # option ids against this product's live groups, fold the signed
                # deltas into the unit price BEFORE the discount, snapshot the
                # choice for the order line.
                pgroups = await fetch_option_groups(conn, [item.product_id])
                try:
                    opt_delta, opt_snapshot = validate_and_price_options(
                        pgroups.get(item.product_id, []), item.selected_option_ids,
                    )
                except ValueError as exc:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
                dpct = best_discount_percent(
                    discounts, kind="product", target_id=str(item.product_id), on_date=today,
                )
                unit_price = apply_discount_cents(max(0, product["price_cents"] + opt_delta), dpct)
                line_rows.append(
                    (item.product_id, product["name"], unit_price, qty, f, intake, booking_id, opt_snapshot)
                )

            subtotal = order_subtotal((unit, qty) for (_, _, unit, qty, *_rest) in line_rows)
            order = await conn.fetchrow(
                """INSERT INTO cappe_orders
                       (site_id, customer_email, customer_name, status, subtotal_cents, currency,
                        note, requires_approval)
                   VALUES ($1, $2, $3, 'pending', $4, $5, $6, $7)
                   RETURNING id, status, subtotal_cents, currency, access_token, requires_approval""",
                site["id"], email, body.customer_name, subtotal, order_currency or "USD", body.note,
                order_requires_approval,
            )
            for product_id, title, unit_price, qty, f, intake, booking_id, opt_snapshot in line_rows:
                await conn.execute(
                    """INSERT INTO cappe_order_items
                           (order_id, site_id, product_id, title, unit_price_cents, quantity,
                            fulfillment, intake_answers, selected_options, booking_id)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)""",
                    order["id"], site["id"], product_id, title, unit_price, qty,
                    f, json.dumps(intake), json.dumps(opt_snapshot), booking_id,
                )
        owner = await _site_owner(conn, site["id"])

    # Notifications (best-effort, after response): receipt → customer, alert → creator.
    items_summary = build_order_items_summary(
        [{"title": t, "quantity": q} for (_pid, t, _u, q, *_r) in line_rows]
    )
    if email:
        background.add_task(
            send_cappe_order_receipt_email, email, body.customer_name, site["name"],
            items_summary, order["subtotal_cents"], order["currency"], order["requires_approval"],
        )
    if owner and owner["email"]:
        background.add_task(
            send_cappe_order_alert_email, owner["email"], owner["name"], site["name"],
            body.customer_name, order["subtotal_cents"], order["currency"],
            dashboard_url(f"/sites/{site['id']}/orders"),
        )

    return {
        "order_id": str(order["id"]),
        "order_token": order["access_token"],
        "status": order["status"],
        "subtotal_cents": order["subtotal_cents"],
        "currency": order["currency"],
        "requires_approval": order["requires_approval"],
    }


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


# --- Newsletter -------------------------------------------------------------

@router.post("/public/sites/{slug}/subscribe", status_code=status.HTTP_201_CREATED)
async def public_subscribe(slug: str, body: CappeSubscribeRequest, request: Request):
    ip = client_ip(request)
    await check_rate_limit(ip, "cappe_subscribe", 5, 60)
    await check_rate_limit(ip, "cappe_subscribe_hr", 20, 3600)
    # TODO(captcha): verify an hCaptcha/Turnstile token before insert (list-bombing surface).
    email = str(body.email).strip().lower()
    _reject_reserved(email)

    async with get_connection() as conn:
        site = await _published_site(conn, slug)
        # Re-subscribe resurrects a previously-unsubscribed/bounced row.
        await conn.execute(
            """INSERT INTO cappe_subscribers (site_id, email, name, source, status)
               VALUES ($1, $2, $3, 'website', 'subscribed')
               ON CONFLICT (site_id, email)
               DO UPDATE SET status = 'subscribed', unsubscribed_at = NULL,
                             name = COALESCE(EXCLUDED.name, cappe_subscribers.name),
                             updated_at = NOW()""",
            site["id"], email, body.name,
        )
    return {"ok": True}


@router.get("/public/sites/{slug}/unsubscribe/{token}")
async def public_unsubscribe(slug: str, token: str, request: Request):
    await _read_rate_limit(request)
    async with get_connection() as conn:
        site = await _published_site(conn, slug)
        res = await conn.execute(
            "UPDATE cappe_subscribers SET status = 'unsubscribed', unsubscribed_at = NOW(), updated_at = NOW() "
            "WHERE site_id = $1 AND unsubscribe_token = $2 AND status != 'unsubscribed'",
            site["id"], token,
        )
    # Idempotent: a bad/used token still returns ok (don't leak token validity).
    return {"ok": True, "updated": not res.endswith(" 0")}


# --- Forms ------------------------------------------------------------------

@router.post("/public/sites/{slug}/forms/{form_slug}", status_code=status.HTTP_201_CREATED)
async def public_submit_form(slug: str, form_slug: str, body: dict, request: Request, background: BackgroundTasks):
    """Store a submission. `body` shape: {data: {...}, submitter_email?: str}."""
    ip = client_ip(request)
    await check_rate_limit(ip, "cappe_form", 5, 60)
    await check_rate_limit(ip, "cappe_form_hr", 30, 3600)
    # TODO(captcha): verify a challenge token before insert (spam surface).

    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict):
        data = {k: v for k, v in (body or {}).items() if k not in ("submitter_email",)}
    submitter_email = (body or {}).get("submitter_email") if isinstance(body, dict) else None
    if submitter_email:
        submitter_email = str(submitter_email).strip().lower()
        _reject_reserved(submitter_email)

    async with get_connection() as conn:
        site = await _published_site(conn, slug)
        form = await conn.fetchrow(
            "SELECT id, name, status FROM cappe_forms WHERE site_id = $1 AND slug = $2", site["id"], form_slug
        )
        if form is None or form["status"] != "active":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Form not found")
        await conn.execute(
            "INSERT INTO cappe_form_submissions (form_id, site_id, data, submitter_email) "
            "VALUES ($1, $2, $3, $4)",
            form["id"], site["id"], json.dumps(data), submitter_email,
        )
        owner = await _site_owner(conn, site["id"])

    # Best-effort alert to the creator (submission content is not echoed).
    if owner and owner["email"]:
        background.add_task(
            send_cappe_form_alert_email, owner["email"], owner["name"], site["name"],
            form["name"], dashboard_url(f"/sites/{site['id']}/forms"),
        )
    return {"ok": True}


# --- Reviews ----------------------------------------------------------------

@router.get("/public/sites/{slug}/reviews", response_model=list[CappePublicReview])
async def public_reviews(slug: str, request: Request):
    """Approved reviews for the public site (hydrates the reviews widget)."""
    await _read_rate_limit(request)
    async with get_connection() as conn:
        site = await _published_site(conn, slug)
        rows = await conn.fetch(
            "SELECT author_name, rating, body, created_at FROM cappe_reviews "
            "WHERE site_id = $1 AND status = 'approved' ORDER BY created_at DESC LIMIT 50",
            site["id"],
        )
    return [dict(r) for r in rows]


@router.post("/public/sites/{slug}/reviews", status_code=status.HTTP_201_CREATED)
async def public_submit_review(slug: str, body: CappeReviewCreate, request: Request):
    """Visitor submits a review (lands `pending` until the creator approves)."""
    ip = client_ip(request)
    await check_rate_limit(ip, "cappe_review", 5, 60)
    await check_rate_limit(ip, "cappe_review_hr", 20, 3600)
    async with get_connection() as conn:
        site = await _published_site(conn, slug)
        await conn.execute(
            "INSERT INTO cappe_reviews (site_id, author_name, rating, body, status) "
            "VALUES ($1, $2, $3, $4, 'pending')",
            site["id"], body.author_name.strip(), body.rating, body.body.strip(),
        )
    return {"ok": True}


# --- Bookings ---------------------------------------------------------------

async def _active_staff_for_type(conn, site_id, type_id) -> list:
    """Active staff ids who perform this service, ordered. Empty = unstaffed
    (legacy shared-calendar path)."""
    rows = await conn.fetch(
        "SELECT ss.staff_id FROM cappe_staff_services ss "
        "JOIN cappe_staff s ON s.id = ss.staff_id "
        "WHERE ss.booking_type_id = $1 AND ss.site_id = $2 AND s.active = true "
        "ORDER BY s.sort_order, s.created_at",
        type_id, site_id,
    )
    return [r["staff_id"] for r in rows]


@router.get("/public/sites/{slug}/locations", response_model=list[CappePublicLocation])
async def public_locations(slug: str, request: Request):
    """Active locations for the booking widget's "choose a location" step."""
    await _read_rate_limit(request)
    async with get_connection() as conn:
        site = await _published_site(conn, slug)
        rows = await conn.fetch(
            "SELECT id, name, address, lat, lng, timezone, hours, contact_phone, contact_email "
            "FROM cappe_locations WHERE site_id = $1 AND active = true "
            "ORDER BY is_default DESC, sort_order, created_at",
            site["id"],
        )
    return [{**dict(r), "hours": loads_list(r["hours"])} for r in rows]


@router.get("/public/sites/{slug}/staff", response_model=list[CappePublicStaff])
async def public_staff(slug: str, request: Request, location_id: UUID | None = Query(default=None)):
    """Active bookable staff for the booking-widget picker (location-or-shared)."""
    await _read_rate_limit(request)
    async with get_connection() as conn:
        site = await _published_site(conn, slug)
        rows = await conn.fetch(
            "SELECT id, name, bio, image_url FROM cappe_staff "
            "WHERE site_id = $1 AND active = true AND (location_id IS NULL OR location_id = $2) "
            "ORDER BY sort_order, created_at",
            site["id"], location_id,
        )
    return [dict(r) for r in rows]


@router.get("/public/sites/{slug}/booking-types", response_model=list[CappeBookingType])
async def public_booking_types(slug: str, request: Request, location_id: UUID | None = Query(default=None)):
    await _read_rate_limit(request)
    async with get_connection() as conn:
        site = await _published_site(conn, slug)
        rows = await conn.fetch(
            "SELECT id, site_id, name, description, duration_minutes, price_cents, status, "
            "requires_approval, pricing_mode, category, buffer_minutes, location_id, created_at, updated_at "
            "FROM cappe_booking_types WHERE site_id = $1 AND status = 'active' "
            "AND (location_id IS NULL OR location_id = $2) ORDER BY created_at",
            site["id"], location_id,
        )
        staff = await conn.fetch(
            "SELECT ss.booking_type_id, ss.staff_id FROM cappe_staff_services ss "
            "JOIN cappe_staff s ON s.id = ss.staff_id WHERE ss.site_id = $1 AND s.active = true",
            site["id"],
        )
    by_type: dict = {}
    for r in staff:
        by_type.setdefault(r["booking_type_id"], []).append(r["staff_id"])
    return [{**dict(r), "staff_ids": by_type.get(r["id"], [])} for r in rows]


@router.get("/public/sites/{slug}/rider")
async def public_rider(slug: str, request: Request):
    """The site's rider items (booking requirements the buyer agrees to)."""
    await _read_rate_limit(request)
    async with get_connection() as conn:
        site = await _published_site(conn, slug)
        items = await _site_rider(conn, site["id"])
    return {"items": items}


@router.get("/public/sites/{slug}/availability")
async def public_availability(slug: str, request: Request):
    await _read_rate_limit(request)
    async with get_connection() as conn:
        site = await _published_site(conn, slug)
        rows = await conn.fetch(
            "SELECT weekday, start_time, end_time, booking_type_id "
            "FROM cappe_availability WHERE site_id = $1 ORDER BY weekday, start_time",
            site["id"],
        )
    return {
        "timezone": site["timezone"],
        "slots": [
            {
                "weekday": r["weekday"],
                "start_time": r["start_time"].strftime("%H:%M"),
                "end_time": r["end_time"].strftime("%H:%M"),
                "booking_type_id": str(r["booking_type_id"]) if r["booking_type_id"] else None,
            }
            for r in rows
        ],
    }


@router.get("/public/sites/{slug}/booking-types/{type_id}/slots")
async def public_booking_slots(
    slug: str, type_id: UUID, request: Request,
    days: int = Query(default=21, ge=1, le=60),
    staff_id: UUID | None = Query(default=None),
    location_id: UUID | None = Query(default=None),
):
    """Concrete, openable slots for a booking type — the widget renders these as
    one-tap chips so a visitor never has to guess a valid time. Already-booked
    ranges are subtracted; each slot is pre-priced (dynamic rate rules applied).

    `staff_id`: a concrete stylist → that staff's slots; omitted → "any available"
    (union across the service's staff for a staffed service, else the legacy
    shared calendar)."""
    await _read_rate_limit(request)
    async with get_connection() as conn:
        site = await _published_site(conn, slug)
        btype = await conn.fetchrow(
            "SELECT id, duration_minutes, price_cents, pricing_mode, requires_approval, buffer_minutes, status "
            "FROM cappe_booking_types WHERE id = $1 AND site_id = $2",
            type_id, site["id"],
        )
        if btype is None or btype["status"] != "active":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking type not found")
        _, tz = await _location_ctx(conn, site, location_id)
        avail = await conn.fetch(
            "SELECT weekday, start_time, end_time, booking_type_id, staff_id "
            "FROM cappe_availability WHERE site_id = $1 AND (location_id IS NULL OR location_id = $2)",
            site["id"], location_id,
        )
        booked = await conn.fetch(
            "SELECT starts_at, ends_at, staff_id FROM cappe_bookings "
            "WHERE site_id = $1 AND booking_type_id = $2 AND status IN ('pending', 'confirmed') "
            "AND (location_id IS NULL OR location_id = $3)",
            site["id"], type_id, location_id,
        )
        rules = await _site_rate_rules(conn, site["id"], type_id, location_id)
        discounts = await _active_discounts(conn, site["id"])
        now_utc = await conn.fetchval("SELECT NOW()")
        offering_staff = await _active_staff_for_type(conn, site["id"], type_id)

    availability = [
        {
            "weekday": r["weekday"], "start_time": r["start_time"], "end_time": r["end_time"],
            "booking_type_id": str(r["booking_type_id"]) if r["booking_type_id"] else None,
            "staff_id": str(r["staff_id"]) if r["staff_id"] else None,
        }
        for r in avail
    ]
    btype_d = {
        "id": str(btype["id"]), "duration_minutes": btype["duration_minutes"],
        "price_cents": btype["price_cents"], "pricing_mode": btype["pricing_mode"],
        "buffer_minutes": btype["buffer_minutes"],
    }

    def _busy_for(sid):
        # Per-staff bookings (concrete) or all of them (legacy NULL-staff).
        return [(b["starts_at"], b["ends_at"]) for b in booked
                if sid is None or (b["staff_id"] and str(b["staff_id"]) == sid)]

    if staff_id is not None:                          # a specific stylist
        sid = str(staff_id)
        slots = generate_slots(availability, btype_d, _busy_for(sid), tz, now_utc, rules, days_ahead=days, staff_id=sid)
    elif offering_staff:                              # "any available" across the service's staff
        per_staff = []
        for s in offering_staff:
            sid = str(s)
            per_staff.append((sid, generate_slots(
                availability, btype_d, _busy_for(sid), tz, now_utc, rules, days_ahead=days, staff_id=sid)))
        slots = merge_any_staff_slots(per_staff)
    else:                                             # legacy unstaffed shared calendar
        slots = generate_slots(availability, btype_d, _busy_for(None), tz, now_utc, rules, days_ahead=days)

    # Apply the best active discount so each chip already shows the sale price.
    pct = best_discount_percent(
        discounts, kind="booking_type", target_id=str(type_id),
        on_date=_site_today(now_utc, tz),
    )
    if pct:
        for s in slots:
            s["original_price_cents"] = s["price_cents"]
            s["price_cents"] = apply_discount_cents(s["price_cents"], pct)
    return {
        "timezone": tz,
        "duration_minutes": btype["duration_minutes"],
        "pricing_mode": btype["pricing_mode"],
        "requires_approval": bool(btype["requires_approval"]),
        "discount_percent": pct,
        "slots": slots,
    }


@router.post("/public/sites/{slug}/bookings", status_code=status.HTTP_201_CREATED)
async def public_create_booking(slug: str, body: CappeBookingRequest, request: Request, background: BackgroundTasks):
    """Request a booking. `ends_at` is computed from the type's duration; the
    slot must fall inside an availability window (in the site's timezone) and not
    overlap an existing booking."""
    ip = client_ip(request)
    await check_rate_limit(ip, "cappe_booking", 5, 60)
    await check_rate_limit(ip, "cappe_booking_hr", 20, 3600)
    cust_email = str(body.customer_email).strip().lower()
    _reject_reserved(cust_email)

    async with get_connection() as conn:
        site = await _published_site(conn, slug)
        loc_id, loc_tz = await _location_ctx(conn, site, body.location_id)
        btype = await conn.fetchrow(
            "SELECT id, name, duration_minutes, status, price_cents, pricing_mode, requires_approval, buffer_minutes "
            "FROM cappe_booking_types WHERE id = $1 AND site_id = $2",
            body.booking_type_id, site["id"],
        )
        if btype is None or btype["status"] != "active":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking type not found")

        # Rider: if the creator requires any item, the buyer must acknowledge.
        rider = await _site_rider(conn, site["id"])
        if any(r["is_required"] for r in rider) and not body.rider_acknowledged:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Please review and agree to the booking requirements.",
            )

        # Resolve which staff to book. A staffed service must be booked with one
        # of its staff; an unstaffed service uses the legacy shared calendar.
        offering = await _active_staff_for_type(conn, site["id"], body.booking_type_id)
        if body.staff_id is not None:
            if not offering or body.staff_id not in offering:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="That staff member isn't available for this service")
            candidates = [body.staff_id]
        elif offering:
            candidates = list(offering)        # "any available" — try each in order
        else:
            candidates = [None]                # unstaffed / legacy

        booking = None
        last_taken = False
        for sid in candidates:
            try:
                async with conn.transaction():
                    booking = await _create_booking_in_tx(
                        conn, site, btype, body.starts_at, body.customer_name,
                        cust_email, body.note,
                        ends_at_override=body.ends_at,
                        rider_acknowledged=body.rider_acknowledged,
                        rider_snapshot=rider, staff_id=sid,
                        location_id=loc_id, tz=loc_tz,
                    )
                break
            except HTTPException as exc:
                # 409 = this staff is taken at that time; with "any available"
                # fall through and try the next staff. Other 4xx (bad slot) abort.
                if exc.status_code == status.HTTP_409_CONFLICT and len(candidates) > 1:
                    last_taken = True
                    continue
                raise
        if booking is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="That time was just taken." if last_taken else "That slot is taken",
            )
        owner = await _site_owner(conn, site["id"])

    # Notifications (best-effort): confirmation → customer, alert → creator.
    when_label = format_when(booking["starts_at"], loc_tz)
    needs_approval = bool(booking["requires_approval"])
    if cust_email:
        background.add_task(
            send_cappe_booking_received_email, cust_email, body.customer_name, site["name"],
            btype["name"], when_label, needs_approval, booking_manage_url(booking["access_token"]),
        )
    if owner and owner["email"]:
        background.add_task(
            send_cappe_booking_alert_email, owner["email"], owner["name"], site["name"],
            body.customer_name, btype["name"], when_label, needs_approval,
            dashboard_url(f"/sites/{site['id']}/bookings"),
        )
    return {
        "booking_id": str(booking["id"]),
        "status": booking["status"],
        "starts_at": booking["starts_at"].isoformat(),
        "ends_at": booking["ends_at"].isoformat(),
        "quoted_price_cents": booking["quoted_price_cents"],
        "requires_approval": booking["requires_approval"],
    }


# --- Booking self-serve (customer, token-gated) -----------------------------

async def _booking_by_token(conn, token: str):
    """Resolve a booking + its type/site by the customer access token, or None."""
    return await conn.fetchrow(
        """SELECT b.id, b.site_id, b.booking_type_id, b.staff_id, b.location_id, b.status,
                  b.starts_at, b.ends_at, b.customer_name, b.customer_email, b.quoted_price_cents,
                  bt.name AS type_name, bt.duration_minutes, bt.pricing_mode, bt.buffer_minutes,
                  bt.price_cents AS bt_price_cents, bt.requires_approval AS bt_requires_approval,
                  s.name AS site_name, s.slug, COALESCE(loc.timezone, s.timezone) AS timezone
           FROM cappe_bookings b
           JOIN cappe_sites s ON s.id = b.site_id
           LEFT JOIN cappe_booking_types bt ON bt.id = b.booking_type_id
           LEFT JOIN cappe_locations loc ON loc.id = b.location_id
           WHERE b.access_token = $1""",
        token,
    )


def _booking_can_modify(row, now_utc) -> bool:
    return row["status"] in ("pending", "confirmed") and row["starts_at"] > now_utc


@router.get("/public/bookings/{token}", response_model=CappePublicBooking)
async def public_booking_view(token: str, request: Request):
    """Customer views their booking via the unguessable token (emailed link)."""
    await check_rate_limit(client_ip(request), "cappe_booking_view", 30, 60)
    async with get_connection() as conn:
        row = await _booking_by_token(conn, token)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
        now_utc = await conn.fetchval("SELECT NOW()")
    return CappePublicBooking(
        status=row["status"], type_name=row["type_name"] or "Booking", site_name=row["site_name"],
        slug=row["slug"], booking_type_id=row["booking_type_id"],
        starts_at=row["starts_at"], ends_at=row["ends_at"], quoted_price_cents=row["quoted_price_cents"],
        timezone=row["timezone"], can_modify=_booking_can_modify(row, now_utc),
    )


@router.post("/public/bookings/{token}/cancel", response_model=CappePublicBooking)
async def public_booking_cancel(token: str, request: Request, background: BackgroundTasks):
    """Customer cancels a future pending/confirmed booking (frees the slot)."""
    await check_rate_limit(client_ip(request), "cappe_booking_modify", 10, 60)
    async with get_connection() as conn:
        async with conn.transaction():
            row = await _booking_by_token(conn, token)
            if row is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
            now_utc = await conn.fetchval("SELECT NOW()")
            if not _booking_can_modify(row, now_utc):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This booking can no longer be cancelled")
            await conn.execute(
                "UPDATE cappe_bookings SET status = 'cancelled', updated_at = NOW() WHERE id = $1", row["id"],
            )
            owner = await _site_owner(conn, row["site_id"])
    when_label = format_when(row["starts_at"], row["timezone"])
    if owner and owner["email"]:
        background.add_task(
            send_cappe_booking_cancelled_email, owner["email"], owner["name"], row["site_name"],
            row["customer_name"], row["type_name"] or "Booking", when_label,
            dashboard_url(f"/sites/{row['site_id']}/bookings"),
        )
    return CappePublicBooking(
        status="cancelled", type_name=row["type_name"] or "Booking", site_name=row["site_name"],
        slug=row["slug"], booking_type_id=row["booking_type_id"],
        starts_at=row["starts_at"], ends_at=row["ends_at"], quoted_price_cents=row["quoted_price_cents"],
        timezone=row["timezone"], can_modify=False,
    )


@router.post("/public/bookings/{token}/reschedule", response_model=CappePublicBooking)
async def public_booking_reschedule(token: str, body: CappeBookingReschedule, request: Request):
    """Customer moves a future booking to a new time (re-validates availability +
    overlap, re-prices, in place — same token + id)."""
    await check_rate_limit(client_ip(request), "cappe_booking_modify", 10, 60)
    async with get_connection() as conn:
        async with conn.transaction():
            row = await _booking_by_token(conn, token)
            if row is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
            now_utc = await conn.fetchval("SELECT NOW()")
            if not _booking_can_modify(row, now_utc):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This booking can no longer be changed")
            site = {"id": row["site_id"], "timezone": row["timezone"], "name": row["site_name"]}
            btype = {
                "id": row["booking_type_id"], "duration_minutes": row["duration_minutes"],
                "pricing_mode": row["pricing_mode"], "price_cents": row["bt_price_cents"],
                "requires_approval": row["bt_requires_approval"], "buffer_minutes": row["buffer_minutes"],
            }
            # Keep the same stylist + location on reschedule (tz is location-aware).
            slot = await _resolve_booking_slot(
                conn, site, btype, body.starts_at, body.ends_at,
                exclude_booking_id=row["id"], staff_id=row["staff_id"],
                location_id=row["location_id"], tz=row["timezone"],
            )
            try:
                updated = await conn.fetchrow(
                    """UPDATE cappe_bookings
                       SET starts_at = $2, ends_at = $3, quoted_price_cents = $4,
                           reminder_sent_at = NULL, updated_at = NOW()
                       WHERE id = $1
                       RETURNING starts_at, ends_at, quoted_price_cents, status""",
                    row["id"], slot["s_utc"], slot["e_utc"], slot["quote_cents"],
                )
            except Exception as exc:
                if "idx_cappe_bookings_no_doublebook" in str(exc):
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That slot is taken")
                raise
    return CappePublicBooking(
        status=updated["status"], type_name=row["type_name"] or "Booking", site_name=row["site_name"],
        slug=row["slug"], booking_type_id=row["booking_type_id"],
        starts_at=updated["starts_at"], ends_at=updated["ends_at"],
        quoted_price_cents=updated["quoted_price_cents"], timezone=row["timezone"], can_modify=True,
    )


@router.post("/public/sites/{slug}/booking-quote", response_model=CappeBookingQuote)
async def public_booking_quote(slug: str, body: CappeBookingQuoteRequest, request: Request):
    """Price a prospective booking without creating it (live quote in the
    widget). No availability/overlap checks — purely the money math."""
    await _read_rate_limit(request)
    async with get_connection() as conn:
        site = await _published_site(conn, slug)
        btype = await conn.fetchrow(
            "SELECT id, duration_minutes, status, price_cents, pricing_mode, requires_approval "
            "FROM cappe_booking_types WHERE id = $1 AND site_id = $2",
            body.booking_type_id, site["id"],
        )
        if btype is None or btype["status"] != "active":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking type not found")
        loc_id, tz = await _location_ctx(conn, site, body.location_id)
        starts_at = _anchor_local(body.starts_at, tz)
        pricing_mode = btype["pricing_mode"]
        if body.ends_at is not None and pricing_mode == "hourly":
            ends_at = _anchor_local(body.ends_at, tz)
            duration_min = (ends_at - starts_at).total_seconds() / 60
            if duration_min <= 0:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="End time must be after start")
        else:
            duration_min = btype["duration_minutes"]
        bt = booking_times(starts_at, duration_min, tz)
        rules = await _site_rate_rules(conn, site["id"], btype["id"], loc_id)
        quote = booking_quote_cents(
            btype["price_cents"] or 0, pricing_mode, bt["local_start"], bt["local_end"], rules
        )
        discounts = await _active_discounts(conn, site["id"])
        now_utc = await conn.fetchval("SELECT NOW()")
    pct = best_discount_percent(
        discounts, kind="booking_type", target_id=str(btype["id"]),
        on_date=_site_today(now_utc, tz),
    )
    final = apply_discount_cents(quote, pct)
    return CappeBookingQuote(
        price_cents=final, currency="USD", pricing_mode=pricing_mode,
        requires_approval=bool(btype["requires_approval"]), duration_minutes=int(duration_min),
        original_price_cents=quote if pct else None, discount_percent=pct,
    )


# --- Messages (client side, token-gated) ------------------------------------

@router.get("/public/threads/{token}", response_model=CappePublicThread)
async def public_thread(token: str, request: Request):
    """A client reads their conversation via the unguessable thread token."""
    await check_rate_limit(client_ip(request), "cappe_thread", 30, 60)
    try:
        tok = UUID(token)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    async with get_connection() as conn:
        thread = await conn.fetchrow(
            """SELECT t.id, t.subject, s.name AS site_name
               FROM cappe_threads t JOIN cappe_sites s ON s.id = t.site_id
               WHERE t.access_token = $1""",
            tok,
        )
        if thread is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        await conn.execute("UPDATE cappe_threads SET client_unread = 0 WHERE id = $1", thread["id"])
        msgs = await conn.fetch(
            "SELECT id, thread_id, sender, body, created_at FROM cappe_messages "
            "WHERE thread_id = $1 ORDER BY created_at",
            thread["id"],
        )
    return {"site_name": thread["site_name"], "subject": thread["subject"], "messages": [dict(m) for m in msgs]}


@router.post("/public/threads/{token}/messages", status_code=status.HTTP_201_CREATED)
async def public_thread_reply(token: str, body: CappeMessageCreate, request: Request, background: BackgroundTasks):
    """A client replies to their conversation."""
    ip = client_ip(request)
    await check_rate_limit(ip, "cappe_thread_reply", 5, 60)
    await check_rate_limit(ip, "cappe_thread_reply_hr", 30, 3600)
    try:
        tok = UUID(token)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    async with get_connection() as conn:
        thread = await conn.fetchrow(
            """SELECT t.id, t.site_id, t.client_name, s.name AS site_name, a.email AS owner_email,
                      a.name AS owner_name
               FROM cappe_threads t
               JOIN cappe_sites s ON s.id = t.site_id
               JOIN cappe_accounts a ON a.id = s.account_id
               WHERE t.access_token = $1""",
            tok,
        )
        if thread is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        async with conn.transaction():
            await conn.execute(
                "INSERT INTO cappe_messages (thread_id, site_id, sender, body) VALUES ($1, $2, 'client', $3)",
                thread["id"], thread["site_id"], body.body,
            )
            await conn.execute(
                "UPDATE cappe_threads SET owner_unread = owner_unread + 1, status = 'open', "
                "last_message_at = NOW() WHERE id = $1", thread["id"],
            )
    dash = f"https://{os.getenv('CAPPE_BASE_DOMAIN', 'hey-matcha.com')}/cappe/sites/{thread['site_id']}/messages"
    background.add_task(
        send_cappe_message_email, thread["owner_email"], thread["owner_name"], thread["site_name"],
        body.body, dash, thread["client_name"] or "a client",
    )
    return {"status": "ok"}


# --- Blog -------------------------------------------------------------------

@router.get("/public/sites/{slug}/posts", response_model=list[CappePost])
async def public_posts(slug: str, request: Request):
    await _read_rate_limit(request)
    async with get_connection() as conn:
        site = await _published_site(conn, slug)
        rows = await conn.fetch(
            "SELECT id, site_id, title, slug, excerpt, body, cover_image_url, status, "
            "published_at, created_at, updated_at "
            "FROM cappe_posts WHERE site_id = $1 AND status = 'published' "
            "ORDER BY published_at DESC NULLS LAST, created_at DESC",
            site["id"],
        )
    return [dict(r) for r in rows]


@router.get("/public/sites/{slug}/posts/{post_slug}", response_model=CappePost)
async def public_post(slug: str, post_slug: str, request: Request):
    await _read_rate_limit(request)
    async with get_connection() as conn:
        site = await _published_site(conn, slug)
        row = await conn.fetchrow(
            "SELECT id, site_id, title, slug, excerpt, body, cover_image_url, status, "
            "published_at, created_at, updated_at "
            "FROM cappe_posts WHERE site_id = $1 AND slug = $2 AND status = 'published'",
            site["id"], post_slug,
        )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    return dict(row)
