"""Compliance complexity score — deterministic, recomputed-on-read.

Blends four signals into a 0–100 score so admins can triage *how hard* a company
is to keep compliant — distinct from coverage (whether its requirements are
filled). An ICU is intrinsically far more complex than a coffee shop; a coffee
shop in 20 cities across 10 states can out-score the ICU on breadth. The score
is a weighted blend of domain risk, jurisdictional breadth, scale, and
requirement load.

Pure (no I/O, no Gemini) so it recomputes cheaply on every dashboard load and
moves up/down as the company's inputs change. All weights/tiers are constants
below — tune here.
"""
from __future__ import annotations

from typing import Any, Optional

# ── Tunable weights (sum to 1.0) ──
W_DOMAIN, W_BREADTH, W_SCALE, W_LOAD = 0.35, 0.30, 0.15, 0.20

# ── Category risk tiers (points). Unknown slug → MEDIUM. ──
TIER_HIGH, TIER_MED, TIER_LOW = 3, 2, 1

_HIGH_CATEGORIES = {
    "hipaa_privacy", "clinical_safety", "healthcare_workforce", "billing_integrity",
    "corporate_integrity", "research_consent", "state_licensing", "radiation_safety",
    "chemotherapy_handling", "tumor_registry", "oncology_clinical_trials",
    "oncology_patient_rights", "pharmacy_drugs", "medical_devices", "transplant_organ",
    "cybersecurity", "health_it", "gmp_manufacturing", "glp_nonclinical",
    "clinical_trials_gcp", "drug_supply_chain", "reproductive_behavioral",
    "pediatric_vulnerable", "telehealth", "emergency_preparedness", "quality_reporting",
    "payer_relations", "antitrust", "environmental_safety",
}
_MEDIUM_CATEGORIES = {
    "leave", "sick_leave", "workers_comp", "anti_discrimination", "workplace_safety",
    "overtime", "meal_breaks", "scheduling_reporting", "final_pay", "pay_frequency",
    "minor_work_permit", "posting_requirements", "records_retention", "language_access",
}
_LOW_CATEGORIES = {
    "minimum_wage", "business_license", "tax_rate", "tax_exempt", "marketing_comms",
}
# Substring fallbacks for slugs not in the explicit sets (keeps new healthcare /
# life-science categories HIGH without a code change).
_HIGH_KEYWORDS = (
    "oncology", "clinical", "medical", "drug", "pharmacy", "radiation", "hazard",
    "hipaa", "phi", "patient", "license", "credential", "cyber", "transplant",
    "device", "gmp", "glp", "gcp", "controlled", "behavioral", "research",
)


def _category_tier(slug: str) -> int:
    s = (slug or "").lower()
    if s in _HIGH_CATEGORIES:
        return TIER_HIGH
    if s in _MEDIUM_CATEGORIES:
        return TIER_MED
    if s in _LOW_CATEGORIES:
        return TIER_LOW
    if any(k in s for k in _HIGH_KEYWORDS):
        return TIER_HIGH
    return TIER_MED  # unknown → medium


# ── Industry base risk (0–40) by keyword ──
def _industry_base(industry: Optional[str], specialty: Optional[str]) -> int:
    text = f"{industry or ''} {specialty or ''}".lower()
    if any(k in text for k in ("health", "hospital", "clinic", "oncology", "behavioral",
                               "medical", "care", "nursing", "hospice", "dental", "pharma")):
        return 40
    if any(k in text for k in ("manufactur", "laborator", "lab", "construction",
                               "industrial", "chemical", "biotech", "device")):
        return 30
    if any(k in text for k in ("food", "restaurant", "retail", "hospitality", "cafe",
                               "coffee", "hotel", "store")):
        return 12
    return 8  # office / professional / general


# ── Bands ──
def band_for(score: int) -> str:
    if score >= 75:
        return "Severe"
    if score >= 50:
        return "High"
    if score >= 25:
        return "Moderate"
    return "Low"


def _domain(category_slugs: list[str], industry: Optional[str], specialty: Optional[str]) -> float:
    base = _industry_base(industry, specialty)
    points = sum(_category_tier(s) for s in category_slugs)
    return float(min(100, base + points))


def _breadth(states: int, jurisdictions: int) -> float:
    extra_locales = max(0, jurisdictions - states)
    return float(min(100, states * 9 + extra_locales * 1.5))


def _scale(headcount: int) -> float:
    if headcount >= 500:
        return 95.0
    if headcount >= 100:
        return 75.0
    if headcount >= 50:
        return 55.0
    if headcount >= 15:
        return 35.0
    return 15.0


def _load(counts: dict[str, Any]) -> float:
    def n(k: str) -> int:
        try:
            return int(counts.get(k, 0) or 0)
        except (TypeError, ValueError):
            return 0
    reqs = n("covered") + n("gaps")
    raw = (
        reqs * 2
        + (n("certifications") + n("licenses") + n("credentials")) * 3
        + n("policies") * 1
        + n("ambiguous") * 4
    )
    return float(min(100, raw))


def score_complexity(
    *,
    industry: Optional[str] = None,
    specialty: Optional[str] = None,
    category_slugs: Optional[list[str]] = None,
    states: int = 0,
    jurisdictions: int = 0,
    headcount: int = 0,
    counts: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Weighted 0–100 complexity score with an explainable breakdown."""
    category_slugs = category_slugs or []
    counts = counts or {}

    domain = _domain(category_slugs, industry, specialty)
    breadth = _breadth(states, jurisdictions)
    scale = _scale(headcount)
    load = _load(counts)

    score = round(W_DOMAIN * domain + W_BREADTH * breadth + W_SCALE * scale + W_LOAD * load)
    score = max(0, min(100, score))

    return {
        "score": score,
        "band": band_for(score),
        "breakdown": {
            "domain": round(domain),
            "breadth": round(breadth),
            "scale": round(scale),
            "load": round(load),
            "drivers": {
                "industry": industry or None,
                "states": states,
                "jurisdictions": jurisdictions,
                "headcount": headcount,
                "category_count": len(category_slugs),
                "requirement_count": int(counts.get("covered", 0) or 0) + int(counts.get("gaps", 0) or 0),
            },
        },
    }


def complexity_from_session(
    *,
    ai_scope: Optional[dict] = None,
    resolved: Optional[dict] = None,
    locations: Optional[list] = None,
    size: Optional[dict] = None,
    industry: Optional[str] = None,
    specialty: Optional[str] = None,
) -> dict[str, Any]:
    """Extract complexity inputs from a gap session's parsed JSONB and score them."""
    ai_scope = ai_scope or {}
    resolved = resolved or {}
    locations = locations or []
    size = size or {}

    cats = [
        c.get("category_slug")
        for c in (ai_scope.get("compliance_categories") or [])
        if isinstance(c, dict) and c.get("category_slug")
    ]

    states_set: set[str] = set()
    juris_set: set[tuple[str, str, str]] = set()
    for loc in locations:
        if not isinstance(loc, dict):
            continue
        st = (loc.get("state") or "").strip().upper()
        city = (loc.get("city") or "").strip().lower()
        county = (loc.get("county") or "").strip().lower()
        if st:
            states_set.add(st)
            juris_set.add((city, county, st))
    # Fallback to AI-scoped jurisdictions when no locations are recorded yet.
    if not states_set:
        for j in (ai_scope.get("applicable_jurisdictions") or []):
            if not isinstance(j, dict):
                continue
            st = (j.get("state") or "").strip().upper()
            if st:
                states_set.add(st)
            juris_set.add(((j.get("city") or "").lower(), (j.get("county") or "").lower(), st))

    def _sz(k: str) -> int:
        try:
            return int(size.get(k, 0) or 0)
        except (TypeError, ValueError):
            return 0

    headcount = _sz("full_time") + _sz("part_time") + _sz("contractor")

    counts = {
        "covered": len(resolved.get("existing") or []),
        "gaps": len(resolved.get("missing") or []),
        "ambiguous": len(resolved.get("ambiguous") or []),
        "certifications": len(ai_scope.get("required_certifications") or []),
        "licenses": len(ai_scope.get("required_licenses") or []),
        "credentials": len(ai_scope.get("required_credentials") or []),
        "policies": len(ai_scope.get("required_policies") or []),
    }

    return score_complexity(
        industry=industry,
        specialty=specialty,
        category_slugs=cats,
        states=len(states_set),
        jurisdictions=len(juris_set),
        headcount=headcount,
        counts=counts,
    )
