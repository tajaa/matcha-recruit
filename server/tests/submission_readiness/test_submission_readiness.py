"""Pure tests for submission-readiness scoring (DB gather smoke-tested vs dev)."""

from app.matcha.services import submission_readiness as sr

# Signals that mark every item done (perfect submission).
ALL_DONE = dict(
    states_count=2, headcount=50, industry="retail", experience_mod_present=True,
    recordable_cases=3, untyped_recordables=0, lost_time_cases=1, rtw_resolved=1,
    rtw_avg_days=30, class_count=4, epl_unknown_count=0, ah_policy_score=80,
    controls_verified_count=5, controls_unverified_count=0,
)
# Signals that mark every item missing (thin submission).
NONE_DONE = dict(
    states_count=0, headcount=None, industry=None, experience_mod_present=False,
    recordable_cases=5, untyped_recordables=5, lost_time_cases=2, rtw_resolved=0,
    rtw_avg_days=None, class_count=0, epl_unknown_count=5, ah_policy_score=0,
    controls_verified_count=0, controls_unverified_count=8,
)


def test_all_done_is_100_ready():
    r = sr.evaluate(**ALL_DONE)
    assert r["score"] == 100
    assert r["band"] == "ready"
    assert r["summary"] == {"done": 10, "total": 10}
    assert r["top_fixes"] == []


def test_none_done_is_0_thin():
    r = sr.evaluate(**NONE_DONE)
    assert r["score"] == 0
    assert r["band"] == "thin"
    assert r["summary"]["done"] == 0
    # highest-weight missing items lead the fix list (epl_questionnaire=18, experience_mod=14)
    items = {i["key"]: i for i in r["items"]}
    assert items["epl_questionnaire"]["weight"] == 18
    assert r["top_fixes"][0] == items["epl_questionnaire"]["fix"]
    assert len(r["top_fixes"]) == 5  # capped


def test_weights_sum_to_100():
    assert sum(i["weight"] for i in sr.evaluate(**NONE_DONE)["items"]) == 100


def test_claim_typing_done_when_no_recordables():
    sig = {**NONE_DONE, "recordable_cases": 0, "untyped_recordables": 0}
    items = {i["key"]: i for i in sr.evaluate(**sig)["items"]}
    assert items["claim_typing"]["done"] is True


def test_rtw_done_when_no_lost_time():
    sig = {**NONE_DONE, "lost_time_cases": 0}
    items = {i["key"]: i for i in sr.evaluate(**sig)["items"]}
    assert items["return_to_work"]["done"] is True


def test_band_thresholds():
    assert sr.readiness_band(80) == "ready"
    assert sr.readiness_band(79) == "developing"
    assert sr.readiness_band(50) == "developing"
    assert sr.readiness_band(49) == "thin"


def test_partial_score_is_sum_of_done_weights():
    # only operating_locations (10) + experience_mod (14) done
    sig = {**NONE_DONE, "states_count": 1, "experience_mod_present": True}
    r = sr.evaluate(**sig)
    assert r["score"] == 24
