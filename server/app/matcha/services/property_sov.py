"""Commercial-property Statement of Values (SOV) — per-building capture + rollups.

The property analog of the casualty data services. A company records its buildings
(COPE — construction / occupancy / protection / exposure — plus values), and this
computes the underwriting-relevant rollups:

  - **TIV** (total insured value) = building + contents + business-interruption,
  - **ITV** (insurance-to-value) = insured_value ÷ replacement_cost — the
    underinsurance signal property underwriters price on,
  - a **COPE grade** per building from construction quality + sprinklers +
    protection class + roof/building age.

Pure helpers (``cope_grade`` / ``itv_ratio`` / ``building_tiv`` / ``rollup`` —
unit-tested, no DB) + async CRUD wrappers that never raise. Catastrophe exposure
is layered on in Phase 3 (``property_cat``); this module is network-free.
"""

from datetime import date
from typing import Optional
from uuid import UUID

# Construction quality (ISO classes, fire-resistive best). Drives the COPE base.
CONSTRUCTION_GRADE = {
    "fire_resistive": 100,
    "modified_fire_resistive": 85,
    "masonry_non_combustible": 70,
    "non_combustible": 60,
    "joisted_masonry": 45,
    "frame": 25,
}
_DEFAULT_CONSTRUCTION = 50
_ITV_FLOOR = 0.90  # insured below this fraction of replacement cost = underinsured


def _num(v) -> Optional[float]:
    return float(v) if v is not None else None


def building_tiv(b: dict) -> float:
    """Total insured value for one building = building + contents + BI. Pure."""
    return float(sum((b.get(k) or 0) for k in ("building_value", "contents_value", "bi_value")))


def itv_ratio(insured_value, replacement_cost) -> Optional[float]:
    """Insurance-to-value = insured ÷ replacement cost (None when no RC on file). Pure.
    < 0.90 signals underinsurance (a coinsurance-penalty exposure)."""
    rc = float(replacement_cost) if replacement_cost else 0.0
    if rc <= 0:
        return None
    return round(float(insured_value or 0) / rc, 3)


def cope_grade(b: dict, current_year: int) -> tuple[str, int]:
    """Per-building COPE quality → (letter grade, 0-100 score). Pure.

    Base from construction class, then sprinkler / protection-class / roof-age /
    building-age adjustments. Higher = better risk."""
    score = float(CONSTRUCTION_GRADE.get((b.get("construction_type") or "").strip().lower(), _DEFAULT_CONSTRUCTION))
    score += 15 if b.get("sprinklered") else -10

    ppc = b.get("protection_class")
    try:
        ppc_n = int(str(ppc).strip()) if ppc not in (None, "") else None
    except (TypeError, ValueError):
        ppc_n = None
    if ppc_n is not None:
        score += (5.5 - ppc_n) * 2  # PPC 1 → +9, PPC 10 → -9

    roof_year = b.get("roof_year")
    if roof_year:
        roof_age = current_year - int(roof_year)
        if roof_age > 25:
            score -= 10
        elif roof_age > 15:
            score -= 5

    year_built = b.get("year_built")
    if year_built:
        age = current_year - int(year_built)
        if age > 50:
            score -= 8
        elif age > 30:
            score -= 4

    s = max(0, min(100, round(score)))
    grade = "A" if s >= 80 else "B" if s >= 65 else "C" if s >= 45 else "D"
    return grade, s


_WORST_GRADE_ORDER = {"D": 3, "C": 2, "B": 1, "A": 0}


def rollup(buildings: list[dict], current_year: int) -> dict:
    """Company-wide SOV rollup from per-building rows. Pure (unit-tested).

    Each input dict carries the raw SOV fields; this adds TIV, the value breakdown,
    the average/worst COPE grade, and the portfolio ITV + underinsured count."""
    n = len(buildings)
    if n == 0:
        return {
            "building_count": 0, "tiv": 0.0,
            "values": {"building": 0.0, "contents": 0.0, "bi": 0.0, "insured": 0.0, "replacement": 0.0},
            "avg_cope_score": None, "worst_cope_grade": None,
            "itv": {"portfolio_ratio": None, "under_count": 0, "rated_count": 0},
        }
    tiv = sum(building_tiv(b) for b in buildings)
    vb = {
        "building": float(sum((b.get("building_value") or 0) for b in buildings)),
        "contents": float(sum((b.get("contents_value") or 0) for b in buildings)),
        "bi": float(sum((b.get("bi_value") or 0) for b in buildings)),
        "insured": float(sum((b.get("insured_value") or 0) for b in buildings)),
        "replacement": float(sum((b.get("replacement_cost") or 0) for b in buildings)),
    }
    cope = [cope_grade(b, current_year) for b in buildings]
    avg_score = round(sum(s for _, s in cope) / n)
    worst_grade = max((g for g, _ in cope), key=lambda g: _WORST_GRADE_ORDER[g])

    rated = [b for b in buildings if (b.get("replacement_cost") or 0) > 0]
    under = sum(1 for b in rated if (itv_ratio(b.get("insured_value"), b.get("replacement_cost")) or 1) < _ITV_FLOOR)
    portfolio_itv = round(vb["insured"] / vb["replacement"], 3) if vb["replacement"] > 0 else None
    return {
        "building_count": n, "tiv": round(tiv, 2), "values": {k: round(v, 2) for k, v in vb.items()},
        "avg_cope_score": avg_score, "worst_cope_grade": worst_grade,
        "itv": {"portfolio_ratio": portfolio_itv, "under_count": under, "rated_count": len(rated)},
    }


# --- DB layer (async; callers own the connection) --------------------------

_COLS = (
    "id, company_id, location_id, name, address, city, state, zipcode, county, occupancy, "
    "construction_type, year_built, sq_ft, stories, roof_year, sprinklered, protection_class, "
    "building_value, contents_value, bi_value, replacement_cost, insured_value, "
    "lat, lng, geocoded_at, geocode_source, cat_refreshed_at, note, created_at, updated_at"
)


def _serialize(r, current_year: int) -> dict:
    b = {
        "id": str(r["id"]),
        "company_id": str(r["company_id"]),
        "location_id": str(r["location_id"]) if r["location_id"] else None,
        "name": r["name"], "address": r["address"], "city": r["city"], "state": r["state"],
        "zipcode": r["zipcode"], "county": r["county"], "occupancy": r["occupancy"],
        "construction_type": r["construction_type"], "year_built": r["year_built"],
        "sq_ft": r["sq_ft"], "stories": r["stories"], "roof_year": r["roof_year"],
        "sprinklered": r["sprinklered"], "protection_class": r["protection_class"],
        "building_value": _num(r["building_value"]), "contents_value": _num(r["contents_value"]),
        "bi_value": _num(r["bi_value"]), "replacement_cost": _num(r["replacement_cost"]),
        "insured_value": _num(r["insured_value"]),
        "lat": _num(r["lat"]), "lng": _num(r["lng"]),
        "geocoded_at": r["geocoded_at"].isoformat() if r["geocoded_at"] else None,
        "geocode_source": r["geocode_source"],
        "cat_refreshed_at": r["cat_refreshed_at"].isoformat() if r["cat_refreshed_at"] else None,
        "note": r["note"],
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
    }
    grade, score = cope_grade(b, current_year)
    b["cope_grade"] = grade
    b["cope_score"] = score
    b["tiv"] = round(building_tiv(b), 2)
    b["itv_ratio"] = itv_ratio(b.get("insured_value"), b.get("replacement_cost"))
    return b


async def list_buildings(conn, company_id: UUID) -> list[dict]:
    rows = await conn.fetch(
        f"SELECT {_COLS} FROM company_property_buildings WHERE company_id = $1 "
        "ORDER BY (building_value + COALESCE(contents_value,0) + COALESCE(bi_value,0)) DESC NULLS LAST, name",
        company_id,
    )
    yr = date.today().year
    return [_serialize(r, yr) for r in rows]


_FIELDS = [
    "location_id", "name", "address", "city", "state", "zipcode", "county", "occupancy",
    "construction_type", "year_built", "sq_ft", "stories", "roof_year", "sprinklered",
    "protection_class", "building_value", "contents_value", "bi_value", "replacement_cost",
    "insured_value", "note",
]


async def upsert_building(conn, company_id: UUID, building_id, data: dict, user_id) -> Optional[dict]:
    """Insert (building_id None) or update an owned building. Returns the row, or
    None when updating a building the company doesn't own. Geocode/cat columns are
    deliberately untouched here — the Phase-3 task owns them."""
    vals = {k: data.get(k) for k in _FIELDS}
    if building_id:
        owned = await conn.fetchval(
            "SELECT 1 FROM company_property_buildings WHERE id = $1 AND company_id = $2",
            building_id, company_id,
        )
        if not owned:
            return None
        sets = ", ".join(f"{f} = ${i + 3}" for i, f in enumerate(_FIELDS))
        row = await conn.fetchrow(
            f"UPDATE company_property_buildings SET {sets}, updated_by = $2, updated_at = NOW() "
            f"WHERE id = $1 RETURNING {_COLS}",
            building_id, user_id, *[vals[f] for f in _FIELDS],
        )
    else:
        cols = ", ".join(_FIELDS)
        ph = ", ".join(f"${i + 3}" for i in range(len(_FIELDS)))
        row = await conn.fetchrow(
            f"INSERT INTO company_property_buildings (company_id, created_by, updated_by, {cols}) "
            f"VALUES ($1, $2, $2, {ph}) RETURNING {_COLS}",
            company_id, user_id, *[vals[f] for f in _FIELDS],
        )
    return _serialize(row, date.today().year)


async def delete_building(conn, company_id: UUID, building_id) -> bool:
    res = await conn.execute(
        "DELETE FROM company_property_buildings WHERE id = $1 AND company_id = $2",
        building_id, company_id,
    )
    return res.split()[-1] != "0"


async def _perils_by_building(conn, building_ids: list[str]) -> dict[str, list[dict]]:
    """Per-building cat perils (empty until Phase 3 writes them)."""
    if not building_ids:
        return {}
    rows = await conn.fetch(
        "SELECT building_id, peril, zone, score, tier, source, fetched_at, error "
        "FROM property_building_perils WHERE building_id = ANY($1::uuid[])",
        [UUID(b) for b in building_ids],
    )
    out: dict[str, list[dict]] = {}
    for r in rows:
        out.setdefault(str(r["building_id"]), []).append({
            "peril": r["peril"], "zone": r["zone"], "score": r["score"], "tier": r["tier"],
            "source": r["source"], "error": r["error"],
            "fetched_at": r["fetched_at"].isoformat() if r["fetched_at"] else None,
        })
    return out


async def build_sov(conn, company_id: UUID) -> dict:
    """Full Statement-of-Values payload: buildings (with COPE/ITV/perils) + rollup."""
    buildings = await list_buildings(conn, company_id)
    perils = await _perils_by_building(conn, [b["id"] for b in buildings])
    for b in buildings:
        b["perils"] = perils.get(b["id"], [])
    return {
        "company_id": str(company_id),
        "buildings": buildings,
        "rollup": rollup(buildings, date.today().year),
    }
