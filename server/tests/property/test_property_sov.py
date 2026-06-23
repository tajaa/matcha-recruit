"""Pure-logic tests for commercial-property SOV math + the line-key widenings.

No DB — only the pure helpers in app.matcha.services.property_sov plus a regression
guard that the new 'property' line key is wired into the shared casualty engines.
"""

from app.matcha.services import property_sov as sov
from app.matcha.services import limit_adequacy as la
from app.matcha.services import loss_development as ld

YEAR = 2026


def _b(**kw) -> dict:
    base = {
        "construction_type": None, "sprinklered": False, "protection_class": None,
        "year_built": None, "roof_year": None,
        "building_value": None, "contents_value": None, "bi_value": None,
        "replacement_cost": None, "insured_value": None,
    }
    base.update(kw)
    return base


# --- cope_grade ------------------------------------------------------------

def test_cope_grade_best_class_is_A():
    g, s = sov.cope_grade(_b(construction_type="fire_resistive", sprinklered=True,
                             protection_class="2", year_built=2015, roof_year=2020), YEAR)
    assert g == "A" and s == 100   # base 100 + sprinkler + ppc, clamped


def test_cope_grade_worst_class_is_D():
    g, s = sov.cope_grade(_b(construction_type="frame", sprinklered=False,
                             protection_class="9", year_built=1970, roof_year=1990), YEAR)
    assert g == "D" and s == 0     # frame, unsprinklered, bad ppc, old → floored


def test_cope_grade_unknown_construction_defaults_midrange():
    g, s = sov.cope_grade(_b(construction_type="non_combustible", sprinklered=False), YEAR)
    assert s == 50 and g == "C"    # 60 base - 10 unsprinklered


def test_cope_grade_old_roof_penalized():
    new = sov.cope_grade(_b(construction_type="masonry_non_combustible", roof_year=2024), YEAR)[1]
    old = sov.cope_grade(_b(construction_type="masonry_non_combustible", roof_year=1990), YEAR)[1]
    assert old < new


# --- itv_ratio -------------------------------------------------------------

def test_itv_ratio_basic():
    assert sov.itv_ratio(900_000, 1_000_000) == 0.9
    assert sov.itv_ratio(1_000_000, 1_000_000) == 1.0


def test_itv_ratio_none_when_no_replacement_cost():
    assert sov.itv_ratio(500_000, 0) is None
    assert sov.itv_ratio(500_000, None) is None


# --- building_tiv ----------------------------------------------------------

def test_building_tiv_sums_three_values_treating_none_as_zero():
    assert sov.building_tiv(_b(building_value=1_000_000, contents_value=500_000, bi_value=200_000)) == 1_700_000
    assert sov.building_tiv(_b(building_value=1_000_000)) == 1_000_000


# --- rollup ----------------------------------------------------------------

def test_rollup_empty():
    r = sov.rollup([], YEAR)
    assert r["building_count"] == 0 and r["tiv"] == 0.0
    assert r["avg_cope_score"] is None and r["worst_cope_grade"] is None


def test_rollup_aggregates_tiv_cope_and_itv():
    b1 = _b(construction_type="fire_resistive", sprinklered=True,
            building_value=1_000_000, insured_value=1_000_000, replacement_cost=1_000_000)
    b2 = _b(construction_type="frame", sprinklered=False,
            building_value=500_000, insured_value=300_000, replacement_cost=600_000)
    r = sov.rollup([b1, b2], YEAR)
    assert r["building_count"] == 2
    assert r["tiv"] == 1_500_000.0
    assert r["worst_cope_grade"] == "D"           # frame drags the worst grade
    assert r["itv"]["rated_count"] == 2
    assert r["itv"]["under_count"] == 1           # b2 at 0.5 is underinsured
    assert r["itv"]["portfolio_ratio"] == 0.812   # 1.3M / 1.6M (banker's rounding)


# --- regression: 'property' line wired into shared casualty engines ---------

def test_property_line_in_limit_adequacy():
    assert "property" in la.LINE_KEYS
    assert la.normalize_line("Commercial Property") == "property"
    assert any(c["key"] == "property" for c in la.COVERAGE_LINES)


def test_property_line_in_loss_development():
    assert ld.LINE_LABELS.get("property") == "Commercial Property"
