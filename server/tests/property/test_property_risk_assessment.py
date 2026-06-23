"""Pure-logic tests for the composite property risk ASSESSMENT (per-building + portfolio).

No DB — only app.matcha.services.property_risk. (Distinct from test_property_risk.py,
which covers risk_index._property_score, the cross-line composite feed.)
"""

from app.matcha.services import property_risk as pr


def _b(bid="b1", cope_score=90, cope_grade="A", itv_ratio=1.0, perils=None,
       building_value=5_000_000, contents_value=0, bi_value=0):
    return {
        "id": bid, "name": f"Bldg {bid}", "cope_score": cope_score, "cope_grade": cope_grade,
        "itv_ratio": itv_ratio, "perils": perils or [],
        "building_value": building_value, "contents_value": contents_value, "bi_value": bi_value,
    }


def test_clean_building_scores_high():
    r = pr.building_risk(_b(cope_score=92, cope_grade="A", itv_ratio=1.0, perils=[{"peril": "wind", "tier": "low"}]))
    assert r["score"] == 92 and r["grade"] == "A" and r["risk_level"] == "low"


def test_underinsurance_penalizes_capped():
    r = pr.building_risk(_b(cope_score=90, itv_ratio=0.60))   # (0.90-0.60)*100=30 → capped at 25
    assert r["score"] == 65
    assert any(d["factor"] == "Under-insured" and d["delta"] == -25 for d in r["drivers"])


def test_catastrophe_penalizes_by_worst_tier():
    r = pr.building_risk(_b(cope_score=90, itv_ratio=1.0,
                            perils=[{"peril": "flood", "tier": "low"}, {"peril": "quake", "tier": "severe"}]))
    assert r["score"] == 90 - pr._CAT_PENALTY["severe"]
    assert r["worst_cat"] == "severe"


def test_no_cope_is_unscored():
    r = pr.building_risk(_b(cope_score=None, cope_grade=None))
    assert r["score"] is None and r["grade"] is None


def test_score_floored_at_zero():
    r = pr.building_risk(_b(cope_score=5, itv_ratio=0.50, perils=[{"peril": "quake", "tier": "severe"}]))
    assert r["score"] >= 0


def test_portfolio_is_tiv_weighted():
    big = _b("big", cope_score=95, cope_grade="A", building_value=50_000_000)
    small = _b("small", cope_score=20, cope_grade="D", building_value=1_000_000,
               itv_ratio=0.5, perils=[{"peril": "quake", "tier": "severe"}])
    out = pr.portfolio_risk([big, small])
    assert out["rated"] == 2
    assert out["score"] > 85                                   # weighted toward the big clean building
    assert out["top_risks"][0]["building_id"] == "small"       # worst posture surfaces first


def test_portfolio_empty():
    out = pr.portfolio_risk([])
    assert out["score"] is None and out["top_risks"] == [] and out["rated"] == 0


# --- deeper capture (propd01): valuation / hazards / protection -----------

def test_acv_valuation_penalizes():
    r = pr.building_risk({**_b(cope_score=90, perils=[{"peril": "wind", "tier": "low"}]), "valuation_basis": "ACV"})
    assert r["score"] == 86 and any(d["factor"] == "Valuation" for d in r["drivers"])


def test_occupancy_hazards_capped_at_12():
    r = pr.building_risk({**_b(cope_score=90, perils=[{"peril": "wind", "tier": "low"}]),
                          "cooking_nfpa96": True, "hot_work": True, "hazmat": True})  # 4+4+6=14 → cap 12
    assert any(d["factor"] == "Occupancy hazard" and d["delta"] == -12 for d in r["drivers"])
    assert r["score"] == 78


def test_central_station_alarm_credit():
    base = pr.building_risk(_b(cope_score=80, perils=[{"peril": "wind", "tier": "low"}]))["score"]
    boosted = pr.building_risk({**_b(cope_score=80, perils=[{"peril": "wind", "tier": "low"}]),
                                "central_station_alarm": True})["score"]
    assert boosted == base + 3
