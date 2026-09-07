"""Pure break-staggering tests; no database or network is required."""

from datetime import datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from app.matcha.services.scheduling.schedule_breaks import BreakPlan, BreakRequirement
from app.matcha.services.scheduling.schedule_break_stagger import (
    FloorWindow,
    LockedBreak,
    StaggerAssignment,
    prune_planned_breaks,
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


def test_spare_headcount_is_a_ceiling_not_a_target():
    """The budget allows two concurrent breaks; the window can hold four serial
    ones, so nobody is doubled up."""
    plan = _run(_crew(4), required_staff=2)

    assert plan.max_concurrent_breaks == 2
    assert len(_intervals(plan)) == 4
    assert _overlaps(_intervals(plan)) == 1
    assert plan.advisories == ()


def test_spare_headcount_is_spent_only_when_the_window_is_too_tight():
    """Four 30-minute meals inside 12:00–13:00: two fit serially, the other two
    must share — and the budget of two lets them, instead of `insufficient_coverage`."""
    crowded = lambda: _requirement(  # noqa: E731 - table-style fixture
        earliest_local=_local(12), recommended_local=_local(12), deadline_local=_local(13),
    )
    plan = _run(_crew(4, crowded), required_staff=2)

    assert [result.status for result in plan.results] == ["suggested"] * 4
    assert sorted(_intervals(plan)) == [
        (_local(12), _local(12, 30)), (_local(12), _local(12, 30)),
        (_local(12, 30), _local(13)), (_local(12, 30), _local(13)),
    ]
    assert _overlaps(_intervals(plan)) == 2


def test_a_shared_allowed_time_beats_a_clear_discouraged_one():
    """Stagger-first never reaches below the policy floor while an allowed time
    can still be shared: a doubled-up break after two hours of work beats a
    lone one after thirty minutes.

    Budget 2, window 08:30–09:00 above the floor on a 06:30 shift (deadline
    09:30): the first break takes 08:30 clear; the second could be clear at
    07:00 but shares 08:30 instead.
    """
    tight = lambda: _ca_meal(deadline_local=_local(9, 30))  # noqa: E731
    plan = _opener(tight, required_staff=0, crew=2)

    assert sorted(result.suggested_start for result in plan.results) == [
        _local(8, 30), _local(9),
    ]
    plan = _opener(tight, required_staff=0, crew=3)
    assert sorted(result.suggested_start for result in plan.results) == [
        _local(8, 30), _local(8, 30), _local(9),
    ]


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
    # The shift window is the envelope, but its first two hours are not
    # offered: a statute-silent rule set still gets the placement floor.
    assert _local(11) == result.suggested_start
    assert result.suggested_end <= _local(17)
    assert result.suggested_end - result.suggested_start == timedelta(minutes=30)


def test_suggestion_prefers_the_recommended_time():
    plan = _run(_crew(1), required_staff=1)

    assert plan.results[0].suggested_start == _local(12)


# ── placement floor: a suggestion is never the shift's own start ──────────────
#
# The California legacy rule set carries a deadline and nothing else, which is
# how a 06:30-14:30 shift came to be told to take its meal break at 06:30.


def _opener(*requirements, required_staff=1, crew=1, locked=()):
    """A 06:30-14:30 shift; each assignee owes the given requirement(s)."""
    factories = requirements or (lambda: _ca_meal(),)
    return stagger_shift_breaks(
        shift_start_local=_local(6, 30),
        shift_end_local=_local(14, 30),
        required_staff=required_staff,
        assignments=[
            StaggerAssignment(
                employee_id=_employee(index),
                plan=_plan(*(factory() for factory in factories)),
            )
            for index in range(1, crew + 1)
        ],
        locked=locked,
    )


def _ca_meal(**overrides):
    """What `_legacy_rules` produces for California: deadline only."""
    values = {
        "earliest_local": None,
        "recommended_local": None,
        "deadline_local": _local(11, 30),  # § 512: before the end of the 5th hour
    }
    values.update(overrides)
    return _requirement(**values)


def test_early_shift_regression_never_suggests_the_shift_start():
    plan = _opener()

    result = plan.results[0]
    assert result.status == "suggested"
    assert result.suggested_start == _local(8, 30)
    assert result.suggested_start != _local(6, 30)


def test_two_openers_are_staggered_even_when_the_floor_allows_both_at_once():
    """The send-back: two 06:30–14:30 openers both told 08:30 because a third
    person clocks in then.  Inside the budget and still the wrong answer —
    breaks stagger whenever the legal window has room."""
    plan = _opener(required_staff=0, crew=2)

    assert plan.max_concurrent_breaks == 2
    assert sorted(result.suggested_start for result in plan.results) == [
        _local(8, 30), _local(9),
    ]


def test_the_whole_crew_stays_above_the_placement_floor():
    """Serialized off the floor (budget 1), not spread back over the opening."""
    plan = _opener(required_staff=3, crew=3)

    starts = sorted(result.suggested_start for result in plan.results)
    assert starts == [_local(8, 30), _local(9), _local(9, 30)]
    assert all(start >= _local(8, 30) for start in starts)


def test_a_too_early_recommendation_is_pulled_up_to_the_floor():
    plan = _opener(lambda: _ca_meal(recommended_local=_local(6, 30)))

    assert plan.results[0].suggested_start == _local(8, 30)


def test_statutory_earliest_wins_over_the_placement_floor():
    """OR's >7h tier opens at the 3rd hour — later than the policy floor."""
    plan = _opener(lambda: _ca_meal(earliest_local=_local(9, 30)))

    assert plan.results[0].suggested_start == _local(9, 30)


def test_a_statutory_earliest_below_the_floor_is_not_raised_to_it():
    """WA opens at the 2nd hour; the floor never overrides a real statute."""
    plan = _opener(lambda: _ca_meal(earliest_local=_local(8)))

    assert plan.results[0].suggested_start == _local(8)


def test_a_zero_offset_statute_still_avoids_the_shift_start():
    plan = _opener(lambda: _ca_meal(earliest_local=_local(6, 30)))

    assert plan.results[0].suggested_start == _local(6, 35)


def test_the_placement_floor_yields_to_the_legal_deadline():
    """A short shift keeps its legal window: policy never invents a conflict."""
    plan = stagger_shift_breaks(
        shift_start_local=_local(6, 30),
        shift_end_local=_local(12),
        required_staff=1,
        assignments=[StaggerAssignment(
            employee_id=_employee(1),
            plan=_plan(_ca_meal(deadline_local=_local(8))),
        )],
    )

    result = plan.results[0]
    assert result.status == "suggested"
    assert result.suggested_start == _local(6, 35)
    assert result.suggested_end <= _local(8)


def test_the_floor_yields_to_coverage_before_it_costs_a_suggestion():
    """Policy is a preference: a crew too big for it spills into lawful time.

    Breaks serialize when a shift carries no spare headcount, so the floor
    window (08:30-11:00 here) holds exactly six 30-minute breaks. Treating the
    floor as a bound would report `insufficient_coverage` for the rest — a
    strictly worse answer than the lawful early time they had before the floor
    existed.
    """
    plan = _opener(required_staff=9, crew=9)

    assert [result.status for result in plan.results] == ["suggested"] * 9
    starts = sorted(result.suggested_start for result in plan.results)
    # Six above the floor, and the overflow walks backwards from it — closest
    # to the floor first, never past the shift's own start.
    assert starts == [
        _local(7), _local(7, 30), _local(8), _local(8, 30), _local(9),
        _local(9, 30), _local(10), _local(10, 30), _local(11),
    ]


def test_the_crew_that_fits_the_floor_still_gets_it_whole():
    plan = _opener(required_staff=6, crew=6)

    assert all(result.suggested_start >= _local(8, 30) for result in plan.results)


def test_a_saved_time_below_the_floor_is_still_honored():
    """The floor is placement policy; a reviewed time is the manager's call."""
    saved = LockedBreak(
        employee_id=_employee(1), kind="meal", ordinal=1,
        start=_local(7), duration_minutes=30,
    )
    plan = _opener(crew=1, locked=[saved])

    result = plan.results[0]
    assert result.status == "saved"
    assert result.suggested_start == _local(7)


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


# ── the review findings, each pinned by the case that reproduced it ───────────


def test_one_employee_is_never_sent_on_two_breaks_at_once():
    """A concurrency budget is not a per-person constraint.

    3 assignees on a required_staff=1 shift buys max_concurrent=2, which used
    to let employee 1's meal and rest both land at 12:00 — one person, two
    places.
    """
    crew = [
        StaggerAssignment(
            employee_id=_employee(1),
            plan=_plan(
                _requirement(kind="meal", ordinal=1, duration_minutes=30),
                _requirement(kind="rest", ordinal=1, duration_minutes=10),
            ),
        ),
        StaggerAssignment(employee_id=_employee(2), plan=_plan()),
        StaggerAssignment(employee_id=_employee(3), plan=_plan()),
    ]
    plan = _run(crew, required_staff=1)

    assert plan.max_concurrent_breaks == 2
    own = [
        (result.suggested_start, result.suggested_end)
        for result in plan.results
        if result.employee_id == _employee(1) and result.suggested_start
    ]
    assert len(own) == 2
    (first_start, first_end), (second_start, second_end) = sorted(own)
    assert first_end <= second_start, "one body cannot take two breaks at once"


def test_a_window_too_short_for_the_break_is_not_a_confident_suggestion():
    """13:50-14:00 cannot hold 30 minutes; anchoring at 13:50 overruns 14:00."""
    tight = _requirement(
        earliest_local=_local(13, 50),
        recommended_local=_local(13, 50),
        deadline_local=_local(14),
    )
    plan = stagger_shift_breaks(
        shift_start_local=_local(9),
        shift_end_local=_local(17),
        required_staff=1,
        assignments=[StaggerAssignment(employee_id=_employee(1), plan=_plan(tight))],
    )

    result = plan.results[0]
    assert result.status == "deadline_conflict"
    assert result.suggested_end == _local(14, 20)
    assert result.reason and "past it" in result.reason
    assert [advisory["code"] for advisory in plan.advisories] == ["coverage_shortfall", "deadline_conflict"]


def test_an_off_grid_window_boundary_is_still_tried():
    """Two 6-minute breaks in a 12:00-12:12 window both fit, back to back.

    The candidate walk only lands on the 5-minute grid, so 12:06 — the one
    start that works for the second break — was never evaluated and the break
    was reported unschedulable with a reason blaming other breaks.
    """
    def _six():
        return _requirement(
            duration_minutes=6,
            earliest_local=_local(12),
            recommended_local=_local(12),
            deadline_local=_local(12, 12),
        )

    plan = _run(_crew(2, _six), required_staff=2)

    assert [result.status for result in plan.results] == ["suggested"] * 2
    starts = sorted(result.suggested_start for result in plan.results)
    assert starts == [_local(12), _local(12, 6)]


def test_a_saved_time_is_kept_and_placed_around():
    saved = LockedBreak(
        employee_id=_employee(1), kind="meal", ordinal=1,
        start=_local(13), duration_minutes=30,
    )
    plan = stagger_shift_breaks(
        shift_start_local=_local(9),
        shift_end_local=_local(17),
        required_staff=2,
        assignments=_crew(2),
        locked=[saved],
    )

    by_employee = {result.employee_id: result for result in plan.results}
    assert by_employee[_employee(1)].status == "saved"
    assert by_employee[_employee(1)].suggested_start == _local(13)
    other = by_employee[_employee(2)]
    assert other.status == "suggested"
    assert not (other.suggested_start < _local(13, 30) and _local(13) < other.suggested_end)


def test_another_shift_break_occupies_the_same_floor_without_becoming_saved():
    """Daily orchestration can reserve a peer shift's break transparently."""
    peer = LockedBreak(
        employee_id=_employee(9), kind="meal", ordinal=1,
        start=_local(12), duration_minutes=30,
    )

    plan = stagger_shift_breaks(
        shift_start_local=_local(9),
        shift_end_local=_local(17),
        required_staff=1,
        assignments=_crew(1),
        occupied=[peer],
    )

    result = plan.results[0]
    assert result.status == "suggested"
    assert result.suggested_start == _local(12, 30)


# ── the ceiling and the occupancy describe the same floor ────────────────────


def _floor(start, end, assigned, required):
    return FloorWindow(start=start, end=end, assigned=assigned, required=required)


def _peer_break(index, hour, minute=0, duration=30):
    return LockedBreak(
        employee_id=_employee(index), kind="meal", ordinal=1,
        start=_local(hour, minute), duration_minutes=duration,
    )


def _crowded():
    return _requirement(
        earliest_local=_local(12), recommended_local=_local(12),
        deadline_local=_local(13),
    )


def _shared_floor(*, floor):
    """Two assignees needing a 12:00-13:00 meal, two peers already in it."""
    return stagger_shift_breaks(
        shift_start_local=_local(9),
        shift_end_local=_local(17),
        required_staff=2,
        assignments=_crew(2, _crowded),
        occupied=[_peer_break(8, 12), _peer_break(9, 12, 30)],
        floor=floor,
    )


def test_the_ceiling_is_read_from_the_floor_not_from_the_opened_row():
    """A row-sized budget against a floor-sized occupancy blocks everything.

    This row has no spare headcount of its own (2 assigned, 2 required), but
    the floor it stands on carries six spare bodies. Both of its breaks fit
    beside the peers already off the floor; refusing them would report
    `insufficient_coverage` for a floor with six people to spare.
    """
    plan = _shared_floor(floor=[_floor(_local(9), _local(17), 2, 2), _floor(_local(9), _local(17), 6, 0)])

    assert [result.status for result in plan.results] == ["suggested"] * 2
    assert sorted(_intervals(plan)) == [
        (_local(12), _local(12, 30)), (_local(12, 30), _local(13)),
    ]
    assert plan.max_concurrent_breaks == 6
    assert plan.advisories == ()


def test_a_floor_with_nothing_to_spare_still_serializes():
    """The same rows on a floor that is fully committed: the peers hold both
    slots, so neither break fits and the shortfall is reported."""
    plan = _shared_floor(floor=[_floor(_local(9), _local(17), 2, 2)])

    assert [result.status for result in plan.results] == ["insufficient_coverage"] * 2
    assert plan.max_concurrent_breaks == 1
    assert {advisory["code"] for advisory in plan.advisories} == {
        "coverage_shortfall", "insufficient_coverage",
    }


def test_the_ceiling_follows_the_floor_through_the_shift():
    """Capacity is read at each instant, not once for the shift.

    A 06:30 opener stands alone until the 08:30 crew arrives. The reported
    ceiling is the tightest moment (1, before they clock in), and placement
    still uses the wider ceiling that exists from 08:30 on: the opener's break
    may sit beside a peer's once there are bodies to spare.
    """
    plan = stagger_shift_breaks(
        shift_start_local=_local(6, 30),
        shift_end_local=_local(14, 30),
        required_staff=1,
        assignments=[StaggerAssignment(
            employee_id=_employee(1),
            plan=_plan(_ca_meal(
                earliest_local=_local(8, 30), recommended_local=_local(8, 30),
                deadline_local=_local(9),
            )),
        )],
        occupied=[_peer_break(9, 8, 30)],
        floor=[
            _floor(_local(6, 30), _local(14, 30), 1, 1),
            _floor(_local(8, 30), _local(16, 30), 3, 0),
        ],
    )

    assert plan.max_concurrent_breaks == 1, "tightest instant is the lone opener"
    result = plan.results[0]
    assert result.status == "suggested"
    assert result.suggested_start == _local(8, 30), "shares once the floor can afford it"


def test_a_discouraged_time_never_reaches_the_shift_start():
    """Spilling below the policy floor stops one step short of the opening.

    A crew of 10 on a CA opener fills 08:30-11:00 and then walks backwards
    through the discouraged times. The tenth used to land on 06:30-07:00 — the
    only clear half hour left — and 06:30 is the shift's own start, the exact
    suggestion the placement floor exists to prevent. It is now reported
    honestly instead: no lawful time is left that anybody could take.
    """
    plan = _opener(required_staff=10, crew=10)

    starts = [result.suggested_start for result in plan.results if result.suggested_start]
    assert _local(6, 30) not in starts
    assert min(starts) == _local(7)
    statuses = [result.status for result in plan.results]
    assert statuses.count("suggested") == 9
    assert statuses.count("insufficient_coverage") == 1


# ── prune_planned_breaks ──────────────────────────────────────────────────────


def _saved(hour=12, minute=0, kind="meal", ordinal=1, duration=30):
    return {
        "kind": kind, "ordinal": ordinal,
        "start_local": _local(hour, minute).isoformat(),
        "duration_minutes": duration, "source": "manager",
    }


def _prune(planned, requirements, *, start_hour=9, end_hour=17):
    return prune_planned_breaks(
        planned,
        requirements=requirements,
        shift_start_local=_local(start_hour),
        shift_end_local=_local(end_hour),
    )


def test_prune_keeps_a_still_valid_saved_time():
    assert _prune([_saved()], [_requirement()]) == [_saved()]


def test_prune_drops_a_time_the_retimed_shift_no_longer_contains():
    # 09:00-17:00 becomes 18:00-02:00; a saved noon break is now wrong, not stale.
    assert _prune([_saved()], [_requirement()], start_hour=18, end_hour=23) == []


def test_prune_drops_a_time_whose_requirement_was_waived():
    assert _prune([_saved()], [_requirement(waived=True)]) == []


def test_prune_drops_a_time_running_past_the_end_of_the_shift():
    assert _prune([_saved(hour=16, minute=45)], [_requirement()]) == []


def test_prune_tolerates_malformed_rows():
    assert _prune(["nonsense", {}, _saved()], [_requirement()]) == [_saved()]
