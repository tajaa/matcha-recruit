"""Cappe Discover — the public directory.

**This is the first many-site public read in Cappe.** Every other endpoint under
`routes/public/` resolves a single known slug, so a caller can only ever see a
site they already knew about. A directory is different by definition, and that
makes it a new abuse surface: without care it is a one-request dump of every
tenant on the platform. Three deliberate mitigations, none of them optional:

* **Its own rate-limit bucket** (`cappe_pub_directory`), tighter than the shared
  `cappe_pub_read`. That 120/60s budget is sized for the 2-3 widget fetches a
  single tenant page load fires; directory browsing is one request per user
  action, which is a different traffic shape and deserves a different budget.
* **A hard depth cap** (`_MAX_DEPTH`). Browsing needs "next page"; nothing
  legitimate needs to walk the entire tenant list. The cap is what turns
  "paginate politely" into "cannot enumerate", and it is also why plain OFFSET
  is fine here — the offset can never grow large enough to matter.
* **A strict response allowlist.** `_ENTRY_COLS` is everything a card needs and
  nothing else. In particular NO contact email and NO account id: a directory
  that returned tenant emails would be a one-request harvest of the whole
  customer base.

Two more predicates that are about quality rather than abuse: a site must be
`published AND listed AND NOT directory_blocked` (tenant opt-out and platform
takedown are separate switches on purpose — see the migration), its account must
still be active, and it must have BOTH a category and a blurb. That last one is
the quality gate: a published-but-empty template has neither, so the first
screen can never be six "Untitled Site" cards.
"""

import os
from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException, Query, Request, status

from ....core.services.redis_cache import check_rate_limit, client_ip
from ....database import get_connection
from ...models.cappe import CappeDirectoryPage, CappeDirectoryCategories
from ...services.directory import CATEGORY_LABELS, category_options, normalize_category
from ...services.render.sanitize import _safe_image

router = APIRouter()

_BASE_DOMAIN = os.getenv("CAPPE_BASE_DOMAIN", "hey-matcha.com")

# Browsing is one request per user action, unlike the widget fetches the shared
# public budget is sized for.
_RATE_LIMIT_CALLS = 30
_RATE_LIMIT_WINDOW_S = 60

# Past this many results the directory simply stops. See the module docstring —
# this is the anti-enumeration control, not a performance tuning knob.
_MAX_DEPTH = 200
_MAX_LIMIT = 24

_MAX_RADIUS_KM = 500.0

# The response allowlist. Adding a column here puts it on the public internet
# for every tenant at once.
_ENTRY_COLS = """
    s.slug, s.name, s.subdomain, s.custom_domain,
    s.directory_category, s.directory_tags, s.directory_blurb,
    s.meta_config #>> '{logo_url}' AS logo_url,
    a.account_type,
    s.published_at
"""

# Card display only (no geo filter in play): the site's default location, for
# the "Los Angeles, CA" line on the card. LEFT JOIN LATERAL so a site with no
# location still appears in unfiltered browsing. Deliberately NOT used for
# radius search — see `_geo_cte` below for why a default location is the
# wrong row to filter/sort on once lat/lng are supplied.
_LOCATION_LATERAL = """
LEFT JOIN LATERAL (
    SELECT l.city, l.region
      FROM cappe_locations l
     WHERE l.site_id = s.id AND l.active
     ORDER BY l.is_default DESC, l.sort_order, l.created_at
     LIMIT 1
) loc ON true
"""

# Haversine, great-circle km. Inline rather than earthdistance/PostGIS so this
# needs no CREATE EXTENSION on prod (which requires explicit approval).
_DISTANCE_EXPR = """
    6371.0 * acos(least(1.0, greatest(-1.0,
        sin(radians($LAT)) * sin(radians(geo.lat)) +
        cos(radians($LAT)) * cos(radians(geo.lat)) * cos(radians(geo.lng - $LNG))
    )))
"""

_BASE_PREDICATE = """
    s.status = 'published'
    AND s.listed
    AND NOT s.directory_blocked
    AND a.status = 'active'
    AND s.directory_category IS NOT NULL
    AND s.directory_blurb IS NOT NULL
"""


async def _directory_rate_limit(request: Request) -> None:
    await check_rate_limit(
        client_ip(request), "cappe_pub_directory", _RATE_LIMIT_CALLS, _RATE_LIMIT_WINDOW_S
    )


def _public_url(row) -> str:
    """The site's own public address — the whole point of a directory entry."""
    if row["custom_domain"]:
        return f"https://{row['custom_domain']}"
    return f"https://{row['subdomain'] or row['slug']}.{_BASE_DOMAIN}"


def _entry(row, *, distance_km: Optional[float] = None) -> dict[str, Any]:
    return {
        "slug": row["slug"],
        "name": row["name"],
        "url": _public_url(row),
        "category": row["directory_category"],
        "category_label": CATEGORY_LABELS.get(row["directory_category"] or ""),
        "tags": list(row["directory_tags"] or []),
        "blurb": row["directory_blurb"],
        # `meta_config.logo_url` is tenant-controlled free text, unlike
        # everything else in the allowlist. Every other render path
        # (services/render/) runs it through this same guard before emitting
        # an <img src>; skipping it here would let a tenant point their logo
        # at their own server and log the IP/UA of every Discover visitor —
        # not just visitors to their own site — plus `javascript:`/`data:`
        # schemes and unescaped quote/paren characters.
        "logo_url": _safe_image(row["logo_url"]),
        "account_type": row["account_type"],
        "city": row["city"],
        "region": row["region"],
        "distance_km": round(distance_km, 1) if distance_km is not None else None,
        "rating": float(row["rating"]) if row["rating"] is not None else None,
        "review_count": row["review_count"] or 0,
        "published_at": row["published_at"],
    }


@router.get("/public/directory/categories", response_model=CappeDirectoryCategories)
async def directory_categories(request: Request):
    """The fixed taxonomy plus a live count per category.

    Counts use the same base predicate as the listing itself, so a category chip
    never promises results the grid can't show.
    """
    await _directory_rate_limit(request)
    async with get_connection() as conn:
        rows = await conn.fetch(
            f"""SELECT s.directory_category AS slug, COUNT(*) AS n
                  FROM cappe_sites s
                  JOIN cappe_accounts a ON a.id = s.account_id
                 WHERE {_BASE_PREDICATE}
                 GROUP BY s.directory_category"""
        )
    counts = {r["slug"]: r["n"] for r in rows}
    return CappeDirectoryCategories(
        categories=[{**opt, "count": counts.get(opt["slug"], 0)} for opt in category_options()],
        total=sum(counts.values()),
    )


@router.get("/public/directory", response_model=CappeDirectoryPage)
async def browse_directory(
    request: Request,
    q: Optional[str] = Query(default=None, max_length=120),
    category: Optional[str] = Query(default=None, max_length=60),
    # Aliased: the query key must be `type`, but shadowing the builtin in the
    # function body invites a subtle bug later.
    account_type: Literal["business", "personal", "all"] = Query(default="all", alias="type"),
    lat: Optional[float] = Query(default=None, ge=-90, le=90),
    lng: Optional[float] = Query(default=None, ge=-180, le=180),
    radius_km: float = Query(default=25.0, gt=0, le=_MAX_RADIUS_KM),
    sort: Literal["relevance", "newest", "distance"] = "relevance",
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=12, ge=1, le=_MAX_LIMIT),
):
    await _directory_rate_limit(request)

    # A half-supplied coordinate pair is a client bug; silently ignoring it
    # would return the whole country to someone who asked for "near me".
    if (lat is None) != (lng is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="lat and lng must be provided together",
        )
    has_geo = lat is not None and lng is not None
    if sort == "distance" and not has_geo:
        sort = "relevance"

    if offset >= _MAX_DEPTH:
        return CappeDirectoryPage(entries=[], total=0, next_offset=None)
    limit = min(limit, _MAX_DEPTH - offset)

    query = (q or "").strip()
    cat = normalize_category(category) if category else None
    # An unrecognized category is an empty result, NOT an ignored filter — the
    # alternative silently returns the entire directory for a typo'd chip.
    if category and cat is None:
        return CappeDirectoryPage(entries=[], total=0, next_offset=None)

    args: list[Any] = []
    where = [_BASE_PREDICATE]

    query_param: Optional[str] = None
    if query:
        args.append(query)
        # Captured rather than assumed to be $1: the ranking expression below
        # reuses this exact placeholder, and hardcoding it would break silently
        # the first time a filter is appended ahead of the query.
        query_param = f"${len(args)}"
        where.append(f"sv.search_vector @@ websearch_to_tsquery('english', {query_param})")
    if cat:
        args.append(cat)
        where.append(f"s.directory_category = ${len(args)}")
    if account_type != "all":
        args.append(account_type)
        where.append(f"a.account_type = ${len(args)}")

    # Two entirely different join shapes depending on whether a radius was
    # asked for — see the long comment below for why they can't share one.
    geo_cte = ""
    geo_join = _LOCATION_LATERAL
    distance_km_expr = "NULL::float8"
    if has_geo:
        args.append(lat)
        lat_param = f"${len(args)}"
        args.append(lng)
        lng_param = f"${len(args)}"
        args.append(radius_km)
        radius_param = f"${len(args)}"

        loc_distance_expr = (
            _DISTANCE_EXPR.replace("$LAT", lat_param).replace("$LNG", lng_param).replace("geo.", "l.")
        )
        bbox_predicate = f"""
                l.lat IS NOT NULL AND l.lng IS NOT NULL
                AND l.lat BETWEEN {lat_param} - ({radius_param} / 111.045)
                              AND {lat_param} + ({radius_param} / 111.045)
                AND l.lng BETWEEN {lng_param} - ({radius_param} / (111.045 * greatest(cos(radians({lat_param})), 0.01)))
                              AND {lng_param} + ({radius_param} / (111.045 * greatest(cos(radians({lat_param})), 0.01)))
        """
        # Drive off `cappe_locations` directly rather than picking each site's
        # DEFAULT location and filtering that: a multi-location business whose
        # default is its unmapped HQ has a real location inside the radius that
        # the old per-site-default lateral would never see (its lateral output
        # was one row — the default — and the radius filter then ran against
        # THAT row's lat/lng, dropping the site even though a branch matched).
        # Filtering on `l.*` (the bbox + `active`) here also means Postgres can
        # use `idx_cappe_locations_geo` as the driving scan; the old shape ran
        # the bbox against the output of a per-site `LIMIT 1` lateral, which
        # can't be pushed into an index scan at all.
        geo_cte = f"""
        WITH nearest_loc AS (
            SELECT DISTINCT ON (l.site_id)
                   l.site_id, l.city, l.region, ({loc_distance_expr}) AS distance_km
              FROM cappe_locations l
             WHERE l.active AND ({bbox_predicate})
             ORDER BY l.site_id, distance_km ASC
        )
        """
        # INNER join: a site with no geocoded location inside the box has
        # nothing to rank or filter by, and radius search is exactly the query
        # where "no matching location" should mean "not a result", not "show it
        # anyway with a blank distance".
        geo_join = "JOIN nearest_loc loc ON loc.site_id = s.id"
        # The bbox above is a square approximation; the exact circle is only
        # knowable once distance_km is computed, so it's enforced here rather
        # than inside the CTE's WHERE (which runs before that column exists).
        where.append(f"loc.distance_km <= {radius_param}")
        distance_km_expr = "loc.distance_km"

    rank_expr = "0::float4"
    if query_param:
        # ts_rank_cd over the weighted vector: name beats tags beats a stray
        # product name (see services/directory.py:_SEARCH_SQL).
        rank_expr = f"ts_rank_cd(sv.search_vector, websearch_to_tsquery('english', {query_param}))"

    if sort == "distance" and has_geo:
        order_by = "distance_km ASC NULLS LAST, s.published_at DESC NULLS LAST, s.id"
    elif sort == "newest" or not query:
        # Recency is honest and un-gameable. Note ratings are deliberately NOT a
        # sort key anywhere: cappe_reviews are collected by the very site being
        # ranked, so ordering by them would be a gaming vector on day one. They
        # ride along on the card as information only.
        order_by = "s.published_at DESC NULLS LAST, s.id"
    else:
        order_by = "rank DESC, s.published_at DESC NULLS LAST, s.id"

    where_sql = " AND ".join(f"({w})" for w in where)

    args.append(limit)
    limit_param = f"${len(args)}"
    args.append(offset)
    offset_param = f"${len(args)}"

    sql = f"""
        {geo_cte}
        SELECT {_ENTRY_COLS},
               loc.city, loc.region,
               {distance_km_expr} AS distance_km,
               {rank_expr} AS rank,
               rev.rating, rev.review_count,
               COUNT(*) OVER () AS total_count
          FROM cappe_sites s
          JOIN cappe_accounts a ON a.id = s.account_id
          -- Search index lives in its own table (see the migration): a
          -- tsvector column on cappe_sites would be decoded on every
          -- SELECT * owner read that never uses it.
          LEFT JOIN cappe_site_search sv ON sv.site_id = s.id
          {geo_join}
          LEFT JOIN LATERAL (
              -- COUNT(r.rating), not COUNT(*): rating is nullable, and counting
              -- unrated reviews would print "4.5 (12)" off 3 actual ratings.
              SELECT ROUND(AVG(r.rating)::numeric, 1) AS rating, COUNT(r.rating) AS review_count
                FROM cappe_reviews r
               WHERE r.site_id = s.id AND r.status = 'approved'
          ) rev ON true
         WHERE {where_sql}
         ORDER BY {order_by}
         LIMIT {limit_param} OFFSET {offset_param}
    """

    async with get_connection() as conn:
        rows = await conn.fetch(sql, *args)

    total = min(rows[0]["total_count"], _MAX_DEPTH) if rows else 0
    entries = [_entry(r, distance_km=r["distance_km"]) for r in rows]
    next_offset = offset + len(entries)
    if next_offset >= min(total, _MAX_DEPTH) or not entries:
        next_offset = None

    return CappeDirectoryPage(entries=entries, total=total, next_offset=next_offset)
