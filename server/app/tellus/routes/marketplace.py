"""Tell-Us city marketplace — consumer browse + redeem, brand listing mgmt.

Consumers see their city's active listings plus platform-curated rewards, and
redeem for points (atomic, via points_service). Brands create/manage listings
and verify redemptions at the counter.
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status

from ...database import get_connection
from ..dependencies import require_brand, require_consumer
from ..models.tellus import (
    TellusAccount,
    TellusListing,
    TellusListingCreate,
    TellusListingUpdate,
    TellusRedeemRequest,
    TellusRedemption,
    TellusRedemptionStatusUpdate,
)
from ..services.email import send_tellus_redemption_email
from ..services.marketplace_service import list_marketplace, serialize_listing, serialize_redemption
from ..services.points_service import RedeemError, redeem_points

router = APIRouter()


# ── Consumer: browse + redeem ───────────────────────────────────────────────────

@router.get("/marketplace", response_model=list[TellusListing])
async def browse_marketplace(
    account: TellusAccount = Depends(require_consumer),
    city: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
):
    """Active listings for a city (defaults to the consumer's saved city) plus
    platform-curated rewards available everywhere."""
    use_city = city or account.city
    use_state = state or account.state
    async with get_connection() as conn:
        return await list_marketplace(conn, use_city, use_state)


@router.post("/redeem", response_model=TellusRedemption, status_code=status.HTTP_201_CREATED)
async def redeem(
    body: TellusRedeemRequest, background: BackgroundTasks,
    account: TellusAccount = Depends(require_consumer),
):
    async with get_connection() as conn:
        try:
            redemption = await redeem_points(conn, account.id, body.listing_id)
        except RedeemError as e:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
        listing_title = await conn.fetchval(
            "SELECT title FROM tellus_reward_listings WHERE id = $1", body.listing_id
        )

    background.add_task(
        send_tellus_redemption_email, account.email, account.display_name,
        listing_title or "your reward", redemption.get("code"),
    )
    redemption["listing_title"] = listing_title
    return serialize_redemption(redemption)


# ── Brand: listing management ───────────────────────────────────────────────────

@router.get("/listings", response_model=list[TellusListing])
async def list_listings(account: TellusAccount = Depends(require_brand)):
    async with get_connection() as conn:
        rows = await conn.fetch(
            "SELECT l.*, b.name AS brand_name FROM tellus_reward_listings l "
            "LEFT JOIN tellus_brands b ON b.id = l.brand_id "
            "WHERE l.brand_id = $1 ORDER BY l.created_at DESC",
            account.brand_id,
        )
    return [serialize_listing(r) for r in rows]


@router.post("/listings", response_model=TellusListing, status_code=status.HTTP_201_CREATED)
async def create_listing(body: TellusListingCreate, account: TellusAccount = Depends(require_brand)):
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """INSERT INTO tellus_reward_listings
                   (brand_id, city, state, title, description, image_url, points_cost,
                    quantity_total, redemption_type, terms, active_from, active_to, is_active)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
               RETURNING *""",
            account.brand_id, body.city, body.state, body.title, body.description, body.image_url,
            body.points_cost, body.quantity_total, body.redemption_type, body.terms,
            body.active_from, body.active_to, body.is_active,
        )
    return serialize_listing(row)


@router.patch("/listings/{listing_id}", response_model=TellusListing)
async def update_listing(
    listing_id: UUID, body: TellusListingUpdate, account: TellusAccount = Depends(require_brand)
):
    async with get_connection() as conn:
        owned = await conn.fetchval(
            "SELECT 1 FROM tellus_reward_listings WHERE id = $1 AND brand_id = $2",
            listing_id, account.brand_id,
        )
        if not owned:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found")
        row = await conn.fetchrow(
            """UPDATE tellus_reward_listings SET
                   title = COALESCE($3, title), description = COALESCE($4, description),
                   image_url = COALESCE($5, image_url), points_cost = COALESCE($6, points_cost),
                   quantity_total = COALESCE($7, quantity_total),
                   redemption_type = COALESCE($8, redemption_type), terms = COALESCE($9, terms),
                   city = COALESCE($10, city), state = COALESCE($11, state),
                   active_from = COALESCE($12, active_from), active_to = COALESCE($13, active_to),
                   is_active = COALESCE($14, is_active), updated_at = NOW()
               WHERE id = $1 AND brand_id = $2 RETURNING *""",
            listing_id, account.brand_id, body.title, body.description, body.image_url,
            body.points_cost, body.quantity_total, body.redemption_type, body.terms,
            body.city, body.state, body.active_from, body.active_to, body.is_active,
        )
    return serialize_listing(row)


@router.delete("/listings/{listing_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_listing(listing_id: UUID, account: TellusAccount = Depends(require_brand)):
    """Soft-delete: deactivate so outstanding redemptions keep resolving."""
    async with get_connection() as conn:
        res = await conn.execute(
            "UPDATE tellus_reward_listings SET is_active = FALSE, updated_at = NOW() "
            "WHERE id = $1 AND brand_id = $2",
            listing_id, account.brand_id,
        )
    if res.endswith("0"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found")


# ── Brand: redemption verification ──────────────────────────────────────────────

@router.get("/listings/{listing_id}/redemptions", response_model=list[TellusRedemption])
async def listing_redemptions(listing_id: UUID, account: TellusAccount = Depends(require_brand)):
    async with get_connection() as conn:
        owned = await conn.fetchval(
            "SELECT 1 FROM tellus_reward_listings WHERE id = $1 AND brand_id = $2",
            listing_id, account.brand_id,
        )
        if not owned:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found")
        rows = await conn.fetch(
            "SELECT r.*, l.title AS listing_title FROM tellus_redemptions r "
            "JOIN tellus_reward_listings l ON l.id = r.listing_id "
            "WHERE r.listing_id = $1 ORDER BY r.created_at DESC",
            listing_id,
        )
    return [serialize_redemption(r) for r in rows]


@router.patch("/redemptions/{redemption_id}", response_model=TellusRedemption)
async def verify_redemption(
    redemption_id: UUID, body: TellusRedemptionStatusUpdate, account: TellusAccount = Depends(require_brand)
):
    """Brand marks a redemption redeemed (claimed at the counter) / cancelled /
    expired. Scoped to a listing this brand owns."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """UPDATE tellus_redemptions r SET
                   status = $3,
                   redeemed_at = CASE WHEN $3 = 'redeemed' THEN NOW() ELSE redeemed_at END
               FROM tellus_reward_listings l
               WHERE r.id = $1 AND r.listing_id = l.id AND l.brand_id = $2
               RETURNING r.*, l.title AS listing_title""",
            redemption_id, account.brand_id, body.status,
        )
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Redemption not found")
    return serialize_redemption(row)
