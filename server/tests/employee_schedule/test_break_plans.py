"""Pure break-plan tests; no database or network is required."""

from datetime import date, datetime, time, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.matcha.services.scheduling.schedule_breaks import (
    BreakRule,
    MealWaiverAttestation,
    evaluate_break_plan,
    guidance_payload,
    minimum_meal_break_minutes,
    reinterpret_schedule_wall_time,
    render_break_plan,
)

LA = ZoneInfo("America/Los_Angeles")
NY = ZoneInfo("America/New_York")


def _rule(**overrides):
    values = {
        "rule_set_id": uuid4(),
        "kind": "meal",
        "ordinal": 1,
        "trigger_after_minutes": 300,
        "duration_minutes": 30,
        "paid": False,
        "deadline_offset_minutes": 300,
        "citation": "Test citation",
    }
    values.update(overrides)
    return BreakRule(**values)


def _window(start_hour=9, end_hour=17):
    return (
        datetime(2026, 8, 21, start_hour, tzinfo=timezone.utc),
        datetime(2026, 8, 21, end_hour, tzinfo=timezone.utc),
    )


def _ny_rules():
    """Executable representation of the card's NY Labor Law § 162 cases.

    These are fixture data, not a production-law seed: the normal import and
    admin-review workflow must approve authoritative rows before runtime use.
    """
    common = {
        "rule_set_id": uuid4(),
        "kind": "meal",
        "trigger_after_minutes": 360,
        "paid": False,
        "citation": "N.Y. Lab. Law § 162",
        "effective_from": date(2026, 1, 1),
        "authority_url": "https://www.nysenate.gov/legislation/laws/LAB/162",
        "source_type": "manual",
    }
    return [
        BreakRule(
            **common, ordinal=1, duration_minutes=30,
            shift_spans_window_start=time(11), shift_spans_window_end=time(14),
            window_start=time(11), window_end=time(14),
        ),
        BreakRule(
            **common, ordinal=2, duration_minutes=45,
            shift_start_window_from=time(13), shift_start_window_before=time(6),
            recommend_midpoint=True,
        ),
        BreakRule(
            **common, ordinal=3, duration_minutes=20,
            shift_starts_before=time(11), shift_ends_after=time(19),
            window_start=time(17), window_end=time(19),
        ),
    ]


def _ny_window(start_hour, end_hour):
    return (
        datetime(2026, 9, 1, start_hour, tzinfo=timezone.utc),
        datetime(2026, 9, 1, end_hour, tzinfo=timezone.utc),
    )


def test_ny_noon_shift_gets_thirty_minutes_inside_noon_window():
    starts_at, ends_at = _ny_window(8, 15)
    plan = evaluate_break_plan(
        starts_at=starts_at, ends_at=ends_at, timezone=NY, rules=_ny_rules(),
    )
    assert [(r.duration_minutes, r.earliest_local.hour, r.deadline_local.hour)
            for r in plan.requirements] == [(30, 11, 14)]


def test_ny_afternoon_shift_gets_midpoint_forty_five_minute_meal():
    starts_at, ends_at = _ny_window(14, 22)
    plan = evaluate_break_plan(
        starts_at=starts_at, ends_at=ends_at, timezone=NY, rules=_ny_rules(),
    )
    assert len(plan.requirements) == 1
    requirement = plan.requirements[0]
    assert requirement.duration_minutes == 45
    assert (requirement.recommended_local.hour, requirement.recommended_local.minute) == (17, 37)


def test_ny_long_day_gets_noon_and_additional_evening_meals():
    starts_at, ends_at = _ny_window(8, 20)
    plan = evaluate_break_plan(
        starts_at=starts_at, ends_at=ends_at, timezone=NY, rules=_ny_rules(),
    )
    assert [(r.duration_minutes, r.earliest_local.hour, r.deadline_local.hour)
            for r in plan.requirements] == [(30, 11, 14), (20, 17, 19)]


def test_ny_clock_conditions_do_not_affect_a_short_or_unmatched_shift():
    starts_at, ends_at = _ny_window(9, 15)
    plan = evaluate_break_plan(
        starts_at=starts_at, ends_at=ends_at, timezone=NY, rules=_ny_rules(),
    )
    assert plan.requirements == ()


def test_midnight_crossing_clock_window_keeps_deadline_after_earliest():
    starts_at, ends_at = _ny_window(12, 20)
    plan = evaluate_break_plan(
        starts_at=starts_at,
        ends_at=ends_at,
        timezone=NY,
        rules=[_rule(
            trigger_after_minutes=360,
            window_start=time(22),
            window_end=time(2),
            deadline_offset_minutes=None,
        )],
    )

    requirement = plan.requirements[0]
    assert requirement.earliest_local == datetime(
        2026, 9, 1, 22, tzinfo=NY,
    )
    assert requirement.deadline_local == datetime(
        2026, 9, 2, 2, tzinfo=NY,
    )


def test_midnight_crossing_window_uses_the_occurrence_overlapping_a_late_shift():
    plan = evaluate_break_plan(
        starts_at=datetime(2026, 9, 1, 23, tzinfo=timezone.utc),
        ends_at=datetime(2026, 9, 2, 6, tzinfo=timezone.utc),
        timezone=NY,
        rules=[_rule(
            trigger_after_minutes=360,
            window_start=time(22),
            window_end=time(2),
            deadline_offset_minutes=None,
        )],
    )

    requirement = plan.requirements[0]
    assert requirement.earliest_local == datetime(2026, 9, 1, 22, tzinfo=NY)
    assert requirement.deadline_local == datetime(2026, 9, 2, 2, tzinfo=NY)


def test_midnight_crossing_window_uses_prior_day_for_an_early_shift():
    plan = evaluate_break_plan(
        starts_at=datetime(2026, 9, 1, 0, tzinfo=timezone.utc),
        ends_at=datetime(2026, 9, 1, 8, tzinfo=timezone.utc),
        timezone=NY,
        rules=[_rule(
            trigger_after_minutes=360,
            window_start=time(22),
            window_end=time(2),
            deadline_offset_minutes=None,
        )],
    )

    requirement = plan.requirements[0]
    assert requirement.earliest_local == datetime(2026, 8, 31, 22, tzinfo=NY)
    assert requirement.deadline_local == datetime(2026, 9, 1, 2, tzinfo=NY)


def test_overnight_shift_satisfies_absolute_end_after_threshold():
    starts_at = datetime(2026, 9, 1, 8, tzinfo=timezone.utc)
    ends_at = datetime(2026, 9, 2, 1, tzinfo=timezone.utc)
    plan = evaluate_break_plan(
        starts_at=starts_at,
        ends_at=ends_at,
        timezone=NY,
        rules=_ny_rules(),
    )

    assert [(item.ordinal, item.duration_minutes) for item in plan.requirements] == [
        (1, 30), (3, 20),
    ]


def test_overnight_shift_can_span_a_next_day_clock_window():
    plan = evaluate_break_plan(
        starts_at=datetime(2026, 9, 1, 23, tzinfo=timezone.utc),
        ends_at=datetime(2026, 9, 2, 15, tzinfo=timezone.utc),
        timezone=NY,
        rules=[_rule(
            trigger_after_minutes=360,
            shift_spans_window_start=time(11),
            shift_spans_window_end=time(14),
        )],
    )

    assert len(plan.requirements) == 1


def test_employer_size_scopes_rules_and_missing_context_fails_visible():
    starts_at, ends_at = _window()
    rule = _rule(minimum_employees=50)
    small = evaluate_break_plan(
        starts_at=starts_at, ends_at=ends_at, timezone=LA, rules=[rule],
        employer_employee_count=49,
    )
    covered = evaluate_break_plan(
        starts_at=starts_at, ends_at=ends_at, timezone=LA, rules=[rule],
        employer_employee_count=50,
    )
    unknown = evaluate_break_plan(
        starts_at=starts_at, ends_at=ends_at, timezone=LA, rules=[rule],
    )
    assert small.requirements == ()
    assert len(covered.requirements) == 1
    assert unknown.status == "error"
    assert unknown.advisories[0]["code"] == "employer_context_unverified"
    assert small.rule_set_hash != covered.rule_set_hash


def test_reinterpret_preserves_schedule_wall_clock_fields():
    value = datetime(2026, 8, 21, 9, 0, tzinfo=timezone.utc)
    local = reinterpret_schedule_wall_time(value, LA)
    assert local.hour == 9
    assert local.minute == 0
    assert local.tzinfo == LA


def test_nine_to_five_shift_renders_meal_by_two_pm():
    starts_at, ends_at = _window()
    plan = evaluate_break_plan(
        starts_at=starts_at,
        ends_at=ends_at,
        timezone=LA,
        rules=[_rule(
            effective_from=date(2026, 1, 1),
            authority_url="https://example.gov/meal-breaks",
            source_type="manual",
        )],
    )
    assert plan.status == "complete"
    assert plan.requirements[0].deadline_local.hour == 14
    assert render_break_plan(plan) == "Mandatory 30-minute unpaid meal break by 2 PM"


def test_trigger_operator_is_explicit_at_boundary():
    starts_at, ends_at = _window(9, 14)
    strict = evaluate_break_plan(
        starts_at=starts_at,
        ends_at=ends_at,
        timezone=LA,
        rules=[_rule(trigger_operator="gt")],
    )
    inclusive = evaluate_break_plan(
        starts_at=starts_at,
        ends_at=ends_at,
        timezone=LA,
        rules=[_rule(trigger_operator="gte")],
    )
    assert strict.requirements == ()
    assert len(inclusive.requirements) == 1


def test_second_meal_and_two_rest_breaks_render_as_distinct_requirements():
    starts_at, ends_at = _window(6, 18)
    rules = [
        _rule(ordinal=1, deadline_offset_minutes=300),
        _rule(ordinal=2, trigger_after_minutes=600, deadline_offset_minutes=600),
        _rule(kind="rest", ordinal=1, trigger_after_minutes=210, duration_minutes=10,
              paid=True, deadline_offset_minutes=None, recommended_offset_minutes=240),
        _rule(kind="rest", ordinal=2, trigger_after_minutes=420, duration_minutes=10,
              paid=True, deadline_offset_minutes=None, recommended_offset_minutes=480),
    ]
    plan = evaluate_break_plan(
        starts_at=starts_at,
        ends_at=ends_at,
        timezone=LA,
        rules=rules,
    )
    rendered = render_break_plan(plan)
    assert rendered is not None
    assert "Mandatory 30-minute unpaid meal break by 11 AM" in rendered
    assert "Mandatory 30-minute unpaid meal break by 4 PM" in rendered
    assert "2 10-minute paid rest breaks" in rendered
    assert "by" not in rendered.split("2 10-minute paid rest breaks", 1)[1]


def test_permitted_waiver_marks_meal_as_waived():
    starts_at, ends_at = _window()
    waiver = MealWaiverAttestation(
        id=uuid4(),
        on_file=True,
        effective_from=date(2026, 1, 1),
        confirmed_by=uuid4(),
        confirmed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    plan = evaluate_break_plan(
        starts_at=starts_at,
        ends_at=ends_at,
        timezone=LA,
        rules=[_rule(waiver_allowed=True, waiver_max_shift_minutes=600)],
        waiver=waiver,
    )
    assert plan.requirements[0].waived is True
    assert plan.requirements[0].waiver_attestation_id == waiver.id
    assert render_break_plan(plan) == "Meal break waiver on file; no mandatory meal break applies to this shift."
    assert minimum_meal_break_minutes(plan) == 0


def test_age_scoped_rule_changes_only_the_minor_plan():
    starts_at, ends_at = _window()
    minor_rule = _rule(trigger_after_minutes=240, maximum_age=17)

    minor_plan = evaluate_break_plan(
        starts_at=starts_at, ends_at=ends_at, timezone=LA,
        rules=[minor_rule], employee_age=16,
    )
    adult_plan = evaluate_break_plan(
        starts_at=starts_at, ends_at=ends_at, timezone=LA,
        rules=[minor_rule], employee_age=18,
    )

    assert minimum_meal_break_minutes(minor_plan) == 30
    assert minimum_meal_break_minutes(adult_plan) == 0


def test_waiver_that_exceeds_rule_limit_does_not_suppress_meal():
    starts_at, ends_at = _window()
    waiver = MealWaiverAttestation(
        id=uuid4(),
        on_file=True,
        effective_from=date(2026, 1, 1),
        confirmed_by=uuid4(),
        confirmed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    plan = evaluate_break_plan(
        starts_at=starts_at,
        ends_at=ends_at,
        timezone=LA,
        rules=[_rule(waiver_allowed=True, waiver_max_shift_minutes=360)],
        waiver=waiver,
    )
    # The scheduled span is eight hours, so the six-hour waiver limit fails.
    assert plan.requirements[0].waived is False
    assert plan.advisories[0]["code"] == "meal_waiver_inapplicable"


def test_waiver_on_file_but_rule_disallows_waiver_is_visible():
    starts_at, ends_at = _window()
    waiver = MealWaiverAttestation(
        id=uuid4(),
        on_file=True,
        effective_from=date(2026, 1, 1),
        confirmed_by=uuid4(),
        confirmed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    plan = evaluate_break_plan(
        starts_at=starts_at,
        ends_at=ends_at,
        timezone=LA,
        rules=[_rule(waiver_allowed=False)],
        waiver=waiver,
    )
    assert plan.requirements[0].waived is False
    assert plan.advisories[0]["code"] == "meal_waiver_inapplicable"


def test_future_waiver_does_not_apply():
    starts_at, ends_at = _window()
    waiver = MealWaiverAttestation(
        id=uuid4(),
        on_file=True,
        effective_from=date(2026, 8, 22),
        confirmed_by=uuid4(),
        confirmed_at=datetime(2026, 8, 21, tzinfo=timezone.utc),
    )
    plan = evaluate_break_plan(
        starts_at=starts_at,
        ends_at=ends_at,
        timezone=LA,
        rules=[_rule(waiver_allowed=True)],
        waiver=waiver,
    )
    assert plan.requirements[0].waived is False


def test_empty_rules_are_unmapped_and_never_clear():
    starts_at, ends_at = _window()
    plan = evaluate_break_plan(
        starts_at=starts_at,
        ends_at=ends_at,
        timezone=LA,
        rules=[],
    )
    assert plan.status == "unmapped"
    assert render_break_plan(plan) == "Break requirements could not be mapped for this location; verify manually."


def test_error_plan_has_explicit_manual_review_summary():
    starts_at, ends_at = _window()
    plan = evaluate_break_plan(
        starts_at=starts_at, ends_at=ends_at, timezone=LA, rules=[],
    )
    from dataclasses import replace
    assert render_break_plan(replace(plan, status="error")) == (
        "Break requirements could not be fully evaluated; verify manually."
    )


def test_guidance_payload_is_json_safe_and_versioned():
    starts_at, ends_at = _window()
    plan = evaluate_break_plan(
        starts_at=starts_at,
        ends_at=ends_at,
        timezone=LA,
        rules=[_rule(
            effective_from=date(2026, 1, 1),
            authority_url="https://example.gov/meal-breaks",
            source_type="manual",
        )],
    )
    payload = guidance_payload(
        plan,
        timezone="America/Los_Angeles",
        evaluated_at=datetime(2026, 8, 21, 12, tzinfo=timezone.utc),
    )
    assert payload["schema_version"] == 2
    assert payload["summary"] == "Mandatory 30-minute unpaid meal break by 2 PM"
    assert payload["requirements"][0]["rule_set_id"] == str(plan.rule_set_ids[0])
    assert payload["requirements"][0]["effective_from"] == "2026-01-01"
    assert payload["requirements"][0]["authority_url"] == "https://example.gov/meal-breaks"
    assert payload["requirements"][0]["source_type"] == "manual"
    assert payload["context"] == {"employer_employee_count": None}
