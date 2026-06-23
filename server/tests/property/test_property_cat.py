"""Pure-logic tests for the catastrophe tier mappers + company rollup.

No network / no DB — only the pure functions in property_cat. The geocode + FEMA/
USGS/USFS fetchers and enrich_building are best-effort and exercised by a manual
dev smoke against real addresses.
"""

from app.matcha.services import property_cat as pc


# --- flood -----------------------------------------------------------------

def test_flood_tier_coastal_vs_sfha_vs_minimal():
    assert pc._flood_tier("VE") == ("severe", 90)
    assert pc._flood_tier("AE") == ("high", 75)
    assert pc._flood_tier("0.2 PCT ANNUAL CHANCE FLOOD HAZARD") == ("elevated", 45)
    assert pc._flood_tier("X") == ("low", 10)
    assert pc._flood_tier("D") == ("moderate", 35)


# --- quake -----------------------------------------------------------------

def test_quake_tier_bands():
    assert pc._quake_tier(None) is None
    assert pc._quake_tier(0.85)[0] == "severe"
    assert pc._quake_tier(0.6)[0] == "high"
    assert pc._quake_tier(0.4)[0] == "elevated"
    assert pc._quake_tier(0.2)[0] == "moderate"
    assert pc._quake_tier(0.05)[0] == "low"


# --- wildfire --------------------------------------------------------------

def test_wildfire_tier_numeric_and_text():
    assert pc._wildfire_tier(5) == ("severe", 90)
    assert pc._wildfire_tier(1) == ("low", 12)
    assert pc._wildfire_tier("Very High") == ("severe", 90)
    assert pc._wildfire_tier(None) is None
    assert pc._wildfire_tier("garbage") is None


# --- wind (DB reference) ---------------------------------------------------

def _wind_rows():
    return [
        {"state": "FL", "county": "", "tier": "severe", "score": 90},
        {"state": "FL", "county": "Monroe", "tier": "severe", "score": 97},
        {"state": "TX", "county": "", "tier": "high", "score": 72},
    ]


def test_wind_tier_county_then_state_then_inland():
    assert pc._wind_tier("FL", "Monroe", _wind_rows()) == ("severe", 97)   # county-specific
    assert pc._wind_tier("FL", "Orange", _wind_rows()) == ("severe", 90)   # state baseline
    assert pc._wind_tier("KS", "", _wind_rows()) == ("low", 10)            # inland, unseeded
    assert pc._wind_tier(None, None, _wind_rows()) is None


# --- summarize -------------------------------------------------------------

def test_summarize_empty():
    s = pc.summarize([])
    assert s["worst_tier"] is None and s["buildings_total"] == 0


def test_summarize_rolls_up_worst_and_counts():
    rows = [
        {"building_id": "b1", "lat": 27.5, "peril": "flood", "tier": "severe", "score": 90},
        {"building_id": "b1", "lat": 27.5, "peril": "wind", "tier": "high", "score": 75},
        {"building_id": "b2", "lat": None, "peril": None, "tier": None, "score": None},
    ]
    s = pc.summarize(rows)
    assert s["worst_tier"] == "severe"
    assert s["by_peril"] == {"flood": "severe", "wind": "high"}
    assert s["severe_high_count"] == 1     # only b1 reaches high+
    assert s["buildings_total"] == 2
    assert s["buildings_geocoded"] == 1    # b2 not geocoded
