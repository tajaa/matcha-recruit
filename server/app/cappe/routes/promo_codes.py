"""Cappe promo codes — the owner's side (create, edit, switch off, delete).

The buyer's side is the bag: `/quote` and order creation take `promo_code`
(services/promos.py). Plan feature `promo_codes`; listing works on any plan
so a downgraded store can still see and remove its codes.

Deleting a code keeps the orders that used it as they were (they carry the
code and the amount it took off).
"""
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status

from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import CappeAccount, CappePromoCode, CappePromoCodeInput, CappePromoCodes
from ..services.entitlements import resolve_entitlements
from ..services.promos import PROMO_COLS
from ..services.shipping import site_currency
from ._shared import get_owned_site

router = APIRouter()

MAX_CODES = 200

_FIELDS = (
    "code", "kind", "percent_off", "amount_off_cents", "min_subtotal_cents", "starts_on",
    "ends_on", "max_redemptions", "once_per_customer", "active",
)


async def _require_plan(conn, account) -> None:
    if not (await resolve_entitlements(account.plan, conn=conn)).has("promo_codes"):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Promo codes aren't included in your plan.",
        )


def _taken(code: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"You already have a code called {code}.")


@router.get("/sites/{site_id}/promo-codes", response_model=CappePromoCodes)
async def list_promo_codes(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)
        rows = await conn.fetch(
            f"SELECT {PROMO_COLS} FROM cappe_promo_codes WHERE site_id = $1 ORDER BY created_at DESC",
            site_id,
        )
        ent = await resolve_entitlements(account.plan, conn=conn)
    return {"enabled": ent.has("promo_codes"), "currency": site_currency(site), "codes": [dict(r) for r in rows]}


@router.post("/sites/{site_id}/promo-codes", response_model=CappePromoCode, status_code=status.HTTP_201_CREATED)
async def create_promo_code(
    site_id: UUID, body: CappePromoCodeInput, account: CappeAccount = Depends(require_cappe_account),
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        await _require_plan(conn, account)
        if await conn.fetchval("SELECT COUNT(*) FROM cappe_promo_codes WHERE site_id = $1", site_id) >= MAX_CODES:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"A store can have at most {MAX_CODES} codes.")
        values = [getattr(body, f) for f in _FIELDS]
        try:
            row = await conn.fetchrow(
                f"""INSERT INTO cappe_promo_codes (site_id, {', '.join(_FIELDS)})
                    VALUES ($1, {', '.join(f'${i + 2}' for i in range(len(_FIELDS)))})
                    RETURNING {PROMO_COLS}""",
                site_id, *values,
            )
        except asyncpg.UniqueViolationError:
            raise _taken(body.code)
    return dict(row)


@router.put("/sites/{site_id}/promo-codes/{code_id}", response_model=CappePromoCode)
async def update_promo_code(
    site_id: UUID, code_id: UUID, body: CappePromoCodeInput,
    account: CappeAccount = Depends(require_cappe_account),
):
    """Replace a code's settings. Its use count is kept."""
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        await _require_plan(conn, account)
        sets = ", ".join(f"{f} = ${i + 3}" for i, f in enumerate(_FIELDS))
        try:
            row = await conn.fetchrow(
                f"""UPDATE cappe_promo_codes SET {sets}, updated_at = NOW()
                     WHERE id = $1 AND site_id = $2 RETURNING {PROMO_COLS}""",
                code_id, site_id, *[getattr(body, f) for f in _FIELDS],
            )
        except asyncpg.UniqueViolationError:
            raise _taken(body.code)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Code not found")
    return dict(row)


@router.delete("/sites/{site_id}/promo-codes/{code_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_promo_code(site_id: UUID, code_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        deleted = await conn.fetchval(
            "DELETE FROM cappe_promo_codes WHERE id = $1 AND site_id = $2 RETURNING id", code_id, site_id,
        )
    if deleted is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Code not found")
