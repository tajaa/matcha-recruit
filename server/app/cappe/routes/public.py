"""Cappe public surface — anonymous, by site slug.

Everything here is unauthenticated and reachable by any visitor, so each write
endpoint is (a) rate-limited per IP (layered minute+hour buckets), (b) guards
every email field against reserved/test domains, and (c) never trusts
client-supplied money/time — prices, order totals, and booking end-times are all
recomputed server-side. A site must be `published` to expose any public surface.
"""
import json
from datetime import timezone
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request, status

from ...core.services.email._shared import _is_reserved_test_domain
from ...core.services.redis_cache import check_rate_limit, client_ip
from ...database import get_connection
from ..services.commerce import booking_times, order_subtotal
from ..models.cappe import (
    CappeBookingRequest,
    CappeBookingType,
    CappeCheckoutRequest,
    CappeForm,
    CappeOrderReceipt,
    CappePost,
    CappeProduct,
    CappePublicSite,
    CappeSubscribeRequest,
)
from ._shared import loads, loads_list, page_row_to_dict

# Public product listing exposes everything EXCEPT digital_file_url (the gated
# deliverable — released only via the order receipt once paid/fulfilled).
_PUBLIC_PRODUCT_COLS = (
    "id, site_id, name, description, price_cents, currency, image_url, sku, "
    "inventory, status, sort_order, fulfillment, booking_type_id, intake_fields, "
    "created_at, updated_at"
)

router = APIRouter()


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
    return [{**dict(r), "intake_fields": loads_list(r["intake_fields"])} for r in rows]


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


async def _create_booking_in_tx(conn, site, btype, starts_at, customer_name, customer_email, note):
    """Validate availability + overlap and insert a booking. MUST run inside a
    transaction. Shared by the public booking intake and booking-fulfillment
    order lines so the timezone/overlap logic lives in one place."""
    # A naive time from the widget is the visitor's pick in the SITE's timezone
    # (the seller's availability is site-local) — anchor it there before math.
    if starts_at.tzinfo is None:
        try:
            starts_at = starts_at.replace(tzinfo=ZoneInfo(site["timezone"] or "UTC"))
        except Exception:
            starts_at = starts_at.replace(tzinfo=timezone.utc)
    bt = booking_times(starts_at, btype["duration_minutes"], site["timezone"])
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
           LIMIT 1""",
        site["id"], bt["weekday"], bt["local_start"].time(), bt["local_end"].time(), btype["id"],
    )
    if not window:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Time is outside availability")

    overlap = await conn.fetchval(
        """SELECT 1 FROM cappe_bookings
           WHERE site_id = $1 AND booking_type_id = $2 AND status IN ('pending', 'confirmed')
             AND tstzrange(starts_at, ends_at) && tstzrange($3, $4) LIMIT 1""",
        site["id"], btype["id"], s_utc, e_utc,
    )
    if overlap:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That slot is taken")
    try:
        return await conn.fetchrow(
            """INSERT INTO cappe_bookings
                   (site_id, booking_type_id, customer_name, customer_email, starts_at, ends_at, note)
               VALUES ($1, $2, $3, $4, $5, $6, $7)
               RETURNING id, status, starts_at, ends_at""",
            site["id"], btype["id"], customer_name, customer_email, s_utc, e_utc, note,
        )
    except Exception as exc:
        if "idx_cappe_bookings_no_doublebook" in str(exc):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That slot is taken")
        raise


@router.post("/public/sites/{slug}/orders", status_code=status.HTTP_201_CREATED)
async def public_create_order(slug: str, body: CappeCheckoutRequest, request: Request):
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
        async with conn.transaction():
            order_currency = None
            # (product_id, title, unit_price, qty, fulfillment, intake_answers, booking_id)
            line_rows = []
            for item in body.items:
                product = await conn.fetchrow(
                    "SELECT id, name, price_cents, currency, inventory, status, fulfillment, "
                    "booking_type_id, intake_fields "
                    "FROM cappe_products WHERE id = $1 AND site_id = $2 FOR UPDATE",
                    item.product_id, site["id"],
                )
                if product is None or product["status"] != "active":
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Product unavailable")
                if order_currency is None:
                    order_currency = product["currency"]
                elif product["currency"] != order_currency:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Mixed currencies not supported")

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
                        "SELECT id, duration_minutes, status FROM cappe_booking_types WHERE id = $1 AND site_id = $2",
                        product["booking_type_id"], site["id"],
                    )
                    if btype is None or btype["status"] != "active":
                        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Booking unavailable")
                    _validate_intake(loads_list(product["intake_fields"]), intake)
                    booking = await _create_booking_in_tx(
                        conn, site, btype, item.starts_at, body.customer_name, email, body.note
                    )
                    booking_id = booking["id"]

                line_rows.append(
                    (item.product_id, product["name"], product["price_cents"], qty, f, intake, booking_id)
                )

            subtotal = order_subtotal((unit, qty) for (_, _, unit, qty, *_rest) in line_rows)
            order = await conn.fetchrow(
                """INSERT INTO cappe_orders
                       (site_id, customer_email, customer_name, status, subtotal_cents, currency, note)
                   VALUES ($1, $2, $3, 'pending', $4, $5, $6)
                   RETURNING id, status, subtotal_cents, currency, access_token""",
                site["id"], email, body.customer_name, subtotal, order_currency or "USD", body.note,
            )
            for product_id, title, unit_price, qty, f, intake, booking_id in line_rows:
                await conn.execute(
                    """INSERT INTO cappe_order_items
                           (order_id, site_id, product_id, title, unit_price_cents, quantity,
                            fulfillment, intake_answers, booking_id)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
                    order["id"], site["id"], product_id, title, unit_price, qty,
                    f, json.dumps(intake), booking_id,
                )

    return {
        "order_id": str(order["id"]),
        "order_token": order["access_token"],
        "status": order["status"],
        "subtotal_cents": order["subtotal_cents"],
        "currency": order["currency"],
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
                      oi.deliverable_url, p.digital_file_url,
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
async def public_submit_form(slug: str, form_slug: str, body: dict, request: Request):
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
            "SELECT id, status FROM cappe_forms WHERE site_id = $1 AND slug = $2", site["id"], form_slug
        )
        if form is None or form["status"] != "active":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Form not found")
        await conn.execute(
            "INSERT INTO cappe_form_submissions (form_id, site_id, data, submitter_email) "
            "VALUES ($1, $2, $3, $4)",
            form["id"], site["id"], json.dumps(data), submitter_email,
        )
    return {"ok": True}


# --- Bookings ---------------------------------------------------------------

@router.get("/public/sites/{slug}/booking-types", response_model=list[CappeBookingType])
async def public_booking_types(slug: str, request: Request):
    await _read_rate_limit(request)
    async with get_connection() as conn:
        site = await _published_site(conn, slug)
        rows = await conn.fetch(
            "SELECT id, site_id, name, description, duration_minutes, price_cents, status, created_at, updated_at "
            "FROM cappe_booking_types WHERE site_id = $1 AND status = 'active' ORDER BY created_at",
            site["id"],
        )
    return [dict(r) for r in rows]


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


@router.post("/public/sites/{slug}/bookings", status_code=status.HTTP_201_CREATED)
async def public_create_booking(slug: str, body: CappeBookingRequest, request: Request):
    """Request a booking. `ends_at` is computed from the type's duration; the
    slot must fall inside an availability window (in the site's timezone) and not
    overlap an existing booking."""
    ip = client_ip(request)
    await check_rate_limit(ip, "cappe_booking", 5, 60)
    await check_rate_limit(ip, "cappe_booking_hr", 20, 3600)
    _reject_reserved(str(body.customer_email))

    async with get_connection() as conn:
        site = await _published_site(conn, slug)
        btype = await conn.fetchrow(
            "SELECT id, duration_minutes, status FROM cappe_booking_types WHERE id = $1 AND site_id = $2",
            body.booking_type_id, site["id"],
        )
        if btype is None or btype["status"] != "active":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking type not found")

        async with conn.transaction():
            booking = await _create_booking_in_tx(
                conn, site, btype, body.starts_at, body.customer_name,
                str(body.customer_email).strip().lower(), body.note,
            )
    return {
        "booking_id": str(booking["id"]),
        "status": booking["status"],
        "starts_at": booking["starts_at"].isoformat(),
        "ends_at": booking["ends_at"].isoformat(),
    }


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
