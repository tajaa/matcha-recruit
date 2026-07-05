"""Composite client risk index — one 0–100 rolling up the WC, EPL, and
compliance engines Matcha already computes (higher = lower risk, matching the
EPL convention). The report's "Risk Index Model" / "Risk Intelligence Central"
(WTW p.10, p.29). No new data — a weighted roll-up of existing scores.

Used by the broker portfolio (one benchmarkable number per client) and the
client-facing risk portal (the business's own insurability at a glance).
"""

from datetime import date
from typing import Optional
from uuid import UUID

from . import epl_readiness, wc_depth

# severity_band → sub-score (lower band = higher risk = lower score)
_WC_BAND_SCORE = {"good": 90, "fair": 70, "at_risk": 45, "critical": 20}

# component weights (renormalized over whichever components have data)
_WEIGHTS = {"wc": 40, "epl": 35, "compliance": 25, "property": 30}

# (label, weight) per component key — lets _assemble name components that are
# ABSENT (no data to score), not just report on the ones present.
_COMPONENT_META = {
    "wc": ("Workers' Comp", _WEIGHTS["wc"]),
    "epl": ("EPL readiness", _WEIGHTS["epl"]),
    "compliance": ("Compliance coverage", _WEIGHTS["compliance"]),
    "property": ("Commercial Property", _WEIGHTS["property"]),
}

# re-export the EPL band thresholds (≥80 strong / ≥60 adequate / ≥35 developing / <35 exposed)
band = epl_readiness.readiness_band


def _wc_score(severity_band, emr, ever_recordable, trir=None):
    """Pure WC sub-score (score, detail) from band + mod, or None when it can't
    be assessed. Shared by the tenant and off-platform paths."""
    if severity_band in _WC_BAND_SCORE:
        base = float(_WC_BAND_SCORE[severity_band])
        detail = f"TRIR {trir} ({severity_band.replace('_', ' ')} vs benchmark)" if trir is not None \
            else f"{severity_band.replace('_', ' ')} vs benchmark"
    elif ever_recordable is False:
        base, detail = 85.0, "No recordable injuries on file"
    else:
        return None  # has injuries but no benchmark → can't band
    if emr is not None:
        if emr > 1.0:
            base -= min(40.0, (emr - 1.0) * 50)
        elif emr < 1.0:
            base += min(10.0, (1.0 - emr) * 20)
        detail += f"; EMR {emr:.2f}"
    return max(0, min(100, round(base))), detail


async def _wc_component(conn, company_id: UUID):
    """Tenant WC sub-score — pulls metrics + latest mod, then scores."""
    from ..routes.ir_incidents.analytics import compute_wc_metrics  # lazy: route module
    m = await compute_wc_metrics(conn, company_id)
    emr = (await wc_depth.latest_mods(conn, [company_id])).get(str(company_id), {}).get("experience_mod")
    return _wc_score(m.get("severity_band"), emr, m.get("ever_recordable"), trir=m.get("trir"))


async def _compliance_component(conn, company_id: UUID):
    """(score, detail) = share of the company's active locations with CURRENT
    (non-expired) compliance requirements tracked, or None when there are no
    locations. A location whose only requirements have lapsed doesn't count as
    covered — mirrors the expiration-filter idiom in epl_readiness's wage_hour
    factor, generalized to all categories."""
    row = await conn.fetchrow(
        """
        SELECT COUNT(DISTINCT bl.id) AS locs,
               COUNT(DISTINCT bl.id) FILTER (WHERE cr.cnt > 0) AS covered
        FROM business_locations bl
        LEFT JOIN LATERAL (
            SELECT COUNT(*) AS cnt FROM compliance_requirements cr
            WHERE cr.location_id = bl.id
              AND (cr.expiration_date IS NULL OR cr.expiration_date > CURRENT_DATE)
        ) cr ON true
        WHERE bl.company_id = $1 AND COALESCE(bl.is_active, true) = true
        """,
        company_id,
    )
    locs = int(row["locs"] or 0)
    if locs == 0:
        return None
    covered = int(row["covered"] or 0)
    return round(100 * covered / locs), f"{covered}/{locs} locations with compliance tracked"


def _top_fixes(components: list[dict], epl: dict) -> list[str]:
    # Rank by weight × shortfall (points actually at stake), not raw score — a
    # heavy component barely below the bar can cost more than a light one deep in
    # the red. Same formula as epl_readiness.top_gap.
    weak = sorted(
        (c for c in components if c["score"] < 70),
        key=lambda c: c["weight"] * (100 - c["score"]),
        reverse=True,
    )
    fixes = [f"Raise {c['label'].lower()} ({c['score']}/100)" for c in weak][:3]
    gap = epl_readiness.top_gap(epl)
    if gap and (msg := f"EPL: address {gap['label'].lower()}") not in fixes:
        fixes.append(msg)
    return fixes[:4]


def _assemble(components: list[dict], epl: dict,
              universe: tuple[str, ...] = ("wc", "epl", "compliance", "property")) -> dict:
    """Renormalize whichever components have data into a composite + band + fixes.

    ``universe`` is the full set of components this caller could ever produce
    (tenant vs. off-platform differ — see callers). ``coverage`` is the share of
    that universe's weight actually present, and ``components_missing`` names
    what's absent, so a thin index (e.g. EPL-only) isn't presented with the same
    confidence as a fully-assessed one."""
    total_w = sum(c["weight"] for c in components)
    index = round(sum(c["score"] * c["weight"] for c in components) / total_w) if total_w else None
    universe_weight = sum(_COMPONENT_META[k][1] for k in universe)
    present = {c["key"] for c in components}
    components_missing = [
        {"key": k, "label": _COMPONENT_META[k][0], "weight": _COMPONENT_META[k][1]}
        for k in universe if k not in present
    ]
    return {
        "index": index,
        "band": band(index) if index is not None else None,
        "components": components,
        "top_fixes": _top_fixes(components, epl),
        "coverage": round(total_w / universe_weight, 2) if universe_weight else None,
        "components_missing": components_missing,
    }


def _epl_component(epl: dict) -> dict:
    return {"key": "epl", "label": "EPL readiness", "weight": _WEIGHTS["epl"],
            "score": epl["score"], "detail": f"{epl['score']}/100 ({epl['band']})"}


# Catastrophe penalty is CAPPED (exposure leaking into posture) so a well-built
# building in a flood zone isn't scored as uninsurable. COPE + ITV are the posture.
_CAT_PENALTY = {"severe": 15, "high": 10, "elevated": 5, "moderate": 0, "low": 0}


def _property_score(rollup: Optional[dict], cat: Optional[dict] = None,
                    loss: Optional[dict] = None) -> Optional[tuple[int, str]]:
    """Property sub-score (0-100, detail) from the SOV rollup. Pure (unit-tested).

    Posture = COPE quality, penalized by under-insurance (ITV) and — capped — by
    catastrophe tier and adverse property-loss development. None when there are no
    buildings to assess."""
    if not rollup or not rollup.get("building_count"):
        return None
    base = rollup.get("avg_cope_score")
    if base is None:
        return None
    score = float(base)
    bits = [f"COPE {base}/100"]

    itv = rollup.get("itv") or {}
    ratio = itv.get("portfolio_ratio")
    if ratio is not None:
        if ratio < 0.90:
            score -= min(25, round((0.90 - ratio) * 100))
        under = itv.get("under_count") or 0
        bits.append(f"ITV {round(ratio * 100)}%" + (f", {under} under-insured" if under else ""))

    worst = (cat or {}).get("worst_tier")
    if worst:
        score -= _CAT_PENALTY.get(worst, 0)
        bits.append(f"cat {worst}")

    if loss and loss.get("adverse_penalty"):
        score -= min(15, loss["adverse_penalty"])
        bits.append("adverse loss dev")

    return max(0, min(100, round(score))), "; ".join(bits)


async def _property_component(conn, company_id: UUID):
    """Tenant property sub-score from the Statement of Values. None when no buildings.
    Catastrophe is wired via ``property_cat.company_cat_exposure``; adverse loss
    development via the company's own property loss-run triangle.

    Best-effort: degrades to None if the property tables aren't present yet (migration
    lag on a server that has the code but not ``prop01``) so the composite index never
    500s. The loss-development lookup gets the same best-effort treatment — a bad
    triangle degrades the loss signal, not the whole component."""
    import asyncpg
    from . import property_sov  # lazy: avoid import cycle
    try:
        # list_buildings (1 query) + pure rollup — skip build_sov's per-building peril
        # fetch, which this composite path doesn't use (cat comes from the rollup query).
        buildings = await property_sov.list_buildings(conn, company_id)
    except asyncpg.exceptions.UndefinedTableError:
        return None
    if not buildings:
        return None
    rollup = property_sov.rollup(buildings, date.today().year)
    cat = None
    try:
        from . import property_cat
        cat = await property_cat.company_cat_exposure(conn, company_id)
    except (ImportError, AttributeError, asyncpg.exceptions.UndefinedTableError):
        cat = None
    loss = None
    try:
        from . import loss_development
        snaps = await loss_development.list_company_snapshots(conn, company_id, line="property")
        loss = loss_development.property_loss_signal(loss_development.build_triangle(snaps))
    except Exception:
        loss = None
    return _property_score(rollup, cat, loss)


async def compute_risk_index(conn, company_id: UUID) -> dict:
    """Composite 0–100 index for an on-platform (tenant) client: WC + EPL + compliance."""
    components: list[dict] = []

    wc = await _wc_component(conn, company_id)
    if wc is not None:
        components.append({"key": "wc", "label": "Workers' Comp", "weight": _WEIGHTS["wc"],
                           "score": wc[0], "detail": wc[1]})

    epl = await epl_readiness.compute_epl_readiness(conn, company_id)
    components.append(_epl_component(epl))

    comp = await _compliance_component(conn, company_id)
    if comp is not None:
        components.append({"key": "compliance", "label": "Compliance coverage", "weight": _WEIGHTS["compliance"],
                           "score": comp[0], "detail": comp[1]})

    prop = await _property_component(conn, company_id)
    if prop is not None:
        components.append({"key": "property", "label": "Commercial Property", "weight": _WEIGHTS["property"],
                           "score": prop[0], "detail": prop[1]})

    return {"company_id": str(company_id),
            **_assemble(components, epl, universe=("wc", "epl", "compliance", "property"))}


_BANDS = ("strong", "adequate", "developing", "exposed")


def weighted_book_risk(clients: list[dict], basis: str = "headcount") -> dict:
    """Exposure-weighted roll-up of a book's per-client risk indices. Pure (no DB).

    Each ``clients`` dict carries ``index`` (0-100), ``band``, ``headcount`` and
    ``annual_premium``. A client's weight is its ``basis`` field (``headcount`` or
    ``premium``→annual_premium); a missing/zero basis means weight 0 — the client is
    excluded from the weighted mean, band mix and curve width, but still counts in
    the equal-weight mean and is reported via ``missing_basis_count``.

    Canonical source of truth for the interactive book risk curve + any future
    submission-packet PDF (the client-side TS port in ``utils/bookRisk.ts`` mirrors
    this exactly — keep them in sync)."""
    field = "annual_premium" if basis == "premium" else "headcount"
    scored = [c for c in clients if c.get("index") is not None]
    weights = [float(c.get(field) or 0) for c in scored]
    total_weight = sum(weights)

    weighted_mean = (
        round(sum(c["index"] * w for c, w in zip(scored, weights)) / total_weight, 1)
        if total_weight > 0 else None
    )
    equal_weight_mean = round(sum(c["index"] for c in scored) / len(scored), 1) if scored else None

    band_mix = {b: 0.0 for b in _BANDS}
    if total_weight > 0:
        for c, w in zip(scored, weights):
            if c.get("band") in band_mix:
                band_mix[c["band"]] += w / total_weight
        band_mix = {b: round(v, 4) for b, v in band_mix.items()}

    return {
        "basis": basis,
        "weighted_mean": weighted_mean,
        "equal_weight_mean": equal_weight_mean,
        "weighted_band": band(round(weighted_mean)) if weighted_mean is not None else None,
        "total_weight": round(total_weight, 2),
        "scored_count": len(scored),
        "weighted_count": sum(1 for w in weights if w > 0),
        "missing_basis_count": sum(1 for w in weights if w <= 0),
        "band_mix": band_mix,
    }


def external_risk_index(wc: dict, epl: dict, prop: Optional[dict] = None) -> dict:
    """Composite index for an off-platform (Broker Pro) client from the broker-keyed
    WC snapshot + EPL questionnaire (+ optional property summary). Compliance is
    omitted (no location data for non-tenant clients); weights renormalize over
    whichever components have data. ``prop`` carries ``{rollup, cat}`` (Phase 4)."""
    components: list[dict] = []
    ever_recordable = (wc.get("recordable_cases") or 0) > 0
    s = _wc_score(wc.get("severity_band"), wc.get("current_emr"), ever_recordable,
                  trir=wc.get("trir")) if wc.get("has_data") else None
    if s is not None:
        components.append({"key": "wc", "label": "Workers' Comp", "weight": _WEIGHTS["wc"],
                           "score": s[0], "detail": s[1]})
    components.append(_epl_component(epl))
    if prop is not None:
        ps = _property_score(prop.get("rollup"), prop.get("cat"), None)
        if ps is not None:
            components.append({"key": "property", "label": "Commercial Property",
                               "weight": _WEIGHTS["property"], "score": ps[0], "detail": ps[1]})
    return _assemble(components, epl, universe=("wc", "epl", "property"))
