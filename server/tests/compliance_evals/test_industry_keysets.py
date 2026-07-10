"""Industry → expected category/key mapping, and the tagging root-match rule."""
import pytest

from app.core.compliance_registry import LABOR_CATEGORIES
from app.core.services.compliance_evals import industry_keysets as iks
from app.core.services.compliance_evals.tagging import tag_satisfies


def test_every_supported_industry_has_a_category_set():
    for industry in iks.SUPPORTED_INDUSTRIES:
        assert industry in iks.INDUSTRY_CATEGORY_SETS


def test_base_categories_apply_to_every_industry():
    for industry in iks.SUPPORTED_INDUSTRIES:
        cats = iks.expected_categories(industry)
        assert LABOR_CATEGORIES <= cats, industry


def test_manufacturing_expects_machine_and_chemical_safety():
    cats = iks.expected_categories("manufacturing")
    assert "machine_safety" in cats
    assert "chemical_safety" in cats
    assert "process_safety" in cats


def test_manufacturing_expects_lockout_tagout_key():
    keys = iks.expected_keys("manufacturing")
    assert "lockout_tagout" in keys["machine_safety"]


def test_healthcare_does_not_expect_manufacturing_categories():
    cats = iks.expected_categories("healthcare")
    assert "machine_safety" not in cats
    assert "hipaa_privacy" in cats


def test_oncology_is_a_superset_of_healthcare():
    assert iks.expected_categories("healthcare") < iks.expected_categories("healthcare:oncology")
    assert "radiation_safety" in iks.expected_categories("healthcare:oncology")


def test_no_industry_still_gets_the_base_stack():
    cats = iks.expected_categories(None)
    assert LABOR_CATEGORIES <= cats
    assert "machine_safety" not in cats


def test_retail_adds_no_industry_specific_categories():
    """A real property of the registry, asserted so a future category group is noticed."""
    assert iks.expected_categories("retail") == iks.expected_categories(None)


def test_expected_keys_country_filter_drops_us_only_keys():
    us = iks.expected_keys(None, country_code="US")
    uk = iks.expected_keys(None, country_code="GB")
    assert "tipped_minimum_wage" in us["minimum_wage"]
    assert "tipped_minimum_wage" not in uk.get("minimum_wage", set())


def test_us_jurisdictions_are_not_asked_for_mexico_only_keys():
    """`get_missing_regulations` skips the country filter for the US and so demands
    `finiquito` of a Los Angeles employer. The eval must not inherit that."""
    us = iks.expected_keys(None, country_code="US")
    assert "finiquito" not in us.get("final_pay", set())
    assert "liquidacion" not in us.get("final_pay", set())
    assert "nom_035_psychosocial_risk" not in us.get("anti_discrimination", set())


def test_mexico_jurisdictions_do_get_those_keys():
    mx = iks.expected_keys(None, country_code="MX")
    assert "finiquito" in mx["final_pay"]


def test_industry_specific_category_attribution():
    assert iks.industry_specific_category("machine_safety") == "manufacturing"
    assert iks.industry_specific_category("hipaa_privacy") == "healthcare"
    # Universal labor categories belong to nobody.
    assert iks.industry_specific_category("minimum_wage") is None
    assert iks.industry_specific_category("overtime") is None


def test_focused_categories_always_include_industry_specific_ones():
    focused = iks.focused_categories("manufacturing", {})
    assert "machine_safety" in focused


def test_focused_categories_pick_up_high_confidence_profile_categories():
    focused = iks.focused_categories("manufacturing", {"overtime": 0.95, "sick_leave": 0.75})
    assert "overtime" in focused
    assert "sick_leave" not in focused


# ── tag matching ──────────────────────────────────────────────────────────────

def test_tag_satisfies_exact():
    assert tag_satisfies(["manufacturing"], "manufacturing")


def test_tag_satisfies_root_match_for_specialty():
    """An oncology row tagged plain `healthcare` is loose but not leaky."""
    assert tag_satisfies(["healthcare"], "healthcare:oncology")
    assert tag_satisfies(["healthcare:oncology"], "healthcare")


def test_untagged_row_never_satisfies():
    assert not tag_satisfies([], "manufacturing")
    assert not tag_satisfies(None or [], "healthcare")


def test_wrong_industry_tag_does_not_satisfy():
    assert not tag_satisfies(["healthcare"], "manufacturing")


@pytest.mark.parametrize("raw,expected", [
    ("Manufacturing", "manufacturing"),
    ("hospital", "healthcare"),
    ("restaurant", "hospitality"),
    ("SaaS", "technology"),
])
def test_resolve_industry_delegates_to_pipeline_aliases(raw, expected):
    assert iks.resolve_industry(raw) == expected
