"""Composite property risk assessment — one 0-100 score + grade per building and for the
whole portfolio, fusing COPE quality + insurance-to-value + catastrophe exposure into the
single underwriting number a business hands to its broker/carrier.

Higher score = better risk posture (same convention as ``risk_index``). The building-
granular companion to ``risk_index._property_score`` (which feeds the cross-line composite
index from the rollup); both are COPE-anchored and apply the same ITV + catastrophe
penalties. Pure (unit-tested, no DB / no network).
"""

from typing import Optional

from app.matcha.services.property_sov import building_tiv

# Catastrophe posture penalty by worst peril tier (capped — exposure isn't the same as a
# bad building; a well-built structure in a flood zone shouldn't read as uninsurable).
_CAT_PENALTY = {"severe": 22, "high": 15, "elevated": 8, "moderate": 3, "low": 0}
_TIER_RANK = {"severe": 4, "high": 3, "elevated": 2, "moderate": 1, "low": 0}


def _grade(score: int) -> str:
    return "A" if score >= 80 else "B" if score >= 65 else "C" if score >= 45 else "D"


def _risk_level(score: int) -> str:
    """Narrative risk LEVEL (inverse of the posture score) for underwriting language."""
    return "low" if score >= 80 else "moderate" if score >= 65 else "elevated" if score >= 45 else "high"


def _worst_tier(perils: list[dict]) -> Optional[str]:
    worst, rank = None, -1
    for p in perils or []:
        t = p.get("tier")
        if t and _TIER_RANK.get(t, -1) > rank:
            worst, rank = t, _TIER_RANK[t]
    return worst


def building_risk(b: dict) -> dict:
    """Per-building risk score (0-100, higher = better) + grade + risk level + the drivers
    that moved it. Pure. Posture = COPE quality, penalized by under-insurance (ITV) and the
    worst catastrophe tier. score=None when COPE can't be assessed."""
    cope = b.get("cope_score")
    if cope is None:
        return {"score": None, "grade": None, "risk_level": None, "worst_cat": None, "drivers": []}
    score = float(cope)
    drivers = [{"factor": "COPE quality", "detail": f"COPE {b.get('cope_grade')} ({int(cope)})", "delta": 0}]

    itv = b.get("itv_ratio")
    if itv is not None and itv < 0.90:
        pen = min(25, round((0.90 - itv) * 100))
        score -= pen
        drivers.append({"factor": "Under-insured", "detail": f"ITV {round(itv * 100)}%", "delta": -pen})

    worst = _worst_tier(b.get("perils") or [])
    if worst:
        pen = _CAT_PENALTY.get(worst, 0)
        if pen:
            score -= pen
            drivers.append({"factor": "Catastrophe", "detail": f"worst peril {worst}", "delta": -pen})

    # ACV valuation recovers depreciated value → weaker recovery posture.
    if b.get("valuation_basis") == "ACV":
        score -= 4
        drivers.append({"factor": "Valuation", "detail": "ACV (not replacement cost)", "delta": -4})

    # Occupancy fire-load hazards (capped).
    haz_labels = []
    haz = 0
    if b.get("cooking_nfpa96"):
        haz += 4; haz_labels.append("commercial cooking")
    if b.get("hot_work"):
        haz += 4; haz_labels.append("hot work")
    if b.get("hazmat"):
        haz += 6; haz_labels.append("hazmat")
    haz = min(12, haz)
    if haz:
        score -= haz
        drivers.append({"factor": "Occupancy hazard", "detail": ", ".join(haz_labels), "delta": -haz})

    # Central-station fire alarm is a recognized protection credit.
    if b.get("central_station_alarm"):
        score += 3
        drivers.append({"factor": "Protection", "detail": "central-station alarm", "delta": 3})

    s = max(0, min(100, round(score)))
    return {"score": s, "grade": _grade(s), "risk_level": _risk_level(s), "worst_cat": worst, "drivers": drivers}


def portfolio_risk(buildings: list[dict]) -> dict:
    """TIV-weighted portfolio risk score + grade + risk level, the per-building scores, and
    the top risk contributors (lowest score, biggest TIV) for broker/carrier focus. Pure."""
    rated = [(b, building_risk(b)) for b in buildings]
    rated = [(b, r) for b, r in rated if r["score"] is not None]
    if not rated:
        return {"score": None, "grade": None, "risk_level": None, "by_building": {}, "top_risks": [], "rated": 0}

    tw = sum(max(building_tiv(b), 1) for b, _ in rated)
    score = round(sum(r["score"] * max(building_tiv(b), 1) for b, r in rated) / tw)
    by_building = {b["id"]: r for b, r in rated}
    # worst posture first; ties broken by larger TIV (bigger risk contribution)
    ordered = sorted(rated, key=lambda x: (x[1]["score"], -building_tiv(x[0])))
    top_risks = [{
        "building_id": b["id"], "name": b.get("name"), "tiv": round(building_tiv(b)),
        "score": r["score"], "grade": r["grade"], "risk_level": r["risk_level"],
        "worst_cat": r.get("worst_cat"),
        "drivers": [d for d in r["drivers"] if d["delta"] < 0],
    } for b, r in ordered[:5]]
    return {
        "score": score, "grade": _grade(score), "risk_level": _risk_level(score),
        "by_building": by_building, "top_risks": top_risks, "rated": len(rated),
    }
