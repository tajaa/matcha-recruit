"""Cappe public surface — bookings (locations, staff, booking types, rider,
availability, slots, create)."""
from datetime import date, timedelta
from uuid import UUID

from fastapi import BackgroundTasks, Depends, HTTPException, Query, Request, status

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
    OutsideAvailability,
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
from ...services.shipping import site_currency
from ...services.booking_rules import blocked_for, load_time_off
from ...services.slots import generate_slots, merge_any_staff_slots
from ...services.booking_suggestions import (
    extract_booking_preference,
    rank_booking_suggestions,
    resolve_booking_windows,
    resolve_staff_preferences,
)
from .booking_suggestion_access import require_booking_suggestion_session
from ._body_limit import CappePublicJsonBodyLimitRoute, limited_public_router
from .._shared import _site_owner, loads_list
from ._common import _location_ctx, _published_site, _read_rate_limit, _reject_reserved

router = limited_public_router()
_SUGGESTION_SEARCH_DAYS = 14
# Slots the public picker returns. It was 60 — about two days of a 15-minute
# service — and it was applied to each stylist BEFORE the "any available"
# merge, so the merged list was ragged as well as short.
PUBLIC_SLOT_CAP = 300
# How far the widget can page when a service sets no horizon of its own.
MAX_SLOT_DAYS = 365
suggestions_router = limited_public_router()
# Kept as a module alias for existing body-limit tests and downstream imports.
_BookingSuggestionBodyLimitRoute = CappePublicJsonBodyLimitRoute


async def _active_staff_for_type(conn, site_id, type_id, location_id=None) -> list:
    """Active staff ids who perform this service, ordered. Empty = unstaffed
    (legacy shared-calendar path).

    At a location, only staff who work there (or at every location) count —
    "any available" used to hand a San Diego booking to someone in LA. With no
    location (a single-location site) every active staff member counts."""
    rows = await conn.fetch(
        "SELECT ss.staff_id FROM cappe_staff_services ss "
        "JOIN cappe_staff s ON s.id = ss.staff_id "
        "WHERE ss.booking_type_id = $1 AND ss.site_id = $2 AND s.active = true "
        "AND ($3::uuid IS NULL OR s.location_id IS NULL OR s.location_id = $3) "
        "ORDER BY s.sort_order, s.created_at",
        type_id, site_id, location_id,
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
            "requires_approval, pricing_mode, category, buffer_minutes, location_id, created_at, updated_at, "
            "min_notice_minutes, max_advance_days, cancel_cutoff_hours "
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
    currency = site_currency(site)
    return [{**dict(r), "staff_ids": by_type.get(r["id"], []), "currency": currency} for r in rows]


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
    from_date: date | None = Query(default=None, alias="from"),
):
    """Concrete, openable slots for a booking type — the widget renders these as
    one-tap chips so a visitor never has to guess a valid time. Already-booked
    ranges are subtracted; each slot is pre-priced (dynamic rate rules applied).

    `staff_id`: a concrete stylist → that staff's slots; omitted → "any available"
    (union across the service's staff for a staffed service, else the legacy
    shared calendar).

    `from` pages through dates: the slots from that day for `days` days, and
    `next_from` for the next page (None at the service's booking horizon).
    The widget used to stop at the first few weeks with no way further."""
    await _read_rate_limit(request)
    async with get_connection() as conn:
        site = await _published_site(conn, slug)
        btype = await conn.fetchrow(
            "SELECT id, duration_minutes, price_cents, pricing_mode, requires_approval, buffer_minutes, status, "
            "min_notice_minutes, max_advance_days "
            "FROM cappe_booking_types WHERE id = $1 AND site_id = $2",
            type_id, site["id"],
        )
        if btype is None or btype["status"] != "active":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking type not found")
        _, tz = await _location_ctx(conn, site, location_id)
        discounts = await fetch_active_discounts(conn, site["id"])
        now_utc = await conn.fetchval("SELECT NOW()")
        today = site_today(now_utc, tz)
        start_day = max(0, (from_date - today).days) if from_date else 0
        horizon = btype.get("max_advance_days")
        slots = await _load_live_booking_slots(
            conn, site=site, booking_type=btype, location_id=location_id,
            timezone_name=tz, days=days, staff_id=staff_id, discounts=discounts,
            max_slots=PUBLIC_SLOT_CAP, start_day=start_day,
        ) if horizon is None or start_day <= int(horizon) else []
    pct = best_discount_percent(
        discounts,
        kind="booking_type", target_id=str(type_id),
        on_date=today, location_id=location_id,
    )
    next_day = start_day + days
    next_from = (
        (today + timedelta(days=next_day)).isoformat()
        if next_day <= (int(horizon) if horizon else MAX_SLOT_DAYS) else None
    )
    return {
        "timezone": tz,
        "duration_minutes": btype["duration_minutes"],
        "pricing_mode": btype["pricing_mode"],
        "requires_approval": bool(btype["requires_approval"]),
        "discount_percent": pct,
        "slots": slots,
        "from": (today + timedelta(days=start_day)).isoformat(),
        "next_from": next_from,
    }


async def _load_live_booking_slots(
    conn, *, site, booking_type, location_id: UUID | None,
    timezone_name: str, days: int, staff_id: UUID | None,
    discounts: list[dict] | None = None, include_staff_ids: bool = False,
    max_slots: int | None = PUBLIC_SLOT_CAP, start_day: int = 0,
) -> list[dict]:
    """Generate live candidates shared by the normal picker and AI suggestions.
    The service's notice and horizon and any time off are honoured."""
    type_id = booking_type["id"]
    # DISTINCT: a window saved both as shared and for a location (the location
    # editor used to copy shared rows into the location on every save) must
    # not produce every slot twice.
    avail = await conn.fetch(
        "SELECT DISTINCT weekday, start_time, end_time, booking_type_id, staff_id "
        "FROM cappe_availability WHERE site_id = $1 AND (location_id IS NULL OR location_id = $2)",
        site["id"], location_id,
    )
    offering_staff = await _active_staff_for_type(conn, site["id"], type_id, location_id)
    booked = await conn.fetch(
        "SELECT b.starts_at, b.ends_at, b.staff_id, COALESCE(obt.buffer_minutes, 0) AS buffer_minutes "
        "FROM cappe_bookings b LEFT JOIN cappe_booking_types obt ON obt.id = b.booking_type_id "
        "WHERE b.site_id = $1 AND b.status IN ('pending', 'confirmed') "
        "AND (b.staff_id = ANY($4::uuid[]) "
        "     OR (b.staff_id IS NULL AND b.booking_type_id = $2 "
        "         AND b.location_id IS NOT DISTINCT FROM $3))",
        site["id"], type_id, location_id, list(offering_staff),
    )
    rules = await fetch_rate_rules(conn, site["id"], type_id, location_id)
    discounts = discounts if discounts is not None else await fetch_active_discounts(conn, site["id"])
    now_utc = await conn.fetchval("SELECT NOW()")
    time_off = await load_time_off(
        conn, site["id"], location_id=location_id,
        start_utc=now_utc + timedelta(days=start_day - 1), end_utc=now_utc + timedelta(days=start_day + days + 1),
    )
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
        "min_notice_minutes": booking_type.get("min_notice_minutes") or 0,
        "max_advance_days": booking_type.get("max_advance_days"),
    }

    def _busy_for(sid):
        return [(b["starts_at"], b["ends_at"], b["buffer_minutes"]) for b in booked
                if sid is None or (b["staff_id"] and str(b["staff_id"]) == sid)]

    if staff_id is not None:
        sid = str(staff_id)
        slots = generate_slots(
            availability, btype, _busy_for(sid), timezone_name, now_utc, rules,
            days_ahead=days, max_slots=max_slots, staff_id=sid,
            start_day=start_day, blocked=blocked_for(time_off, sid),
        )
        if include_staff_ids:
            for slot in slots:
                slot["available_staff_ids"] = [sid]
    elif offering_staff:
        # Each stylist's list is generated uncapped (it is bounded by `days`)
        # and the cap applied to the merged list: capping each one first cut
        # every stylist off at the same count, not at the same date.
        per_staff = []
        for sid_value in offering_staff:
            sid = str(sid_value)
            per_staff.append((sid, generate_slots(
                availability, btype, _busy_for(sid), timezone_name, now_utc, rules,
                days_ahead=days, max_slots=None, staff_id=sid,
                start_day=start_day, blocked=blocked_for(time_off, sid),
            )))
        slots = merge_any_staff_slots(per_staff)
        if max_slots is not None:
            slots = slots[:max_slots]
    else:
        slots = generate_slots(
            availability, btype, _busy_for(None), timezone_name, now_utc, rules,
            days_ahead=days, max_slots=max_slots,
            start_day=start_day, blocked=blocked_for(time_off, None),
        )

    pct = best_discount_percent(
        discounts, kind="booking_type", target_id=str(type_id),
        on_date=site_today(now_utc, timezone_name), location_id=location_id,
    )
    if pct:
        for slot in slots:
            slot["original_price_cents"] = slot["price_cents"]
            slot["price_cents"] = apply_discount_cents(slot["price_cents"], pct)
    return slots


@suggestions_router.post(
    "/public/sites/{slug}/booking-suggestions",
    response_model=CappeBookingSuggestions,
)
async def public_booking_suggestions(
    slug: str,
    body: CappeBookingSuggestionRequest,
    request: Request,
    verified_client_email: str = Depends(require_booking_suggestion_session),
):
    """Return live booking options parsed from a bounded natural-language request."""
    if body.website.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid request")
    ip = client_ip(request)
    await check_rate_limit(ip, "cappe_booking_suggest_min", 1, 60)
    await check_rate_limit(ip, "cappe_booking_suggest_hr", 6, 3600)

    async with get_connection() as conn:
        site = await _published_site(conn, slug)
        await check_rate_limit(str(site["id"]), "cappe_booking_suggest_site_hr", 30, 3600)
        loc_id, tz = await _location_ctx(conn, site, body.location_id)
        btype = await conn.fetchrow(
            "SELECT id, duration_minutes, price_cents, pricing_mode, requires_approval, buffer_minutes, status, "
            "min_notice_minutes, max_advance_days "
            "FROM cappe_booking_types WHERE id = $1 AND site_id = $2",
            body.booking_type_id, site["id"],
        )
        if btype is None or btype["status"] != "active":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking type not found")
        staff_rows = await conn.fetch(
            "SELECT s.id, s.name FROM cappe_staff_services ss "
            "JOIN cappe_staff s ON s.id = ss.staff_id "
            "WHERE ss.booking_type_id = $1 AND ss.site_id = $2 AND s.active = true "
            "AND ($3::uuid IS NULL OR s.location_id IS NULL OR s.location_id = $3) "
            "ORDER BY s.sort_order, s.created_at",
            body.booking_type_id, site["id"], loc_id,
        )
        eligible_ids = {row["id"] for row in staff_rows}
        if body.staff_id is not None and body.staff_id not in eligible_ids:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="That staff member isn't available for this service")
        slots = await _load_live_booking_slots(
            conn, site=site, booking_type=btype, location_id=loc_id,
            timezone_name=tz, days=_SUGGESTION_SEARCH_DAYS, staff_id=body.staff_id,
            include_staff_ids=True, max_slots=None,
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
    # The hidden field only a script fills in. Refused the same way the
    # suggestions endpoint refuses it.
    if body.website.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid request")
    ip = client_ip(request)
    await check_rate_limit(ip, "cappe_booking", 5, 60)
    await check_rate_limit(ip, "cappe_booking_hr", 20, 3600)
    cust_email = str(body.customer_email).strip().lower()
    _reject_reserved(cust_email)

    async with get_connection() as conn:
        site = await _published_site(conn, slug)
        loc_id, loc_tz = await _location_ctx(conn, site, body.location_id)
        btype = await conn.fetchrow(
            "SELECT id, name, duration_minutes, status, price_cents, pricing_mode, requires_approval, buffer_minutes, "
            "min_notice_minutes, max_advance_days "
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
        offering = await _active_staff_for_type(conn, site["id"], body.booking_type_id, loc_id)
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
            except OutsideAvailability:
                # With "any available", this stylist simply doesn't work then —
                # the slot the picker showed came from someone else. Try the next.
                if len(candidates) > 1:
                    continue
                raise
            except HTTPException as exc:
                # 409 = this staff is taken at that time; with "any available"
                # fall through and try the next staff. Other 4xx (bad slot) abort.
                if exc.status_code == status.HTTP_409_CONFLICT and len(candidates) > 1:
                    last_taken = True
                    continue
                raise
        if booking is None:
            if not last_taken:
                # Nobody who offers this service works at that time.
                raise OutsideAvailability()
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That time was just taken.")
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
        "currency": site_currency(site),
        "requires_approval": booking["requires_approval"],
        # What the times mean, and where the customer can change the booking.
        # The token is the one emailed to the same person who just made it.
        "timezone": loc_tz,
        "manage_url": booking_manage_url(booking["access_token"]),
    }
