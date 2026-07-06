"""Geocoded catastrophe exposure for property buildings.

Per building: geocode the address (US Census), then read each peril hazard at that
point — flood (FEMA National Flood Hazard Layer), earthquake (USGS ASCE-7 design
ground motion), wildfire (USFS Wildfire Hazard Potential), and wind (coarse
state/county coastal tier; there is no free per-address wind API). Results are
normalized to the shared severe/high/elevated/moderate/low tier vocabulary and
cached on ``property_building_perils``.

Everything network-facing is BEST-EFFORT: timed out, broadly excepted, returns
None / writes an ``error`` peril row, and NEVER raises into a request. Geocode +
fetch run only in the Phase-3 Celery task (``property_cat_refresh``), never inline
on save. The pure tier mappers + ``summarize`` are unit-tested without network.
"""

import json
import logging
import os
from uuid import UUID

import httpx

logger = logging.getLogger(__name__)

# Endpoints (free, no key). Overridable via env for testing / outage swaps.
CENSUS_GEOCODER_URL = os.getenv(
    "CENSUS_GEOCODER_URL",
    "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress",
)
FEMA_NFHL_URL = os.getenv(
    "FEMA_NFHL_URL",
    "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query",
)
USGS_DESIGNMAPS_URL = os.getenv(
    # USGS relocated the ASCE7-16 service (the old designmaps/asce7-16.json now 301s
    # here). Same response shape (response.data.sds). follow_redirects below also
    # covers a stale env value still pointing at the old path.
    "USGS_DESIGNMAPS_URL",
    "https://earthquake.usgs.gov/ws/building-codes/asce7-16/calculate",
)
USFS_WHP_URL = os.getenv(
    "USFS_WHP_URL",
    "https://apps.fs.usda.gov/arcx/rest/services/RDW_Wildfire/RMRS_WRC_WildfireHazardPotential_classified/ImageServer/identify",
)
CAT_FETCH_TIMEOUT_S = float(os.getenv("CAT_FETCH_TIMEOUT_S", "12"))
CAT_FETCH_ENABLED = os.getenv("CAT_FETCH_ENABLED", "true").strip().lower() in ("1", "true", "yes")

PERILS = ("flood", "quake", "wildfire", "wind")
TIER_RANK = {"severe": 4, "high": 3, "elevated": 2, "moderate": 1, "low": 0}

# Only flood and quake have a hazard-agency-documented annual-probability
# reading (see _flood_probability / _quake_probability below). Wildfire
# (directional state/county baseline) and wind (coarse seeded reference) have
# no defensible probability model — they stay tier-only, deliberately.
DOCUMENTED_PROBABILITY_PERILS = ("flood", "quake")


# --- pure tier mappers (unit-tested, no network) ---------------------------

def _flood_tier(zone) -> tuple[str, int]:
    """FEMA flood zone → (tier, score). V*=coastal SFHA (worst), A*=SFHA,
    0.2%-annual (shaded X)=elevated, X/B/C=minimal, D=undetermined."""
    z = str(zone or "").upper().strip()
    if z.startswith("V"):
        return "severe", 90
    if z.startswith("A"):
        return "high", 75
    if "0.2 PCT" in z or z in ("X500", "SHADED X"):
        return "elevated", 45
    if z == "D":
        return "moderate", 35
    if z in ("X", "B", "C", "", "AREA OF MINIMAL FLOOD HAZARD"):
        return "low", 10
    return "moderate", 30


def _quake_tier(sds) -> tuple[str, int] | None:
    """USGS design short-period spectral acceleration S_DS (g) → (tier, score),
    banded ~ ASCE-7 seismic design category."""
    if sds is None:
        return None
    s = float(sds)
    if s >= 0.75:
        return "severe", 90
    if s >= 0.50:
        return "high", 72
    if s >= 0.33:
        return "elevated", 50
    if s >= 0.167:
        return "moderate", 30
    return "low", 12


def _wildfire_tier(whp) -> tuple[str, int] | None:
    """USFS Wildfire Hazard Potential class (1-5 or Very Low..Very High) → tier."""
    by_n = {1: ("low", 12), 2: ("moderate", 30), 3: ("elevated", 50), 4: ("high", 72), 5: ("severe", 90)}
    try:
        return by_n[int(whp)]
    except (TypeError, ValueError, KeyError):
        pass
    t = str(whp or "").lower()
    if "very high" in t:
        return "severe", 90
    if "high" in t:
        return "high", 72
    if "moderate" in t:
        return "elevated", 50
    if "very low" in t:
        return "low", 12
    if "low" in t:
        return "moderate", 30
    return None


def _flood_probability(zone) -> float | None:
    """FEMA's own regulatory probability definitions — V*/A* zones ARE the
    1%-annual-chance (100-year) special flood hazard area by definition; the
    0.2%-annual-chance (500-year) band is literally named in the zone
    subtype. Minimal (X/B/C) and undetermined (D) are ceilings/unknowns, not
    point probabilities — None rather than a fabricated number."""
    z = str(zone or "").upper().strip()
    if z.startswith("V") or z.startswith("A"):
        return 0.01
    if "0.2 PCT" in z or z in ("X500", "SHADED X"):
        return 0.002
    return None


def _quake_probability(sds) -> float | None:
    """Deliberately always None (a judgment call to preserve, not a gap to
    fix). ASCE-7 MCER design ground motion is risk-targeted — calibrated to a
    uniform COLLAPSE-risk target and blended with deterministic caps near
    active faults — not to a uniform ground-motion exceedance probability. A
    single Sds value doesn't map to one annual probability without the full
    USGS probabilistic seismic hazard curve, a different API this module
    doesn't call."""
    return None


def _peril_annual_probability(peril, zone) -> float | None:
    """Dispatch to the documented-probability mapper for this peril, else
    None. Derived at read time from the stored zone — no schema change
    needed. Quake stays wired through _quake_probability so its
    deliberately-None judgment call remains live code, not lore."""
    if peril == "flood":
        return _flood_probability(zone)
    if peril == "quake":
        return _quake_probability(None)
    return None


def _wind_tier(state, county, ref_rows: list[dict]) -> tuple[str, int] | None:
    """Coastal-wind tier from the seeded coastal_wind_tier reference. County-specific
    row first, else the state baseline (county=''), else low (inland)."""
    if not state:
        return None
    st = str(state).upper().strip()
    cty = str(county or "").strip()
    by = {(r["state"], r["county"]): r for r in ref_rows}
    r = by.get((st, cty)) or by.get((st, ""))
    if not r:
        return "low", 10
    return r["tier"], int(r["score"])


# Coarse wildfire baseline by state/county. The free per-address WHP point services
# (USFS apps.fs.usda.gov, ESRI Living Atlas) are now 403/token-gated, so — exactly like
# wind — wildfire resolves from a directional, sourced, editable reference (network-free).
# County rows override the statewide baseline; everything else is low.
_WF_TIER_SCORE = {"low": 10, "moderate": 30, "elevated": 50, "high": 72, "severe": 90}
# Statewide baselines are deliberately conservative (≤ elevated) so a coarse state read
# doesn't overstate wildfire on an urban core (a downtown high-rise isn't WUI). True
# wildland-urban-interface exposure comes from the county overrides below (high/severe).
WILDFIRE_STATE_TIER = {
    "CA": "elevated", "CO": "elevated", "OR": "elevated", "ID": "elevated", "MT": "elevated",
    "AZ": "elevated", "NV": "elevated", "NM": "elevated", "WA": "elevated", "UT": "elevated",
    "WY": "elevated", "TX": "elevated", "OK": "elevated",
    "FL": "moderate", "GA": "moderate", "NC": "moderate", "SC": "moderate", "TN": "moderate",
    "AR": "moderate", "KS": "moderate", "NE": "moderate", "SD": "moderate", "ND": "moderate",
    "MN": "moderate", "WI": "moderate",
}
WILDFIRE_COUNTY_TIER = {
    ("CA", "Napa"): "severe", ("CA", "Sonoma"): "severe", ("CA", "Butte"): "severe",
    ("CA", "Lake"): "severe", ("CA", "Shasta"): "severe", ("CA", "El Dorado"): "severe",
    ("CA", "Nevada"): "severe", ("CA", "Mariposa"): "severe",
    ("CA", "San Diego"): "high", ("CA", "Riverside"): "high", ("CA", "San Bernardino"): "high",
    ("CA", "Ventura"): "high",
    ("CO", "Boulder"): "severe", ("CO", "El Paso"): "high", ("CO", "Larimer"): "high",
    ("OR", "Jackson"): "severe", ("OR", "Deschutes"): "high",
    ("WA", "Chelan"): "high", ("WA", "Okanogan"): "high", ("WA", "Spokane"): "elevated",
    ("AZ", "Coconino"): "high", ("MT", "Flathead"): "high", ("NV", "Washoe"): "high",
    ("ID", "Ada"): "elevated", ("TX", "Bastrop"): "high",
}


def _wildfire_state_tier(state, county) -> tuple[str, int] | None:
    """Directional wildfire tier from the state/county baseline (county overrides state).
    Network-free fallback now that the WHP point services are gated. Pure."""
    if not state:
        return None
    st = str(state).upper().strip()
    cty = str(county or "").strip()
    tier = WILDFIRE_COUNTY_TIER.get((st, cty)) or WILDFIRE_STATE_TIER.get(st, "low")
    return tier, _WF_TIER_SCORE[tier]


# --- network helpers (best-effort; None on any failure) --------------------

async def _get_json(client: httpx.AsyncClient, url: str, params: dict):
    try:
        resp = await client.get(url, params=params, timeout=CAT_FETCH_TIMEOUT_S)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:  # noqa: BLE001 - best-effort external call
        logger.warning("property_cat: GET %s failed: %s", url, exc)
        return None


async def geocode(client, address, city, state, zipcode) -> dict | None:
    """US Census one-line geocode → {lat, lng, county, source}. None on no match."""
    one_line = ", ".join(p for p in (address, city, state, zipcode) if p)
    if not one_line:
        return None
    data = await _get_json(client, CENSUS_GEOCODER_URL, {
        "address": one_line, "benchmark": "Public_AR_Current",
        "vintage": "Current_Current", "format": "json",
    })
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


async def fetch_flood(client, lat, lng) -> dict | None:
    data = await _get_json(client, FEMA_NFHL_URL, {
        "geometry": f"{lng},{lat}", "geometryType": "esriGeometryPoint", "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects", "outFields": "FLD_ZONE,ZONE_SUBTY",
        "returnGeometry": "false", "f": "json",
    })
    try:
        feats = data.get("features") or []
        attrs = feats[0]["attributes"] if feats else {}
        fld = attrs.get("FLD_ZONE") or "X"
        subty = str(attrs.get("ZONE_SUBTY") or "")
        # the 0.2%-annual-chance band lives in ZONE_SUBTY; score + store that when present
        scored = subty if subty.startswith("0.2") else fld
        tier, score = _flood_tier(scored)
        return {"zone": str(scored), "tier": tier, "score": score, "source": "FEMA NFHL", "raw": attrs}
    except (AttributeError, KeyError, IndexError, TypeError):
        return None


async def fetch_quake(client, lat, lng) -> dict | None:
    data = await _get_json(client, USGS_DESIGNMAPS_URL, {
        "latitude": lat, "longitude": lng, "riskCategory": "II", "siteClass": "D", "title": "matcha",
    })
    try:
        sds = data["response"]["data"]["sds"]
        mapped = _quake_tier(sds)
        if mapped is None:
            return None
        tier, score = mapped
        return {"zone": f"SDS {round(float(sds), 2)}g", "tier": tier, "score": score,
                "source": "USGS ASCE7-16", "raw": {"sds": sds}}
    except (KeyError, TypeError, ValueError):
        return None


async def fetch_wildfire(client, lat, lng) -> dict | None:
    data = await _get_json(client, USFS_WHP_URL, {
        "geometry": f"{lng},{lat}", "geometryType": "esriGeometryPoint",
        "returnGeometry": "false", "f": "json",
    })
    try:
        val = (data.get("results") or [{}])[0].get("value") if data.get("results") else data.get("value")
        mapped = _wildfire_tier(val)
        if mapped is None:
            return None
        tier, score = mapped
        return {"zone": f"WHP {val}", "tier": tier, "score": score, "source": "USFS WHP", "raw": {"value": val}}
    except (AttributeError, KeyError, IndexError, TypeError):
        return None


# --- orchestration ----------------------------------------------------------

async def _coastal_wind_rows(conn) -> list[dict]:
    rows = await conn.fetch("SELECT state, county, tier, score FROM coastal_wind_tier")
    return [dict(r) for r in rows]


async def _upsert_peril(conn, building_id, peril, result, error=None):
    await conn.execute(
        """
        INSERT INTO property_building_perils (building_id, peril, zone, score, tier, raw, source, fetched_at, error)
        VALUES ($1,$2,$3,$4,$5,$6,$7,NOW(),$8)
        ON CONFLICT ON CONSTRAINT uq_building_peril DO UPDATE SET
            zone = EXCLUDED.zone, score = EXCLUDED.score, tier = EXCLUDED.tier, raw = EXCLUDED.raw,
            source = EXCLUDED.source, fetched_at = NOW(), error = EXCLUDED.error
        """,
        building_id, peril,
        (result or {}).get("zone"), (result or {}).get("score"), (result or {}).get("tier"),
        json.dumps((result or {}).get("raw")) if result and result.get("raw") is not None else None,
        (result or {}).get("source"), error,
    )


async def enrich_building(conn, building_id: UUID) -> dict:
    """Geocode (if needed) + refresh all peril rows for one building. Best-effort:
    a failed peril writes an error row; the building's save already returned."""
    if not CAT_FETCH_ENABLED:
        return {"status": "disabled"}
    b = await conn.fetchrow(
        "SELECT id, address, city, state, zipcode, county, lat, lng "
        "FROM company_property_buildings WHERE id = $1",
        building_id,
    )
    if not b:
        return {"status": "not_found"}

    lat, lng = b["lat"], b["lng"]
    async with httpx.AsyncClient(follow_redirects=True) as client:
        if lat is None or lng is None:
            geo = await geocode(client, b["address"], b["city"], b["state"], b["zipcode"])
            if geo:
                lat, lng = geo["lat"], geo["lng"]
                await conn.execute(
                    "UPDATE company_property_buildings SET lat=$2, lng=$3, geocoded_at=NOW(), "
                    "geocode_source=$4, county=COALESCE(county,$5) WHERE id=$1",
                    building_id, lat, lng, geo["source"], geo.get("county"),
                )

        if lat is None or lng is None:
            await conn.execute(
                "UPDATE company_property_buildings SET cat_refreshed_at=NOW() WHERE id=$1", building_id)
            return {"status": "no_geocode"}

        # point perils (live external sources): flood + quake.
        # NOTE: wildfire is NOT a point fetch here — every free WHP point service is now
        # 403/token-gated, so wildfire resolves from the coarse state/county baseline below
        # (same approach as wind). fetch_wildfire / _wildfire_tier are kept for a future
        # working point source.
        for peril, fn in (("flood", fetch_flood), ("quake", fetch_quake)):
            try:
                res = await fn(client, lat, lng)
                await _upsert_peril(conn, building_id, peril, res, error=None if res else "no data")
            except Exception as exc:  # noqa: BLE001
                await _upsert_peril(conn, building_id, peril, None, error=str(exc)[:300])

    # county/state reference perils (no network): wind + wildfire.
    refreshed_county = await conn.fetchval(
        "SELECT county FROM company_property_buildings WHERE id = $1", building_id)
    try:
        ref = await _coastal_wind_rows(conn)
        wt = _wind_tier(b["state"], refreshed_county, ref)
        if wt:
            await _upsert_peril(conn, building_id, "wind",
                                {"zone": f"{b['state']} coastal", "tier": wt[0], "score": wt[1],
                                 "source": "coastal_wind_tier", "raw": None})
    except Exception as exc:  # noqa: BLE001
        await _upsert_peril(conn, building_id, "wind", None, error=str(exc)[:300])
    try:
        wf = _wildfire_state_tier(b["state"], refreshed_county)
        if wf:
            await _upsert_peril(conn, building_id, "wildfire",
                                {"zone": f"{b['state']} baseline", "tier": wf[0], "score": wf[1],
                                 "source": "WHP state/county baseline (directional)", "raw": None})
    except Exception as exc:  # noqa: BLE001
        await _upsert_peril(conn, building_id, "wildfire", None, error=str(exc)[:300])

    await conn.execute(
        "UPDATE company_property_buildings SET cat_refreshed_at=NOW() WHERE id=$1", building_id)
    return {"status": "ok", "lat": lat, "lng": lng}


def summarize(rows: list[dict]) -> dict:
    """Roll up (building_id, peril, tier, score, lat[, zone]) rows → company
    cat exposure. Pure. ``zone`` is optional — when absent (e.g. an older
    caller), ``by_peril_detail`` entries just carry ``annual_probability: None``.

    ``worst_peril`` is deterministic under rank ties: a hazard-agency-documented
    peril (flood/quake) beats a directional baseline (wildfire/wind) at the same
    tier, and peril name breaks any remaining tie — the SQL feeding this has no
    ORDER BY, so first-row-wins would flap between requests."""
    buildings = {}
    by_peril: dict[str, str] = {}
    by_peril_detail: dict[str, dict] = {}
    present_ranks: list[int] = []
    worst_key: tuple | None = None  # (rank, documented, peril) — max wins
    for r in rows:
        bid = r["building_id"]
        buildings.setdefault(bid, {"geocoded": r.get("lat") is not None, "worst": 0})
        tier = r.get("tier")
        if tier and tier in TIER_RANK:
            rank = TIER_RANK[tier]
            present_ranks.append(rank)
            buildings[bid]["worst"] = max(buildings[bid]["worst"], rank)
            peril = r.get("peril")
            key = (rank, peril in DOCUMENTED_PROBABILITY_PERILS, peril or "")
            if worst_key is None or key > worst_key:
                worst_key = key
            if peril and rank > TIER_RANK.get(by_peril.get(peril, "low"), 0):
                by_peril[peril] = tier
                by_peril_detail[peril] = {"tier": tier,
                                          "annual_probability": _peril_annual_probability(peril, r.get("zone"))}
    rank_to_tier = {v: k for k, v in TIER_RANK.items()}
    # worst_tier only from tiers actually fetched — un-geocoded buildings (no peril
    # rows) report None, not a misleading "low".
    worst_rank = max(present_ranks) if present_ranks else None
    severe_high = sum(1 for b in buildings.values() if b["worst"] >= TIER_RANK["high"])
    return {
        "worst_tier": rank_to_tier[worst_rank] if worst_rank is not None else None,
        "worst_peril": (worst_key[2] or None) if worst_key is not None else None,
        "worst_peril_documented": worst_key[1] if worst_key is not None else None,
        "by_peril": by_peril,
        "by_peril_detail": by_peril_detail,
        "documented_probability_perils": list(DOCUMENTED_PROBABILITY_PERILS),
        "severe_high_count": severe_high,
        "buildings_total": len(buildings),
        "buildings_geocoded": sum(1 for b in buildings.values() if b["geocoded"]),
    }


async def company_cat_exposure(conn, company_id: UUID) -> dict:
    """One-query catastrophe rollup for a company's whole SOV."""
    rows = await conn.fetch(
        """
        SELECT b.id AS building_id, b.lat, p.peril, p.tier, p.score, p.zone
        FROM company_property_buildings b
        LEFT JOIN property_building_perils p
          ON p.building_id = b.id AND p.error IS NULL
        WHERE b.company_id = $1
        """,
        company_id,
    )
    return summarize([dict(r) for r in rows])


async def book_cat_exposure(conn, company_ids: list) -> dict[str, dict]:
    """Batched catastrophe rollup per company → {company_id_str: summary}. One query
    across the whole broker book for the property-portfolio."""
    ids = list({c for c in company_ids})
    if not ids:
        return {}
    rows = await conn.fetch(
        """
        SELECT b.company_id, b.id AS building_id, b.lat, p.peril, p.tier, p.score, p.zone
        FROM company_property_buildings b
        LEFT JOIN property_building_perils p
          ON p.building_id = b.id AND p.error IS NULL
        WHERE b.company_id = ANY($1::uuid[])
        """,
        ids,
    )
    by: dict[str, list[dict]] = {}
    for r in rows:
        by.setdefault(str(r["company_id"]), []).append(dict(r))
    return {cid: summarize(rs) for cid, rs in by.items()}
