"""New York meal-period law (N.Y. Lab. Law § 162) end to end.

§ 162 fixes meal periods by TIME OF DAY, which is exactly what the scalar
threshold table cannot say — so these tests drive the curated period payloads
through the same parser the reviewed import path uses, then through the break
evaluator, and assert the three scenarios the ticket names:

  (2) >6h shift overlapping 11:00–14:00     → 30 minutes inside that window
  (4) >6h shift starting 11:01–06:00        → 45 minutes around the midpoint
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


def test_a_shift_that_clocks_out_before_two_still_owes_the_noonday_meal():
    # 07:00–13:30 is over six hours and is working through part of the noon day
    # period, so § 162(2) attaches even though the shift ends before 2 PM. The
    # stagger clamps the 2 PM deadline to what the shift can actually hold.
    plan = _plan(_ny_rules().rules, 7, 0, 13, 30)

    assert [r.duration_minutes for r in plan.requirements] == [30]
    assert plan.requirements[0].earliest_local.strftime("%H:%M") == "11:00"


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


def test_a_shift_starting_after_eleven_gets_the_midway_meal():
    # The 11 AM–1 PM slice is unassigned by § 162's own text. It goes to (4):
    # someone who clocks in after the noon day period has begun cannot take the
    # noon day meal at a sensible hour.
    plan = _plan(_ny_rules().rules, 12, 0, 19, 0)

    assert [(r.duration_minutes, r.ordinal) for r in plan.requirements] == [(45, 2)]
    assert plan.requirements[0].recommended_local.strftime("%H:%M") == "15:07"


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


# ── The three shifts the reviewer scheduled by hand (round 2) ─────────────
#
# Verbatim from the send-back: 6:30a–2:30p and 10:30a–6:30p were each owed a
# 30-minute break, the first correctly suggested at 11 AM and the second
# "compliant but not realistic to send an employee on break after only 30
# minutes"; 12:30p–8:30p was "incorrectly recommending no break, this should be
# recommending a 45 minute break and it should suggest 'midway through'".

def _suggested(rules, start_hour, start_minute, end_hour, end_minute):
    """What the manager actually sees: the plan, placed."""
    starts = datetime(2026, 9, 14, start_hour, start_minute, tzinfo=dt_timezone.utc)
    ends = datetime(2026, 9, 14, end_hour, end_minute, tzinfo=dt_timezone.utc)
    plan = evaluate_break_plan(starts_at=starts, ends_at=ends, timezone=NY, rules=rules)
    staggered = stagger_shift_breaks(
        shift_start_local=reinterpret_schedule_wall_time(starts, NY),
        shift_end_local=reinterpret_schedule_wall_time(ends, NY),
        required_staff=1,
        assignments=[StaggerAssignment(employee_id=uuid4(), plan=plan)],
    )
    return [
        (r.duration_minutes, r.suggested_start.strftime("%H:%M"))
        for r in sorted(staggered.results, key=lambda r: r.ordinal)
    ]


def test_reviewer_case_0630_to_1430_keeps_the_eleven_am_noonday_meal():
    assert _suggested(_ny_rules().rules, 6, 30, 14, 30) == [(30, "11:00")]


def test_reviewer_case_1030_to_1830_is_not_sent_on_break_thirty_minutes_in():
    # Still inside the 11:00–14:00 noon day window, but no longer at its very
    # opening: the placement floor reaches a wall-clock earliest now.
    assert _suggested(_ny_rules().rules, 10, 30, 18, 30) == [(30, "12:30")]


def test_reviewer_case_1230_to_2030_gets_the_forty_five_minute_midway_meal():
    assert _suggested(_ny_rules().rules, 12, 30, 20, 30) == [(45, "16:07")]


def test_no_start_time_falls_between_the_two_primary_meal_rules():
    """No >6h shift may fall between § 162(2) and § 162(4), at any start time.

    A gap is the bug the reviewer found. The rules are NOT mutually exclusive:
    a shift starting before 6 a.m. that works through midday meets both
    subdivisions on their own terms and is owed both meals. What must never
    happen is zero primary meals, or a `(kind, ordinal)` collision on the key
    the stagger and `planned_breaks` persist.
    """
    rules = _ny_rules().rules
    for minutes in range(0, 24 * 60, 30):
        start_hour, start_minute = divmod(minutes, 60)
        end = minutes + 8 * 60
        plan = _plan(
            rules, start_hour, start_minute, (end // 60) % 24, end % 60,
            end_day=14 + (1 if end >= 24 * 60 else 0),
        )
        where = f"{start_hour:02d}:{start_minute:02d}"
        assert plan.requirements, f"{where} → no meal period at all"
        primary = [r for r in plan.requirements if r.ordinal in (1, 2)]
        assert primary, f"{where} → only add-on periods {plan.requirements}"
        if len(primary) == 2:
            # Both only ever apply together to an early start that reaches the
            # noon day period; every other start time gets exactly one.
            assert start_hour < 6, f"{where} → unexpected stacking {primary}"
        keys = [(r.kind, r.ordinal) for r in plan.requirements]
        assert len(keys) == len(set(keys)), f"{where} → {keys}"


def test_the_walked_shifts_are_actually_eight_hours_long():
    """Guard on the walk above: an off-by-one in `end_day` silently turns the
    afternoon half of the clock into 32-hour shifts, which tests nothing."""
    for minutes in range(0, 24 * 60, 30):
        start_hour, start_minute = divmod(minutes, 60)
        end = minutes + 8 * 60
        start = datetime(2026, 9, 14, start_hour, start_minute, tzinfo=dt_timezone.utc)
        finish = datetime(
            2026, 9, 14 + (1 if end >= 24 * 60 else 0),
            (end // 60) % 24, end % 60, tzinfo=dt_timezone.utc,
        )
        assert finish - start == timedelta(hours=8), f"{start} → {finish}"


# ── (2) and (4) stack for a shift that satisfies both ─────────────────────

def test_an_early_shift_through_midday_is_owed_both_primary_meals():
    """05:00 starts "between one o'clock in the afternoon and six o'clock in
    the morning" (§ 162(4)) AND extends over the noon day period (§ 162(2)).
    Keying the two rules off start time alone dropped the noonday meal here."""
    plan = _plan(_ny_rules().rules, 5, 0, 20, 0)

    by_ordinal = {r.ordinal: r for r in plan.requirements}
    assert sorted(by_ordinal) == [1, 2, 3]
    assert by_ordinal[1].duration_minutes == 30 and "162(2)" in by_ordinal[1].citation
    assert by_ordinal[2].duration_minutes == 45 and "162(4)" in by_ordinal[2].citation
    assert by_ordinal[3].duration_minutes == 20 and "162(3)" in by_ordinal[3].citation
    assert minimum_meal_break_minutes(plan) == 95


def test_a_pre_six_shift_that_never_reaches_eleven_gets_only_the_midway_meal():
    # 02:00–10:00 is clear of the noon day period, so § 162(2) does not attach.
    assert [r.ordinal for r in _plan(_ny_rules().rules, 2, 0, 10, 0).requirements] == [2]


def test_the_factory_early_shift_stacks_at_factory_durations():
    plan = _plan(_ny_rules(naics="311811").rules, 5, 0, 20, 0)
    assert [r.duration_minutes for r in sorted(plan.requirements, key=lambda r: r.ordinal)] == [60, 60, 20]
