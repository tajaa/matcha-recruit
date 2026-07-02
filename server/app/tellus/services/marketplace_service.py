"""Tell-Us marketplace helpers — row → model serialization and city queries."""
from typing import Optional
from uuid import UUID

from ..models.tellus import TellusListing, TellusRedemption


def serialize_listing(row) -> TellusListing:
    total = row["quantity_total"]
    claimed = row["quantity_claimed"]
    remaining = (total - claimed) if total is not None else None
    brand_name = row["brand_name"] if "brand_name" in row.keys() else None
    return TellusListing(
        id=row["id"],
        brand_id=row["brand_id"],
        brand_name=brand_name,
        city=row["city"],
        state=row["state"],
        title=row["title"],
        description=row["description"],
        image_url=row["image_url"],
        points_cost=row["points_cost"],
        quantity_total=total,
        quantity_claimed=claimed,
        quantity_remaining=remaining,
        redemption_type=row["redemption_type"],
        terms=row["terms"],
        active_from=row["active_from"],
        active_to=row["active_to"],
        is_active=row["is_active"],
        created_at=row["created_at"],
    )


def serialize_redemption(row) -> TellusRedemption:
    return TellusRedemption(
        id=row["id"],
        account_id=row["account_id"],
        listing_id=row["listing_id"],
        listing_title=row["listing_title"] if "listing_title" in row.keys() else None,
        points_spent=row["points_spent"],
        status=row["status"],
        code=row["code"],
        issued_at=row["issued_at"],
        redeemed_at=row["redeemed_at"],
        expires_at=row["expires_at"],
        created_at=row["created_at"],
    )


async def list_marketplace(conn, city: Optional[str], state: Optional[str]) -> list[TellusListing]:
    """Active listings for a city (case-insensitive) plus platform-curated
    (brand_id IS NULL, city IS NULL) rewards available everywhere."""
    rows = await conn.fetch(
        """SELECT l.*, b.name AS brand_name
           FROM tellus_reward_listings l
           LEFT JOIN tellus_brands b ON b.id = l.brand_id
           WHERE l.is_active
             AND (l.active_from IS NULL OR NOW() >= l.active_from)
             AND (l.active_to IS NULL OR NOW() <= l.active_to)
             AND (l.quantity_total IS NULL OR l.quantity_claimed < l.quantity_total)
             AND (
                   l.city IS NULL
                   OR ($1::text IS NOT NULL AND lower(l.city) = lower($1)
                       AND ($2::text IS NULL OR l.state IS NULL OR lower(l.state) = lower($2)))
                 )
           ORDER BY (l.city IS NULL), l.points_cost ASC, l.created_at DESC""",
        city, state,
    )
    return [serialize_listing(r) for r in rows]
