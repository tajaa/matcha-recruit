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


def test_minor_16_17_federal_no_cap_is_silent():
    # FLSA affirmatively imposes no 16-17 hour cap (NO_CAP sentinel) — a
    # determination, not a gap: no violation AND no bogus "not researched"
    # advisory on every shift.
    r = sc.rules_for_state("TX")
    assert r["minor_16_17_day_hours"] is sc.NO_CAP
    assert sc.check_minor_hours(17, 10.0, 50.0, r, "TX") == []


def test_minor_16_17_state_cap_overrides_federal_no_cap():
    # CA's own 8h cap for 16-17 wins over the federal NO_CAP.
    r = sc.rules_for_state("CA")
    v = sc.check_minor_hours(17, 9.0, None, r, "CA")
    assert len(v) == 1 and v[0]["severity"] == "block"


def test_minor_truly_unresearched_bracket_is_advisory():
    # Simulate a bracket with NO determination at all (neither cap nor NO_CAP):
    # advisory, never a silent pass.
    bare = {"citations": {}}
    v = sc.check_minor_hours(17, 10.0, None, bare, "ZZ")
    assert len(v) == 1 and v[0]["severity"] == "advisory"


def test_rules_summary_is_json_safe():
    import json
    json.dumps(sc.rules_summary("TX"))  # NO_CAP sentinel must serialize
    assert sc.rules_summary("TX")["minor_16_17_day_hours"] == "no_cap"


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


# --------------------------------------------------------------------------- #
# Catalog-extraction gate merge (db_rules) — per-state precedence, block_grade,
# safety-net partial-coverage.
# --------------------------------------------------------------------------- #

def test_is_curated_state():
    assert sc.is_curated_state("CA") is True
    assert sc.is_curated_state("ca") is True
    assert sc.is_curated_state("TX") is False
    assert sc.is_curated_state(None) is False


def test_db_rules_apply_for_an_uncurated_state():
    db_rules = {
        "meal_break_after_hours": 5.0, "meal_break_minutes": 30.0,
        "citations": {"meal_break": "Wash. Rev. Code § 49.12.020"},
    }
    r = sc.rules_for_state("WA", db_rules)
    assert r["meal_break_after_hours"] == 5.0
    assert r["citations"]["meal_break"] == "Wash. Rev. Code § 49.12.020"
    # federal baseline still underneath
    assert r["weekly_ot_hours"] == 40
    v = sc.check_meal_break(5.5, 0, r, "WA")
    assert len(v) == 1 and v[0]["statute"] == "Wash. Rev. Code § 49.12.020"


def test_db_rules_ignored_for_a_code_curated_state():
    # CA is hand-curated — db_rules must never leak in, even a wildly
    # different value, because per-state precedence ignores it entirely.
    db_rules = {"meal_break_after_hours": 99.0, "citations": {"meal_break": "bogus"}}
    r = sc.rules_for_state("CA", db_rules)
    assert r["meal_break_after_hours"] == 5          # CA's own curated value
    assert r["citations"]["meal_break"] == "Cal. Lab. Code § 512"


def test_no_rule_becomes_no_cap_sentinel():
    db_rules = {"minor_16_17_day_hours": sc.NO_CAP, "citations": {}}
    r = sc.rules_for_state("WA", db_rules)
    assert r["minor_16_17_day_hours"] is sc.NO_CAP


def test_minor_block_grade_advisory_by_default():
    # DB-sourced minor caps are advisory unless explicitly block-graded.
    db_rules = {
        "minor_u16_day_hours": 8.0, "citations": {"minor_hours": "Wash. Rev. Code § 26.28.060"},
        "_minor_block_grade": {"minor_u16_day_hours": False},
    }
    v = sc.evaluate_shift_for_employee(state="WA", shift_hours=9.0, break_minutes=0, age=15, db_rules=db_rules)
    minor = [x for x in v if x["check"] == "minor_hours"]
    assert len(minor) == 1 and minor[0]["severity"] == "advisory"


def test_minor_block_grade_blocks_when_flagged():
    db_rules = {
        "minor_u16_day_hours": 8.0, "citations": {"minor_hours": "Wash. Rev. Code § 26.28.060"},
        "_minor_block_grade": {"minor_u16_day_hours": True},
    }
    v = sc.evaluate_shift_for_employee(state="WA", shift_hours=9.0, break_minutes=0, age=15, db_rules=db_rules)
    minor = [x for x in v if x["check"] == "minor_hours"]
    assert len(minor) == 1 and minor[0]["severity"] == "block"
    assert sc.has_block(v) is True


def test_curated_state_minor_caps_still_always_block():
    # In-code CA/US minor caps are unaffected by the block_grade machinery —
    # block_grade is None for them (rules_for_state never attaches it).
    v = sc.evaluate_shift_for_employee(state="CA", shift_hours=9.0, break_minutes=0, age=15)
    minor = [x for x in v if x["check"] == "minor_hours"]
    assert len(minor) == 1 and minor[0]["severity"] == "block"


def test_safety_net_fires_on_partial_db_coverage():
    # Only weekly OT approved for this state — meal-break/daily-OT are still
    # undetermined, so an extreme shift must still warn.
    db_rules = {"weekly_ot_hours": 45.0, "citations": {"weekly_overtime": "cited"}}
    v = sc.evaluate_shift_for_employee(state="WA", shift_hours=13.0, break_minutes=60, db_rules=db_rules)
    assert any(x["check"] == "unmapped_state" for x in v)


def test_safety_net_silenced_once_meal_or_ot_is_determined():
    db_rules = {"daily_ot_hours": 10.0, "citations": {"daily_overtime": "cited"}}
    v = sc.evaluate_shift_for_employee(state="WA", shift_hours=13.0, break_minutes=60, db_rules=db_rules)
    # daily_ot_hours=10 fires its own advisory instead of the generic net.
    checks = {x["check"] for x in v}
    assert "daily_overtime" in checks
    assert "unmapped_state" not in checks


def test_rules_summary_source_marker():
    assert sc.rules_summary("CA")["source"] == "curated"
    assert sc.rules_summary("WA")["source"] == "unmapped"
    assert sc.rules_summary("WA", {"weekly_ot_hours": 40.0})["source"] == "catalog_extraction"
    # internal minor_block_grade key never leaks into the JSON-safe summary
    assert "_minor_block_grade" not in sc.rules_summary(
        "WA", {"minor_u16_day_hours": 8.0, "_minor_block_grade": {"minor_u16_day_hours": True}}
    )
