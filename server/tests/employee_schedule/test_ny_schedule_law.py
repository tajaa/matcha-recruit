"""New York meal-period law (N.Y. Lab. Law § 162) end to end.

§ 162 fixes meal periods by TIME OF DAY, which is exactly what the scalar
threshold table cannot say — so these tests drive the curated period payloads
through the same parser the reviewed import path uses, then through the break
evaluator, and assert the three scenarios the ticket names:

  (2) >6h shift spanning 11:00–14:00        → 30 minutes inside that window
  (4) >6h shift starting 13:00–06:00        → 45 minutes around the midpoint
  (3) shift starting before 11:00 and
      ending after 19:00                    → an extra 20 minutes, 17:00–19:00

and that none of it reaches a state § 162 does not govern.
"""

import asyncio
from datetime import date, datetime, timedelta, timezone as dt_timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.matcha.services.scheduling import schedule_compliance, shift_compliance
from app.matcha.services.scheduling.schedule_break_rule_store import (
    resolve_break_rules,
    validate_break_rule_payload,
)
from app.matcha.services.scheduling.schedule_break_stagger import (
    StaggerAssignment,
    stagger_shift_breaks,
)
from app.matcha.services.scheduling.schedule_review import jurisdiction_message
from app.matcha.services.scheduling.schedule_breaks import (
    evaluate_break_plan,
    minimum_meal_break_minutes,
    reinterpret_schedule_wall_time,
)
from app.matcha.services.scheduling.shift_compliance import _DB_RULES_CACHE

from .test_schedule_break_rule_store import FakeConn

NY = ZoneInfo("America/New_York")


def _ny_location(*, naics=None):
    return {
        "id": uuid4(),
        "address": "42 Broadway",
        "city": "New York",
        "state": "NY",
        "zipcode": "10004",
        "jurisdiction_id": uuid4(),
        "timezone": "America/New_York",
        "naics": naics,
    }


def _ny_rules(*, naics=None, industry="hospitality"):
    """The BreakRules a NY location actually resolves to (no structured rows)."""
    _DB_RULES_CACHE.clear()
    location = _ny_location(naics=naics)
    resolved = asyncio.run(resolve_break_rules(
        FakeConn(location, structured=[], state="NY", industry=industry),
        company_id=uuid4(),
        location_id=location["id"],
        shift_date=date(2026, 9, 14),
    ))
    assert resolved.source == "legacy_curated"
    return resolved


def _plan(rules, start_hour, start_minute, end_hour, end_minute, *, day=14, end_day=None):
    """Schedule timestamps are UTC-tagged wall-clock values, not instants."""
    return evaluate_break_plan(
        starts_at=datetime(2026, 9, day, start_hour, start_minute, tzinfo=dt_timezone.utc),
        ends_at=datetime(
            2026, 9, end_day or day, end_hour, end_minute, tzinfo=dt_timezone.utc,
        ),
        timezone=NY,
        rules=rules,
    )


# ── § 162(2): the noon day meal period ────────────────────────────────────

def test_noonday_meal_for_a_shift_over_six_hours_spanning_11_to_14():
    plan = _plan(_ny_rules().rules, 7, 0, 15, 0)

    assert len(plan.requirements) == 1
    meal = plan.requirements[0]
    assert (meal.kind, meal.duration_minutes, meal.paid) == ("meal", 30, False)
    assert meal.earliest_local.strftime("%H:%M") == "11:00"
    assert meal.deadline_local.strftime("%H:%M") == "14:00"
    assert "162(2)" in meal.citation
    assert minimum_meal_break_minutes(plan) == 30


def test_a_six_hour_shift_owes_no_noonday_meal():
    # § 162(2) is "more than six hours"; exactly six is not more than six.
    assert _plan(_ny_rules().rules, 8, 0, 14, 0).requirements == ()


def test_a_shift_that_clocks_out_before_two_owes_no_noonday_meal():
    # 07:00–13:30 is over six hours but does not extend over the whole noon
    # day period, so § 162(2) does not attach. The scalar 6h/30min floor in
    # `_SCHEDULING_RULES` is what still flags it at write time — see
    # `test_scalar_floor_still_flags_a_long_shift_without_a_break`.
    assert _plan(_ny_rules().rules, 7, 0, 13, 30).requirements == ()


# ── § 162(4): the midway meal for afternoon/night shifts ──────────────────

def test_afternoon_shift_starting_after_one_gets_45_minutes_at_the_midpoint():
    plan = _plan(_ny_rules().rules, 15, 0, 23, 30)

    assert len(plan.requirements) == 1
    meal = plan.requirements[0]
    assert meal.duration_minutes == 45
    # Midway between the beginning and end of the shift: 8h30 - 45min, halved.
    assert meal.recommended_local.strftime("%H:%M") == "18:52"
    assert meal.deadline_local is None
    assert "162(4)" in meal.citation
    assert "§ 162(5)" in meal.citation  # the only permitted shortening


def test_overnight_shift_starting_before_six_am_is_also_midway_governed():
    plan = _plan(_ny_rules().rules, 22, 0, 6, 0, end_day=15)

    assert [r.duration_minutes for r in plan.requirements] == [45]
    assert plan.requirements[0].recommended_local.strftime("%H:%M") == "01:37"


def test_a_shift_starting_at_noon_is_outside_the_midway_window():
    # Starts after 11:00 (so not § 162(2)-spanning) and before 13:00 (so not
    # § 162(4)). The statute leaves this seam; we do not invent a rule for it.
    assert _plan(_ny_rules().rules, 12, 0, 19, 0).requirements == ()


# ── § 162(3): the additional evening meal period ──────────────────────────

def test_early_start_late_finish_adds_twenty_minutes_between_five_and_seven():
    plan = _plan(_ny_rules().rules, 9, 0, 20, 0)

    assert [(r.duration_minutes, r.ordinal) for r in plan.requirements] == [(30, 1), (20, 3)]
    extra = plan.requirements[1]
    assert extra.earliest_local.strftime("%H:%M") == "17:00"
    assert extra.deadline_local.strftime("%H:%M") == "19:00"
    assert extra.citation == "N.Y. Lab. Law § 162(3)"
    # Both periods are meals, so the shift's planned break must cover both.
    assert minimum_meal_break_minutes(plan) == 50


def test_stagger_places_both_new_york_periods_inside_their_own_windows():
    starts = datetime(2026, 9, 14, 9, 0, tzinfo=dt_timezone.utc)
    ends = datetime(2026, 9, 14, 20, 0, tzinfo=dt_timezone.utc)
    plan = evaluate_break_plan(
        starts_at=starts, ends_at=ends, timezone=NY, rules=_ny_rules().rules,
    )
    staggered = stagger_shift_breaks(
        shift_start_local=reinterpret_schedule_wall_time(starts, NY),
        shift_end_local=reinterpret_schedule_wall_time(ends, NY),
        required_staff=1,
        assignments=[
            StaggerAssignment(employee_id=uuid4(), plan=plan) for _ in range(3)
        ],
    )

    assert {result.status for result in staggered.results} == {"suggested"}
    for window_ordinal, opens, closes in ((1, 11, 14), (3, 17, 19)):
        starts_local = sorted(
            result.suggested_start for result in staggered.results
            if result.ordinal == window_ordinal
        )
        assert len(set(starts_local)) == 3, "one crew must not all break at once"
        for suggested, result in zip(starts_local, staggered.results):
            assert suggested.hour >= opens
            assert (
                suggested + timedelta(minutes=result.duration_minutes)
            ).hour <= closes


def test_a_shift_ending_exactly_at_seven_owes_no_additional_period():
    plan = _plan(_ny_rules().rules, 9, 0, 19, 0)

    assert [r.duration_minutes for r in plan.requirements] == [30]


# ── Industry variation: factories get sixty minutes ───────────────────────

def test_factory_naics_selects_the_sixty_minute_noonday_period():
    plan = _plan(_ny_rules(naics="3118").rules, 7, 0, 15, 0)

    assert [r.duration_minutes for r in plan.requirements] == [60]
    assert "162(1)" in plan.requirements[0].citation


def test_manufacturing_industry_without_naics_also_selects_the_factory_rule():
    plan = _plan(_ny_rules(industry="manufacturing").rules, 15, 0, 23, 30)

    assert [r.duration_minutes for r in plan.requirements] == [60]


def test_a_coffee_shop_gets_the_general_rule_not_the_factory_one():
    entry = schedule_compliance.curated_break_periods("NY", "hospitality")
    assert entry["scope"] == "general"


# ── Scope: § 162 governs New York and nowhere else ────────────────────────

def test_no_other_state_picks_up_new_yorks_periods():
    for state in ("CA", "TX", "WA", None):
        assert schedule_compliance.curated_break_periods(state) is None


def test_california_still_resolves_its_own_deadline_rule():
    _DB_RULES_CACHE.clear()
    location = _ny_location()
    location["state"] = "CA"
    location["timezone"] = "America/Los_Angeles"
    resolved = asyncio.run(resolve_break_rules(
        FakeConn(location, structured=[], state="CA"),
        company_id=uuid4(), location_id=location["id"], shift_date=date(2026, 9, 14),
    ))
    rule = resolved.rules[0]
    assert (rule.trigger_after_minutes, rule.duration_minutes) == (300, 30)
    assert rule.window_start is None and rule.shift_spans_window_start is None


# ── The thresholds behind the write-path gate and the legality banner ─────

def test_new_york_reads_as_researched_rather_than_unverified(monkeypatch):
    """The reported bug: NY used to answer `unmapped`, so every surface said
    "Legality was NOT verified for NY"."""
    async def fake_location_state(*_a):
        return "NY", "New York"

    async def boom(*_a):
        raise AssertionError("a curated state must not consult the catalog")

    monkeypatch.setattr(shift_compliance, "_location_state", fake_location_state)
    monkeypatch.setattr(shift_compliance, "_approved_db_rules", boom)
    status = asyncio.run(
        shift_compliance.jurisdiction_rule_status(None, uuid4(), uuid4())
    )
    assert status == {"state": "NY", "status": "curated"}
    assert "on file" in jurisdiction_message(status)["message"]
    assert "NOT verified" not in jurisdiction_message(status)["message"]


def test_scalar_floor_still_flags_a_long_shift_without_a_break():
    violations = schedule_compliance.evaluate_shift_for_employee(
        state="NY", shift_hours=6.5, break_minutes=0,
    )
    assert [v["check"] for v in violations] == ["meal_break"]
    assert violations[0]["statute"] == "N.Y. Lab. Law § 162"


def test_new_york_has_no_daily_overtime_and_no_statewide_rest_gap():
    violations = schedule_compliance.evaluate_shift_for_employee(
        state="NY", shift_hours=10.0, break_minutes=60, min_rest_gap_hours=6.0,
    )
    assert violations == []


def test_weekly_overtime_and_minor_caps_come_from_new_york_law():
    weekly = schedule_compliance.evaluate_shift_for_employee(
        state="NY", shift_hours=8.0, break_minutes=30, week_hours=44.0,
    )
    assert [v["check"] for v in weekly] == ["weekly_overtime"]
    assert weekly[0]["statute"] == "12 NYCRR § 142-2.2"

    minor = schedule_compliance.evaluate_shift_for_employee(
        state="NY", shift_hours=9.0, break_minutes=30, age=16,
    )
    assert [(v["check"], v["severity"]) for v in minor] == [("minor_hours", "block")]
    assert minor[0]["statute"] == "N.Y. Lab. Law §§ 171-172"


# ── The payloads themselves ───────────────────────────────────────────────

def test_curated_break_payloads_parse():
    """`_legacy_rules` lets a malformed payload raise; this is the guard."""
    for state, entries in schedule_compliance._CURATED_BREAK_PERIODS.items():
        assert entries, state
        for entry in entries:
            validate_break_rule_payload(entry["payload"], entry["citation"])
            assert entry["citation"] and entry["authority_url"]


def test_every_curated_period_carries_its_own_subdivision():
    rules = _ny_rules().rules
    # (kind, ordinal) is the key the stagger and the saved planned-break rows
    # use, so two subdivisions governing one shift must not collide.
    assert len({(rule.kind, rule.ordinal) for rule in rules}) == len(rules)
    assert all(rule.citation.startswith("N.Y. Lab. Law") for rule in rules)
    assert all(rule.authority_url for rule in rules)
