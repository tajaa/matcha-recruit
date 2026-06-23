"""Pure-logic tests for the property risk-improvement plan.

No DB — only app.matcha.services.property_recommendations.build_plan.
"""

from app.matcha.services import property_recommendations as recs

YEAR = 2026


def _b(bid="b1", **kw):
    base = {
        "id": bid, "name": f"Bldg {bid}", "city": "Dallas", "state": "TX",
        "construction_type": None, "sprinklered": False, "protection_class": "3",
        "year_built": 2015, "roof_year": 2015, "occupancy": None,
        "insured_value": None, "replacement_cost": None, "itv_ratio": None,
        "tiv": 5_000_000, "perils": [],
    }
    base.update(kw)
    return base


def test_frame_unsprinklered_yields_high_sprinkler_fix():
    b = _b(construction_type="frame", sprinklered=False)
    plan = recs.build_plan([b], current_year=YEAR)
    spr = [f for f in plan["fixes"] if f["key"] == "sprinkler"]
    assert spr and spr[0]["severity"] == "high"
    assert spr[0]["impact"].startswith("COPE +")


def test_sprinklered_building_has_no_sprinkler_fix():
    b = _b(construction_type="frame", sprinklered=True)
    plan = recs.build_plan([b], current_year=YEAR)
    assert not [f for f in plan["fixes"] if f["key"] == "sprinkler"]


def test_low_itv_yields_itv_fix_with_shortfall_impact():
    b = _b(construction_type="fire_resistive", sprinklered=True,
           itv_ratio=0.60, insured_value=5_400_000, replacement_cost=9_000_000)
    exposure = {"buildings": {"b1": {"coinsurance_shortfall": 2_700_000, "worst_pml": 0}}}
    plan = recs.build_plan([b], exposure=exposure, current_year=YEAR)
    itv = [f for f in plan["fixes"] if f["key"] == "itv"]
    assert itv and itv[0]["severity"] == "high"   # <0.75 → high
    assert "2.7M" in itv[0]["impact"]


def test_severe_wind_yields_named_storm_fix():
    b = _b(construction_type="fire_resistive", sprinklered=True,
           perils=[{"peril": "wind", "tier": "severe"}])
    plan = recs.build_plan([b], current_year=YEAR)
    assert [f for f in plan["fixes"] if f["key"] == "wind_deductible"]


def test_cooking_occupancy_yields_nfpa96_fix():
    b = _b(construction_type="fire_resistive", sprinklered=True, occupancy="Cafe / kitchen")
    plan = recs.build_plan([b], current_year=YEAR)
    assert [f for f in plan["fixes"] if f["key"] == "nfpa96"]


def test_aged_roof_yields_low_roof_fix():
    b = _b(construction_type="fire_resistive", sprinklered=True, roof_year=2000)  # 26 yrs
    plan = recs.build_plan([b], current_year=YEAR)
    roof = [f for f in plan["fixes"] if f["key"] == "roof"]
    assert roof and roof[0]["severity"] == "low"


def test_high_severity_ranks_before_low():
    b = _b(construction_type="frame", sprinklered=False, roof_year=1990)  # sprinkler(high) + roof(low)
    plan = recs.build_plan([b], current_year=YEAR)
    sevs = [f["severity"] for f in plan["fixes"]]
    assert sevs.index("high") < sevs.index("low")


def test_clean_building_has_no_fixes():
    b = _b(construction_type="fire_resistive", sprinklered=True, roof_year=2020,
           itv_ratio=1.0, insured_value=5_000_000, replacement_cost=5_000_000)
    plan = recs.build_plan([b], current_year=YEAR)
    assert plan["fixes"] == [] and plan["summary"]["total"] == 0
