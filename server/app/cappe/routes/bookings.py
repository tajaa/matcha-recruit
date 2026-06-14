"""Cappe bookings — booking types, weekly availability, booking management.

Public booking intake (with availability-window + overlap validation) lives in
public.py.
"""
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from ...database import get_connection
from ..dependencies import require_cappe_account
from ..services.email import format_when, send_cappe_booking_decision_email
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
    CappeRateRule,
    CappeRateRulesReplace,
    CappeRequestSummary,
)
from ._shared import get_owned_site, loads_list

router = APIRouter()

_TYPE_COLS = (
    "id, site_id, name, description, duration_minutes, price_cents, status, "
    "requires_approval, pricing_mode, category, buffer_minutes, created_at, updated_at"
)
_AVAIL_COLS = "id, weekday, start_time, end_time, booking_type_id, staff_id"


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
_RULE_COLS = "id, site_id, booking_type_id, label, weekday, start_time, end_time, multiplier, created_at"
_BOOKING_COLS = (
    "id, site_id, booking_type_id, staff_id, customer_name, customer_email, starts_at, "
    "ends_at, status, note, requires_approval, quoted_price_cents, approved_at, "
    "decline_reason, rider_acknowledged, rider_snapshot, created_at"
)


# `b.`-qualified column list for joins against cappe_staff (id/site_id/created_at
# are ambiguous otherwise).
_BOOKING_COLS_Q = ", ".join("b." + c.strip() for c in _BOOKING_COLS.split(","))


def _booking_row(r) -> dict:
    d = dict(r)
    # rider_snapshot is a JSON ARRAY — use the list normalizer (loads() coerces to
    # a dict, which fails CappeBooking validation and 500s the bookings list).
    d["rider_snapshot"] = loads_list(d.get("rider_snapshot"))
    return d


# --- Booking types ----------------------------------------------------------

@router.get("/sites/{site_id}/booking-types", response_model=list[CappeBookingType])
async def list_booking_types(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        rows = await conn.fetch(
            f"SELECT {_TYPE_COLS} FROM cappe_booking_types WHERE site_id = $1 ORDER BY created_at",
            site_id,
        )
        staff = await _staff_ids_for_types(conn, [r["id"] for r in rows])
    return [{**dict(r), "staff_ids": staff.get(r["id"], [])} for r in rows]


@router.post("/sites/{site_id}/booking-types", response_model=CappeBookingType, status_code=status.HTTP_201_CREATED)
async def create_booking_type(
    site_id: UUID, body: CappeBookingTypeCreate, account: CappeAccount = Depends(require_cappe_account)
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        async with conn.transaction():
            row = await conn.fetchrow(
                f"""INSERT INTO cappe_booking_types
                        (site_id, name, description, duration_minutes, price_cents, status,
                         requires_approval, pricing_mode, category, buffer_minutes)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10) RETURNING {_TYPE_COLS}""",
                site_id, body.name, body.description, body.duration_minutes, body.price_cents, body.status,
                body.requires_approval, body.pricing_mode, body.category, body.buffer_minutes,
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
        async with conn.transaction():
            sets, args = [], []
            for col in ("name", "description", "duration_minutes", "price_cents", "status",
                        "requires_approval", "pricing_mode", "category", "buffer_minutes"):
                val = getattr(body, col)
                if val is not None:
                    args.append(val)
                    sets.append(f"{col} = ${len(args)}")
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
async def get_availability(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        rows = await conn.fetch(
            f"SELECT {_AVAIL_COLS} FROM cappe_availability WHERE site_id = $1 ORDER BY weekday, start_time",
            site_id,
        )
    return [dict(r) for r in rows]


@router.put("/sites/{site_id}/availability", response_model=list[CappeAvailability])
async def replace_availability(
    site_id: UUID, body: CappeAvailabilityReplace, account: CappeAccount = Depends(require_cappe_account)
):
    """Replace the entire weekly availability set in one transaction."""
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
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
            await conn.execute("DELETE FROM cappe_availability WHERE site_id = $1", site_id)
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
                    """INSERT INTO cappe_availability (site_id, weekday, start_time, end_time, booking_type_id, staff_id)
                       VALUES ($1, $2, $3, $4, $5, $6)""",
                    site_id, s.weekday, s.start_time, s.end_time, s.booking_type_id, s.staff_id,
                )
            rows = await conn.fetch(
                f"SELECT {_AVAIL_COLS} FROM cappe_availability WHERE site_id = $1 ORDER BY weekday, start_time",
                site_id,
            )
    return [dict(r) for r in rows]


# --- Bookings ---------------------------------------------------------------

@router.get("/sites/{site_id}/bookings", response_model=list[CappeBooking])
async def list_bookings(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        rows = await conn.fetch(
            f"""SELECT {_BOOKING_COLS_Q}, st.name AS staff_name
                FROM cappe_bookings b LEFT JOIN cappe_staff st ON st.id = b.staff_id
                WHERE b.site_id = $1 ORDER BY b.starts_at DESC""",
            site_id,
        )
    return [_booking_row(r) for r in rows]


@router.patch("/sites/{site_id}/bookings/{booking_id}", response_model=CappeBooking)
async def update_booking_status(
    site_id: UUID, booking_id: UUID, body: CappeBookingStatusUpdate,
    account: CappeAccount = Depends(require_cappe_account),
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        row = await conn.fetchrow(
            f"""UPDATE cappe_bookings SET status = $1, updated_at = NOW()
                WHERE id = $2 AND site_id = $3 RETURNING {_BOOKING_COLS}""",
            body.status, booking_id, site_id,
        )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    return _booking_row(row)


# --- Approval queue ---------------------------------------------------------

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
        approved, format_when(row["starts_at"], site["timezone"]), type_name or "Booking", reason,
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
    return _booking_row(row)


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
    return _booking_row(row)


@router.get("/sites/{site_id}/requests", response_model=list[CappeRequestSummary])
async def list_requests(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    """Unified accept/decline queue: bookings needing approval (pending +
    requires_approval) and orders needing approval (pending + requires_approval),
    newest first."""
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        currency = "USD"
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
async def list_rate_rules(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        rows = await conn.fetch(
            f"SELECT {_RULE_COLS} FROM cappe_rate_rules WHERE site_id = $1 "
            "ORDER BY weekday NULLS FIRST, start_time",
            site_id,
        )
    return [dict(r) for r in rows]


@router.put("/sites/{site_id}/rate-rules", response_model=list[CappeRateRule])
async def replace_rate_rules(
    site_id: UUID, body: CappeRateRulesReplace, account: CappeAccount = Depends(require_cappe_account)
):
    """Replace the whole rate-rule set in one transaction (mirrors availability)."""
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        type_ids = {r.booking_type_id for r in body.rules if r.booking_type_id}
        if type_ids:
            valid = await conn.fetchval(
                "SELECT COUNT(*) FROM cappe_booking_types WHERE site_id = $1 AND id = ANY($2::uuid[])",
                site_id, list(type_ids),
            )
            if valid != len(type_ids):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown booking type")
        async with conn.transaction():
            await conn.execute("DELETE FROM cappe_rate_rules WHERE site_id = $1", site_id)
            for r in body.rules:
                if r.end_time <= r.start_time:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Rule end_time must be after start_time",
                    )
                await conn.execute(
                    """INSERT INTO cappe_rate_rules
                           (site_id, booking_type_id, label, weekday, start_time, end_time, multiplier)
                       VALUES ($1, $2, $3, $4, $5, $6, $7)""",
                    site_id, r.booking_type_id, r.label, r.weekday, r.start_time, r.end_time, r.multiplier,
                )
            rows = await conn.fetch(
                f"SELECT {_RULE_COLS} FROM cappe_rate_rules WHERE site_id = $1 "
                "ORDER BY weekday NULLS FIRST, start_time",
                site_id,
            )
    return [dict(r) for r in rows]
