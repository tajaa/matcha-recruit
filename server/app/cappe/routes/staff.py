"""Cappe staff / stylists — owner CRUD.

Staff are the people a salon books appointments with. Which staff perform which
service is set per booking type (the `staff_ids` replace-set on the booking-type
routes in bookings.py). Public booking reads active staff via public.py.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import CappeAccount, CappeStaff, CappeStaffCreate, CappeStaffUpdate
from ._shared import get_owned_site

router = APIRouter()

_STAFF_COLS = "id, site_id, name, bio, image_url, active, sort_order, created_at, updated_at"


@router.get("/sites/{site_id}/staff", response_model=list[CappeStaff])
async def list_staff(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        rows = await conn.fetch(
            f"SELECT {_STAFF_COLS} FROM cappe_staff WHERE site_id = $1 ORDER BY sort_order, created_at",
            site_id,
        )
    return [dict(r) for r in rows]


@router.post("/sites/{site_id}/staff", response_model=CappeStaff, status_code=status.HTTP_201_CREATED)
async def create_staff(
    site_id: UUID, body: CappeStaffCreate, account: CappeAccount = Depends(require_cappe_account)
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        row = await conn.fetchrow(
            f"""INSERT INTO cappe_staff (site_id, name, bio, image_url, active, sort_order)
                VALUES ($1, $2, $3, $4, $5, $6) RETURNING {_STAFF_COLS}""",
            site_id, body.name, body.bio, body.image_url, body.active, body.sort_order,
        )
    return dict(row)


@router.put("/sites/{site_id}/staff/{staff_id}", response_model=CappeStaff)
async def update_staff(
    site_id: UUID, staff_id: UUID, body: CappeStaffUpdate,
    account: CappeAccount = Depends(require_cappe_account),
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        sets, args = [], []
        for col in ("name", "bio", "image_url", "active", "sort_order"):
            val = getattr(body, col)
            if val is not None:
                args.append(val)
                sets.append(f"{col} = ${len(args)}")
        if not sets:
            row = await conn.fetchrow(
                f"SELECT {_STAFF_COLS} FROM cappe_staff WHERE id = $1 AND site_id = $2", staff_id, site_id
            )
            if row is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staff not found")
            return dict(row)
        sets.append("updated_at = NOW()")
        args.extend([staff_id, site_id])
        row = await conn.fetchrow(
            f"UPDATE cappe_staff SET {', '.join(sets)} "
            f"WHERE id = ${len(args) - 1} AND site_id = ${len(args)} RETURNING {_STAFF_COLS}",
            *args,
        )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staff not found")
    return dict(row)


@router.delete("/sites/{site_id}/staff/{staff_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_staff(
    site_id: UUID, staff_id: UUID, account: CappeAccount = Depends(require_cappe_account)
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        result = await conn.execute(
            "DELETE FROM cappe_staff WHERE id = $1 AND site_id = $2", staff_id, site_id
        )
    if result.endswith(" 0"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Staff not found")
