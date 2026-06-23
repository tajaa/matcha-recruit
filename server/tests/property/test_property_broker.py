"""Pure-logic tests for the broker-side property pieces:
external-client property compute + the separate property submission-readiness block.
No DB.
"""

from app.matcha.services import external_clients as ext
from app.matcha.services import submission_readiness as sr


# --- _compute_property (off-platform summary → scoring shape) ---------------

def test_compute_property_empty_snapshot():
    p = ext._compute_property(None)
    assert p["has_data"] is False
    assert p["rollup"]["building_count"] == 0
    assert p["cat"] is None


def test_compute_property_builds_rollup_and_cat():
    snap = {
        "building_count": 3, "total_tiv": 5_000_000, "worst_construction": "frame",
        "sprinklered_pct": 50, "worst_cat_tier": "high", "insured_to_value_pct": 80,
        "carrier": "Acme", "annual_premium": 120_000, "period_label": "2026",
    }
    p = ext._compute_property(snap)
    assert p["has_data"] is True
    assert p["building_count"] == 3
    assert p["total_tiv"] == 5_000_000.0
    # coarse COPE = frame(25)*0.7 + 50%*0.3 = 32.5 → 32 (banker's rounding)
    assert p["rollup"]["avg_cope_score"] == 32
    assert p["rollup"]["itv"]["portfolio_ratio"] == 0.8
    assert p["rollup"]["itv"]["under_count"] == 1          # 0.8 < 0.90
    assert p["cat"] == {"worst_tier": "high"}


def test_compute_property_well_insured_no_underinsurance():
    snap = {
        "building_count": 1, "total_tiv": 1_000_000, "worst_construction": "fire_resistive",
        "sprinklered_pct": 100, "worst_cat_tier": None, "insured_to_value_pct": 100,
        "carrier": None, "annual_premium": None, "period_label": None,
    }
    p = ext._compute_property(snap)
    assert p["rollup"]["itv"]["under_count"] == 0
    assert p["cat"] is None


# --- evaluate_property (separate readiness block) --------------------------

def test_evaluate_property_empty_is_thin():
    r = sr.evaluate_property(building_count=0, valued_count=0, cope_known_count=0,
                             itv_known=False, cat_geocoded_count=0)
    assert r["score"] == 0 and r["band"] == "thin"


def test_evaluate_property_complete_is_ready():
    r = sr.evaluate_property(building_count=2, valued_count=2, cope_known_count=2,
                             itv_known=True, cat_geocoded_count=2)
    assert r["score"] == 100 and r["band"] == "ready"


def test_evaluate_property_weights_sum_to_100():
    r = sr.evaluate_property(building_count=1, valued_count=0, cope_known_count=0,
                             itv_known=False, cat_geocoded_count=0)
    assert sum(i["weight"] for i in r["items"]) == 100
    assert r["score"] == 30   # only the SOV item done
