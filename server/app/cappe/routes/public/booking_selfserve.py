"""Cappe public surface — booking self-serve (customer, token-gated), plus the
booking-quote endpoint (grouped with these historically)."""
from datetime import timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status

from ....core.services.redis_cache import check_rate_limit, client_ip
from ....database import get_connection
from ...models.cappe import CappeBookingQuote, CappeBookingQuoteRequest, CappeBookingReschedule, CappePublicBooking
from ...services.commerce import booking_quote_cents, booking_times, fetch_rate_rules, resolve_booking_slot
from ...services.discounts import apply_discount_cents, best_discount_percent, fetch_active_discounts, site_today
from ...services.email import dashboard_url, format_when, send_cappe_booking_cancelled_email
from .._shared import _site_owner
from ._common import _location_ctx, _published_site, _read_rate_limit

router = APIRouter()


def _anchor_local(dt, tz_name):
    """A naive datetime from the widget is the visitor's pick in the SITE's
    timezone (availability is site-local) — anchor it there."""
    if dt.tzinfo is not None:
        return dt
    try:
        return dt.replace(tzinfo=ZoneInfo(tz_name or "UTC"))
    except Exception:
        return dt.replace(tzinfo=timezone.utc)


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
            slot = await resolve_booking_slot(
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
        rules = await fetch_rate_rules(conn, site["id"], btype["id"], loc_id)
        quote = booking_quote_cents(
            btype["price_cents"] or 0, pricing_mode, bt["local_start"], bt["local_end"], rules
        )
        discounts = await fetch_active_discounts(conn, site["id"])
        now_utc = await conn.fetchval("SELECT NOW()")
    pct = best_discount_percent(
        discounts, kind="booking_type", target_id=str(btype["id"]),
        on_date=site_today(now_utc, tz),
    )
    final = apply_discount_cents(quote, pct)
    return CappeBookingQuote(
        price_cents=final, currency="USD", pricing_mode=pricing_mode,
        requires_approval=bool(btype["requires_approval"]), duration_minutes=int(duration_min),
        original_price_cents=quote if pct else None, discount_percent=pct,
    )
