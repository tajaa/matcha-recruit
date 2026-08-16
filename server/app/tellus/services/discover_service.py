"""Tell-Us Discover — pure helpers (no DB, no network).

Everything unit-testable lives here since the app has no mock/protocol seam
for services (all hard singletons) — see TELLUS_DISCOVER_PLAN.md at the repo
root for the full feature design and the route that calls these.
"""
from typing import Any, Collection, Optional

# Matches Google searchNearby's own hard cap, so a wider ask can't silently
# return a narrower Google result set than what was requested.
MAX_RADIUS_KM = 50.0

# Redis key coordinate precision — 3 decimal places is ~110m buckets, so two
# users a block apart share one cached Google response. This rounding IS the
# cost control (Nearby/Text Search are billed per request, no session token).
_COORD_PRECISION = 3

# Google primaryType -> display label. Same whitelist idiom as
# cappe/services/directory.normalize_category: an unrecognized/invented value
# is dropped rather than shown, so Google can't inject an arbitrary label
# into our UI.
GOOGLE_TYPE_LABELS: dict[str, str] = {
    "restaurant": "Restaurant",
    "cafe": "Cafe",
    "coffee_shop": "Cafe",
    "bar": "Bar",
    "bakery": "Bakery",
    "gym": "Gym",
    "beauty_salon": "Hair & Beauty",
    "hair_salon": "Hair & Beauty",
    "hair_care": "Hair & Beauty",
    "spa": "Spa",
    "store": "Shop",
    "clothing_store": "Shop",
    "book_store": "Shop",
    "pharmacy": "Pharmacy",
    "pet_store": "Pets",
    "veterinary_care": "Pets",
    "car_repair": "Auto",
    "lodging": "Stay",
}

# Haversine, great-circle km. Inline rather than earthdistance/PostGIS so this
# needs no CREATE EXTENSION on prod (which requires explicit approval) — ported
# verbatim from cappe/routes/public/directory.py:_DISTANCE_EXPR.
DISTANCE_SQL = """
    6371.0 * acos(least(1.0, greatest(-1.0,
        sin(radians($LAT)) * sin(radians(st.lat)) +
        cos(radians($LAT)) * cos(radians(st.lat)) * cos(radians(st.lng - $LNG))
    )))
"""


def discover_cache_key(lat: float, lng: float, radius_km: float, q: Optional[str]) -> str:
    """Redis key for a Google fill. Coords rounded to _COORD_PRECISION so
    nearby opens share one cache entry — see module docstring."""
    lat_b = round(lat, _COORD_PRECISION)
    lng_b = round(lng, _COORD_PRECISION)
    q_part = (q or "").strip().lower()
    return f"tellus:discover:{lat_b}:{lng_b}:{radius_km}:{q_part}"


def normalize_google_type(primary_type: Any) -> Optional[str]:
    """Google primaryType -> display label; unknown or non-str -> None (never
    shown to the user)."""
    if not isinstance(primary_type, str):
        return None
    return GOOGLE_TYPE_LABELS.get(primary_type)


# Brand-authored category vocabulary. Sourced from GOOGLE_TYPE_LABELS' own
# values (not its keys) so a brand-picked category and a Google-derived one
# always render from the same single vocabulary — no risk of the two lists
# drifting apart into different display strings for the same concept.
BRAND_CATEGORIES: tuple[str, ...] = tuple(sorted(set(GOOGLE_TYPE_LABELS.values())))


def normalize_brand_category(value: Any) -> Optional[str]:
    """Brand-authored category -> canonical label, or None. Case-insensitive
    exact match against BRAND_CATEGORIES; unknown or non-str input is dropped
    rather than shown — same never-show-an-unvetted-label rule as
    normalize_google_type."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    for label in BRAND_CATEGORIES:
        if value.lower() == label.lower():
            return label
    return None


def dedupe_google(google_rows: list[dict], known_place_ids: Collection[str]) -> list[dict]:
    """Drop Google entries already represented by a Tell-Us brand. Arg order
    mirrors iOS PlacesViewModel.dedupe(_:against:). A row with no place_id
    (shouldn't happen post-_parse_discover, but don't trust it twice) is
    dropped too rather than shown un-dedupeable."""
    known = set(known_place_ids)
    return [row for row in google_rows if row.get("place_id") and row["place_id"] not in known]


def bbox_predicate(lat_param: str, lng_param: str, radius_param: str) -> str:
    """SQL fragment bounding st.lat/st.lng to a square around the point, as a
    cheap index-usable prefilter before the exact haversine circle is applied
    in the outer WHERE. greatest(cos(radians(...)), 0.01) guards the pole
    singularity (cos(90) == 0 would blow up the longitude delta). Same shape
    as cappe/routes/public/directory.py's bbox_predicate."""
    return f"""
        st.lat IS NOT NULL AND st.lng IS NOT NULL
        AND st.lat BETWEEN {lat_param} - ({radius_param} / 111.045)
                        AND {lat_param} + ({radius_param} / 111.045)
        AND st.lng BETWEEN {lng_param} - ({radius_param} / (111.045 * greatest(cos(radians({lat_param})), 0.01)))
                        AND {lng_param} + ({radius_param} / (111.045 * greatest(cos(radians({lat_param})), 0.01)))
    """
