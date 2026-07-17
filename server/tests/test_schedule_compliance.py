"""Pure-logic tests for scheduling compliance (no DB, no network).

Covers the curated-table evaluators + orchestration. The DB assembly
(`routes/employee_schedule/_compliance.py`) and catalog fetch are exercised
manually on dev DB — see the plan's verification section.
"""

from app.matcha.services import schedule_compliance as sc


def test_rules_for_state_merges_federal_and_state():
    r = sc.rules_for_state("CA")
    assert r["meal_break_after_hours"] == 5          # CA override
    assert r["weekly_ot_hours"] == 40                # shared
    assert r["citations"]["meal_break"] == "Cal. Lab. Code § 512"
    # unmapped state → federal baseline only
    assert "meal_break_after_hours" not in sc.rules_for_state("TX")


def test_meal_break_boundary():
    r = sc.rules_for_state("CA")
    assert sc.check_meal_break(5.0, 0, r, "CA") == []          # exactly 5h → clear
    v = sc.check_meal_break(5.5, 0, r, "CA")                    # over 5h, no break
    assert len(v) == 1 and v[0]["severity"] == "advisory"
    assert v[0]["statute"] == "Cal. Lab. Code § 512"
    assert sc.check_meal_break(5.5, 30, r, "CA") == []          # adequate break → clear


def test_daily_and_weekly_overtime_advisory():
    r = sc.rules_for_state("CA")
    assert sc.check_daily_overtime(8.0, r, "CA") == []
    assert sc.check_daily_overtime(9.0, r, "CA")[0]["check"] == "daily_overtime"
    assert "double-time" in sc.check_daily_overtime(13.0, r, "CA")[0]["message"]
    assert sc.check_weekly_hours(40.0, r, "CA") == []
    assert sc.check_weekly_hours(45.0, r, "CA")[0]["severity"] == "advisory"
    assert sc.check_weekly_hours(None, r, "CA") == []           # unknown → skip


def test_weekly_overtime_applies_to_unmapped_state_via_federal():
    r = sc.rules_for_state("TX")  # no state row → federal 40h still applies
    assert sc.check_weekly_hours(50.0, r, "TX")[0]["statute"] == "FLSA, 29 U.S.C. § 207(a)"


def test_minor_hours_blocks():
    r = sc.rules_for_state("CA")
    v = sc.check_minor_hours(15, 9.0, None, r, "CA")            # 15yo, 9h > 8h cap
    assert len(v) == 1 and v[0]["severity"] == "block"
    assert sc.check_minor_hours(15, 7.0, None, r, "CA") == []   # within cap → clear
    assert sc.check_minor_hours(19, 12.0, None, r, "CA") == []  # adult → no minor rule
    assert sc.check_minor_hours(None, 12.0, None, r, "CA") == []  # unknown age → skip


def test_minor_unmapped_bracket_is_advisory_not_clear():
    # 16-17 in a state with no researched 16-17 cap → advisory, never silent pass.
    r = sc.rules_for_state("TX")
    v = sc.check_minor_hours(17, 10.0, None, r, "TX")
    assert len(v) == 1 and v[0]["severity"] == "advisory"


def test_min_rest_only_fires_when_threshold_mapped():
    r = sc.rules_for_state("CA")  # min_rest_between_shifts_hours = None
    assert sc.check_min_rest(2.0, r, "CA") == []               # no CA statute → no result


def test_evaluate_orchestration_and_has_block():
    # CA minor on an 11h shift → block (minor) + advisories (meal, daily OT).
    v = sc.evaluate_shift_for_employee(
        state="CA", shift_hours=11.0, break_minutes=0, week_hours=44.0, age=15,
    )
    checks = {x["check"] for x in v}
    assert "minor_hours" in checks and "meal_break" in checks and "daily_overtime" in checks
    assert sc.has_block(v) is True


def test_unmapped_state_extreme_shift_warns():
    v = sc.evaluate_shift_for_employee(state="TX", shift_hours=13.0, break_minutes=60)
    assert any(x["check"] == "unmapped_state" for x in v)
    # an ordinary unmapped-state shift stays quiet (weekly/daily need data)
    assert sc.evaluate_shift_for_employee(state="TX", shift_hours=6.0, break_minutes=30) == []
