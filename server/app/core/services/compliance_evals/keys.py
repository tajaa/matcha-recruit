"""Normalize a catalog row's regulation key into the registry's key vocabulary.

The catalog speaks two dialects for `minimum_wage`, and both are live today:

  * ``_compute_requirement_key`` (compliance_service) keys minimum-wage rows on
    their **rate_type**, producing ``minimum_wage:general``, ``:tipped``,
    ``:exempt_salary``.
  * The registry's ``EXPECTED_REGULATION_KEYS['minimum_wage']`` names the same
    facts ``state_minimum_wage``, ``tipped_minimum_wage``,
    ``exempt_salary_threshold``.

Dev holds rows in *both* dialects. Comparing raw strings would report
``state_minimum_wage`` as missing for a jurisdiction that plainly has its minimum
wage — a phantom gap that would then drive pointless Gemini re-research. So the
eval normalizes before it compares.

``general`` is level-sensitive: at a city or county it means the *local* ordinance
rate; at a state it means the state rate; federally it is the national floor.
"""
from __future__ import annotations

from typing import Optional

# rate_type → registry key, for jurisdiction levels at or above `state`.
_RATE_TYPE_TO_KEY = {
    "tipped": "tipped_minimum_wage",
    "exempt_salary": "exempt_salary_threshold",
    # A named sub-state region's own exempt threshold (NY downstate). Distinct
    # from the statewide tier: two different dollar figures, both live, both
    # binding on their own geography. minimum_wage keys off rate_type, so
    # without this dialect entry the two rows collide on one identity.
    "exempt_salary_regional": "exempt_salary_threshold_regional",
    "fast_food": "fast_food_minimum_wage",
    "healthcare": "healthcare_minimum_wage",
    "large_employer": "large_employer_minimum_wage",
    "small_employer": "small_employer_minimum_wage",
    # `hotel` has no registry key. Left unmapped on purpose: the resulting
    # `invalid_key` finding is a true gap in EXPECTED_REGULATION_KEYS, not noise.
}

_LOCAL_LEVELS = {"city", "county", "special_district"}
_NATIONAL_LEVELS = {"federal", "national"}


def normalize_key(
    category: Optional[str],
    bare_key: Optional[str],
    jurisdiction_level: Optional[str] = None,
    country_code: str = "US",
) -> Optional[str]:
    """Map a catalog key onto the registry vocabulary. Idempotent."""
    if not bare_key or not category:
        return bare_key

    if category != "minimum_wage":
        return bare_key

    if bare_key == "general":
        level = (jurisdiction_level or "").lower()
        if level in _LOCAL_LEVELS:
            return "local_minimum_wage"
        if level in _NATIONAL_LEVELS or country_code != "US":
            return "national_minimum_wage"
        return "state_minimum_wage"

    return _RATE_TYPE_TO_KEY.get(bare_key, bare_key)
