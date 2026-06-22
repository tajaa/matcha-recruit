"""Venue / nuclear-verdict severity — the casualty exposure dimension.

We already own the exposure geography (`business_locations.state`/`county`); this
joins it to the curated `venue_severity` reference (seeded from free public
sources) to flag plaintiff-friendly / nuclear-verdict venues per client location.
Surfaced in the submission packet + risk profile — NOT folded into the composite
risk index, because venue is exposure (where you are) not posture (what you
control). Severity is a directional reputational flag, not an actuarial price.
"""

from uuid import UUID

_TIER_RANK = {"severe": 5, "high": 4, "elevated": 3, "moderate": 2, "low": 1, "unknown": 0}


def _norm_county(c) -> str:
    """Normalize a county string for matching: lower, drop a trailing 'county'."""
    s = (c or "").strip().lower()
    if s.endswith(" county"):
        s = s[: -len(" county")].strip()
    if s.endswith(" parish"):  # Louisiana
        s = s[: -len(" parish")].strip()
    return s


def resolve_tier(state_rows: list[dict], county) -> dict | None:
    """Pure: pick the county-specific row, else the state baseline (county=''), from
    the venue_severity rows for one state. Returns the row dict or None."""
    if not state_rows:
        return None
    nc = _norm_county(county)
    if nc:
        for r in state_rows:
            if r["county"] and _norm_county(r["county"]) == nc:
                return r
    for r in state_rows:
        if not r["county"]:
            return r
    return None


def summarize(locations: list[dict]) -> dict:
    """Pure rollup over per-location severities → worst tier/score + counts."""
    rated = [l for l in locations if l.get("tier") and l["tier"] != "unknown"]
    worst = max(rated, key=lambda l: _TIER_RANK.get(l["tier"], 0), default=None)
    counts: dict[str, int] = {}
    for l in locations:
        counts[l.get("tier") or "unknown"] = counts.get(l.get("tier") or "unknown", 0) + 1
    return {
        "worst_tier": worst["tier"] if worst else "unknown",
        "worst_score": worst["score"] if worst else None,
        "severe_high_count": sum(1 for l in locations if l.get("tier") in ("severe", "high")),
        "rated_locations": len(rated),
        "total_locations": len(locations),
        "tier_counts": counts,
    }


async def company_venue_exposure(conn, company_id: UUID) -> dict:
    """Per-location venue severity for a tenant + a rollup. Never raises (best-effort)."""
    locs = await conn.fetch(
        "SELECT city, state, county FROM business_locations "
        "WHERE company_id = $1 AND COALESCE(is_active, true) = true",
        company_id,
    )
    states = sorted({(l["state"] or "").upper() for l in locs if l["state"]})
    by_state: dict[str, list[dict]] = {}
    if states:
        rows = await conn.fetch(
            "SELECT state, county, tier, score, source, note FROM venue_severity WHERE state = ANY($1)",
            states,
        )
        for r in rows:
            by_state.setdefault(r["state"], []).append(dict(r))

    locations: list[dict] = []
    for l in locs:
        st = (l["state"] or "").upper()
        hit = resolve_tier(by_state.get(st, []), l["county"])
        locations.append({
            "city": l["city"], "state": st, "county": l["county"],
            "tier": hit["tier"] if hit else "unknown",
            "score": hit["score"] if hit else None,
            "source": hit["source"] if hit else None,
            "note": hit["note"] if hit else None,
        })
    # worst-venue first for display
    locations.sort(key=lambda l: _TIER_RANK.get(l["tier"], 0), reverse=True)
    return {"locations": locations, "summary": summarize(locations)}


async def state_venue(conn, state) -> dict:
    """State-baseline severity for off-platform clients (primary_state only, no counties)."""
    st = (state or "").upper()
    if not st:
        return {"locations": [], "summary": summarize([])}
    rows = await conn.fetch(
        "SELECT state, county, tier, score, source, note FROM venue_severity WHERE state = $1", st
    )
    hit = resolve_tier([dict(r) for r in rows], None)
    loc = {
        "city": None, "state": st, "county": None,
        "tier": hit["tier"] if hit else "unknown",
        "score": hit["score"] if hit else None,
        "source": hit["source"] if hit else None,
        "note": hit["note"] if hit else None,
    }
    return {"locations": [loc], "summary": summarize([loc])}
