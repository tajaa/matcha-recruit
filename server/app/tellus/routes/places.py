"""Tell-Us public places — search any place, add an unclaimed one, review it.

Unclaimed place = tellus_brands row with owner_account_id NULL (source
'consumer_added') + one store + one always-on link whose token feeds the
existing /i/{token} intake flow. Unauthenticated; mirrors public_intake.py
hygiene (rate limits + honeypot accept-and-drop).

Invariant: every unclaimed brand has an active community link — see
ensure_community_link() below. Any code path that produces or exposes an
unclaimed brand must call it (currently: this file's own dedupe branch, and
routes/admin/brands.py:unassign_owner).
"""
import secrets
from typing import Optional

import asyncpg
from fastapi import APIRouter, HTTPException, Query, Request, status

from ...core.services.redis_cache import cache_get, cache_set, check_rate_limit, client_ip, get_redis_cache
from ...database import get_connection
from ..models.tellus import (
    TellusPlaceAutocompleteResult,
    TellusPlaceCreate,
    TellusPlaceCreateResponse,
    TellusPlaceSearchResult,
)
from ..services import google_places
from ._shared import escape_like, slugify

router = APIRouter()


async def ensure_community_link(
    conn, brand_id, *, store_id=None, actor_ip: Optional[str] = None,
    detail: str = "community link ensure",
) -> str:
    """Return an active intake token for the brand, minting the always-on
    'Community feedback' link (+ tellus_link_history row, actor NULL — same
    shape as create_place's own mint) if none is active.

    This is where the "every unclaimed brand is reviewable" invariant lives —
    call it from any path that creates, exposes, or un-claims a brand without
    guaranteeing it already has a link. Caller owns the transaction.
    """
    token = await conn.fetchval(
        "SELECT token FROM tellus_links WHERE brand_id = $1 AND is_active "
        "ORDER BY created_at LIMIT 1",
        brand_id,
    )
    if token:
        return token
    if store_id is None:
        store_id = await conn.fetchval(
            "SELECT id FROM tellus_stores WHERE brand_id = $1 ORDER BY created_at LIMIT 1",
            brand_id,
        )
    token = secrets.token_urlsafe(12)
    link_id = await conn.fetchval(
        "INSERT INTO tellus_links (brand_id, store_id, token, label) "
        "VALUES ($1, $2, $3, 'Community feedback') RETURNING id",
        brand_id, store_id, token,
    )
    await conn.execute(
        "INSERT INTO tellus_link_history (link_id, action, actor_account_id, actor_ip, detail) "
        "VALUES ($1, 'created', NULL, $2, $3)",
        link_id, actor_ip, detail,
    )
    return token


@router.get("/places/search", response_model=list[TellusPlaceSearchResult])
async def search_places(
    request: Request,
    q: str = Query(min_length=1, max_length=120),
    city: Optional[str] = Query(default=None, max_length=120),
):
    await check_rate_limit(client_ip(request), "tellus_place_search", 60, 3600)
    q = q.strip()
    if not q:
        return []
    city_filter = (city or "").strip() or None
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
                                   WHERE brand_id = b.id
                                   ORDER BY ($2::text IS NOT NULL AND city ILIKE '%' || $2 || '%') DESC,
                                            created_at
                                   LIMIT 1) s ON TRUE
               LEFT JOIN LATERAL (SELECT token FROM tellus_links
                                   WHERE brand_id = b.id AND is_active
                                   ORDER BY created_at LIMIT 1) lk ON TRUE
               WHERE b.name ILIKE '%' || $1 || '%'
                 AND ($2::text IS NULL OR EXISTS
                      (SELECT 1 FROM tellus_stores st
                        WHERE st.brand_id = b.id AND st.city ILIKE '%' || $2 || '%'))
               ORDER BY review_count DESC, b.name
               LIMIT 20""",
            escape_like(q), escape_like(city_filter) if city_filter else None,
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


@router.get("/places/autocomplete", response_model=list[TellusPlaceAutocompleteResult])
async def autocomplete_places(
    request: Request,
    q: str = Query(min_length=2, max_length=120),
    city: Optional[str] = Query(default=None, max_length=120),
):
    """Server-proxied Google Places autocomplete for the add-a-place form.
    Returns [] when GOOGLE_MAPS_API_KEY is unset — the frontend silently
    falls back to manual entry, never an error state."""
    ip = client_ip(request)
    await check_rate_limit(ip, "tellus_place_ac_min", 10, 60)
    await check_rate_limit(ip, "tellus_place_ac_hr", 60, 3600)

    q = q.strip()
    city_norm = (city or "").strip()
    if not q:
        return []

    cache_key = f"tellus:place_ac:{q.lower()}|{city_norm.lower()}"
    redis = get_redis_cache()
    if redis:
        cached = await cache_get(redis, cache_key)
        if cached is not None:
            return cached

    results = await google_places.autocomplete(q, city_norm or None)
    if redis:
        await cache_set(redis, cache_key, results, ttl=300)
    return results


@router.post("/places", response_model=TellusPlaceCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_place(body: TellusPlaceCreate, request: Request):
    ip = client_ip(request)
    await check_rate_limit(ip, "tellus_place_create_burst", 3, 60)
    await check_rate_limit(ip, "tellus_place_create", 5, 3600)

    if body.website:  # honeypot — synthetic success, no write
        return TellusPlaceCreateResponse(slug="place", name=body.name.strip(), intake_token=None)

    # Resolve Google details server-side — NEVER trust client-sent name/city
    # for a place_id submission (TellusPlaceCreate.google_place_id docstring).
    # Failure (Google down, bad id) falls back to the submitted free-text
    # below; the place still gets created, just without a place_id.
    details = None
    if body.google_place_id:
        details = await google_places.place_details(body.google_place_id)

    name = ((details or {}).get("name") or body.name).strip()
    city = ((details or {}).get("city") or body.city or "").strip()
    state = ((details or {}).get("state") or body.state) or None
    address = (details or {}).get("address")
    lat = (details or {}).get("lat")
    lng = (details or {}).get("lng")

    if not name or not city:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                            detail="Name and city are required.")

    async with get_connection() as conn:
        async with conn.transaction():
            # Dedupe pass 1: exact Google place. Only meaningful when the
            # lookup above actually resolved (a bad/stale id behaves like no
            # id — falls through to the name+city path like manual entry).
            if details:
                by_place_id = await conn.fetchrow(
                    "SELECT id, slug, name, owner_account_id FROM tellus_brands WHERE google_place_id = $1",
                    body.google_place_id,
                )
                if by_place_id is not None:
                    claimed = by_place_id["owner_account_id"] is not None
                    token = None
                    if not claimed:
                        token = await ensure_community_link(
                            conn, by_place_id["id"], actor_ip=ip, detail="dedupe re-mint (place_id)",
                        )
                    return TellusPlaceCreateResponse(
                        slug=by_place_id["slug"], name=by_place_id["name"],
                        claimed=claimed, intake_token=token, existing=True,
                    )

            # Serialize concurrent creates of the same (name, city): the dedup
            # SELECT and the INSERTs below must be atomic, or duplicate places
            # are the normal outcome under concurrency. The lock releases at
            # commit; a loser then sees the winner's committed row in the SELECT.
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(lower($1) || '|' || lower($2), 0))",
                name, city,
            )

            # Dedupe pass 2: same name + same city (or a store-less brand with
            # the name) — the pre-existing, place_id-agnostic path.
            existing = await conn.fetchrow(
                """SELECT b.id, b.slug, b.name, b.owner_account_id, b.google_place_id
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
                    token = await ensure_community_link(
                        conn, existing["id"], actor_ip=ip, detail="dedupe re-mint",
                    )
                # Backfill a resolved place_id onto this legacy (pre-Google)
                # match — best-effort, skipped if that place_id already
                # belongs to a different brand (partial unique index).
                if body.google_place_id and existing["google_place_id"] is None:
                    try:
                        async with conn.transaction():
                            await conn.execute(
                                "UPDATE tellus_brands SET google_place_id = $1 WHERE id = $2",
                                body.google_place_id, existing["id"],
                            )
                    except asyncpg.UniqueViolationError as e:
                        if e.constraint_name != "ux_tellus_brands_google_place_id":
                            raise
                return TellusPlaceCreateResponse(
                    slug=existing["slug"], name=existing["name"],
                    claimed=claimed, intake_token=token, existing=True,
                )

            # Consumer-added places NEVER take the canonical slug — that's
            # reserved for the real brand's own signup (routes/auth.py), so a
            # squatter can't permanently own /b/<canonical> for a brand they
            # don't run.
            slug = f"{slugify(name)}-{secrets.token_hex(3)}"
            brand_id = None
            for attempt in range(2):
                try:
                    # SAVEPOINT so a constraint hit only rolls back this insert.
                    async with conn.transaction():
                        brand_id = await conn.fetchval(
                            "INSERT INTO tellus_brands "
                            "(owner_account_id, name, slug, location_count, source, google_place_id) "
                            "VALUES (NULL, $1, $2, 1, 'consumer_added', $3) RETURNING id",
                            name, slug, body.google_place_id,
                        )
                    break
                except asyncpg.UniqueViolationError as e:
                    if e.constraint_name == "ux_tellus_brands_slug" and attempt == 0:
                        # Astronomically rare hex collision — regenerate once.
                        slug = f"{slugify(name)}-{secrets.token_hex(3)}"
                        continue
                    if e.constraint_name == "ux_tellus_brands_google_place_id":
                        # Race: a concurrent request just inserted this exact
                        # place between our dedupe SELECT and this INSERT.
                        row = await conn.fetchrow(
                            "SELECT id, slug, name, owner_account_id FROM tellus_brands "
                            "WHERE google_place_id = $1", body.google_place_id,
                        )
                        claimed = row["owner_account_id"] is not None
                        token = None
                        if not claimed:
                            token = await ensure_community_link(
                                conn, row["id"], actor_ip=ip, detail="race re-mint (place_id)",
                            )
                        return TellusPlaceCreateResponse(
                            slug=row["slug"], name=row["name"], claimed=claimed,
                            intake_token=token, existing=True,
                        )
                    raise
            if brand_id is None:
                raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                                    "Could not create this place — please try again.")

            # lat/lng: from Google details when we have them; otherwise
            # deliberately NULL (city+state can never match the Census
            # street-address geocoder — the old call here was a guaranteed-
            # NULL 15s network hit in the request path).
            store_id = await conn.fetchval(
                "INSERT INTO tellus_stores (brand_id, name, city, state, address, lat, lng, google_place_id) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING id",
                brand_id, name, city, state, address, lat, lng, body.google_place_id,
            )
            token = await ensure_community_link(
                conn, brand_id, store_id=store_id, actor_ip=ip, detail="consumer_added place",
            )

    return TellusPlaceCreateResponse(slug=slug, name=name, intake_token=token)
