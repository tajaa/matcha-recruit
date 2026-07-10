"""Industry → expected category/key mapping.

This module is the single answer to "what does a manufacturing company in Los
Angeles actually need?". Before it existed, three mechanisms each held a piece
and none of them intersected:

  * ``_missing_required_categories`` (compliance_service) gates research on a
    fixed labor-category set that ignores industry entirely.
  * ``EXPECTED_REGULATION_KEYS`` (compliance_registry) is keyed by *category*,
    so it can say "minimum_wage is missing tipped_minimum_wage" but never
    "manufacturing is missing lockout_tagout".
  * ``applicable_industries`` on catalog rows is a free-text array the research
    model fills in, in practice only ever with ``healthcare*``.

The completeness suite consumes this module now. The industry-tag backfill and
the tagging suite's structural check consume it too, so the eval and any future
pipeline fix cannot disagree about what an industry requires.

Nothing here hits the network or the model. The only DB read is the optional
weight lookup against ``industry_compliance_profiles``.
"""
from __future__ import annotations

from typing import Any, Dict, FrozenSet, List, Optional, Set

from app.core.compliance_registry import (
    EXPECTED_REGULATION_KEYS,
    HEALTHCARE_CATEGORIES,
    LABOR_CATEGORIES,
    LIFE_SCIENCES_CATEGORIES,
    MANUFACTURING_CATEGORIES,
    ONCOLOGY_CATEGORIES,
    SUPPLEMENTARY_CATEGORIES,
    _key_applies_to_country,
)

# Every employer, regardless of industry, owes the labor + supplementary stack.
BASE_CATEGORIES: FrozenSet[str] = LABOR_CATEGORIES | SUPPLEMENTARY_CATEGORIES

# Industry-specific categories layered on top of the base. Keys are the canonical
# industry names produced by ``compliance_service._resolve_industry``; the two
# dotted entries are healthcare sub-specialties carried in company
# ``healthcare_specialties`` and in the ``applicable_industries`` tag vocabulary.
#
# hospitality / retail / technology / "fast food" carry no additional *categories*
# — their industry weight comes entirely from the profile confidence scores below.
# That is a real finding, not an omission: the registry defines no category group
# for them.
INDUSTRY_CATEGORY_SETS: Dict[str, FrozenSet[str]] = {
    "manufacturing": MANUFACTURING_CATEGORIES,
    "healthcare": HEALTHCARE_CATEGORIES,
    "healthcare:oncology": HEALTHCARE_CATEGORIES | ONCOLOGY_CATEGORIES,
    "biotech": LIFE_SCIENCES_CATEGORIES,
    "hospitality": frozenset(),
    "retail": frozenset(),
    "technology": frozenset(),
    "fast food": frozenset(),
}

# Canonical industry → the ``industry_compliance_profiles.name`` that carries its
# ``category_evidence`` confidence weights.
INDUSTRY_PROFILE_NAMES: Dict[str, str] = {
    "hospitality": "Restaurant / Hospitality",
    "healthcare": "Healthcare",
    "healthcare:oncology": "Healthcare",
    "retail": "Retail",
    "technology": "Tech / Professional Services",
    "fast food": "Fast Food",
    "manufacturing": "Construction / Manufacturing",
}

SUPPORTED_INDUSTRIES: List[str] = sorted(INDUSTRY_CATEGORY_SETS)

# A category that belongs to exactly one industry's specific set. Used by the
# tagging suite: a catalog row in one of these categories that carries no
# matching ``applicable_industries`` tag is silently served to every company by
# ``_filter_requirements_for_company``.
_INDUSTRY_SPECIFIC_CATEGORIES: Dict[str, str] = {}
for _ind in ("manufacturing", "healthcare", "biotech"):
    for _cat in INDUSTRY_CATEGORY_SETS[_ind]:
        _INDUSTRY_SPECIFIC_CATEGORIES.setdefault(_cat, _ind)
for _cat in ONCOLOGY_CATEGORIES:
    _INDUSTRY_SPECIFIC_CATEGORIES.setdefault(_cat, "healthcare:oncology")


def resolve_industry(raw: Optional[str]) -> str:
    """Free-text industry → canonical name. Delegates to the pipeline's resolver.

    Imported lazily: ``compliance_service`` pulls in Gemini clients and the whole
    research stack, which the eval suites have no business loading at import time.
    """
    from app.core.services.compliance_service import _resolve_industry

    return _resolve_industry(raw)


def industry_specific_category(category: str) -> Optional[str]:
    """Industry that owns this category, or None if it is universal."""
    return _INDUSTRY_SPECIFIC_CATEGORIES.get(category)


def expected_categories(industry: Optional[str]) -> Set[str]:
    """Categories a company in `industry` is expected to have data for."""
    cats = set(BASE_CATEGORIES)
    if industry:
        cats |= set(INDUSTRY_CATEGORY_SETS.get(industry, frozenset()))
    return cats


def expected_keys(
    industry: Optional[str],
    country_code: str = "US",
    categories: Optional[Set[str]] = None,
) -> Dict[str, Set[str]]:
    """Expected regulation keys per category for (industry, country).

    Country filtering reuses ``_key_applies_to_country`` so a UK jurisdiction is
    never flagged for missing ``tipped_minimum_wage``.

    The filter is applied for **every** country, including the US. This differs
    deliberately from ``get_missing_regulations``, which short-circuits the filter
    when ``country_code == "US"`` and therefore reports US jurisdictions as
    missing Mexico-only keys (``finiquito``, ``liquidacion``,
    ``nom_035_psychosocial_risk``). That is a live bug in the gap detector; fixing
    it there is a pipeline change and is out of scope for the eval pass, but the
    eval must not inherit it or every US completeness score would be understated.
    """
    cats = categories if categories is not None else expected_categories(industry)
    out: Dict[str, Set[str]] = {}
    for cat in sorted(cats):
        keys = EXPECTED_REGULATION_KEYS.get(cat, frozenset())
        if not keys:
            continue
        keys = {k for k in keys if _key_applies_to_country(k, cat, country_code)}
        if keys:
            out[cat] = set(keys)
    return out


async def category_weights(conn, industry: Optional[str]) -> Dict[str, float]:
    """Per-category weights from ``industry_compliance_profiles.category_evidence``.

    The seeded profiles carry a hand-researched ``confidence`` (0-100) per focused
    category — e.g. manufacturing overtime is 95 because Davis-Bacon overtime is
    where the DOL actually recovers money. Reuse it rather than inventing a second
    weighting scheme.

    Returns only the categories the profile speaks to; callers default the rest to
    1.0. Missing table / missing profile / malformed JSON all degrade to ``{}``.
    """
    if not industry:
        return {}
    profile_name = INDUSTRY_PROFILE_NAMES.get(industry)
    if not profile_name:
        return {}

    try:
        row = await conn.fetchrow(
            "SELECT category_evidence FROM industry_compliance_profiles WHERE name = $1",
            profile_name,
        )
    except Exception:
        return {}
    if not row or not row["category_evidence"]:
        return {}

    evidence: Any = row["category_evidence"]
    if isinstance(evidence, str):
        # asyncpg has no json codec registered on this pool — jsonb comes back raw.
        import json

        try:
            evidence = json.loads(evidence)
        except (ValueError, TypeError):
            return {}
    if not isinstance(evidence, dict):
        return {}

    weights: Dict[str, float] = {}
    for cat, meta in evidence.items():
        if not isinstance(meta, dict):
            continue
        conf = meta.get("confidence")
        if isinstance(conf, (int, float)) and 0 < conf <= 100:
            weights[cat] = float(conf) / 100.0
    return weights


def focused_categories(industry: Optional[str], weights: Dict[str, float]) -> Set[str]:
    """Categories that carry disproportionate risk for this industry.

    A missing key in one of these is `critical`; elsewhere it is `warn`. Industry
    -specific categories are always focused (a manufacturer with no lockout/tagout
    data has a hole no confidence score can excuse); profile categories join them
    once their researched confidence clears 0.85.
    """
    focused = set(INDUSTRY_CATEGORY_SETS.get(industry or "", frozenset()))
    focused |= {cat for cat, w in weights.items() if w >= 0.85}
    return focused
