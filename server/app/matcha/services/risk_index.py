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


async def _wc_component(conn, company_id: UUID):
    """(score, detail) from WC posture, or None when it can't be assessed."""
    from ..routes.ir_incidents.analytics import compute_wc_metrics  # lazy: route module
    m = await compute_wc_metrics(conn, company_id)
    sb = m.get("severity_band")
    if sb in _WC_BAND_SCORE:
        base = float(_WC_BAND_SCORE[sb])
        detail = f"TRIR {m.get('trir')} ({sb.replace('_', ' ')} vs benchmark)"
    elif m.get("ever_recordable") is False:
        base, detail = 85.0, "No recordable injuries on file"
    else:
        return None  # has injuries but no benchmark → can't band
    emr = (await wc_depth.latest_mods(conn, [company_id])).get(str(company_id), {}).get("experience_mod")
    if emr is not None:
        if emr > 1.0:
            base -= min(40.0, (emr - 1.0) * 50)
        elif emr < 1.0:
            base += min(10.0, (1.0 - emr) * 20)
        detail += f"; EMR {emr:.2f}"
    return max(0, min(100, round(base))), detail


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


async def compute_risk_index(conn, company_id: UUID) -> dict:
    """Composite 0–100 index + band + component breakdown + top fixes."""
    components: list[dict] = []

    wc = await _wc_component(conn, company_id)
    if wc is not None:
        components.append({"key": "wc", "label": "Workers' Comp", "weight": _WEIGHTS["wc"],
                           "score": wc[0], "detail": wc[1]})

    epl = await epl_readiness.compute_epl_readiness(conn, company_id)
    components.append({"key": "epl", "label": "EPL readiness", "weight": _WEIGHTS["epl"],
                       "score": epl["score"], "detail": f"{epl['score']}/100 ({epl['band']})"})

    comp = await _compliance_component(conn, company_id)
    if comp is not None:
        components.append({"key": "compliance", "label": "Compliance coverage", "weight": _WEIGHTS["compliance"],
                           "score": comp[0], "detail": comp[1]})

    total_w = sum(c["weight"] for c in components)
    index = round(sum(c["score"] * c["weight"] for c in components) / total_w) if total_w else None
    return {
        "company_id": str(company_id),
        "index": index,
        "band": band(index) if index is not None else None,
        "components": components,
        "top_fixes": _top_fixes(components, epl),
    }
