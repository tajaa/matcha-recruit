"""Risk-to-Rate lever scoring — pure, DB-free."""

from app.matcha.services import risk_to_rate as rr


def test_realized_vs_available_split():
    # safety in place, training a known gap, everything else untracked
    out = rr.score_levers({"safety_programs": "verified", "training": "gap"})
    by_key = {l["key"]: l for l in out["levers"]}
    assert by_key["safety_programs"]["status"] == "realized"
    assert by_key["safety_programs"]["basis"] == "in_place"
    assert by_key["training"]["status"] == "available"
    assert by_key["training"]["basis"] == "gap"
    # realized credit picks up safety's 200bps; training's 150 sits in available
    assert out["realized_credit_bps"] == 200
    assert out["available_credit_bps"] == out["total_credit_bps"] - 200


def test_nothing_tracked_is_all_available():
    out = rr.score_levers({})
    assert out["realized_credit_bps"] == 0
    assert out["available_credit_bps"] == out["total_credit_bps"] > 0
    assert all(l["status"] == "available" and l["basis"] == "not_tracked" for l in out["levers"])


def test_available_levers_sort_first():
    out = rr.score_levers({"safety_programs": "verified"})  # only safety realized
    statuses = [l["status"] for l in out["levers"]]
    # every 'available' comes before any 'realized'
    assert statuses == sorted(statuses, key=lambda s: s != "available")


def test_readiness_score_passthrough():
    assert rr.score_levers({}, readiness_score=72)["readiness_score"] == 72
