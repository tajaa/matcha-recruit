"""Cappe public surface — bookings (locations, staff, booking types, rider,
availability, slots, create)."""
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, status

from ....core.services.redis_cache import check_rate_limit, client_ip
from ....database import get_connection
from ...models.cappe import (
    CappeBookingRequest,
    CappeBookingSuggestionRequest,
    CappeBookingSuggestions,
    CappeBookingType,
    CappePublicLocation,
    CappePublicStaff,
)
from ...services.commerce import (
    check_recipient_send_ok as _recipient_send_ok,
    create_booking_in_tx,
    fetch_rate_rules,
)
from ...services.discounts import apply_discount_cents, best_discount_percent, fetch_active_discounts, site_today
from ...services.email import (
    booking_manage_url,
    dashboard_url,
    format_when,
    send_cappe_booking_alert_email,
    send_cappe_booking_received_email,
)
from ...services.slots import generate_slots, merge_any_staff_slots
from ...services.booking_suggestions import (
    extract_booking_preference,
    rank_booking_suggestions,
    resolve_booking_windows,
    resolve_staff_preferences,
)
from .._shared import _site_owner, loads_list
from ._common import _location_ctx, _published_site, _read_rate_limit, _reject_reserved

router = APIRouter()

_MAX_SUGGESTION_BODY_BYTES = 8 * 1024


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


async def _site_rider(conn, site_id) -> list[dict]:
    rows = await conn.fetch(
        "SELECT label, detail, is_required FROM cappe_rider_items WHERE site_id = $1 "
        "ORDER BY sort_order, created_at",
        site_id,
    )
    return [dict(r) for r in rows]


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
        discounts = await fetch_active_discounts(conn, site["id"])
        slots = await _load_live_booking_slots(
            conn, site=site, booking_type=btype, location_id=location_id,
            timezone_name=tz, days=days, staff_id=staff_id, discounts=discounts,
        )
        now_utc = await conn.fetchval("SELECT NOW()")
        pct = best_discount_percent(
            discounts,
            kind="booking_type", target_id=str(type_id),
            on_date=site_today(now_utc, tz),
        )
    return {
        "timezone": tz,
        "duration_minutes": btype["duration_minutes"],
        "pricing_mode": btype["pricing_mode"],
        "requires_approval": bool(btype["requires_approval"]),
        "discount_percent": pct,
        "slots": slots,
    }


async def _load_live_booking_slots(
    conn, *, site, booking_type, location_id: UUID | None,
    timezone_name: str, days: int, staff_id: UUID | None,
    discounts: list[dict] | None = None, include_staff_ids: bool = False,
) -> list[dict]:
    """Generate live candidates shared by the normal picker and AI suggestions."""
    type_id = booking_type["id"]
    avail = await conn.fetch(
        "SELECT weekday, start_time, end_time, booking_type_id, staff_id "
        "FROM cappe_availability WHERE site_id = $1 AND (location_id IS NULL OR location_id = $2)",
        site["id"], location_id,
    )
    offering_staff = await _active_staff_for_type(conn, site["id"], type_id)
    booked = await conn.fetch(
        "SELECT starts_at, ends_at, staff_id FROM cappe_bookings "
        "WHERE site_id = $1 AND status IN ('pending', 'confirmed') "
        "AND (staff_id = ANY($4::uuid[]) "
        "     OR (staff_id IS NULL AND booking_type_id = $2 "
        "         AND location_id IS NOT DISTINCT FROM $3))",
        site["id"], type_id, location_id, list(offering_staff),
    )
    rules = await fetch_rate_rules(conn, site["id"], type_id, location_id)
    discounts = discounts if discounts is not None else await fetch_active_discounts(conn, site["id"])
    now_utc = await conn.fetchval("SELECT NOW()")
    availability = [
        {
            "weekday": r["weekday"], "start_time": r["start_time"], "end_time": r["end_time"],
            "booking_type_id": str(r["booking_type_id"]) if r["booking_type_id"] else None,
            "staff_id": str(r["staff_id"]) if r["staff_id"] else None,
        }
        for r in avail
    ]
    btype = {
        "id": str(booking_type["id"]), "duration_minutes": booking_type["duration_minutes"],
        "price_cents": booking_type["price_cents"], "pricing_mode": booking_type["pricing_mode"],
        "buffer_minutes": booking_type["buffer_minutes"],
    }

    def _busy_for(sid):
        return [(b["starts_at"], b["ends_at"]) for b in booked
                if sid is None or (b["staff_id"] and str(b["staff_id"]) == sid)]

    if staff_id is not None:
        sid = str(staff_id)
        slots = generate_slots(
            availability, btype, _busy_for(sid), timezone_name, now_utc, rules,
            days_ahead=days, staff_id=sid,
        )
        if include_staff_ids:
            for slot in slots:
                slot["available_staff_ids"] = [sid]
    elif offering_staff:
        per_staff = []
        for sid_value in offering_staff:
            sid = str(sid_value)
            per_staff.append((sid, generate_slots(
                availability, btype, _busy_for(sid), timezone_name, now_utc, rules,
                days_ahead=days, staff_id=sid,
            )))
        slots = merge_any_staff_slots(per_staff)
    else:
        slots = generate_slots(
            availability, btype, _busy_for(None), timezone_name, now_utc, rules,
            days_ahead=days,
        )

    pct = best_discount_percent(
        discounts, kind="booking_type", target_id=str(type_id),
        on_date=site_today(now_utc, timezone_name),
    )
    if pct:
        for slot in slots:
            slot["original_price_cents"] = slot["price_cents"]
            slot["price_cents"] = apply_discount_cents(slot["price_cents"], pct)
    return slots


@router.post(
    "/public/sites/{slug}/booking-suggestions",
    response_model=CappeBookingSuggestions,
)
async def public_booking_suggestions(
    slug: str, body: CappeBookingSuggestionRequest, request: Request,
):
    """Return live booking options parsed from a bounded natural-language request."""
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > _MAX_SUGGESTION_BODY_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Request is too large")
    if body.website.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid request")
    ip = client_ip(request)
    await check_rate_limit(ip, "cappe_booking_suggest_min", 2, 60)
    await check_rate_limit(ip, "cappe_booking_suggest_hr", 12, 3600)

    async with get_connection() as conn:
        site = await _published_site(conn, slug)
        await check_rate_limit(str(site["id"]), "cappe_booking_suggest_site_hr", 60, 3600)
        loc_id, tz = await _location_ctx(conn, site, body.location_id)
        btype = await conn.fetchrow(
            "SELECT id, duration_minutes, price_cents, pricing_mode, requires_approval, buffer_minutes, status "
            "FROM cappe_booking_types WHERE id = $1 AND site_id = $2",
            body.booking_type_id, site["id"],
        )
        if btype is None or btype["status"] != "active":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking type not found")
        staff_rows = await conn.fetch(
            "SELECT s.id, s.name FROM cappe_staff_services ss "
            "JOIN cappe_staff s ON s.id = ss.staff_id "
            "WHERE ss.booking_type_id = $1 AND ss.site_id = $2 AND s.active = true "
            "ORDER BY s.sort_order, s.created_at",
            body.booking_type_id, site["id"],
        )
        eligible_ids = {row["id"] for row in staff_rows}
        if body.staff_id is not None and body.staff_id not in eligible_ids:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="That staff member isn't available for this service")
        slots = await _load_live_booking_slots(
            conn, site=site, booking_type=btype, location_id=loc_id,
            timezone_name=tz, days=60, staff_id=body.staff_id,
            include_staff_ids=True,
        )
        now_utc = await conn.fetchval("SELECT NOW()")

    preference = await extract_booking_preference(
        body.request, today=site_today(now_utc, tz),
    )
    if preference is None:
        return CappeBookingSuggestions(timezone=tz)
    preferred_ids, unmatched = resolve_staff_preferences(
        [dict(row) for row in staff_rows], preference.staff_names,
    )
    if body.staff_id is not None:
        preferred_ids = [body.staff_id]
    elif preference.staff_names and not preferred_ids:
        return CappeBookingSuggestions(timezone=tz, unmatched_staff_names=unmatched)
    options = rank_booking_suggestions(
        slots,
        staff=[dict(row) for row in staff_rows],
        preferred_staff_ids=preferred_ids,
        resolved_windows=resolve_booking_windows(
            preference, today=site_today(now_utc, tz),
        ),
        requested_count=preference.requested_count,
    )
    return CappeBookingSuggestions(
        timezone=tz, options=options, unmatched_staff_names=unmatched,
    )


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
                    booking = await create_booking_in_tx(
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
    # Per-recipient throttle (same as the order receipt): booking intake is a
    # public, caller-emailable endpoint, so cap confirmations per recipient to
    # stop IP-rotating email-bomb abuse. The booking is created regardless.
    if cust_email and await _recipient_send_ok(cust_email):
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
