"""Property risk-improvement plan — turns the Statement of Values + catastrophe tiers
+ modeled exposure into a PRIORITIZED, actionable fix list the business can work
(sprinkler the combustible building, true up insurance-to-value, review the
named-storm deductible, refresh an aged roof, document hood cleaning). Each fix
carries a grade-or-$ impact so the business sees what moving it is worth.

The property analog of the casualty action plans — pure (unit-tested, no DB);
ranked worst-first like ``risk_index._top_fixes``. Surfaced on /app/property and in
the broker submission packet.
"""

from datetime import date
from typing import Optional

from app.matcha.services.property_sov import cope_grade

_SEV_RANK = {"high": 3, "medium": 2, "low": 1}
_COMBUSTIBLE = {"frame", "joisted_masonry", "non_combustible"}
_COOKING_HINTS = ("restaurant", "cafe", "café", "kitchen", "food", "grill", "bakery", "deli", "cook", "dining")
_MAX_FIXES = 8


def _usd(n) -> str:
    n = float(n or 0)
    if abs(n) >= 1_000_000:
        return f"${n / 1_000_000:.1f}M".replace(".0M", "M")
    if abs(n) >= 1_000:
        return f"${round(n / 1_000)}K"
    return f"${round(n)}"


def _label(b: dict) -> str:
    return b.get("name") or (", ".join(p for p in (b.get("city"), b.get("state")) if p)) or "a building"


def _wind_tier(b: dict) -> Optional[str]:
    for p in (b.get("perils") or []):
        if p.get("peril") == "wind":
            return p.get("tier")
    return None


def build_plan(buildings: list[dict], rollup: Optional[dict] = None, cat: Optional[dict] = None,
               exposure: Optional[dict] = None, inspections: Optional[list] = None,
               current_year: Optional[int] = None) -> dict:
    """Prioritized property fixes. Pure. Each fix: {key, label, severity, detail, impact,
    building_id?, building_name?}. Ranked by severity then $ impact, capped at _MAX_FIXES."""
    yr = current_year or date.today().year
    ex_buildings = (exposure or {}).get("buildings") or {}
    raw: list[dict] = []  # carries a private _rank for sorting

    for b in buildings:
        bid = b.get("id")
        name = _label(b)
        bex = ex_buildings.get(bid, {})
        shortfall = bex.get("coinsurance_shortfall") or 0

        # 1) Sprinkler a combustible, un-sprinklered building → projected COPE lift.
        if not b.get("sprinklered") and (b.get("construction_type") in _COMBUSTIBLE):
            cur_g, cur_s = cope_grade(b, yr)
            new_g, new_s = cope_grade({**b, "sprinklered": True}, yr)
            sev = "high" if b.get("construction_type") == "frame" else "medium"
            raw.append({
                "key": "sprinkler", "building_id": bid, "building_name": name,
                "label": f"Add sprinklers — {name}", "severity": sev,
                "detail": f"Un-sprinklered {(b.get('construction_type') or '').replace('_', ' ')}; sprinklering is the largest single COPE lever — projects COPE {cur_g} ({cur_s}) → {new_g} ({new_s}).",
                "impact": f"COPE +{max(0, new_s - cur_s)}",
                "_rank": (new_s - cur_s),
            })

        # 2) Insurance-to-value below the 90% coinsurance floor.
        itv = b.get("itv_ratio")
        if itv is not None and itv < 0.90:
            sev = "high" if itv < 0.75 else "medium"
            raw.append({
                "key": "itv", "building_id": bid, "building_name": name,
                "label": f"True up insured value — {name}", "severity": sev,
                "detail": f"Insured to {round(itv * 100)}% of replacement cost; a 90% coinsurance clause would cut claim payments. Add ~{_usd(shortfall)} of insured value.",
                "impact": f"{_usd(shortfall)} shortfall",
                "_rank": shortfall,
            })

        # 3) Severe / high wind exposure → confirm a named-storm deductible.
        wt = _wind_tier(b)
        if wt in ("severe", "high"):
            raw.append({
                "key": "wind_deductible", "building_id": bid, "building_name": name,
                "label": f"Review named-storm deductible — {name}", "severity": "medium",
                "detail": f"{wt.title()} wind exposure; confirm a separate named-storm/wind deductible and that limits reflect the {_usd(bex.get('worst_pml'))} modeled PML.",
                "impact": f"{_usd(bex.get('worst_pml'))} PML",
                "_rank": bex.get("worst_pml") or 0,
            })

        # 4) Aged roof — wind/hail driver + underwriting debit.
        ry = b.get("roof_year")
        if ry and (yr - int(ry)) > 20:
            raw.append({
                "key": "roof", "building_id": bid, "building_name": name,
                "label": f"Address roof age — {name}", "severity": "low",
                "detail": f"Roof is ~{yr - int(ry)} years old; aged roofs drive wind/hail losses and underwriting debits.",
                "impact": f"{yr - int(ry)} yr roof",
                "_rank": 0,
            })

        # 5) Cooking occupancy → NFPA-96 hood/duct cleaning documentation.
        occ = (b.get("occupancy") or "").lower()
        if any(h in occ for h in _COOKING_HINTS):
            raw.append({
                "key": "nfpa96", "building_id": bid, "building_name": name,
                "label": f"Document hood/duct cleaning (NFPA-96) — {name}", "severity": "medium",
                "detail": "Commercial cooking is a top fire cause; confirm a Type-I hood and a scheduled NFPA-96 hood/duct cleaning record.",
                "impact": "fire control",
                "_rank": 0,
            })

    raw.sort(key=lambda f: (-_SEV_RANK.get(f["severity"], 0), -(f.get("_rank") or 0)))
    fixes = [{k: v for k, v in f.items() if k != "_rank"} for f in raw[:_MAX_FIXES]]
    by_sev = {s: sum(1 for f in raw if f["severity"] == s) for s in ("high", "medium", "low")}
    return {"fixes": fixes, "summary": {"total": len(raw), "by_severity": by_sev, "shown": len(fixes)}}
