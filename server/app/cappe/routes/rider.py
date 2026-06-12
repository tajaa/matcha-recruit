"""Cappe rider — standard requirements a Pro creator attaches to bookings.

A "rider" is the set of conditions a solo professional needs met to take a job
(a consistent point of contact, water/snacks on site, shade cover, travel
covered, …). Buyers see it on the booking request and acknowledge it; the
booking snapshots what was agreed.

Gating: only **Pro-plan personal (creator)** accounts can define a rider — it's
a creator concept, not a business one. Reads are open to the owner; the public
renderer surfaces the rider through the published-site payload.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import (
    CappeAccount,
    CappeRiderItem,
    CappeRiderReplace,
)
from ._shared import get_owned_site

router = APIRouter()

_RIDER_COLS = "id, site_id, label, detail, is_required, sort_order, created_at"


def _require_rider_capable(account: CappeAccount) -> None:
    """Rider editing is a Pro creator (personal) capability."""
    if account.account_type != "personal":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A rider is a creator feature — switch to a personal account to use it.",
        )
    if account.plan != "pro":
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Riders are a Pro feature. Upgrade to set your booking requirements.",
        )


@router.get("/sites/{site_id}/rider", response_model=list[CappeRiderItem])
async def list_rider(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    """The owner's rider items (any plan can read; only Pro creators can edit)."""
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        rows = await conn.fetch(
            f"SELECT {_RIDER_COLS} FROM cappe_rider_items WHERE site_id = $1 "
            "ORDER BY sort_order, created_at",
            site_id,
        )
    return [dict(r) for r in rows]


@router.put("/sites/{site_id}/rider", response_model=list[CappeRiderItem])
async def replace_rider(
    site_id: UUID, body: CappeRiderReplace, account: CappeAccount = Depends(require_cappe_account)
):
    """Replace the whole rider in one transaction."""
    _require_rider_capable(account)
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        async with conn.transaction():
            await conn.execute("DELETE FROM cappe_rider_items WHERE site_id = $1", site_id)
            for i, item in enumerate(body.items):
                await conn.execute(
                    """INSERT INTO cappe_rider_items (site_id, label, detail, is_required, sort_order)
                       VALUES ($1, $2, $3, $4, $5)""",
                    site_id, item.label, item.detail, item.is_required,
                    item.sort_order if item.sort_order else i,
                )
            rows = await conn.fetch(
                f"SELECT {_RIDER_COLS} FROM cappe_rider_items WHERE site_id = $1 "
                "ORDER BY sort_order, created_at",
                site_id,
            )
    return [dict(r) for r in rows]
