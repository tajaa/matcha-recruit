"""Cappe bookings — booking types, weekly availability, booking management.

Public booking intake (with availability-window + overlap validation) lives in
public.py.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import (
    CappeAccount,
    CappeAvailability,
    CappeAvailabilityReplace,
    CappeBooking,
    CappeBookingStatusUpdate,
    CappeBookingType,
    CappeBookingTypeCreate,
    CappeBookingTypeUpdate,
)
from ._shared import get_owned_site

router = APIRouter()

_TYPE_COLS = "id, site_id, name, description, duration_minutes, price_cents, status, created_at, updated_at"
_AVAIL_COLS = "id, weekday, start_time, end_time, booking_type_id"
_BOOKING_COLS = (
    "id, site_id, booking_type_id, customer_name, customer_email, starts_at, "
    "ends_at, status, note, created_at"
)


# --- Booking types ----------------------------------------------------------

@router.get("/sites/{site_id}/booking-types", response_model=list[CappeBookingType])
async def list_booking_types(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        rows = await conn.fetch(
            f"SELECT {_TYPE_COLS} FROM cappe_booking_types WHERE site_id = $1 ORDER BY created_at",
            site_id,
        )
    return [dict(r) for r in rows]


@router.post("/sites/{site_id}/booking-types", response_model=CappeBookingType, status_code=status.HTTP_201_CREATED)
async def create_booking_type(
    site_id: UUID, body: CappeBookingTypeCreate, account: CappeAccount = Depends(require_cappe_account)
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        row = await conn.fetchrow(
            f"""INSERT INTO cappe_booking_types (site_id, name, description, duration_minutes, price_cents, status)
                VALUES ($1, $2, $3, $4, $5, $6) RETURNING {_TYPE_COLS}""",
            site_id, body.name, body.description, body.duration_minutes, body.price_cents, body.status,
        )
    return dict(row)


@router.put("/sites/{site_id}/booking-types/{type_id}", response_model=CappeBookingType)
async def update_booking_type(
    site_id: UUID, type_id: UUID, body: CappeBookingTypeUpdate,
    account: CappeAccount = Depends(require_cappe_account),
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        sets, args = [], []
        for col in ("name", "description", "duration_minutes", "price_cents", "status"):
            val = getattr(body, col)
            if val is not None:
                args.append(val)
                sets.append(f"{col} = ${len(args)}")
        if not sets:
            row = await conn.fetchrow(
                f"SELECT {_TYPE_COLS} FROM cappe_booking_types WHERE id = $1 AND site_id = $2",
                type_id, site_id,
            )
            if row is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking type not found")
            return dict(row)
        sets.append("updated_at = NOW()")
        args.extend([type_id, site_id])
        row = await conn.fetchrow(
            f"UPDATE cappe_booking_types SET {', '.join(sets)} "
            f"WHERE id = ${len(args) - 1} AND site_id = ${len(args)} RETURNING {_TYPE_COLS}",
            *args,
        )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking type not found")
    return dict(row)


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
        async with conn.transaction():
            await conn.execute("DELETE FROM cappe_availability WHERE site_id = $1", site_id)
            for s in body.slots:
                if s.end_time <= s.start_time:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="end_time must be after start_time",
                    )
                await conn.execute(
                    """INSERT INTO cappe_availability (site_id, weekday, start_time, end_time, booking_type_id)
                       VALUES ($1, $2, $3, $4, $5)
                       ON CONFLICT (site_id, weekday, start_time, end_time, booking_type_id) DO NOTHING""",
                    site_id, s.weekday, s.start_time, s.end_time, s.booking_type_id,
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
            f"SELECT {_BOOKING_COLS} FROM cappe_bookings WHERE site_id = $1 ORDER BY starts_at DESC",
            site_id,
        )
    return [dict(r) for r in rows]


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
    return dict(row)
