"""Tell-Us brand management — brand profile, stores, and QR/feedback links.

All endpoints require a brand account; everything scopes by the caller's
`brand_id` (never a client-supplied one). Links are the per-store QR tokens that
drive the public intake flow.
"""
import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ...core.services.redis_cache import client_ip
from ...database import get_connection
from ..dependencies import require_brand
from ..models.tellus import (
    TellusAccount,
    TellusBrand,
    TellusBrandUpdate,
    TellusLink,
    TellusLinkCreate,
    TellusStore,
    TellusStoreCreate,
    TellusStoreUpdate,
)
from ..services.geo import geocode_location
from ._shared import get_owned_store

router = APIRouter()


def _new_link_token() -> str:
    return secrets.token_urlsafe(12)


# ── Brand profile ─────────────────────────────────────────────────────────────

@router.get("/brand", response_model=TellusBrand)
async def get_brand(account: TellusAccount = Depends(require_brand)):
    async with get_connection() as conn:
        row = await conn.fetchrow("SELECT * FROM tellus_brands WHERE id = $1", account.brand_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found")
    return TellusBrand(**dict(row))


@router.patch("/brand", response_model=TellusBrand)
async def update_brand(body: TellusBrandUpdate, account: TellusAccount = Depends(require_brand)):
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """UPDATE tellus_brands
               SET name = COALESCE($2, name), logo_url = COALESCE($3, logo_url),
                   reward_mode = COALESCE($4, reward_mode), updated_at = NOW()
               WHERE id = $1 RETURNING *""",
            account.brand_id, body.name, body.logo_url, body.reward_mode,
        )
    return TellusBrand(**dict(row))


# ── Stores ────────────────────────────────────────────────────────────────────

@router.get("/stores", response_model=list[TellusStore])
async def list_stores(account: TellusAccount = Depends(require_brand)):
    async with get_connection() as conn:
        rows = await conn.fetch(
            "SELECT * FROM tellus_stores WHERE brand_id = $1 ORDER BY created_at", account.brand_id
        )
    return [TellusStore(**dict(r)) for r in rows]


@router.post("/stores", response_model=TellusStore, status_code=status.HTTP_201_CREATED)
async def create_store(body: TellusStoreCreate, account: TellusAccount = Depends(require_brand)):
    geo = None
    if body.city or body.address:
        geo = await geocode_location(body.city or "", body.state, body.zipcode, body.address)
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """INSERT INTO tellus_stores (brand_id, name, address, city, state, zipcode, lat, lng)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING *""",
            account.brand_id, body.name, body.address, body.city, body.state, body.zipcode,
            geo["lat"] if geo else None, geo["lng"] if geo else None,
        )
    return TellusStore(**dict(row))


@router.patch("/stores/{store_id}", response_model=TellusStore)
async def update_store(
    store_id: UUID, body: TellusStoreUpdate, account: TellusAccount = Depends(require_brand)
):
    async with get_connection() as conn:
        await get_owned_store(conn, store_id, account.brand_id)
        row = await conn.fetchrow(
            """UPDATE tellus_stores
               SET name = COALESCE($3, name), address = COALESCE($4, address),
                   city = COALESCE($5, city), state = COALESCE($6, state),
                   zipcode = COALESCE($7, zipcode), updated_at = NOW()
               WHERE id = $1 AND brand_id = $2 RETURNING *""",
            store_id, account.brand_id, body.name, body.address, body.city, body.state, body.zipcode,
        )
    return TellusStore(**dict(row))


@router.delete("/stores/{store_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_store(store_id: UUID, account: TellusAccount = Depends(require_brand)):
    async with get_connection() as conn:
        await get_owned_store(conn, store_id, account.brand_id)
        await conn.execute("DELETE FROM tellus_stores WHERE id = $1 AND brand_id = $2", store_id, account.brand_id)


# ── Links (QR) ────────────────────────────────────────────────────────────────

def _serialize_link(row) -> TellusLink:
    return TellusLink(
        id=row["id"], brand_id=row["brand_id"], store_id=row["store_id"], token=row["token"],
        label=row["label"], is_active=row["is_active"], use_count=row["use_count"],
        max_uses=row["max_uses"], expires_at=row["expires_at"], revoked_at=row["revoked_at"],
        created_at=row["created_at"],
        store_name=row["store_name"] if "store_name" in row.keys() else None,
    )


@router.get("/links", response_model=list[TellusLink])
async def list_links(account: TellusAccount = Depends(require_brand)):
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT l.*, s.name AS store_name
               FROM tellus_links l LEFT JOIN tellus_stores s ON s.id = l.store_id
               WHERE l.brand_id = $1 ORDER BY l.created_at DESC""",
            account.brand_id,
        )
    return [_serialize_link(r) for r in rows]


@router.post("/links", response_model=TellusLink, status_code=status.HTTP_201_CREATED)
async def create_link(
    body: TellusLinkCreate, request: Request, account: TellusAccount = Depends(require_brand)
):
    async with get_connection() as conn:
        if body.store_id is not None:
            await get_owned_store(conn, body.store_id, account.brand_id)
        async with conn.transaction():
            row = await conn.fetchrow(
                """INSERT INTO tellus_links (brand_id, store_id, token, label, max_uses, expires_at)
                   VALUES ($1, $2, $3, $4, $5, $6) RETURNING *""",
                account.brand_id, body.store_id, _new_link_token(), body.label, body.max_uses, body.expires_at,
            )
            await conn.execute(
                """INSERT INTO tellus_link_history (link_id, action, actor_account_id, actor_ip, detail)
                   VALUES ($1, 'created', $2, $3, $4)""",
                row["id"], account.id, client_ip(request), body.label,
            )
        store_name = None
        if row["store_id"] is not None:
            store_name = await conn.fetchval("SELECT name FROM tellus_stores WHERE id = $1", row["store_id"])
    link = _serialize_link(row)
    link.store_name = store_name
    return link


@router.post("/links/{link_id}/revoke", response_model=TellusLink)
async def revoke_link(
    link_id: UUID, request: Request, account: TellusAccount = Depends(require_brand)
):
    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """UPDATE tellus_links SET is_active = FALSE, revoked_at = NOW()
                   WHERE id = $1 AND brand_id = $2 RETURNING *""",
                link_id, account.brand_id,
            )
            if row is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link not found")
            await conn.execute(
                """INSERT INTO tellus_link_history (link_id, action, actor_account_id, actor_ip)
                   VALUES ($1, 'revoked', $2, $3)""",
                link_id, account.id, client_ip(request),
            )
    return _serialize_link(row)
