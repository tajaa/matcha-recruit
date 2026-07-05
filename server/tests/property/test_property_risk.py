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
    s, detail = ri._property_score(_rollup(80, ratio=1.0))
    assert s == 80 and "COPE 80/100" in detail


def test_property_score_itv_penalty_and_cap():
    assert ri._property_score(_rollup(100, ratio=0.80))[0] == 90      # -10
    assert ri._property_score(_rollup(100, ratio=0.50))[0] == 75      # capped at -25


def test_property_score_cat_penalty_capped():
    base = ri._property_score(_rollup(100, ratio=1.0))[0]
    severe = ri._property_score(_rollup(100, ratio=1.0), cat={"worst_tier": "severe"})[0]
    low = ri._property_score(_rollup(100, ratio=1.0), cat={"worst_tier": "low"})[0]
    assert severe == base - 15
    assert low == base                                               # low/moderate = no penalty


def test_property_score_applies_loss_development_penalty():
    base = ri._property_score(_rollup(100, ratio=1.0))[0]
    with_loss = ri._property_score(_rollup(100, ratio=1.0), loss={"adverse_penalty": 10, "adverse_pct": 40.0})
    assert with_loss[0] == base - 10
    assert "adverse loss dev" in with_loss[1]


def test_property_score_loss_penalty_capped_at_15():
    base = ri._property_score(_rollup(100, ratio=1.0))[0]
    with_loss = ri._property_score(_rollup(100, ratio=1.0), loss={"adverse_penalty": 999})
    assert with_loss[0] == base - 15


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
