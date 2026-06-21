"""Composite client risk index — one 0–100 rolling up the WC, EPL, and
compliance engines Matcha already computes (higher = lower risk, matching the
EPL convention). The report's "Risk Index Model" / "Risk Intelligence Central"
(WTW p.10, p.29). No new data — a weighted roll-up of existing scores.

Used by the broker portfolio (one benchmarkable number per client) and the
client-facing risk portal (the business's own insurability at a glance).
"""

from uuid import UUID

from . import epl_readiness, wc_depth

# severity_band → sub-score (lower band = higher risk = lower score)
_WC_BAND_SCORE = {"good": 90, "fair": 70, "at_risk": 45, "critical": 20}

# component weights (renormalized over whichever components have data)
_WEIGHTS = {"wc": 40, "epl": 35, "compliance": 25}

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
    """(score, detail) = share of the company's active locations with compliance
    tracked, or None when there are no locations."""
    row = await conn.fetchrow(
        """
        SELECT COUNT(DISTINCT bl.id) AS locs,
               COUNT(DISTINCT cr.location_id) AS covered
        FROM business_locations bl
        LEFT JOIN compliance_requirements cr ON cr.location_id = bl.id
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
    fixes = [
        f"Raise {c['label'].lower()} ({c['score']}/100)"
        for c in sorted(components, key=lambda c: c["score"]) if c["score"] < 70
    ][:3]
    gap = epl_readiness.top_gap(epl)
    if gap and (msg := f"EPL: address {gap['label'].lower()}") not in fixes:
        fixes.append(msg)
    return fixes[:4]


def _assemble(components: list[dict], epl: dict) -> dict:
    """Renormalize whichever components have data into a composite + band + fixes."""
    total_w = sum(c["weight"] for c in components)
    index = round(sum(c["score"] * c["weight"] for c in components) / total_w) if total_w else None
    return {
        "index": index,
        "band": band(index) if index is not None else None,
        "components": components,
        "top_fixes": _top_fixes(components, epl),
    }


def _epl_component(epl: dict) -> dict:
    return {"key": "epl", "label": "EPL readiness", "weight": _WEIGHTS["epl"],
            "score": epl["score"], "detail": f"{epl['score']}/100 ({epl['band']})"}


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

    return {"company_id": str(company_id), **_assemble(components, epl)}


def external_risk_index(wc: dict, epl: dict) -> dict:
    """Composite index for an off-platform (Broker Pro) client from the broker-keyed
    WC snapshot + EPL questionnaire. WC + EPL only — no compliance component (no
    location data for non-tenant clients); weights renormalize over the two."""
    components: list[dict] = []
    ever_recordable = (wc.get("recordable_cases") or 0) > 0
    s = _wc_score(wc.get("severity_band"), wc.get("current_emr"), ever_recordable,
                  trir=wc.get("trir")) if wc.get("has_data") else None
    if s is not None:
        components.append({"key": "wc", "label": "Workers' Comp", "weight": _WEIGHTS["wc"],
                           "score": s[0], "detail": s[1]})
    components.append(_epl_component(epl))
    return _assemble(components, epl)
