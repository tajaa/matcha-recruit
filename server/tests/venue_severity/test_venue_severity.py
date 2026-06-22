"""Pure tests for venue-severity resolution + rollup (DB gather smoke-tested vs dev)."""

from app.matcha.services import venue_severity as vs

STATE_ROWS = [
    {"state": "CA", "county": "", "tier": "high", "score": 70, "source": "ATRA", "note": "state"},
    {"state": "CA", "county": "Los Angeles", "tier": "severe", "score": 90, "source": "nv", "note": "LA"},
]


def test_norm_county_strips_suffixes():
    assert vs._norm_county("Harris County") == "harris"
    assert vs._norm_county("Orleans Parish") == "orleans"
    assert vs._norm_county("  Cook  ") == "cook"
    assert vs._norm_county(None) == ""


def test_resolve_county_override_beats_baseline():
    r = vs.resolve_tier(STATE_ROWS, "Los Angeles County")
    assert r["tier"] == "severe"


def test_resolve_falls_back_to_state_baseline():
    r = vs.resolve_tier(STATE_ROWS, "San Francisco")
    assert r["tier"] == "high"  # no SF override → state baseline


def test_resolve_none_when_no_rows():
    assert vs.resolve_tier([], "Anywhere") is None


def test_resolve_baseline_when_county_empty():
    r = vs.resolve_tier(STATE_ROWS, None)
    assert r["tier"] == "high"


def test_summarize_worst_and_counts():
    locs = [
        {"tier": "high", "score": 70}, {"tier": "severe", "score": 90},
        {"tier": "moderate", "score": 30}, {"tier": "unknown", "score": None},
    ]
    s = vs.summarize(locs)
    assert s["worst_tier"] == "severe"
    assert s["worst_score"] == 90
    assert s["severe_high_count"] == 2
    assert s["rated_locations"] == 3  # unknown excluded
    assert s["total_locations"] == 4
    assert s["tier_counts"]["severe"] == 1


def test_summarize_empty():
    s = vs.summarize([])
    assert s["worst_tier"] == "unknown"
    assert s["severe_high_count"] == 0
    assert s["total_locations"] == 0
