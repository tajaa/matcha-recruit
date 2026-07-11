"""Pure tests for driver-risk scoring + fleet rollup (#15)."""

from app.matcha.services import driver_risk as dr


def _s(**kw):
    base = {"license_status": "valid", "major_violation": False,
            "violation_count": 0, "accident_count": 0, "status": "clear"}
    return dr.score_driver({**base, **kw})


def test_clean_driver():
    assert _s()["tier"] == "clean"


def test_high_risk_triggers():
    assert _s(license_status="suspended")["tier"] == "high_risk"
    assert _s(license_status="expired")["tier"] == "high_risk"
    assert _s(major_violation=True)["tier"] == "high_risk"
    assert _s(accident_count=2)["tier"] == "high_risk"
    assert _s(violation_count=4)["tier"] == "high_risk"


def test_marginal_triggers():
    assert _s(accident_count=1)["tier"] == "marginal"
    assert _s(violation_count=1)["tier"] == "marginal"
    assert _s(status="flagged")["tier"] == "marginal"
    assert _s(license_status="unknown")["tier"] == "marginal"


def test_points():
    # 3 violations + 1 accident + major + valid license = 3 + 2 + 5 = 10
    assert _s(violation_count=3, accident_count=1, major_violation=True)["points"] == 10
    # suspended adds 5
    assert _s(license_status="suspended")["points"] == 5


def test_severity_score():
    # clean driver scores 0
    assert _s()["score"] == 0.0
    # score is 0-100, higher = riskier, and monotonic in severity
    minor = _s(violation_count=1)["score"]          # one speeding ticket
    major = _s(major_violation=True)["score"]       # DUI/reckless
    susp = _s(license_status="suspended")["score"]  # invalid license
    assert 0 < minor < major < susp <= 100
    # a major violation weighs far more than several minor ones
    assert _s(major_violation=True)["score"] > _s(violation_count=3)["score"]
    # the worst record saturates high but never exceeds 100
    worst = _s(license_status="suspended", major_violation=True,
               accident_count=3, violation_count=6)["score"]
    assert 90 <= worst <= 100


def test_summarize_and_grade():
    drivers = [
        {"tier": "clean", "overdue": False}, {"tier": "clean", "overdue": True},
        {"tier": "marginal", "overdue": False}, {"tier": "high_risk", "overdue": True},
    ]
    s = dr.summarize(drivers)
    assert s["total_drivers"] == 4 and s["clean"] == 2 and s["high_risk"] == 1
    assert s["overdue_reviews"] == 2 and s["clean_pct"] == 50.0
    assert s["grade"] == "C"  # 50% clean, has high-risk


def test_grade_a_clean_fleet():
    drivers = [{"tier": "clean", "overdue": False}] * 9 + [{"tier": "marginal", "overdue": False}]
    assert dr.summarize(drivers)["grade"] == "A"  # 90% clean, 0 high-risk


def test_grade_d_when_high_risk_heavy():
    drivers = [{"tier": "high_risk", "overdue": False}] * 3 + [{"tier": "clean", "overdue": False}]
    assert dr.summarize(drivers)["grade"] == "D"  # 25% clean


def test_empty_fleet():
    s = dr.summarize([])
    assert s["total_drivers"] == 0 and s["grade"] == "n/a"
