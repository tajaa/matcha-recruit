"""Pure break-staggering tests; no database or network is required."""

from datetime import datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from app.matcha.services.scheduling.schedule_breaks import BreakPlan, BreakRequirement
from app.matcha.services.scheduling.schedule_break_stagger import (
    StaggerAssignment,
    stagger_payload,
    stagger_shift_breaks,
)


LA = ZoneInfo("America/Los_Angeles")
RULE_SET = UUID("00000000-0000-0000-0000-0000000000ff")


def _employee(index: int) -> UUID:
    return UUID(f"00000000-0000-0000-0000-0000000000{index:02d}")


def _local(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 8, 21, hour, minute, tzinfo=LA)


def _requirement(**overrides) -> BreakRequirement:
    values = {
        "kind": "meal",
        "ordinal": 1,
        "duration_minutes": 30,
        "paid": False,
        "earliest_local": _local(11),
        "recommended_local": _local(12),
        "deadline_local": _local(14),
        "waived": False,
        "waiver_attestation_id": None,
        "citation": "Cal. Lab. Code § 512",
        "rule_set_id": RULE_SET,
    }
    values.update(overrides)
    return BreakRequirement(**values)


def _plan(*requirements, status="complete", advisories=()) -> BreakPlan:
    return BreakPlan(
        status=status,
        requirements=tuple(requirements),
        advisories=tuple(advisories),
        rule_set_ids=(RULE_SET,),
        rule_set_hash="hash",
    )


def _crew(count: int, *requirement_factories) -> list[StaggerAssignment]:
    factories = requirement_factories or (lambda: _requirement(),)
    return [
        StaggerAssignment(
            employee_id=_employee(index),
            plan=_plan(*(factory() for factory in factories)),
        )
        for index in range(1, count + 1)
    ]


def _run(assignments, *, required_staff, start_hour=9, end_hour=17):
    return stagger_shift_breaks(
        shift_start_local=_local(start_hour),
        shift_end_local=_local(end_hour),
        required_staff=required_staff,
        assignments=assignments,
    )


def _intervals(plan):
    return [
        (result.suggested_start, result.suggested_end)
        for result in plan.results
        if result.status == "suggested"
    ]


def _overlaps(intervals) -> int:
    """Peak concurrency across the placed intervals."""
    peak = 0
    for start, _ in intervals:
        concurrent = sum(1 for other_start, other_end in intervals if other_start <= start < other_end)
        peak = max(peak, concurrent)
    return peak


def test_no_spare_headcount_still_suggests_serial_breaks():
    # required_staff == assigned is the normal shape: assignment writes 409 on
    # shift_full, so a spare-headcount model would never suggest anything.
    plan = _run(_crew(4), required_staff=4)

    assert plan.max_concurrent_breaks == 1
    assert [result.status for result in plan.results] == ["suggested"] * 4
    assert _overlaps(_intervals(plan)) == 1


def test_no_spare_headcount_reports_the_coverage_shortfall():
    plan = _run(_crew(3), required_staff=3)

    codes = [advisory["code"] for advisory in plan.advisories]
    assert codes == ["coverage_shortfall"]
    assert plan.advisories[0]["severity"] == "advisory"
    assert "3" in plan.advisories[0]["message"]


def test_shortfall_is_not_reported_when_nothing_needs_a_break():
    waived = [
        StaggerAssignment(
            employee_id=_employee(index),
            plan=_plan(_requirement(waived=True, waiver_attestation_id=RULE_SET)),
        )
        for index in range(1, 4)
    ]
    plan = _run(waived, required_staff=3)

    assert plan.results == ()
    assert plan.advisories == ()


def test_spare_headcount_allows_concurrent_breaks():
    plan = _run(_crew(4), required_staff=2)

    assert plan.max_concurrent_breaks == 2
    assert len(_intervals(plan)) == 4
    assert _overlaps(_intervals(plan)) == 2
    assert plan.advisories == ()


def test_waived_requirement_takes_no_slot():
    crew = _crew(2)
    crew.append(StaggerAssignment(
        employee_id=_employee(9),
        plan=_plan(_requirement(waived=True, waiver_attestation_id=RULE_SET)),
    ))
    plan = _run(crew, required_staff=3)

    assert {result.employee_id for result in plan.results} == {_employee(1), _employee(2)}


def test_unmapped_plan_is_unresolved_not_a_guess():
    crew = [StaggerAssignment(
        employee_id=_employee(1),
        plan=_plan(_requirement(), status="unmapped"),
    )]
    plan = _run(crew, required_staff=1)

    assert [result.status for result in plan.results] == ["unresolved"]
    assert plan.results[0].suggested_start is None
    assert plan.results[0].suggested_end is None
    assert "verify manually" in plan.results[0].reason


def test_error_plan_is_unresolved_not_a_guess():
    crew = [StaggerAssignment(
        employee_id=_employee(1),
        plan=_plan(_requirement(), status="error"),
    )]
    plan = _run(crew, required_staff=1)

    assert [result.status for result in plan.results] == ["unresolved"]
    assert plan.results[0].suggested_start is None
    assert "could not be fully evaluated" in plan.results[0].reason


def test_meal_and_rest_share_one_coverage_pool():
    # A rest break takes the same body off the floor a meal break does.
    crew = [
        StaggerAssignment(
            employee_id=_employee(index),
            plan=_plan(
                _requirement(),
                _requirement(
                    kind="rest", ordinal=1, duration_minutes=10, paid=True,
                    earliest_local=_local(11), recommended_local=_local(12),
                    deadline_local=_local(14),
                ),
            ),
        )
        for index in range(1, 3)
    ]
    plan = _run(crew, required_staff=2)

    assert len(_intervals(plan)) == 4
    assert _overlaps(_intervals(plan)) == 1


def test_overcrowded_window_reports_insufficient_coverage_and_keeps_the_row():
    # Six 30-minute meals that must all land inside a 60-minute window, one at
    # a time: four cannot fit and must be surfaced, not dropped.
    crowded = lambda: _requirement(  # noqa: E731 - table-style fixture
        earliest_local=_local(12), recommended_local=_local(12), deadline_local=_local(13),
    )
    crew = [
        StaggerAssignment(employee_id=_employee(index), plan=_plan(crowded()))
        for index in range(1, 7)
    ]
    plan = _run(crew, required_staff=6)

    statuses = [result.status for result in plan.results]
    assert len(plan.results) == 6
    assert statuses.count("suggested") == 2
    assert statuses.count("insufficient_coverage") == 4
    blocked = next(result for result in plan.results if result.status == "insufficient_coverage")
    assert blocked.reason and "legal window" in blocked.reason
    assert "insufficient_coverage" in {advisory["code"] for advisory in plan.advisories}


def test_missing_offsets_fall_back_to_the_shift_window():
    crew = [StaggerAssignment(
        employee_id=_employee(1),
        plan=_plan(_requirement(
            earliest_local=None, recommended_local=None, deadline_local=None,
        )),
    )]
    plan = _run(crew, required_staff=1, start_hour=9, end_hour=17)

    result = plan.results[0]
    assert result.status == "suggested"
    assert _local(9) <= result.suggested_start
    assert result.suggested_end <= _local(17)
    assert result.suggested_end - result.suggested_start == timedelta(minutes=30)


def test_suggestion_prefers_the_recommended_time():
    plan = _run(_crew(1), required_staff=1)

    assert plan.results[0].suggested_start == _local(12)


def test_placement_is_deterministic():
    first = _run(_crew(5), required_staff=5)
    second = _run(_crew(5), required_staff=5)

    assert first == second


def test_placement_is_independent_of_assignment_order():
    crew = _crew(4)
    forward = _run(crew, required_staff=4)
    backward = _run(list(reversed(crew)), required_staff=4)

    assert forward == backward


def test_payload_serializes_times_and_advisories():
    payload = stagger_payload(_run(_crew(2), required_staff=2))

    assert payload["schema_version"] == 1
    assert payload["max_concurrent_breaks"] == 1
    assert len(payload["results"]) == 2
    first = payload["results"][0]
    assert first["status"] == "suggested"
    assert first["suggested_start"].startswith("2026-08-21T")
    assert first["duration_minutes"] == 30
    assert payload["advisories"][0]["code"] == "coverage_shortfall"
