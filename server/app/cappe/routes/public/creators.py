"""Public creator directory + profile pages. Anonymous; published profiles only.
Flagged socials are hidden everywhere public."""
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request, status

from ....core.services.redis_cache import check_rate_limit, client_ip
from ....database import get_connection
from ...models.creators import PublicCreatorCard, PublicCreatorPage, PublicCreatorProfile
from ...services.common import loads

router = APIRouter()
_MAX_LIMIT = 24


async def _rate(request: Request) -> None:
    await check_rate_limit(client_ip(request), "cappe_pub_creators", 30, 60)


@router.get("/public/creators", response_model=PublicCreatorPage)
async def list_public_creators(
    request: Request,
    niche: Optional[str] = None,
    platform: Optional[str] = None,
    min_followers: Optional[int] = Query(default=None, ge=0),
    max_rate_cents: Optional[int] = Query(default=None, ge=0),
    location: Optional[str] = None,
    q: Optional[str] = None,
    verified_only: bool = False,
    limit: int = Query(12, ge=1, le=_MAX_LIMIT),
    offset: int = Query(0, ge=0, le=500),
):
    await _rate(request)
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            WITH base AS (
                SELECT p.id, p.handle, p.display_name, p.avatar_url, p.cover_url, p.bio,
                       p.location, p.niches, p.reach_verified,
                       COALESCE((SELECT MAX(COALESCE(s.verified_follower_count, s.follower_count))
                                   FROM cappe_creator_socials s
                                  WHERE s.profile_id = p.id AND s.audit_status != 'flagged'), 0) AS max_followers,
                       (SELECT MIN(r.price_cents) FROM cappe_creator_rate_cards r
                         WHERE r.profile_id = p.id) AS min_rate_cents,
                       ARRAY(SELECT DISTINCT s.platform FROM cappe_creator_socials s
                              WHERE s.profile_id = p.id AND s.audit_status != 'flagged') AS platforms
                  FROM cappe_creator_profiles p
                 WHERE p.status = 'published' AND p.open_to_offers = true
                   AND ($1::text IS NULL OR $1 = ANY(p.niches))
                   AND ($2::text IS NULL OR EXISTS (SELECT 1 FROM cappe_creator_socials s2
                            WHERE s2.profile_id = p.id AND s2.platform = $2 AND s2.audit_status != 'flagged'))
                   AND ($3::text IS NULL OR p.location ILIKE '%' || $3 || '%')
                   AND ($4::text IS NULL OR p.display_name ILIKE '%' || $4 || '%'
                        OR p.handle ILIKE '%' || $4 || '%' OR p.bio ILIKE '%' || $4 || '%')
                   AND ($5::bool = false OR p.reach_verified = true)
            )
            SELECT *, COUNT(*) OVER() AS total FROM base
             WHERE ($6::int IS NULL OR max_followers >= $6)
               AND ($7::int IS NULL OR (min_rate_cents IS NOT NULL AND min_rate_cents <= $7))
             ORDER BY reach_verified DESC, max_followers DESC, handle
             LIMIT $8 OFFSET $9
            """,
            niche, platform, location, q, verified_only,
            min_followers, max_rate_cents, limit, offset,
        )
        total = rows[0]["total"] if rows else 0
        cards = []
        for r in rows:
            d = dict(r)
            bio = d.get("bio") or ""
            d["bio"] = bio[:200]
            d.pop("id", None)
            d.pop("total", None)
            cards.append(PublicCreatorCard(**d))
        return PublicCreatorPage(creators=cards, total=total)


@router.get("/public/creators/{handle}", response_model=PublicCreatorProfile)
async def get_public_creator(handle: str, request: Request):
    await _rate(request)
    handle = handle.lstrip("@").lower()
    async with get_connection() as conn:
        prof = await conn.fetchrow(
            "SELECT id, handle, display_name, avatar_url, cover_url, bio, location, niches, "
            "languages, open_to_offers, reach_verified, reach_audited_at "
            "FROM cappe_creator_profiles WHERE lower(handle) = $1 AND status = 'published'",
            handle,
        )
        if prof is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Creator not found")

        social_rows = await conn.fetch(
            "SELECT id, platform, handle, url, follower_count, engagement_rate, audit_status, "
            "verified_follower_count, audited_at, sort_order FROM cappe_creator_socials "
            "WHERE profile_id = $1 AND audit_status != 'flagged' ORDER BY sort_order, created_at",
            prof["id"],
        )
        portfolio_rows = await conn.fetch(
            "SELECT id, title, description, media_url, media_type, external_url, brand_name, "
            "metrics, sort_order, created_at FROM cappe_creator_portfolio_items "
            "WHERE profile_id = $1 ORDER BY sort_order, created_at",
            prof["id"],
        )
        rate_rows = await conn.fetch(
            "SELECT id, deliverable_type, platform, price_cents, negotiable, notes, sort_order "
            "FROM cappe_creator_rate_cards WHERE profile_id = $1 ORDER BY sort_order, created_at",
            prof["id"],
        )
        d = dict(prof)
        d["socials"] = [dict(r) for r in social_rows]
        d["portfolio"] = [{**dict(r), "metrics": loads(r["metrics"]) or {}} for r in portfolio_rows]
        d["rates"] = [dict(r) for r in rate_rows]
        return PublicCreatorProfile(**d)
