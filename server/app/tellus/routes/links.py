"""Tell-Us brand management — brand profile, stores, and QR/feedback links.

All endpoints require a brand account; everything scopes by the caller's
`brand_id` (never a client-supplied one). Links are the per-store QR tokens that
drive the public intake flow.
"""
import secrets
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status

from ...core.services.redis_cache import client_ip
from ...core.services.storage import get_storage
from ...database import get_connection
from ..dependencies import require_brand, require_paid_brand
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
from ._shared import delete_managed_object, get_owned_store, is_managed_object

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
async def update_brand(body: TellusBrandUpdate, account: TellusAccount = Depends(require_paid_brand)):
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """UPDATE tellus_brands
               SET name = COALESCE($2, name), reward_mode = COALESCE($3, reward_mode), updated_at = NOW()
               WHERE id = $1 RETURNING *""",
            account.brand_id, body.name, body.reward_mode,
        )
    return TellusBrand(**dict(row))


_LOGO_MAX_BYTES = 2 * 1024 * 1024
_LOGO_TYPES = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
_LOGO_PREFIX = "/tellus/logos/"


@router.post("/brand/logo", response_model=TellusBrand)
async def upload_brand_logo(
    file: UploadFile = File(...),
    account: TellusAccount = Depends(require_paid_brand),
):
    """Multipart logo upload -> public S3 via CloudFront (storage.upload_file),
    replacing the old free-text logo_url. Public bucket on purpose: the URL is
    rendered on the unauthenticated /b/{slug} page, so a presigned-GET (private
    bucket, 15-min expiry like report media) would rot."""
    ext = _LOGO_TYPES.get(file.content_type or "")
    if ext is None:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            detail="Logo must be a PNG, JPEG, or WebP image.")
    data = await file.read()
    if len(data) > _LOGO_MAX_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail="Logo must be 2MB or smaller.")

    storage = get_storage()
    if not (storage.s3_client and storage.bucket):
        # Mirror public_intake.presign_media's unconfigured-storage behavior.
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Image uploads are not configured.")
    url = await storage.upload_file(
        data, f"logo.{ext}", prefix=f"tellus/logos/{account.brand_id}",
        content_type=file.content_type,
    )

    async with get_connection() as conn:
        old = await conn.fetchval("SELECT logo_url FROM tellus_brands WHERE id = $1", account.brand_id)
        row = await conn.fetchrow(
            "UPDATE tellus_brands SET logo_url = $2, updated_at = NOW() WHERE id = $1 RETURNING *",
            account.brand_id, url,
        )
    if old and old != url and is_managed_object(old, _LOGO_PREFIX):
        await delete_managed_object(old)
    return TellusBrand(**dict(row))


@router.delete("/brand/logo", response_model=TellusBrand)
async def delete_brand_logo(account: TellusAccount = Depends(require_paid_brand)):
    async with get_connection() as conn:
        old = await conn.fetchval("SELECT logo_url FROM tellus_brands WHERE id = $1", account.brand_id)
        row = await conn.fetchrow(
            "UPDATE tellus_brands SET logo_url = NULL, updated_at = NOW() WHERE id = $1 RETURNING *",
            account.brand_id,
        )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found")
    if is_managed_object(old, _LOGO_PREFIX):
        await delete_managed_object(old)
    return TellusBrand(**dict(row))


# ── Stores ────────────────────────────────────────────────────────────────────

@router.get("/stores", response_model=list[TellusStore])
async def list_stores(account: TellusAccount = Depends(require_paid_brand)):
    async with get_connection() as conn:
        rows = await conn.fetch(
            "SELECT * FROM tellus_stores WHERE brand_id = $1 ORDER BY created_at", account.brand_id
        )
    return [TellusStore(**dict(r)) for r in rows]


@router.post("/stores", response_model=TellusStore, status_code=status.HTTP_201_CREATED)
async def create_store(body: TellusStoreCreate, account: TellusAccount = Depends(require_paid_brand)):
    geo = None
    if body.city or body.address:
        geo = await geocode_location(body.city or "", body.state, body.zipcode, body.address)
    async with get_connection() as conn:
        async with conn.transaction():
            # Lock the brand row so two concurrent creates can't both pass
            # the cap check before either insert commits.
            location_count = await conn.fetchval(
                "SELECT location_count FROM tellus_brands WHERE id = $1 FOR UPDATE", account.brand_id
            )
            store_count = await conn.fetchval(
                "SELECT count(*) FROM tellus_stores WHERE brand_id = $1", account.brand_id
            )
            if store_count >= location_count:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Store limit reached ({store_count}/{location_count}). "
                        "Update your plan in Billing to add more stores."
                    ),
                )
            row = await conn.fetchrow(
                """INSERT INTO tellus_stores (brand_id, name, address, city, state, zipcode, lat, lng)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING *""",
                account.brand_id, body.name, body.address, body.city, body.state, body.zipcode,
                geo["lat"] if geo else None, geo["lng"] if geo else None,
            )
    return TellusStore(**dict(row))


@router.patch("/stores/{store_id}", response_model=TellusStore)
async def update_store(
    store_id: UUID, body: TellusStoreUpdate, account: TellusAccount = Depends(require_paid_brand)
):
    # Ownership check + geocode happen on their own short connections — the
    # geocode is an outbound Census HTTP call (up to ~15s) and must never sit
    # inside a held pool connection (create_store follows the same shape).
    async with get_connection() as conn:
        existing = await get_owned_store(conn, store_id, account.brand_id)

    # Re-geocode whenever the address-bearing fields change — the old
    # UPDATE left lat/lng untouched, so editing an address kept stale
    # coordinates that Discover (TELLUS_DISCOVER_PLAN.md) ranks on.
    # Geocode the MERGED result, not just the patched fields, since a
    # zipcode-only edit still needs the existing city/state to resolve.
    address_changed = any(
        getattr(body, f) is not None for f in ("address", "city", "state", "zipcode")
    )
    geo = None
    # Distinct from `geo is not None` below: True whenever the address
    # changed and was resolvable at all, so a changed-but-unresolvable
    # address NULLs lat/lng instead of keeping the OLD address's coordinates
    # (Discover would otherwise rank the store at a place it no longer is).
    should_write_coords = False
    if address_changed:
        new_city = body.city if body.city is not None else existing["city"]
        new_state = body.state if body.state is not None else existing["state"]
        new_zipcode = body.zipcode if body.zipcode is not None else existing["zipcode"]
        new_address = body.address if body.address is not None else existing["address"]
        if new_city or new_address:
            should_write_coords = True
            geo = await geocode_location(new_city or "", new_state, new_zipcode, new_address)

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """UPDATE tellus_stores
               SET name = COALESCE($3, name), address = COALESCE($4, address),
                   city = COALESCE($5, city), state = COALESCE($6, state),
                   zipcode = COALESCE($7, zipcode),
                   lat = CASE WHEN $8 THEN $9 ELSE lat END,
                   lng = CASE WHEN $8 THEN $10 ELSE lng END,
                   updated_at = NOW()
               WHERE id = $1 AND brand_id = $2 RETURNING *""",
            store_id, account.brand_id, body.name, body.address, body.city, body.state, body.zipcode,
            should_write_coords, geo["lat"] if geo else None, geo["lng"] if geo else None,
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Store not found")
    return TellusStore(**dict(row))


@router.delete("/stores/{store_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_store(store_id: UUID, account: TellusAccount = Depends(require_paid_brand)):
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
async def list_links(account: TellusAccount = Depends(require_paid_brand)):
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
    body: TellusLinkCreate, request: Request, account: TellusAccount = Depends(require_paid_brand)
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
    link_id: UUID, request: Request, account: TellusAccount = Depends(require_paid_brand)
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
