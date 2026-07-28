"""US Census geocoding — the shared address → coordinates helper.

Lifted here from ``matcha/services/property/property_cat.py`` (2026-07-28) so
Cappe's Discover directory can geocode tenant locations WITHOUT adding a
``cappe -> matcha`` import. That edge is currently 0 and is a stated invariant
in the root CLAUDE.md (Tell-Us already holds the single documented exception);
``core`` is the shared layer both products may import, so moving the function
here adds no cross-product edges at all.

``geocode`` and ``geocode_fips`` keep their EXACT original signatures —
``property_cat`` re-exports both, and Tell-Us imports ``geocode`` through it
(CLAUDE.md: "keep its signature stable"). Callers that already own an
``httpx.AsyncClient`` pass it in; ``geocode_address`` is the convenience
wrapper for callers that don't.

Everything here is BEST-EFFORT, exactly as it was in ``property_cat``: timed
out, broadly excepted, returns ``None`` on any failure, and NEVER raises into a
request. US-only — the Census geocoder has no international coverage, so a
non-US address simply returns None and the caller degrades (in Cappe's case,
the site stays in text/category search and drops out of radius search).
"""

import logging
import os

import httpx

logger = logging.getLogger(__name__)

# Free, no key. Overridable via env for testing / outage swaps. The env name is
# unchanged from property_cat so an existing prod override keeps working.
CENSUS_GEOCODER_URL = os.getenv(
    "CENSUS_GEOCODER_URL",
    "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress",
)
# Falls back to property_cat's original env var so a deployment that already
# tuned CAT_FETCH_TIMEOUT_S doesn't silently revert to the default here.
GEOCODE_TIMEOUT_S = float(
    os.getenv("GEOCODE_TIMEOUT_S", os.getenv("CAT_FETCH_TIMEOUT_S", "12"))
)

_BENCHMARK_PARAMS = {
    "benchmark": "Public_AR_Current",
    "vintage": "Current_Current",
    "format": "json",
}


async def _get_json(client: httpx.AsyncClient, url: str, params: dict):
    """Deliberately a private twin of property_cat's helper rather than an
    import back into matcha — six lines is cheaper than a cross-product edge,
    and property_cat still needs its own for the FEMA/USGS/USFS peril calls."""
    try:
        resp = await client.get(url, params=params, timeout=GEOCODE_TIMEOUT_S)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:  # noqa: BLE001 - best-effort external call
        logger.warning("geo: GET %s failed: %s", url, exc)
        return None


def _one_line(address, city, state, zipcode) -> str:
    return ", ".join(p for p in (address, city, state, zipcode) if p)


async def geocode(client, address, city, state, zipcode) -> dict | None:
    """US Census one-line geocode → {lat, lng, county, source}. None on no match."""
    one_line = _one_line(address, city, state, zipcode)
    if not one_line:
        return None
    data = await _get_json(client, CENSUS_GEOCODER_URL, {"address": one_line, **_BENCHMARK_PARAMS})
    try:
        matches = data["result"]["addressMatches"]
        if not matches:
            return None
        m = matches[0]
        coords = m["coordinates"]  # {x: lng, y: lat}
        county = None
        counties = (m.get("geographies") or {}).get("Counties") or []
        if counties:
            county = counties[0].get("BASENAME")
        return {"lat": float(coords["y"]), "lng": float(coords["x"]), "county": county, "source": "census"}
    except (KeyError, IndexError, TypeError, ValueError):
        return None


async def geocode_fips(client, address, city, state, zipcode) -> dict | None:
    """US Census one-line geocode → deterministic FIPS anchors.

    Returns {county_fips, county_name, place_fips, place_name} or None on no
    match. `place_fips` is None for an address in no incorporated place
    (unincorporated / CDP-only) — the caller uses that to stop the jurisdiction
    chain at the county rather than invent a city node. Sibling of `geocode`
    (kept signature-stable — tellus reuses it); both hit the same geographies
    benchmark, so this just reads more layers out of the same response.
    """
    one_line = _one_line(address, city, state, zipcode)
    if not one_line:
        return None
    data = await _get_json(client, CENSUS_GEOCODER_URL, {"address": one_line, **_BENCHMARK_PARAMS})
    try:
        matches = data["result"]["addressMatches"]
        if not matches:
            return None
        geos = (matches[0].get("geographies") or {})

        county_fips = county_name = None
        counties = geos.get("Counties") or []
        if counties:
            county_fips = counties[0].get("GEOID")          # 5-digit SSCCC
            county_name = counties[0].get("BASENAME")

        # Incorporated Places first (a real municipality with ordinance power);
        # Census Designated Places are unincorporated → no city authority, so we
        # do NOT treat a CDP as a place_fips.
        place_fips = place_name = None
        places = geos.get("Incorporated Places") or []
        if places:
            place_fips = places[0].get("GEOID")             # 7-digit SSPPPPP
            place_name = places[0].get("BASENAME")

        if not (county_fips or place_fips):
            return None
        return {
            "county_fips": county_fips, "county_name": county_name,
            "place_fips": place_fips, "place_name": place_name,
        }
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def _region_from_matched(matched: str | None) -> str | None:
    """Pull the 2-letter state out of a Census matched address string
    ('1600 PENNSYLVANIA AVE NW, WASHINGTON, DC, 20500'). Used only as a
    fallback when the States geography layer is absent from the response."""
    if not matched:
        return None
    parts = [p.strip() for p in matched.split(",")]
    for part in reversed(parts):
        if len(part) == 2 and part.isalpha():
            return part.upper()
    return None


async def geocode_address(address: str | None) -> dict | None:
    """One free-text address → {lat, lng, city, region, county} or None.

    The convenience entry point for callers with a single unstructured address
    string and no httpx client of their own (Cappe locations are a free-text
    `address` column). Manages its own short-lived client. Never raises.
    """
    if not (address or "").strip():
        return None
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            data = await _get_json(
                client, CENSUS_GEOCODER_URL, {"address": address.strip(), **_BENCHMARK_PARAMS}
            )
    except Exception as exc:  # noqa: BLE001 - best-effort external call
        logger.warning("geo: geocode_address failed: %s", exc)
        return None

    try:
        matches = data["result"]["addressMatches"]
        if not matches:
            return None
        m = matches[0]
        coords = m["coordinates"]  # {x: lng, y: lat}
        geos = m.get("geographies") or {}

        places = geos.get("Incorporated Places") or []
        city = places[0].get("BASENAME") if places else None

        counties = geos.get("Counties") or []
        county = counties[0].get("BASENAME") if counties else None

        states = geos.get("States") or []
        region = (states[0].get("STUSAB") or states[0].get("BASENAME")) if states else None
        if not region:
            region = _region_from_matched(m.get("matchedAddress"))

        return {
            "lat": float(coords["y"]),
            "lng": float(coords["x"]),
            "city": city,
            "region": region,
            "county": county,
        }
    except (KeyError, IndexError, TypeError, ValueError):
        return None
