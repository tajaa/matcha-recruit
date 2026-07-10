"""Reconciling the catalog's two minimum-wage key dialects.

`_compute_requirement_key` keys minimum-wage rows on rate_type (`general`,
`tipped`); the registry names the same facts `state_minimum_wage`,
`tipped_minimum_wage`. Dev holds rows in both. Without normalization the
completeness suite reports phantom gaps for keys that plainly exist.
"""
import pytest

from app.core.compliance_registry import EXPECTED_REGULATION_KEYS
from app.core.services.compliance_evals.keys import normalize_key


def test_general_is_level_sensitive():
    """`general` means the local ordinance in a city, the state floor in a state."""
    assert normalize_key("minimum_wage", "general", "city") == "local_minimum_wage"
    assert normalize_key("minimum_wage", "general", "county") == "local_minimum_wage"
    assert normalize_key("minimum_wage", "general", "state") == "state_minimum_wage"
    assert normalize_key("minimum_wage", "general", "federal") == "national_minimum_wage"


def test_general_outside_the_us_is_national():
    assert normalize_key("minimum_wage", "general", "state", "GB") == "national_minimum_wage"


def test_general_with_unknown_level_defaults_to_state():
    assert normalize_key("minimum_wage", "general", None) == "state_minimum_wage"


@pytest.mark.parametrize("rate_type,expected", [
    ("tipped", "tipped_minimum_wage"),
    ("exempt_salary", "exempt_salary_threshold"),
    ("fast_food", "fast_food_minimum_wage"),
    ("healthcare", "healthcare_minimum_wage"),
    ("large_employer", "large_employer_minimum_wage"),
    ("small_employer", "small_employer_minimum_wage"),
])
def test_rate_types_map_to_registry_keys(rate_type, expected):
    assert normalize_key("minimum_wage", rate_type, "state") == expected


def test_every_mapped_key_actually_exists_in_the_registry():
    """A normalization that invents a key would silently pass completeness."""
    known = EXPECTED_REGULATION_KEYS["minimum_wage"]
    for rate_type in ("tipped", "exempt_salary", "fast_food", "healthcare",
                      "large_employer", "small_employer"):
        assert normalize_key("minimum_wage", rate_type, "state") in known
    for level in ("city", "state", "federal"):
        assert normalize_key("minimum_wage", "general", level) in known


def test_is_idempotent():
    """Rows already written in the registry dialect must pass through unchanged."""
    for key in ("state_minimum_wage", "tipped_minimum_wage", "exempt_salary_threshold"):
        assert normalize_key("minimum_wage", key, "state") == key


def test_hotel_is_left_unmapped_on_purpose():
    """No registry key exists; the resulting `invalid_key` finding is a true gap."""
    assert normalize_key("minimum_wage", "hotel", "city") == "hotel"


def test_other_categories_pass_through_untouched():
    assert normalize_key("overtime", "general", "city") == "general"
    assert normalize_key("sick_leave", "local_sick_leave", "city") == "local_sick_leave"


def test_null_inputs():
    assert normalize_key("minimum_wage", None, "city") is None
    assert normalize_key(None, "general", "city") == "general"
