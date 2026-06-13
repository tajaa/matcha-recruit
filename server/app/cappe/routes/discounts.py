"""Cappe discounts — creator-set promotional discounts (replace-all CRUD).

Mirrors the availability / rate-rules pattern: the whole set is replaced in one
transaction. Discounts are applied authoritatively at quote/order time in
public.py (see services/discounts.py).
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

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
    "starts_on, ends_on, created_at"
)


@router.get("/sites/{site_id}/discounts", response_model=list[CappeDiscount])
async def list_discounts(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        rows = await conn.fetch(
            f"SELECT {_DISCOUNT_COLS} FROM cappe_discounts WHERE site_id = $1 ORDER BY created_at",
            site_id,
        )
    return [dict(r) for r in rows]


@router.put("/sites/{site_id}/discounts", response_model=list[CappeDiscount])
async def replace_discounts(
    site_id: UUID, body: CappeDiscountReplace, account: CappeAccount = Depends(require_cappe_account)
):
    """Replace the whole discount set in one transaction."""
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)

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
            await conn.execute("DELETE FROM cappe_discounts WHERE site_id = $1", site_id)
            for d in body.discounts:
                await conn.execute(
                    """INSERT INTO cappe_discounts
                           (site_id, label, percent_off, scope, target_id, active, starts_on, ends_on)
                       VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
                    site_id, d.label, d.percent_off, d.scope,
                    d.target_id if d.scope != "all" else None,
                    d.active, d.starts_on, d.ends_on,
                )
            rows = await conn.fetch(
                f"SELECT {_DISCOUNT_COLS} FROM cappe_discounts WHERE site_id = $1 ORDER BY created_at",
                site_id,
            )
    return [dict(r) for r in rows]
