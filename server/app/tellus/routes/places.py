"""Tell-Us public places — search any place, add an unclaimed one, review it.

Unclaimed place = tellus_brands row with owner_account_id NULL (source
'consumer_added') + one store + one always-on link whose token feeds the
existing /i/{token} intake flow. Unauthenticated; mirrors public_intake.py
hygiene (rate limits + honeypot accept-and-drop).
"""
import secrets
from typing import Optional

import asyncpg
from fastapi import APIRouter, Query, Request, status

from ...core.services.redis_cache import check_rate_limit, client_ip
from ...database import get_connection
from ..models.tellus import TellusPlaceCreate, TellusPlaceCreateResponse, TellusPlaceSearchResult
from ..services.geo import geocode_location
from ._shared import slugify

router = APIRouter()


@router.get("/places/search", response_model=list[TellusPlaceSearchResult])
async def search_places(
    request: Request,
    q: str = Query(min_length=1, max_length=120),
    city: Optional[str] = Query(default=None, max_length=120),
):
    await check_rate_limit(client_ip(request), "tellus_place_search", 60, 3600)
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT b.slug, b.name, b.logo_url, b.owner_account_id,
                      s.city, s.state,
                      (SELECT COUNT(*) FROM tellus_reports r
                        WHERE r.brand_id = b.id AND r.review_state = 'held'
                          AND r.publish_at <= NOW() AND r.moderation_status = 'visible') AS review_count,
                      CASE WHEN b.owner_account_id IS NULL THEN lk.token END AS intake_token
               FROM tellus_brands b
               LEFT JOIN LATERAL (SELECT city, state FROM tellus_stores
                                   WHERE brand_id = b.id ORDER BY created_at LIMIT 1) s ON TRUE
               LEFT JOIN LATERAL (SELECT token FROM tellus_links
                                   WHERE brand_id = b.id AND is_active
                                   ORDER BY created_at LIMIT 1) lk ON TRUE
               WHERE b.name ILIKE '%' || $1 || '%'
                 AND ($2::text IS NULL OR EXISTS
                      (SELECT 1 FROM tellus_stores st
                        WHERE st.brand_id = b.id AND st.city ILIKE '%' || $2 || '%'))
               ORDER BY review_count DESC, b.name
               LIMIT 20""",
            q.strip(), (city or "").strip() or None,
        )
    return [
        TellusPlaceSearchResult(
            slug=r["slug"], name=r["name"], logo_url=r["logo_url"],
            city=r["city"], state=r["state"],
            claimed=r["owner_account_id"] is not None,
            intake_token=r["intake_token"], review_count=r["review_count"],
        )
        for r in rows
    ]


@router.post("/places", response_model=TellusPlaceCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_place(body: TellusPlaceCreate, request: Request):
    ip = client_ip(request)
    await check_rate_limit(ip, "tellus_place_create_burst", 3, 60)
    await check_rate_limit(ip, "tellus_place_create", 5, 3600)

    if body.website:  # honeypot — synthetic success, no write
        return TellusPlaceCreateResponse(slug="place", name=body.name.strip(), intake_token=None)

    name = body.name.strip()
    city = body.city.strip()

    async with get_connection() as conn:
        # Dedup: same name + same city (or a store-less brand with the name).
        existing = await conn.fetchrow(
            """SELECT b.id, b.slug, b.name, b.owner_account_id
               FROM tellus_brands b
               WHERE lower(b.name) = lower($1)
                 AND (EXISTS (SELECT 1 FROM tellus_stores s
                               WHERE s.brand_id = b.id AND lower(s.city) = lower($2))
                      OR NOT EXISTS (SELECT 1 FROM tellus_stores s WHERE s.brand_id = b.id))
               ORDER BY b.created_at LIMIT 1""",
            name, city,
        )
        if existing is not None:
            claimed = existing["owner_account_id"] is not None
            token = None
            if not claimed:
                token = await conn.fetchval(
                    "SELECT token FROM tellus_links WHERE brand_id = $1 AND is_active "
                    "ORDER BY created_at LIMIT 1", existing["id"],
                )
            return TellusPlaceCreateResponse(
                slug=existing["slug"], name=existing["name"],
                claimed=claimed, intake_token=token, existing=True,
            )

    # Geocode before opening the write transaction — it's a network call (up to
    # 15s) and must not hold a pool connection + open transaction idle while it runs.
    geo = await geocode_location(city, body.state, None, None)

    async with get_connection() as conn:
        async with conn.transaction():
            slug = slugify(name)
            try:
                # SAVEPOINT so a slug collision only rolls back this insert (auth.py pattern).
                async with conn.transaction():
                    brand_id = await conn.fetchval(
                        "INSERT INTO tellus_brands (owner_account_id, name, slug, location_count, source) "
                        "VALUES (NULL, $1, $2, 1, 'consumer_added') RETURNING id",
                        name, slug,
                    )
            except asyncpg.UniqueViolationError as e:
                if e.constraint_name != "ux_tellus_brands_slug":
                    raise
                slug = f"{slug}-{secrets.token_hex(3)}"
                brand_id = await conn.fetchval(
                    "INSERT INTO tellus_brands (owner_account_id, name, slug, location_count, source) "
                    "VALUES (NULL, $1, $2, 1, 'consumer_added') RETURNING id",
                    name, slug,
                )

            store_id = await conn.fetchval(
                "INSERT INTO tellus_stores (brand_id, name, city, state, lat, lng) "
                "VALUES ($1, $2, $3, $4, $5, $6) RETURNING id",
                brand_id, name, city, body.state,
                geo["lat"] if geo else None, geo["lng"] if geo else None,
            )
            token = secrets.token_urlsafe(12)
            link_id = await conn.fetchval(
                "INSERT INTO tellus_links (brand_id, store_id, token, label) "
                "VALUES ($1, $2, $3, 'Community feedback') RETURNING id",
                brand_id, store_id, token,
            )
            await conn.execute(
                "INSERT INTO tellus_link_history (link_id, action, actor_account_id, actor_ip, detail) "
                "VALUES ($1, 'created', NULL, $2, 'consumer_added place')",
                link_id, ip,
            )

    return TellusPlaceCreateResponse(slug=slug, name=name, intake_token=token)
