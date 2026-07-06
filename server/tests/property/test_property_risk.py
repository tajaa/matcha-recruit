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


# documented cat (worst_peril_documented=True — flood OR quake) applies the
# full capped penalty and reports "high" confidence.
_DOCUMENTED_SEVERE_CAT = {"worst_tier": "severe", "worst_peril": "flood", "worst_peril_documented": True}
# quake tiers are ALSO documented even though quake never carries a numeric
# annual_probability — the tier itself is a real USGS reading.
_QUAKE_SEVERE_CAT = {"worst_tier": "severe", "worst_peril": "quake", "worst_peril_documented": True}
# a wildfire/wind-driven tier is explicitly marked directional -> discounted
# penalty and "moderate" confidence, even at the same "severe" tier.
_DIRECTIONAL_SEVERE_CAT = {"worst_tier": "severe", "worst_peril": "wildfire", "worst_peril_documented": False}


def test_property_score_cat_penalty_full_weight_when_documented():
    base = ri._property_score(_rollup(100, ratio=1.0))[0]
    severe = ri._property_score(_rollup(100, ratio=1.0), cat=_DOCUMENTED_SEVERE_CAT)
    assert severe[0] == base - 15
    assert severe[2] == "high"
    low = ri._property_score(_rollup(100, ratio=1.0), cat={"worst_tier": "low"})[0]
    assert low == base                                               # low/moderate = no penalty


def test_property_score_cat_penalty_full_weight_for_quake_despite_no_probability():
    # quake's tier is a real USGS ASCE7-16 reading, not a directional guess, even
    # though _quake_probability is deliberately always None — full weight, "high".
    base = ri._property_score(_rollup(100, ratio=1.0))[0]
    severe = ri._property_score(_rollup(100, ratio=1.0), cat=_QUAKE_SEVERE_CAT)
    assert severe[0] == base - 15
    assert severe[2] == "high"


def test_property_score_cat_penalty_discounted_when_directional():
    base = ri._property_score(_rollup(100, ratio=1.0))[0]
    severe = ri._property_score(_rollup(100, ratio=1.0), cat=_DIRECTIONAL_SEVERE_CAT)
    assert severe[0] == base - round(15 * 0.7)  # 70% weight, not the full 15
    assert severe[2] == "moderate"


def test_property_score_cat_penalty_full_weight_when_peril_info_missing():
    # off-platform / legacy cat dicts with no worst_peril_documented signal at
    # all (e.g. a broker-attested snapshot) trust the attested tier at full
    # weight — the discount is for model-derived directional guesses, not for
    # missing metadata.
    base = ri._property_score(_rollup(100, ratio=1.0))[0]
    severe = ri._property_score(_rollup(100, ratio=1.0), cat={"worst_tier": "severe"})
    assert severe[0] == base - 15
    assert severe[2] == "high"


def test_property_score_zero_penalty_cat_tier_does_not_drag_confidence():
    # a "low" tier is truthy (`if worst:`) but contributes zero penalty — it
    # must not be classified as directional/"moderate" just because it has no
    # documented probability.
    s, detail, conf = ri._property_score(_rollup(100, ratio=1.0), cat={"worst_tier": "low"})
    assert conf == "high"
    assert "directional" not in detail


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


def test_external_risk_index_wc_reserve_confidence_flows_from_wc_dict():
    # the broker's WC loss-run triangle confidence rides on the wc dict; a
    # volatile/thin triangle must drag the WC component (and thus the composite)
    # down, not read high. Default (no key) stays high.
    e = epl.assess_from_statuses({})
    default = ri.external_risk_index(_wc(), e)
    wc_comp = next(c for c in default["components"] if c["key"] == "wc")
    assert wc_comp["confidence"] == "high"

    low = ri.external_risk_index({**_wc(), "reserve_confidence": "low"}, e)
    wc_low = next(c for c in low["components"] if c["key"] == "wc")
    assert wc_low["confidence"] == "low"
    assert "reserves low confidence" in wc_low["detail"]
    assert low["index_confidence"] == "low"  # worst-of propagates to the composite
