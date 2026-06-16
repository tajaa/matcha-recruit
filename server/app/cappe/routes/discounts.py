"""Cappe discounts — creator-set promotional discounts (replace-all CRUD).

Mirrors the availability / rate-rules pattern: the whole set is replaced in one
transaction. Discounts are applied authoritatively at quote/order time in
public.py (see services/discounts.py).
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import (
    CappeAccount,
    CappeDiscount,
    CappeDiscountReplace,
)
from ._shared import get_owned_site

router = APIRouter()

_DISCOUNT_COLS = (
    "id, site_id, label, percent_off, scope, target_id, active, "
    "starts_on, ends_on, location_id, created_at"
)


@router.get("/sites/{site_id}/discounts", response_model=list[CappeDiscount])
async def list_discounts(
    site_id: UUID, location_id: Optional[UUID] = Query(None), shared: bool = Query(False),
    account: CappeAccount = Depends(require_cappe_account),
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        args: list = [site_id]
        clause = ""
        if shared:
            clause = " AND location_id IS NULL"
        elif location_id is not None:
            args.append(location_id)
            clause = f" AND (location_id IS NULL OR location_id = ${len(args)})"
        rows = await conn.fetch(
            f"SELECT {_DISCOUNT_COLS} FROM cappe_discounts WHERE site_id = $1{clause} ORDER BY created_at",
            *args,
        )
    return [dict(r) for r in rows]


@router.put("/sites/{site_id}/discounts", response_model=list[CappeDiscount])
async def replace_discounts(
    site_id: UUID, body: CappeDiscountReplace,
    location_id: Optional[UUID] = Query(None),
    account: CappeAccount = Depends(require_cappe_account),
):
    """Replace the discount set FOR ONE LOCATION (None = shared) — others untouched."""
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        if location_id is not None and not await conn.fetchval(
            "SELECT 1 FROM cappe_locations WHERE id = $1 AND site_id = $2", location_id, site_id
        ):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown location")

        # A scoped discount must name a target that belongs to this site.
        bt_ids = {d.target_id for d in body.discounts if d.scope == "booking_type" and d.target_id}
        prod_ids = {d.target_id for d in body.discounts if d.scope == "product" and d.target_id}
        for d in body.discounts:
            if d.scope != "all" and d.target_id is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A scoped discount must target a booking type or product.",
                )
            if d.starts_on and d.ends_on and d.ends_on < d.starts_on:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Discount end date must be on or after the start date.",
                )
        if bt_ids:
            valid = await conn.fetchval(
                "SELECT COUNT(*) FROM cappe_booking_types WHERE site_id = $1 AND id = ANY($2::uuid[])",
                site_id, list(bt_ids),
            )
            if valid != len(bt_ids):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown booking type")
        if prod_ids:
            valid = await conn.fetchval(
                "SELECT COUNT(*) FROM cappe_products WHERE site_id = $1 AND id = ANY($2::uuid[])",
                site_id, list(prod_ids),
            )
            if valid != len(prod_ids):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown product")

        async with conn.transaction():
            await conn.execute(
                "DELETE FROM cappe_discounts WHERE site_id = $1 AND location_id IS NOT DISTINCT FROM $2",
                site_id, location_id,
            )
            for d in body.discounts:
                await conn.execute(
                    """INSERT INTO cappe_discounts
                           (site_id, label, percent_off, scope, target_id, active, starts_on, ends_on, location_id)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
                    site_id, d.label, d.percent_off, d.scope,
                    d.target_id if d.scope != "all" else None,
                    d.active, d.starts_on, d.ends_on, location_id,
                )
            rows = await conn.fetch(
                f"SELECT {_DISCOUNT_COLS} FROM cappe_discounts "
                "WHERE site_id = $1 AND location_id IS NOT DISTINCT FROM $2 ORDER BY created_at",
                site_id, location_id,
            )
    return [dict(r) for r in rows]
