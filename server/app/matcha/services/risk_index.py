"""Composite client risk index — one 0–100 rolling up the WC, EPL,
compliance, and (when enabled) commercial-property engines Matcha already
computes (higher = lower risk, matching the EPL convention). The report's
"Risk Index Model" / "Risk Intelligence Central" (WTW p.10, p.29). A weighted
roll-up of existing component scores (the property component adds catastrophe
tiers, ITV, and loss-development inputs).

Used by the broker portfolio (one benchmarkable number per client) and the
client-facing risk portal (the business's own insurability at a glance).
"""

import logging
from datetime import date
from typing import Optional
from uuid import UUID

import asyncpg

from . import epl_readiness, wc_depth

logger = logging.getLogger(__name__)

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

# Confidence weighting for the property component's penalties — a cat tier or
# loss-dev signal resting on documented/high-confidence data counts at full
# weight; one resting on a directional baseline or thin history is discounted,
# not dropped (the exposure is still real, just less precisely known).
_CONF_RANK = {"low": 0, "moderate": 1, "high": 2}
_CAT_PENALTY_WEIGHT = {True: 1.0, False: 0.7}  # keyed by "documented?"
_LOSS_PENALTY_WEIGHT = {"high": 1.0, "moderate": 0.8, "low": 0.6}


def _worst_conf(confs: list) -> str:
    ranked = [c for c in confs if c in _CONF_RANK]
    return min(ranked, key=lambda c: _CONF_RANK[c]) if ranked else "high"


def _cat_is_documented(cat: dict) -> bool:
    """False ONLY when property_cat explicitly marked the worst tier as coming
    from a directional baseline (wildfire/wind, via ``worst_peril_documented``).
    Hazard-agency perils (flood AND quake — quake's tier is a real USGS reading
    even though it deliberately carries no annual probability) count at full
    weight. So does an ABSENT signal (broker-attested off-platform snapshots,
    legacy dicts): the discount is for model-derived guesses, not for missing
    metadata."""
    return cat.get("worst_peril_documented") is not False


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


async def _wc_reserve_confidence(conn, company_id: UUID) -> str:
    """Confidence of the company's WC loss-run reserve projection, folded into
    the WC component so a client whose reserves are volatile (thin/holed
    triangle) doesn't read high-confidence in the composite. "high" when there's
    no loss-run triangle — no volatility signal to downgrade, same as the WC
    metrics' own current-state read. Best-effort: degrades to a conservative
    "low" on unexpected failure rather than inflating the composite to "high"."""
    try:
        from . import loss_development
        snaps = await loss_development.list_company_snapshots(conn, company_id, line="wc")
        if not snaps:
            return "high"
        wc_line = next((ln for ln in loss_development.build_triangle(snaps)["lines"]
                        if ln["line"] == "wc"), None)
        return wc_line["summary"]["reserve_confidence"] if wc_line else "high"
    except (asyncpg.UndefinedTableError, asyncpg.UndefinedColumnError):
        # Loss-run table not provisioned yet — genuinely no volatility signal.
        return "high"
    except Exception:
        # A real loss_development failure must not silently read as high
        # confidence in an underwriting-facing index.
        logger.exception("reserve_confidence failed for %s — defaulting low", company_id)
        return "low"


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
    if gap:
        msg = f"EPL: address {gap['label'].lower()}"
        # Don't stack the specific EPL sub-gap on top of a generic "raise EPL
        # readiness" line already emitted from the epl component. (The old guard
        # compared differently-formatted strings and so never fired.)
        already_flags_epl = msg in fixes or any("epl" in f.lower() for f in fixes)
        if not already_flags_epl:
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
        # Worst confidence across scored components. WC/EPL/compliance have no
        # variance model yet (default "high"); property's flows from its own
        # cat/loss-dev documentation. NOT an index_low/index_high range — that
        # would need every component to carry real variance, not just property.
        "index_confidence": _worst_conf([c.get("confidence", "high") for c in components]),
    }


def _epl_component(epl: dict) -> dict:
    return {"key": "epl", "label": "EPL readiness", "weight": _WEIGHTS["epl"],
            "score": epl["score"], "detail": f"{epl['score']}/100 ({epl['band']})", "confidence": "high"}


# Catastrophe penalty is CAPPED (exposure leaking into posture) so a well-built
# building in a flood zone isn't scored as uninsurable. COPE + ITV are the posture.
_CAT_PENALTY = {"severe": 15, "high": 10, "elevated": 5, "moderate": 0, "low": 0}


def _property_score(rollup: Optional[dict], cat: Optional[dict] = None,
                    loss: Optional[dict] = None) -> Optional[tuple[int, str, str]]:
    """Property sub-score (0-100, detail, confidence) from the SOV rollup. Pure
    (unit-tested).

    Posture = COPE quality, penalized by under-insurance (ITV) and — capped — by
    catastrophe tier and adverse property-loss development. None when there are no
    buildings to assess.

    ``confidence`` reflects how well-documented the cat/loss-dev signals are:
    a hazard-agency cat tier (flood/quake — see _cat_is_documented), or a
    loss-dev reserve with a real Mack's-method CI, count at full penalty
    weight; a directional wildfire/wind baseline or a thin loss-run history
    are discounted (still penalized — the exposure is real — just less
    precisely known) and drag the reported confidence down."""
    if not rollup or not rollup.get("building_count"):
        return None
    base = rollup.get("avg_cope_score")
    if base is None:
        return None
    score = float(base)
    bits = [f"COPE {base}/100"]
    confs: list[str] = []

    itv = rollup.get("itv") or {}
    ratio = itv.get("portfolio_ratio")
    if ratio is not None:
        if ratio < 0.90:
            score -= min(25, round((0.90 - ratio) * 100))
        under = itv.get("under_count") or 0
        bits.append(f"ITV {round(ratio * 100)}%" + (f", {under} under-insured" if under else ""))

    worst = (cat or {}).get("worst_tier")
    if worst:
        base_penalty = _CAT_PENALTY.get(worst, 0)
        if base_penalty > 0:
            documented = _cat_is_documented(cat or {})
            score -= round(base_penalty * _CAT_PENALTY_WEIGHT[documented])
            bits.append(f"cat {worst}" + ("" if documented else " (directional)"))
            confs.append("high" if documented else "moderate")
        else:
            # low/moderate tiers contribute 0 points — they must not drag the
            # component's confidence either.
            bits.append(f"cat {worst}")

    if loss and loss.get("adverse_penalty"):
        loss_conf = loss.get("confidence", "low")
        weight = _LOSS_PENALTY_WEIGHT.get(loss_conf, _LOSS_PENALTY_WEIGHT["low"])
        score -= round(min(15, loss["adverse_penalty"]) * weight)
        bits.append("adverse loss dev" + ("" if loss_conf == "high" else f" ({loss_conf} confidence)"))
        confs.append(loss_conf)

    return max(0, min(100, round(score))), "; ".join(bits), _worst_conf(confs)


async def _property_component(conn, company_id: UUID):
    """Tenant property sub-score from the Statement of Values. None when no buildings.
    Catastrophe is wired via ``property_cat.company_cat_exposure``; adverse loss
    development via the company's own property loss-run triangle.

    Best-effort: degrades to None if the property tables aren't present yet (migration
    lag on a server that has the code but not ``prop01``) so the composite index never
    500s. The loss-development lookup gets the same best-effort treatment — a bad
    triangle degrades the loss signal, not the whole component."""
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
    """Composite 0–100 index for an on-platform (tenant) client: WC + EPL +
    compliance, plus commercial property when that feature is enabled."""
    from app.core.feature_flags import merge_company_features

    company = await conn.fetchrow(
        "SELECT enabled_features, signup_source FROM companies WHERE id = $1", company_id
    )
    features = merge_company_features(
        company["enabled_features"] if company else None,
        signup_source=company["signup_source"] if company else None,
    )
    # Property is a default-off, unbundled module — a company without it can
    # never produce the property component, so it must not sit in the universe
    # (otherwise coverage is permanently < 1.0 with an unactionable "missing"
    # component). WC/EPL/compliance are universal.
    property_enabled = bool(features.get("property"))
    universe = ("wc", "epl", "compliance", "property") if property_enabled else ("wc", "epl", "compliance")

    components: list[dict] = []

    wc = await _wc_component(conn, company_id)
    if wc is not None:
        wc_conf = await _wc_reserve_confidence(conn, company_id)
        detail = wc[1] if wc_conf == "high" else f"{wc[1]}; reserves {wc_conf} confidence"
        components.append({"key": "wc", "label": "Workers' Comp", "weight": _WEIGHTS["wc"],
                           "score": wc[0], "detail": detail, "confidence": wc_conf})

    epl = await epl_readiness.compute_epl_readiness(conn, company_id)
    components.append(_epl_component(epl))

    comp = await _compliance_component(conn, company_id)
    if comp is not None:
        components.append({"key": "compliance", "label": "Compliance coverage", "weight": _WEIGHTS["compliance"],
                           "score": comp[0], "detail": comp[1], "confidence": "high"})

    if property_enabled:
        prop = await _property_component(conn, company_id)
        if prop is not None:
            components.append({"key": "property", "label": "Commercial Property", "weight": _WEIGHTS["property"],
                               "score": prop[0], "detail": prop[1], "confidence": prop[2]})

    return {"company_id": str(company_id),
            **_assemble(components, epl, universe=universe)}


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
    confidence_mix = {c: 0.0 for c in _CONF_RANK}
    if total_weight > 0:
        for c, w in zip(scored, weights):
            if c.get("band") in band_mix:
                band_mix[c["band"]] += w / total_weight
            conf = c.get("confidence") or c.get("index_confidence")
            if conf in confidence_mix:
                confidence_mix[conf] += w / total_weight
        band_mix = {b: round(v, 4) for b, v in band_mix.items()}
        confidence_mix = {c: round(v, 4) for c, v in confidence_mix.items()}

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
        # share of weighted book resting on each confidence tier — clients missing
        # a confidence signal don't count toward any bucket, mirroring band_mix's
        # own missing-band handling.
        "confidence_mix": confidence_mix,
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
        # WC reserve confidence rides on the wc dict (caller folds in the loss-run
        # triangle's reserve_confidence); "high" when no loss runs — no volatility
        # signal to downgrade. Same treatment as the tenant path.
        wc_conf = wc.get("reserve_confidence") or "high"
        detail = s[1] if wc_conf == "high" else f"{s[1]}; reserves {wc_conf} confidence"
        components.append({"key": "wc", "label": "Workers' Comp", "weight": _WEIGHTS["wc"],
                           "score": s[0], "detail": detail, "confidence": wc_conf})
    components.append(_epl_component(epl))
    if prop is not None:
        ps = _property_score(prop.get("rollup"), prop.get("cat"), None)
        if ps is not None:
            components.append({"key": "property", "label": "Commercial Property",
                               "weight": _WEIGHTS["property"], "score": ps[0], "detail": ps[1],
                               "confidence": ps[2]})
    return _assemble(components, epl, universe=("wc", "epl", "property"))
