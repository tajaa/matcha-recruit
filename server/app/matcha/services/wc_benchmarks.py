"""Workers Comp benchmarks + premium-impact estimator.

NAICS-sector medians from US BLS (2023 private industry). Used to frame
TRIR/DART against an industry peer rather than the flat national number.

Premium estimator is a back-of-napkin directional indicator. NOT a quote.
Inputs:
  - TRIR vs benchmark TRIR  → modeled E-Mod swing
  - sector avg WC premium per FTE × headcount → base premium estimate
  - swing × base = annual $ impact direction

Anything precise requires NCCI class codes, payroll, and carrier-specific
rate tables — none of which we have.
"""

from typing import Optional, Dict, Any

# BLS 2023 private-industry incident rate medians by NAICS 2-digit sector.
SECTOR_BENCHMARKS: Dict[str, Dict[str, Any]] = {
    "11": {"label": "Agriculture",                  "trir": 5.5, "dart": 3.2},
    "21": {"label": "Mining",                       "trir": 1.6, "dart": 0.9},
    "22": {"label": "Utilities",                    "trir": 1.7, "dart": 0.9},
    "23": {"label": "Construction",                 "trir": 2.5, "dart": 1.5},
    "31": {"label": "Manufacturing",                "trir": 3.0, "dart": 1.7},
    "42": {"label": "Wholesale Trade",              "trir": 3.0, "dart": 1.7},
    "44": {"label": "Retail Trade",                 "trir": 3.6, "dart": 2.0},
    "48": {"label": "Transportation/Warehousing",   "trir": 4.6, "dart": 3.0},
    "51": {"label": "Information",                  "trir": 1.0, "dart": 0.6},
    "52": {"label": "Finance/Insurance",            "trir": 0.5, "dart": 0.3},
    "53": {"label": "Real Estate",                  "trir": 1.5, "dart": 0.9},
    "54": {"label": "Professional Services",        "trir": 0.7, "dart": 0.4},
    "56": {"label": "Admin/Waste Services",         "trir": 2.5, "dart": 1.5},
    "61": {"label": "Education",                    "trir": 2.4, "dart": 1.3},
    "62": {"label": "Healthcare/Social Assistance", "trir": 4.5, "dart": 2.6},
    "71": {"label": "Arts/Entertainment",           "trir": 3.6, "dart": 2.0},
    "72": {"label": "Accommodation/Food Service",   "trir": 3.6, "dart": 2.0},
    "81": {"label": "Other Services",               "trir": 1.6, "dart": 0.9},
}

# Fuzzy industry text → NAICS sector. Lowercased + stripped on lookup.
INDUSTRY_TO_SECTOR: Dict[str, str] = {
    "hospitality": "72", "restaurant": "72", "restaurants": "72", "food": "72",
    "food_service": "72", "hotel": "72", "hotels": "72",
    "healthcare": "62", "health": "62", "biotech": "62", "medical": "62",
    "social_services": "62", "social_assistance": "62",
    "retail": "44", "e-commerce": "44", "ecommerce": "44",
    "construction": "23", "trades": "23",
    "manufacturing": "31",
    "transportation": "48", "logistics": "48", "warehouse": "48", "warehousing": "48",
    "technology": "51", "tech": "51", "software": "51", "saas": "51",
    "information": "51",
    "finance": "52", "insurance": "52", "fintech": "52", "banking": "52",
    "professional_services": "54", "consulting": "54", "legal": "54", "law": "54",
    "education": "61",
    "agriculture": "11", "farming": "11",
    "mining": "21",
    "utilities": "22",
    "real_estate": "53",
    "arts": "71", "entertainment": "71",
}

# US average annual Workers Comp premium per FTE by NAICS sector. Very rough
# — actual depends on state, NCCI class, payroll, mod, etc.
SECTOR_AVG_PREMIUM_PER_FTE: Dict[str, int] = {
    "11": 5000, "21": 6000, "22": 1800, "23": 4500,
    "31": 1500, "42": 800, "44": 600, "48": 3500,
    "51": 200, "52": 100, "53": 400, "54": 250,
    "56": 1800, "61": 600, "62": 1200, "71": 1400,
    "72": 1100, "81": 700,
}


def _normalize(industry: Optional[str]) -> str:
    if not industry:
        return ""
    return (
        industry.strip().lower()
        .replace("/", "_").replace(" ", "_").replace("-", "_")
    )


def lookup_benchmark(industry: Optional[str]) -> Optional[Dict[str, Any]]:
    """Return {sector, label, trir, dart} for the company's industry, else None.

    Falls back to None when industry is missing or unrecognized — caller
    should display the national fallback (TRIR 2.7 / DART 1.7) and label it.
    """
    key = _normalize(industry)
    sector = INDUSTRY_TO_SECTOR.get(key)
    if not sector:
        return None
    bench = SECTOR_BENCHMARKS.get(sector)
    if not bench:
        return None
    return {"sector": sector, **bench}


def estimate_premium_impact(
    trir: Optional[float],
    benchmark_trir: Optional[float],
    headcount: Optional[int],
    sector: Optional[str],
) -> Optional[Dict[str, Any]]:
    """Directional dollar impact of current TRIR deviation on next renewal.

    Returns None if any input is missing. Otherwise:
      - mod_swing: ~10pts mod per 1.0× TRIR deviation from benchmark
      - base_premium: sector_avg_per_fte × headcount
      - annual_impact_dollars: base × mod_swing
    """
    if not trir or not benchmark_trir or not headcount or not sector:
        return None
    if benchmark_trir <= 0:
        return None
    ratio = trir / benchmark_trir
    mod_swing = round((ratio - 1.0) * 0.10, 3)
    base_premium = SECTOR_AVG_PREMIUM_PER_FTE.get(sector, 1000) * int(headcount)
    impact_dollars = round(base_premium * mod_swing)
    direction = (
        "increase" if impact_dollars > 0
        else "decrease" if impact_dollars < 0
        else "neutral"
    )
    return {
        "base_premium_estimate": base_premium,
        "mod_swing": mod_swing,
        "annual_impact_dollars": impact_dollars,
        "direction": direction,
    }


def severity_band(trir: Optional[float], benchmark_trir: Optional[float]) -> str:
    """Categorical band for portfolio sorting.

    'good' = below benchmark, 'fair' = near, 'at_risk' = 1.0–1.5×, 'critical' = ≥1.5×.
    Returns 'unknown' when inputs missing.
    """
    if trir is None or benchmark_trir is None or benchmark_trir <= 0:
        return "unknown"
    ratio = trir / benchmark_trir
    if ratio < 0.75:
        return "good"
    if ratio < 1.0:
        return "fair"
    if ratio < 1.5:
        return "at_risk"
    return "critical"


SEVERITY_BAND_RANK = {"critical": 0, "at_risk": 1, "fair": 2, "good": 3, "unknown": 4}
