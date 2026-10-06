"""Cappe bookings — booking types, weekly availability, booking management.

Public booking intake (with availability-window + overlap validation) lives in
public.py.
"""
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status

from ...database import get_connection
from ..dependencies import require_cappe_account
from ..services.booking_lifecycle import transition_error
from ..services.shipping import site_currency
from ..services.commerce import _anchor_local, create_booking_in_tx, resolve_booking_slot
from ..services.email import (
    booking_manage_url,
    format_when,
    send_cappe_booking_cancelled_by_host_email,
    send_cappe_booking_decision_email,
    send_cappe_booking_received_email,
    send_cappe_booking_rescheduled_email,
)
from ..models.cappe import (
    CappeAccount,
    CappeApprovalDecline,
    CappeAvailability,
    CappeAvailabilityReplace,
    CappeBooking,
    CappeBookingStatusUpdate,
    CappeBookingType,
    CappeBookingTypeCreate,
    CappeBookingTypeUpdate,
    CappeOwnerBookingCreate,
    CappeOwnerReschedule,
    CappeRateRule,
    CappeRateRulesReplace,
    CappeRequestSummary,
    CappeTimeOff,
    CappeTimeOffInput,
)
from ._shared import build_patch, get_owned_site, loads_list

router = APIRouter()

_TYPE_COLS = (
    "id, site_id, name, description, duration_minutes, price_cents, status, "
    "requires_approval, pricing_mode, category, buffer_minutes, location_id, created_at, updated_at, "
    "min_notice_minutes, max_advance_days, cancel_cutoff_hours"
)
_AVAIL_COLS = "id, weekday, start_time, end_time, booking_type_id, staff_id, location_id"


def _loc_filter(location_id, shared: bool, args: list, col: str = "location_id") -> str:
    """SQL fragment for the location filter. `shared` → only NULL (the "all
    locations / shared" set); a concrete id → that location's rows PLUS shared
    NULL rows; neither → every row (today's behavior). Appends to `args`."""
    if shared:
        return f" AND {col} IS NULL"
    if location_id is not None:
        args.append(location_id)
        return f" AND ({col} IS NULL OR {col} = ${len(args)})"
    return ""


async def _validate_location(conn, site_id, location_id) -> None:
    """Reject a location_id that isn't an active location of this site."""
    if location_id is None:
        return
    ok = await conn.fetchval(
        "SELECT 1 FROM cappe_locations WHERE id = $1 AND site_id = $2", location_id, site_id
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown location")


async def _staff_ids_for_types(conn, type_ids: list) -> dict:
    """{booking_type_id: [staff_id, …]} for the given services (read-only)."""
    if not type_ids:
        return {}
    rows = await conn.fetch(
        "SELECT booking_type_id, staff_id FROM cappe_staff_services WHERE booking_type_id = ANY($1::uuid[])",
        type_ids,
    )
    out: dict = {}
    for r in rows:
        out.setdefault(r["booking_type_id"], []).append(r["staff_id"])
    return out


async def _replace_type_staff(conn, site_id, type_id, staff_ids) -> None:
    """Replace which staff perform a service (None = leave as-is, [] = unstaffed).
    Validates the staff belong to this site."""
    if staff_ids is None:
        return
    ids = list({s for s in staff_ids})
    if ids:
        valid = await conn.fetchval(
            "SELECT COUNT(*) FROM cappe_staff WHERE site_id = $1 AND id = ANY($2::uuid[])",
            site_id, ids,
        )
        if valid != len(ids):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown staff member")
    await conn.execute("DELETE FROM cappe_staff_services WHERE booking_type_id = $1 AND site_id = $2", type_id, site_id)
    for sid in ids:
        await conn.execute(
            "INSERT INTO cappe_staff_services (staff_id, booking_type_id, site_id) VALUES ($1, $2, $3)",
            sid, type_id, site_id,
        )
_RULE_COLS = "id, site_id, booking_type_id, label, weekday, start_time, end_time, multiplier, location_id, created_at"
_BOOKING_COLS = (
    "id, site_id, booking_type_id, staff_id, location_id, customer_name, customer_email, starts_at, "
    "ends_at, status, note, requires_approval, quoted_price_cents, approved_at, "
    "decline_reason, rider_acknowledged, rider_snapshot, created_at, created_by_owner"
)


# `b.`-qualified column list for joins against cappe_staff (id/site_id/created_at
# are ambiguous otherwise).
_BOOKING_COLS_Q = ", ".join("b." + c.strip() for c in _BOOKING_COLS.split(","))

# One booking with what the dashboard shows beside it: staff and location
# names, the timezone its times mean, and the shop order it came from.
_BOOKING_VIEW = f"""
    SELECT {_BOOKING_COLS_Q}, st.name AS staff_name, loc.name AS location_name,
           COALESCE(loc.timezone, s.timezone) AS timezone,
           ord.id AS order_id, ord.status AS order_status
      FROM cappe_bookings b
      JOIN cappe_sites s ON s.id = b.site_id
      LEFT JOIN cappe_staff st ON st.id = b.staff_id
      LEFT JOIN cappe_locations loc ON loc.id = b.location_id
      LEFT JOIN LATERAL (
            SELECT o.id, o.status FROM cappe_order_items oi
              JOIN cappe_orders o ON o.id = oi.order_id
             WHERE oi.booking_id = b.id
             ORDER BY o.created_at DESC LIMIT 1
      ) ord ON true
"""


async def _booking_view(conn, site_id, booking_id) -> dict:
    row = await conn.fetchrow(f"{_BOOKING_VIEW} WHERE b.id = $1 AND b.site_id = $2", booking_id, site_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    return _booking_row(row)


def _booking_row(r) -> dict:
    d = dict(r)
    # rider_snapshot is a JSON ARRAY — use the list normalizer (loads() coerces to
    # a dict, which fails CappeBooking validation and 500s the bookings list).
    d["rider_snapshot"] = loads_list(d.get("rider_snapshot"))
    return d


# --- Booking types ----------------------------------------------------------

@router.get("/sites/{site_id}/booking-types", response_model=list[CappeBookingType])
async def list_booking_types(
    site_id: UUID, location_id: Optional[UUID] = Query(None), shared: bool = Query(False),
    account: CappeAccount = Depends(require_cappe_account),
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        args: list = [site_id]
        clause = _loc_filter(location_id, shared, args)
        rows = await conn.fetch(
            f"SELECT {_TYPE_COLS} FROM cappe_booking_types WHERE site_id = $1{clause} ORDER BY created_at",
            *args,
        )
        staff = await _staff_ids_for_types(conn, [r["id"] for r in rows])
    return [{**dict(r), "staff_ids": staff.get(r["id"], [])} for r in rows]


@router.post("/sites/{site_id}/booking-types", response_model=CappeBookingType, status_code=status.HTTP_201_CREATED)
async def create_booking_type(
    site_id: UUID, body: CappeBookingTypeCreate, account: CappeAccount = Depends(require_cappe_account)
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        await _validate_location(conn, site_id, body.location_id)
        async with conn.transaction():
            row = await conn.fetchrow(
                f"""INSERT INTO cappe_booking_types
                        (site_id, name, description, duration_minutes, price_cents, status,
                         requires_approval, pricing_mode, category, buffer_minutes, location_id,
                         min_notice_minutes, max_advance_days, cancel_cutoff_hours)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14) RETURNING {_TYPE_COLS}""",
                site_id, body.name, body.description, body.duration_minutes, body.price_cents, body.status,
                body.requires_approval, body.pricing_mode, body.category, body.buffer_minutes, body.location_id,
                body.min_notice_minutes, body.max_advance_days, body.cancel_cutoff_hours,
            )
            await _replace_type_staff(conn, site_id, row["id"], body.staff_ids)
        staff = await _staff_ids_for_types(conn, [row["id"]])
    return {**dict(row), "staff_ids": staff.get(row["id"], [])}


@router.put("/sites/{site_id}/booking-types/{type_id}", response_model=CappeBookingType)
async def update_booking_type(
    site_id: UUID, type_id: UUID, body: CappeBookingTypeUpdate,
    account: CappeAccount = Depends(require_cappe_account),
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        await _validate_location(conn, site_id, body.location_id)
        async with conn.transaction():
            sets, args = build_patch(body, (
                "name", "description", "duration_minutes", "price_cents", "status",
                "requires_approval", "pricing_mode", "category", "buffer_minutes", "location_id",
                "min_notice_minutes", "max_advance_days", "cancel_cutoff_hours",
            ), nullable={"description", "price_cents", "category", "location_id", "max_advance_days"})
            if sets:
                sets.append("updated_at = NOW()")
                args.extend([type_id, site_id])
                row = await conn.fetchrow(
                    f"UPDATE cappe_booking_types SET {', '.join(sets)} "
                    f"WHERE id = ${len(args) - 1} AND site_id = ${len(args)} RETURNING {_TYPE_COLS}",
                    *args,
                )
            else:
                row = await conn.fetchrow(
                    f"SELECT {_TYPE_COLS} FROM cappe_booking_types WHERE id = $1 AND site_id = $2",
                    type_id, site_id,
                )
            if row is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking type not found")
            await _replace_type_staff(conn, site_id, type_id, body.staff_ids)
        staff = await _staff_ids_for_types(conn, [type_id])
    return {**dict(row), "staff_ids": staff.get(type_id, [])}


@router.delete("/sites/{site_id}/booking-types/{type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_booking_type(
    site_id: UUID, type_id: UUID, account: CappeAccount = Depends(require_cappe_account)
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        result = await conn.execute(
            "DELETE FROM cappe_booking_types WHERE id = $1 AND site_id = $2", type_id, site_id
        )
    if result.endswith(" 0"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking type not found")


# --- Availability (whole-schedule replace) ----------------------------------

@router.get("/sites/{site_id}/availability", response_model=list[CappeAvailability])
async def get_availability(
    site_id: UUID, location_id: Optional[UUID] = Query(None), shared: bool = Query(False),
    account: CappeAccount = Depends(require_cappe_account),
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        args: list = [site_id]
        clause = _loc_filter(location_id, shared, args)
        rows = await conn.fetch(
            f"SELECT {_AVAIL_COLS} FROM cappe_availability WHERE site_id = $1{clause} ORDER BY weekday, start_time",
            *args,
        )
    return [dict(r) for r in rows]


@router.put("/sites/{site_id}/availability", response_model=list[CappeAvailability])
async def replace_availability(
    site_id: UUID, body: CappeAvailabilityReplace,
    location_id: Optional[UUID] = Query(None),
    account: CappeAccount = Depends(require_cappe_account),
):
    """Replace the weekly availability set FOR ONE LOCATION (location_id=None =
    the shared/all-locations set) in one transaction — other locations untouched."""
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        await _validate_location(conn, site_id, location_id)
        # Validate any referenced booking types belong to this site.
        type_ids = {s.booking_type_id for s in body.slots if s.booking_type_id}
        if type_ids:
            valid = await conn.fetchval(
                "SELECT COUNT(*) FROM cappe_booking_types WHERE site_id = $1 AND id = ANY($2::uuid[])",
                site_id, list(type_ids),
            )
            if valid != len(type_ids):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown booking type")
        staff_ids = {s.staff_id for s in body.slots if s.staff_id}
        if staff_ids:
            valid = await conn.fetchval(
                "SELECT COUNT(*) FROM cappe_staff WHERE site_id = $1 AND id = ANY($2::uuid[])",
                site_id, list(staff_ids),
            )
            if valid != len(staff_ids):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown staff member")
        async with conn.transaction():
            await conn.execute(
                "DELETE FROM cappe_availability WHERE site_id = $1 AND location_id IS NOT DISTINCT FROM $2",
                site_id, location_id,
            )
            seen = set()
            for s in body.slots:
                if s.end_time <= s.start_time:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="end_time must be after start_time",
                    )
                key = (s.weekday, s.start_time, s.end_time, s.booking_type_id, s.staff_id)
                if key in seen:
                    continue  # de-dupe (whole-set replace, so this is the only dup source)
                seen.add(key)
                await conn.execute(
                    """INSERT INTO cappe_availability
                           (site_id, weekday, start_time, end_time, booking_type_id, staff_id, location_id)
                       VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                    site_id, s.weekday, s.start_time, s.end_time, s.booking_type_id, s.staff_id, location_id,
                )
            rows = await conn.fetch(
                f"SELECT {_AVAIL_COLS} FROM cappe_availability "
                "WHERE site_id = $1 AND location_id IS NOT DISTINCT FROM $2 ORDER BY weekday, start_time",
                site_id, location_id,
            )
    return [dict(r) for r in rows]


# --- Bookings ---------------------------------------------------------------

@router.get("/sites/{site_id}/bookings", response_model=list[CappeBooking])
async def list_bookings(
    site_id: UUID, location_id: Optional[UUID] = Query(None),
    limit: Annotated[int, Query(ge=1, le=1000)] = 500,
    offset: Annotated[int, Query(ge=0)] = 0,
    account: CappeAccount = Depends(require_cappe_account),
):
    """Bookings, latest start first, a page at a time (this returned every
    booking the site had ever taken), each with its staff, location,
    timezone and the shop order it came from."""
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        args: list = [site_id]
        loc = ""
        if location_id is not None:
            args.append(location_id)
            loc = f" AND b.location_id = ${len(args)}"
        args.extend([limit, offset])
        rows = await conn.fetch(
            f"""{_BOOKING_VIEW}
                WHERE b.site_id = $1{loc}
                ORDER BY b.starts_at DESC
                LIMIT ${len(args) - 1} OFFSET ${len(args)}""",
            *args,
        )
    return [_booking_row(r) for r in rows]


@router.patch("/sites/{site_id}/bookings/{booking_id}", response_model=CappeBooking)
async def update_booking_status(
    site_id: UUID, booking_id: UUID, body: CappeBookingStatusUpdate, background: BackgroundTasks,
    account: CappeAccount = Depends(require_cappe_account),
):
    """Move a booking along `booking_lifecycle.ALLOWED_TRANSITIONS`.

    This used to write any status over any other: re-confirming a cancelled
    booking took its slot back unchecked, "confirmed" skipped the approval
    stamp and email, and a cancellation told the customer nothing.
    Confirming a request now IS approving it (same stamp, same email), and
    cancelling a live booking emails the customer."""
    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)
        async with conn.transaction():
            current = await conn.fetchrow(
                "SELECT status FROM cappe_bookings WHERE id = $1 AND site_id = $2 FOR UPDATE",
                booking_id, site_id,
            )
            if current is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
            refusal = transition_error(current["status"], body.status)
            if refusal:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=refusal)
            changed = body.status != current["status"]
            approving = changed and current["status"] == "pending" and body.status == "confirmed"
            row = await conn.fetchrow(
                f"""UPDATE cappe_bookings
                       SET status = $1, updated_at = NOW(),
                           approved_at = CASE WHEN $4 THEN NOW() ELSE approved_at END
                     WHERE id = $2 AND site_id = $3 RETURNING {_BOOKING_COLS}""",
                body.status, booking_id, site_id, approving,
            )
        if changed and approving and row["requires_approval"]:
            await _notify_booking_decision(conn, background, site, row, approved=True)
        elif changed and body.status == "cancelled" and row["customer_email"]:
            await _notify_host_cancelled(conn, background, site, row)
        view = await _booking_view(conn, site_id, booking_id)
    return view


# --- Owner bookings and time off ----------------------------------------------

async def _owner_btype(conn, site_id, type_id):
    btype = await conn.fetchrow(
        "SELECT id, name, duration_minutes, price_cents, pricing_mode, requires_approval, buffer_minutes, status "
        "FROM cappe_booking_types WHERE id = $1 AND site_id = $2",
        type_id, site_id,
    )
    if btype is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Service not found")
    return dict(btype)


async def _owner_where(conn, site, site_id, staff_id, location_id):
    """Check the staff member and location are this site's, and return the
    timezone the booking's times mean."""
    if staff_id is not None and not await conn.fetchval(
        "SELECT 1 FROM cappe_staff WHERE id = $1 AND site_id = $2", staff_id, site_id,
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown staff member")
    tz = site["timezone"]
    if location_id is not None:
        tz_row = await conn.fetchrow(
            "SELECT timezone FROM cappe_locations WHERE id = $1 AND site_id = $2", location_id, site_id,
        )
        if tz_row is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown location")
        tz = tz_row["timezone"] or tz
    return tz


@router.post("/sites/{site_id}/bookings", response_model=CappeBooking, status_code=status.HTTP_201_CREATED)
async def create_owner_booking(
    site_id: UUID, body: CappeOwnerBookingCreate, background: BackgroundTasks,
    account: CappeAccount = Depends(require_cappe_account),
):
    """The owner books someone in — a phone call, a walk-in. It isn't held to
    the service's notice, horizon, opening hours or time off (the owner knows
    when they can see someone), and it's confirmed straight away. It still
    can't double-book a staff member or a slot."""
    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)
        btype = await _owner_btype(conn, site_id, body.booking_type_id)
        tz = await _owner_where(conn, site, site_id, body.staff_id, body.location_id)
        async with conn.transaction():
            row = await create_booking_in_tx(
                conn, site, btype, body.starts_at, body.customer_name.strip(),
                str(body.customer_email).lower() if body.customer_email else None, body.note,
                ends_at_override=body.ends_at, staff_id=body.staff_id, location_id=body.location_id,
                tz=tz, owner=True,
            )
            await conn.execute("UPDATE cappe_bookings SET created_by_owner = true WHERE id = $1", row["id"])
        if body.notify and body.customer_email:
            background.add_task(
                send_cappe_booking_received_email, str(body.customer_email), body.customer_name, site["name"],
                btype["name"], format_when(row["starts_at"], tz), False, booking_manage_url(row["access_token"]),
            )
        return await _booking_view(conn, site_id, row["id"])


@router.put("/sites/{site_id}/bookings/{booking_id}/time", response_model=CappeBooking)
async def reschedule_owner_booking(
    site_id: UUID, booking_id: UUID, body: CappeOwnerReschedule, background: BackgroundTasks,
    account: CappeAccount = Depends(require_cappe_account),
):
    """The owner moves a booking to another time (and, optionally, another
    staff member). Repriced; the customer is emailed. Like an owner booking,
    not held to the customer rules, but it can't double-book."""
    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)
        async with conn.transaction():
            current = await conn.fetchrow(
                "SELECT id, booking_type_id, staff_id, location_id, status, starts_at, customer_email, "
                "customer_name, access_token FROM cappe_bookings WHERE id = $1 AND site_id = $2 FOR UPDATE",
                booking_id, site_id,
            )
            if current is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
            if current["status"] not in ("pending", "confirmed"):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                    detail=f"A {current['status']} booking can't be moved.")
            if current["booking_type_id"] is None:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                    detail="Its service was deleted, so it can't be repriced for a new time.")
            btype = await _owner_btype(conn, site_id, current["booking_type_id"])
            staff_id = body.staff_id if "staff_id" in body.model_fields_set else current["staff_id"]
            tz = await _owner_where(conn, site, site_id, staff_id, current["location_id"])
            slot = await resolve_booking_slot(
                conn, site, btype, body.starts_at, body.ends_at, exclude_booking_id=booking_id,
                staff_id=staff_id, location_id=current["location_id"], tz=tz, owner=True,
            )
            try:
                await conn.execute(
                    "UPDATE cappe_bookings SET starts_at = $2, ends_at = $3, quoted_price_cents = $4, "
                    "staff_id = $5, reminder_sent_at = NULL, updated_at = NOW() WHERE id = $1",
                    booking_id, slot["s_utc"], slot["e_utc"], slot["quote_cents"], staff_id,
                )
            except Exception as exc:
                if "idx_cappe_bookings_no_doublebook" in str(exc):
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That slot is taken")
                raise
        if body.notify and current["customer_email"]:
            background.add_task(
                send_cappe_booking_rescheduled_email, current["customer_email"], current["customer_name"],
                site["name"], btype["name"], format_when(current["starts_at"], tz), format_when(slot["s_utc"], tz),
                for_owner=False, needs_approval=False, link=booking_manage_url(current["access_token"]),
            )
        return await _booking_view(conn, site_id, booking_id)


_TIME_OFF_VIEW = """
    SELECT t.id, t.staff_id, t.location_id, t.starts_at, t.ends_at, t.reason, t.created_at,
           st.name AS staff_name, loc.name AS location_name
      FROM cappe_time_off t
      LEFT JOIN cappe_staff st ON st.id = t.staff_id
      LEFT JOIN cappe_locations loc ON loc.id = t.location_id
"""


@router.get("/sites/{site_id}/time-off", response_model=list[CappeTimeOff])
async def list_time_off(
    site_id: UUID, include_past: bool = Query(False),
    account: CappeAccount = Depends(require_cappe_account),
):
    """Closed periods, soonest first (past ones only when asked)."""
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        rows = await conn.fetch(
            f"{_TIME_OFF_VIEW} WHERE t.site_id = $1 AND ($2 OR t.ends_at > NOW()) ORDER BY t.starts_at LIMIT 500",
            site_id, include_past,
        )
    return [dict(r) for r in rows]


@router.post("/sites/{site_id}/time-off", response_model=CappeTimeOff, status_code=status.HTTP_201_CREATED)
async def add_time_off(
    site_id: UUID, body: CappeTimeOffInput, account: CappeAccount = Depends(require_cappe_account),
):
    """Close a period — the whole business, one location or one staff member.
    Bookings already in it are left alone (the owner decides what to do
    with them); new ones can't be made in it."""
    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)
        tz = await _owner_where(conn, site, site_id, body.staff_id, body.location_id)
        # Times without a zone mean the store's (or the location's) local time.
        starts, ends = _anchor_local(body.starts_at, tz), _anchor_local(body.ends_at, tz)
        new_id = await conn.fetchval(
            "INSERT INTO cappe_time_off (site_id, staff_id, location_id, starts_at, ends_at, reason) "
            "VALUES ($1, $2, $3, $4, $5, $6) RETURNING id",
            site_id, body.staff_id, body.location_id, starts, ends,
            (body.reason or "").strip() or None,
        )
        row = await conn.fetchrow(f"{_TIME_OFF_VIEW} WHERE t.id = $1", new_id)
    return dict(row)


@router.delete("/sites/{site_id}/time-off/{time_off_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_time_off(
    site_id: UUID, time_off_id: UUID, account: CappeAccount = Depends(require_cappe_account),
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        deleted = await conn.fetchval(
            "DELETE FROM cappe_time_off WHERE id = $1 AND site_id = $2 RETURNING id", time_off_id, site_id,
        )
    if deleted is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Time off not found")


# --- Approval queue ---------------------------------------------------------

async def _booking_when(conn, site, row) -> str:
    """The booking's start in ITS timezone — the location's, else the site's.
    Approval emails used the site's, so a location in another zone told its
    customers the wrong hour."""
    tz = site["timezone"]
    if row["location_id"] is not None:
        tz = await conn.fetchval(
            "SELECT timezone FROM cappe_locations WHERE id = $1", row["location_id"],
        ) or tz
    return format_when(row["starts_at"], tz)


async def _notify_booking_decision(conn, background, site, row, *, approved, reason=None):
    """Email the customer that their pending booking was approved/declined."""
    email = row["customer_email"]
    if not email:
        return
    type_name = await conn.fetchval(
        "SELECT name FROM cappe_booking_types WHERE id = $1", row["booking_type_id"]
    )
    background.add_task(
        send_cappe_booking_decision_email, email, row["customer_name"], site["name"],
        approved, await _booking_when(conn, site, row), type_name or "Booking", reason,
    )


async def _notify_host_cancelled(conn, background, site, row):
    """Email the customer that the business cancelled their booking."""
    type_name = await conn.fetchval(
        "SELECT name FROM cappe_booking_types WHERE id = $1", row["booking_type_id"]
    )
    background.add_task(
        send_cappe_booking_cancelled_by_host_email, row["customer_email"], row["customer_name"],
        site["name"], type_name or "Booking", await _booking_when(conn, site, row),
    )


@router.post("/sites/{site_id}/bookings/{booking_id}/accept", response_model=CappeBooking)
async def accept_booking(
    site_id: UUID, booking_id: UUID, background: BackgroundTasks,
    account: CappeAccount = Depends(require_cappe_account),
):
    """Creator approves a pending (awaiting-approval) booking → confirmed."""
    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)
        row = await conn.fetchrow(
            f"""UPDATE cappe_bookings
                SET status = 'confirmed', approved_at = NOW(), updated_at = NOW()
                WHERE id = $1 AND site_id = $2 AND status = 'pending'
                RETURNING {_BOOKING_COLS}""",
            booking_id, site_id,
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No pending booking to accept")
        await _notify_booking_decision(conn, background, site, row, approved=True)
        view = await _booking_view(conn, site_id, booking_id)
    return view


@router.post("/sites/{site_id}/bookings/{booking_id}/decline", response_model=CappeBooking)
async def decline_booking(
    site_id: UUID, booking_id: UUID, body: CappeApprovalDecline, background: BackgroundTasks,
    account: CappeAccount = Depends(require_cappe_account),
):
    """Creator declines a pending booking → declined (frees the slot)."""
    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)
        row = await conn.fetchrow(
            f"""UPDATE cappe_bookings
                SET status = 'declined', decline_reason = $3, updated_at = NOW()
                WHERE id = $1 AND site_id = $2 AND status = 'pending'
                RETURNING {_BOOKING_COLS}""",
            booking_id, site_id, body.reason,
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No pending booking to decline")
        await _notify_booking_decision(conn, background, site, row, approved=False, reason=body.reason)
        view = await _booking_view(conn, site_id, booking_id)
    return view


@router.get("/sites/{site_id}/requests", response_model=list[CappeRequestSummary])
async def list_requests(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    """Unified accept/decline queue: bookings needing approval (pending +
    requires_approval) and orders needing approval (pending + requires_approval),
    newest first."""
    async with get_connection() as conn:
        currency = site_currency(await get_owned_site(conn, site_id, account.id))
        booking_rows = await conn.fetch(
            """SELECT b.id, b.customer_name, b.customer_email, b.starts_at, b.note,
                      b.quoted_price_cents, b.rider_acknowledged, b.created_at,
                      bt.name AS type_name
               FROM cappe_bookings b
               LEFT JOIN cappe_booking_types bt ON bt.id = b.booking_type_id
               WHERE b.site_id = $1 AND b.status = 'pending' AND b.requires_approval = true
               ORDER BY b.created_at DESC""",
            site_id,
        )
        order_rows = await conn.fetch(
            """SELECT id, customer_name, customer_email, subtotal_cents, currency, note, created_at
               FROM cappe_orders
               WHERE site_id = $1 AND status = 'pending' AND requires_approval = true
               ORDER BY created_at DESC""",
            site_id,
        )
    out: list[dict] = []
    for r in booking_rows:
        out.append({
            "kind": "booking", "id": r["id"], "customer_name": r["customer_name"],
            "customer_email": r["customer_email"], "title": r["type_name"] or "Booking",
            "amount_cents": r["quoted_price_cents"], "currency": currency,
            "starts_at": r["starts_at"], "note": r["note"],
            "rider_acknowledged": r["rider_acknowledged"], "created_at": r["created_at"],
        })
    for r in order_rows:
        out.append({
            "kind": "order", "id": r["id"], "customer_name": r["customer_name"],
            "customer_email": r["customer_email"], "title": "Order",
            "amount_cents": r["subtotal_cents"], "currency": r["currency"],
            "starts_at": None, "note": r["note"], "rider_acknowledged": None,
            "created_at": r["created_at"],
        })
    out.sort(key=lambda x: x["created_at"], reverse=True)
    return out


# --- Rate rules (dynamic time pricing) --------------------------------------

@router.get("/sites/{site_id}/rate-rules", response_model=list[CappeRateRule])
async def list_rate_rules(
    site_id: UUID, location_id: Optional[UUID] = Query(None), shared: bool = Query(False),
    account: CappeAccount = Depends(require_cappe_account),
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        args: list = [site_id]
        clause = _loc_filter(location_id, shared, args)
        rows = await conn.fetch(
            f"SELECT {_RULE_COLS} FROM cappe_rate_rules WHERE site_id = $1{clause} "
            "ORDER BY weekday NULLS FIRST, start_time",
            *args,
        )
    return [dict(r) for r in rows]


@router.put("/sites/{site_id}/rate-rules", response_model=list[CappeRateRule])
async def replace_rate_rules(
    site_id: UUID, body: CappeRateRulesReplace,
    location_id: Optional[UUID] = Query(None),
    account: CappeAccount = Depends(require_cappe_account),
):
    """Replace the rate-rule set FOR ONE LOCATION (None = shared) — other
    locations untouched (mirrors availability)."""
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        await _validate_location(conn, site_id, location_id)
        type_ids = {r.booking_type_id for r in body.rules if r.booking_type_id}
        if type_ids:
            valid = await conn.fetchval(
                "SELECT COUNT(*) FROM cappe_booking_types WHERE site_id = $1 AND id = ANY($2::uuid[])",
                site_id, list(type_ids),
            )
            if valid != len(type_ids):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown booking type")
        async with conn.transaction():
            await conn.execute(
                "DELETE FROM cappe_rate_rules WHERE site_id = $1 AND location_id IS NOT DISTINCT FROM $2",
                site_id, location_id,
            )
            for r in body.rules:
                if r.end_time <= r.start_time:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Rule end_time must be after start_time",
                    )
                await conn.execute(
                    """INSERT INTO cappe_rate_rules
                           (site_id, booking_type_id, label, weekday, start_time, end_time, multiplier, location_id)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
                    site_id, r.booking_type_id, r.label, r.weekday, r.start_time, r.end_time, r.multiplier, location_id,
                )
            rows = await conn.fetch(
                f"SELECT {_RULE_COLS} FROM cappe_rate_rules "
                "WHERE site_id = $1 AND location_id IS NOT DISTINCT FROM $2 "
                "ORDER BY weekday NULLS FIRST, start_time",
                site_id, location_id,
            )
    return [dict(r) for r in rows]
