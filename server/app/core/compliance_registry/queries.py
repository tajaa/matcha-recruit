from __future__ import annotations

from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple  # noqa: F401

from app.core.compliance_registry._types import RegulationDef
from app.core.compliance_registry.derived import EXPECTED_REGULATION_KEYS, REGULATION_MAP, _key_applies_to_country


# ---------------------------------------------------------------------------
# Completeness helper
# ---------------------------------------------------------------------------

def get_missing_regulations(
    category: str, existing_keys: Set[str], country_code: str = "US"
) -> List[RegulationDef]:
    """Return regulations in this category not yet present in the DB.

    For non-US jurisdictions, filters to only keys that apply to the given country
    (universal keys + country-specific keys). This prevents flagging UK jurisdictions
    as missing 'tipped_minimum_wage' or Mexico as missing 'state_paid_sick_leave'.
    """
    expected = EXPECTED_REGULATION_KEYS.get(category, frozenset())
    if country_code != "US":
        expected = {k for k in expected
                    if _key_applies_to_country(k, category, country_code)}
    missing_keys = expected - existing_keys
    return [REGULATION_MAP[k] for k in sorted(missing_keys) if k in REGULATION_MAP]


def resolve_weight(
    base_weight: float,
    applicable_industries: Optional[List[str]],
    applicable_entity_types: Optional[List[str]],
    company_industry: Optional[str] = None,
    company_entity_type: Optional[str] = None,
) -> float:
    """Compute contextual weight for a key given a company's profile.

    Uses additive adjustments with a floor to avoid extreme ratios
    that distort mixed-use facility scores. Max ratio ~5:1.
    """
    weight = base_weight
    adjustment = 0.0

    if applicable_industries:
        if company_industry and company_industry in applicable_industries:
            adjustment += 0.5
        elif company_industry:
            adjustment -= 0.5

    if applicable_entity_types:
        if company_entity_type and company_entity_type in applicable_entity_types:
            adjustment += 0.5
        elif company_entity_type:
            adjustment -= 0.5

    # Floor at 0.2 × base_weight
    return max(weight + adjustment, weight * 0.2)


