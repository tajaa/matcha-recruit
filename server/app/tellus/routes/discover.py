"""Tell-Us Discover — nearby/city browse blending Tell-Us brands with live
Google Places results.

Unauthenticated-friendly (mirrors places.py's optional_consumer_account_id
pattern) so browsing works pre-verification; `followed`/`has_board` are
viewer-scoped when a token is present, false otherwise.

Google fill is display-only and NEVER persisted here — a tellus_brands row
only ever materializes through the existing POST /places when the user acts
on a card. See TELLUS_DISCOVER_PLAN.md at the repo root for the full design,
and server/app/tellus/CLAUDE.md's "Places / reviews on unclaimed businesses"
section for the ToS posture this preserves.
"""
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request, status

from ...core.services.redis_cache import cache_get, cache_set, check_rate_limit, client_ip, get_redis_cache
from ...database import get_connection
from ..dependencies import optional_consumer_account_id
from ..models.tellus import TellusDiscoverEntry, TellusDiscoverPage
from ..services import google_places
from ..services.discover_service import (
    MAX_RADIUS_KM,
    DISTANCE_SQL,
    bbox_predicate,
    dedupe_google,
    discover_cache_key,
    normalize_google_type,
)
from ._shared import escape_like

router = APIRouter()

# Own bucket, tighter than /places/search's 240/hr — a miss here can cost a
# Google Nearby/Text Search call, which is billed per request.
_RATE_LIMIT_CALLS = 30
_RATE_LIMIT_WINDOW_S = 60

# Anti-enumeration depth cap, same idiom as cappe's public directory.
_MAX_DEPTH = 200
_MAX_LIMIT = 24
_GOOGLE_CACHE_TTL_S = 300


def _entry_from_tellus_row(row) -> TellusDiscoverEntry:
    return TellusDiscoverEntry(
        source="tellus",
        name=row["name"],
        slug=row["slug"],
        google_place_id=row["google_place_id"],
        logo_url=row["logo_url"],
        city=row["city"],
        state=row["state"],
        distance_km=round(row["distance_km"], 1) if row["distance_km"] is not None else None,
        rating=float(row["rating"]) if row["rating"] is not None else None,
        review_count=row["review_count"] or 0,
        rating_count=row["rating_count"] or 0,
        claimed=row["owner_account_id"] is not None,
        has_board=row["has_board"],
        followed=row["followed"],
        messaging_enabled=bool(row["owner_account_id"] and row["messaging_enabled"]),
        intake_token=row["intake_token"],
    )


def _entry_from_google_row(row: dict) -> TellusDiscoverEntry:
    return TellusDiscoverEntry(
        source="google",
        name=row["name"],
        google_place_id=row["place_id"],
        address=row.get("address"),
        distance_km=None,
        category_label=normalize_google_type(row.get("primary_type")),
        rating=row.get("rating"),
        review_count=row.get("user_rating_count") or 0,
        rating_count=row.get("user_rating_count") or 0,
        claimed=False,
        has_board=False,
        followed=False,
    )


@router.get("/discover", response_model=TellusDiscoverPage)
async def discover(
    request: Request,
    lat: Optional[float] = Query(default=None, ge=-90, le=90),
    lng: Optional[float] = Query(default=None, ge=-180, le=180),
    radius_km: float = Query(default=15.0, gt=0, le=MAX_RADIUS_KM),
    q: Optional[str] = Query(default=None, max_length=120),
    city: Optional[str] = Query(default=None, max_length=120),
    state: Optional[str] = Query(default=None, max_length=60),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=12, ge=1, le=_MAX_LIMIT),
    authorization: Optional[str] = Header(default=None),
) -> TellusDiscoverPage:
    await check_rate_limit(client_ip(request), "tellus_discover", _RATE_LIMIT_CALLS, _RATE_LIMIT_WINDOW_S)

    # A half-supplied coordinate pair is a client bug; silently ignoring it
    # would return the whole country to someone who asked for "near me".
    if (lat is None) != (lng is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="lat and lng must be provided together",
        )
    has_geo = lat is not None and lng is not None

    if offset >= _MAX_DEPTH:
        return TellusDiscoverPage(entries=[], total=0, next_offset=None)
    limit = min(limit, _MAX_DEPTH - offset)

    viewer_id = await optional_consumer_account_id(authorization)
    query = (q or "").strip()
    city_filter = (city or "").strip() or None
    state_filter = (state or "").strip() or None

    async with get_connection() as conn:
        # City fallback: an authenticated caller who supplied neither coords
        # nor city/state gets scoped to their own account row, same source
        # marketplace.py:45 already reads.
        if not has_geo and not city_filter and viewer_id is not None:
            acct = await conn.fetchrow(
                "SELECT city, state FROM tellus_accounts WHERE id = $1", viewer_id
            )
            if acct:
                city_filter = acct["city"]
                state_filter = acct["state"]

        args: list = []
        where_extra = ""
        if query:
            args.append(escape_like(query))
            where_extra = f"AND b.name ILIKE '%' || ${len(args)} || '%'"

        if has_geo:
            args.append(lat)
            lat_p = f"${len(args)}"
            args.append(lng)
            lng_p = f"${len(args)}"
            args.append(radius_km)
            radius_p = f"${len(args)}"
            args.append(viewer_id)
            viewer_p = f"${len(args)}"

            distance_expr = DISTANCE_SQL.replace("$LAT", lat_p).replace("$LNG", lng_p)
            bbox = bbox_predicate(lat_p, lng_p, radius_p)

            args.append(limit)
            limit_p = f"${len(args)}"
            args.append(offset)
            offset_p = f"${len(args)}"

            sql = f"""
                WITH nearest AS (
                    SELECT DISTINCT ON (st.brand_id)
                           st.brand_id, st.city, st.state, ({distance_expr}) AS distance_km
                      FROM tellus_stores st
                     WHERE {bbox}
                     ORDER BY st.brand_id, distance_km ASC
                )
                SELECT b.slug, b.name, b.logo_url, b.google_place_id, b.messaging_enabled,
                       b.owner_account_id, n.city, n.state, n.distance_km,
                       rev.rating, rev.review_count, rev.rating_count,
                       EXISTS (SELECT 1 FROM tellus_boards bd
                                WHERE bd.brand_id = b.id AND bd.is_active) AS has_board,
                       EXISTS (SELECT 1 FROM tellus_brand_follows f
                                WHERE f.brand_id = b.id AND f.consumer_account_id = {viewer_p}) AS followed,
                       CASE WHEN b.owner_account_id IS NULL THEN lk.token END AS intake_token,
                       (SELECT COUNT(*) FROM (
                            SELECT 1 FROM tellus_brands b2
                              JOIN nearest n2 ON n2.brand_id = b2.id
                             WHERE n2.distance_km <= {radius_p} {where_extra.replace('b.name', 'b2.name')}
                             LIMIT {_MAX_DEPTH}
                       ) capped) AS total_count
                  FROM tellus_brands b
                  JOIN nearest n ON n.brand_id = b.id
                  LEFT JOIN LATERAL (
                      SELECT ROUND(AVG(r.rating)::numeric, 1) AS rating,
                             COUNT(*) AS review_count,
                             COUNT(r.rating) AS rating_count
                        FROM tellus_reports r
                       WHERE r.brand_id = b.id AND r.review_state = 'held'
                         AND r.publish_at <= NOW() AND r.publish_at >= NOW() - interval '12 months'
                         AND r.moderation_status = 'visible'
                  ) rev ON TRUE
                  LEFT JOIN LATERAL (SELECT token FROM tellus_links
                                      WHERE brand_id = b.id AND is_active
                                      ORDER BY created_at LIMIT 1) lk ON TRUE
                 WHERE n.distance_km <= {radius_p} {where_extra}
                 ORDER BY n.distance_km ASC, rev.review_count DESC, b.name
                 LIMIT {limit_p} OFFSET {offset_p}
            """
        else:
            args.append(escape_like(city_filter) if city_filter else None)
            city_p = f"${len(args)}"
            args.append(viewer_id)
            viewer_p = f"${len(args)}"
            args.append(limit)
            limit_p = f"${len(args)}"
            args.append(offset)
            offset_p = f"${len(args)}"

            sql = f"""
                SELECT b.slug, b.name, b.logo_url, b.google_place_id, b.messaging_enabled,
                       b.owner_account_id, n.city, n.state, NULL::float8 AS distance_km,
                       rev.rating, rev.review_count, rev.rating_count,
                       EXISTS (SELECT 1 FROM tellus_boards bd
                                WHERE bd.brand_id = b.id AND bd.is_active) AS has_board,
                       EXISTS (SELECT 1 FROM tellus_brand_follows f
                                WHERE f.brand_id = b.id AND f.consumer_account_id = {viewer_p}) AS followed,
                       CASE WHEN b.owner_account_id IS NULL THEN lk.token END AS intake_token,
                       (SELECT COUNT(*) FROM (
                            SELECT 1 FROM tellus_brands b2
                             WHERE ({city_p}::text IS NULL OR EXISTS
                                    (SELECT 1 FROM tellus_stores st2
                                      WHERE st2.brand_id = b2.id AND st2.city ILIKE '%' || {city_p} || '%'))
                               {where_extra.replace('b.name', 'b2.name')}
                             LIMIT {_MAX_DEPTH}
                       ) capped) AS total_count
                  FROM tellus_brands b
                  LEFT JOIN LATERAL (SELECT city, state FROM tellus_stores
                                      WHERE brand_id = b.id ORDER BY created_at LIMIT 1) n ON TRUE
                  LEFT JOIN LATERAL (
                      SELECT ROUND(AVG(r.rating)::numeric, 1) AS rating,
                             COUNT(*) AS review_count,
                             COUNT(r.rating) AS rating_count
                        FROM tellus_reports r
                       WHERE r.brand_id = b.id AND r.review_state = 'held'
                         AND r.publish_at <= NOW() AND r.publish_at >= NOW() - interval '12 months'
                         AND r.moderation_status = 'visible'
                  ) rev ON TRUE
                  LEFT JOIN LATERAL (SELECT token FROM tellus_links
                                      WHERE brand_id = b.id AND is_active
                                      ORDER BY created_at LIMIT 1) lk ON TRUE
                 WHERE ({city_p}::text IS NULL OR EXISTS
                        (SELECT 1 FROM tellus_stores st
                          WHERE st.brand_id = b.id AND st.city ILIKE '%' || {city_p} || '%'))
                   {where_extra}
                 ORDER BY rev.review_count DESC, b.name
                 LIMIT {limit_p} OFFSET {offset_p}
            """

        rows = await conn.fetch(sql, *args)

    tellus_entries = [_entry_from_tellus_row(r) for r in rows]
    total = min(rows[0]["total_count"], _MAX_DEPTH) if rows else 0

    google_entries: list[TellusDiscoverEntry] = []
    # Google fill: page-1-only (Google paginates independently — interleaving
    # it into offset paging produces duplicates and gaps), and only when
    # Tell-Us didn't already fill the page.
    if has_geo and offset == 0 and len(tellus_entries) < limit:
        redis = get_redis_cache()
        cache_key = discover_cache_key(lat, lng, radius_km, query)
        cached = await cache_get(redis, cache_key) if redis else None
        if cached is not None:
            google_rows = cached
        else:
            radius_m = radius_km * 1000
            google_rows = await (
                google_places.search_text(query, lat, lng, radius_m)
                if query
                else google_places.search_nearby(lat, lng, radius_m)
            )
            if google_rows is not None and redis:
                await cache_set(redis, cache_key, google_rows, ttl=_GOOGLE_CACHE_TTL_S)
        known_ids = {e.google_place_id for e in tellus_entries if e.google_place_id}
        google_rows = dedupe_google(google_rows or [], known_ids)
        google_entries = [_entry_from_google_row(r) for r in google_rows[: limit - len(tellus_entries)]]

    entries = tellus_entries + google_entries
    next_offset = offset + len(tellus_entries)
    if next_offset >= min(total, _MAX_DEPTH) or not tellus_entries:
        next_offset = None

    return TellusDiscoverPage(
        entries=entries,
        total=total,
        next_offset=next_offset,
        google_attribution=len(google_entries) > 0,
    )
