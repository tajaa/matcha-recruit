"""Pure-logic tests for the property risk component + index integration.

No DB — only risk_index pure helpers. The DB-backed _property_component /
compute_risk_index are exercised by manual integration on dev.
"""

from app.matcha.services import risk_index as ri
from app.matcha.services import epl_readiness as epl


def _rollup(score, ratio=None, under=0, n=2):
    return {"building_count": n, "avg_cope_score": score,
            "itv": {"portfolio_ratio": ratio, "under_count": under, "rated_count": n}}


# --- _property_score -------------------------------------------------------

def test_property_score_none_without_buildings():
    assert ri._property_score({"building_count": 0}) is None
    assert ri._property_score({"building_count": 2, "avg_cope_score": None}) is None


def test_property_score_is_cope_when_well_insured():
    s, detail, conf = ri._property_score(_rollup(80, ratio=1.0))
    assert s == 80 and "COPE 80/100" in detail
    assert conf == "high"  # no cat/loss signal present at all -> nothing to discount


def test_property_score_itv_penalty_and_cap():
    assert ri._property_score(_rollup(100, ratio=0.80))[0] == 90      # -10
    assert ri._property_score(_rollup(100, ratio=0.50))[0] == 75      # capped at -25


# documented cat (flood/quake with a hazard-agency annual probability) applies
# the full capped penalty and reports "high" confidence.
_DOCUMENTED_SEVERE_CAT = {"worst_tier": "severe", "worst_peril": "flood",
                          "by_peril_detail": {"flood": {"tier": "severe", "annual_probability": 0.01}}}
# a wildfire/wind-driven tier has no documented probability -> discounted penalty
# and "moderate" confidence, even at the same "severe" tier.
_DIRECTIONAL_SEVERE_CAT = {"worst_tier": "severe", "worst_peril": "wildfire",
                          "by_peril_detail": {"wildfire": {"tier": "severe", "annual_probability": None}}}


def test_property_score_cat_penalty_full_weight_when_documented():
    base = ri._property_score(_rollup(100, ratio=1.0))[0]
    severe = ri._property_score(_rollup(100, ratio=1.0), cat=_DOCUMENTED_SEVERE_CAT)
    assert severe[0] == base - 15
    assert severe[2] == "high"
    low = ri._property_score(_rollup(100, ratio=1.0), cat={"worst_tier": "low"})[0]
    assert low == base                                               # low/moderate = no penalty


def test_property_score_cat_penalty_discounted_when_directional():
    base = ri._property_score(_rollup(100, ratio=1.0))[0]
    severe = ri._property_score(_rollup(100, ratio=1.0), cat=_DIRECTIONAL_SEVERE_CAT)
    assert severe[0] == base - round(15 * 0.7)  # 70% weight, not the full 15
    assert severe[2] == "moderate"


def test_property_score_cat_penalty_undocumented_missing_peril_info_discounted():
    # a legacy/synthetic cat dict with no worst_peril/by_peril_detail (e.g. an
    # off-platform snapshot) can't be verified as documented -> discounted too.
    base = ri._property_score(_rollup(100, ratio=1.0))[0]
    severe = ri._property_score(_rollup(100, ratio=1.0), cat={"worst_tier": "severe"})
    assert severe[0] == base - round(15 * 0.7)
    assert severe[2] == "moderate"


def test_property_score_applies_loss_development_penalty_full_weight_when_high_confidence():
    base = ri._property_score(_rollup(100, ratio=1.0))[0]
    with_loss = ri._property_score(_rollup(100, ratio=1.0),
                                    loss={"adverse_penalty": 10, "adverse_pct": 40.0, "confidence": "high"})
    assert with_loss[0] == base - 10
    assert "adverse loss dev" in with_loss[1]
    assert with_loss[2] == "high"


def test_property_score_applies_loss_development_penalty_discounted_when_low_confidence():
    base = ri._property_score(_rollup(100, ratio=1.0))[0]
    # no "confidence" key at all -> defaults to "low" -> 60% weight
    with_loss = ri._property_score(_rollup(100, ratio=1.0), loss={"adverse_penalty": 10, "adverse_pct": 40.0})
    assert with_loss[0] == base - round(10 * 0.6)
    assert with_loss[2] == "low"


def test_property_score_loss_penalty_capped_at_15_before_weighting():
    base = ri._property_score(_rollup(100, ratio=1.0))[0]
    with_loss = ri._property_score(_rollup(100, ratio=1.0), loss={"adverse_penalty": 999, "confidence": "high"})
    assert with_loss[0] == base - 15  # capped at 15 before the (here, full) confidence weight applies


def test_property_score_worst_confidence_wins_across_cat_and_loss():
    # documented (high) cat + low-confidence loss dev -> overall confidence is "low"
    r = ri._property_score(_rollup(100, ratio=1.0), cat=_DOCUMENTED_SEVERE_CAT,
                           loss={"adverse_penalty": 5, "confidence": "low"})
    assert r[2] == "low"


# --- external_risk_index back-compat + property wiring ---------------------

def _wc():
    return {"has_data": True, "severity_band": "good", "current_emr": 0.9,
            "recordable_cases": 1, "trir": 2.0}


def test_external_risk_index_backcompat_when_no_property():
    e = epl.assess_from_statuses({})
    assert ri.external_risk_index(_wc(), e) == ri.external_risk_index(_wc(), e, None)


def test_external_risk_index_adds_property_component():
    e = epl.assess_from_statuses({})
    base = ri.external_risk_index(_wc(), e)
    prop = {"rollup": _rollup(80, ratio=1.0), "cat": None}
    withp = ri.external_risk_index(_wc(), e, prop)
    assert len(withp["components"]) == len(base["components"]) + 1
    assert any(c["key"] == "property" for c in withp["components"])


def test_external_risk_index_property_absent_when_no_buildings():
    e = epl.assess_from_statuses({})
    prop = {"rollup": {"building_count": 0}, "cat": None}
    withp = ri.external_risk_index(_wc(), e, prop)
    assert not any(c["key"] == "property" for c in withp["components"])
