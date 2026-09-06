"""Pure tests for the week coverage evaluator.

No database, no fakes: the whole point of `schedule_coverage` is that a
manager-facing claim about whether a week is covered can be checked by reading
shift windows against the store's own hours.
"""

import json
from datetime import date, timedelta

import pytest

from app.matcha.services.scheduling.schedule_coverage import (
    GAP_KINDS, evaluate_week_coverage, sunday_weekday,
)


# 2026-08-23 is a Sunday, so `week_start + 1` is Monday = operating-hours key "1".
WEEK_START = date(2026, 8, 23)
MONDAY = WEEK_START + timedelta(days=1)
TUESDAY = WEEK_START + timedelta(days=2)
HOURS = {"1": {"open": "08:00", "close": "17:00"}}
LEADER_JOB = "3f6b1c22-2000-4000-8000-0000000000aa"
SECOND_LEADER_JOB = "3f6b1c22-2000-4000-8000-0000000000bb"


def _shift(day, start, end, *, staffed=1, required=1, job_id=None, key="s", end_day=None):
    """One demand row in the shape `build_plan` emits (ISO strings)."""
    return {
        "key": key,
        "starts_at": f"{day.isoformat()}T{start}:00",
        "ends_at": f"{(end_day or day).isoformat()}T{end}:00",
        "required_staff": required,
        "role": "Barista",
        "job_id": job_id,
        "fixed_employee_ids": [],
        "proposed_assignments": [
            {"employee_id": f"employee-{index}"} for index in range(staffed)
        ],
    }


def _kinds(findings):
    return [finding["kind"] for finding in findings]


def _evaluate(shifts, **overrides):
    kwargs = {
        "plan_shifts": shifts,
        "operating_hours": HOURS,
        "week_start": WEEK_START,
    }
    kwargs.update(overrides)
    return evaluate_week_coverage(**kwargs)


def test_sunday_weekday_matches_the_operating_hours_key_convention():
    assert sunday_weekday(WEEK_START) == 0
    assert sunday_weekday(MONDAY) == 1
    assert sunday_weekday(WEEK_START + timedelta(days=6)) == 6


def test_a_shift_starting_at_open_leaves_the_prep_buffer_uncovered():
    findings = _evaluate([_shift(MONDAY, "08:00", "17:00")], open_buffer_minutes=30)

    assert _kinds(findings) == ["open_buffer_uncovered"]
    assert findings[0]["window"] == {"start": "07:30", "end": "08:00"}
    assert findings[0]["minutes"] == 30
    assert findings[0]["severity"] == "gap"
    assert findings[0]["day"] == MONDAY.isoformat()


def test_a_shift_ending_at_close_leaves_the_cleanup_buffer_uncovered():
    findings = _evaluate([_shift(MONDAY, "08:00", "17:00")], close_buffer_minutes=20)

    assert _kinds(findings) == ["close_buffer_uncovered"]
    assert findings[0]["window"] == {"start": "17:00", "end": "17:20"}
    assert findings[0]["minutes"] == 20


def test_buffers_are_covered_when_someone_actually_works_them():
    assert _evaluate(
        [_shift(MONDAY, "07:30", "17:20")],
        open_buffer_minutes=30, close_buffer_minutes=20,
    ) == []


def test_a_midday_hole_is_reported_with_its_minutes():
    findings = _evaluate([
        _shift(MONDAY, "08:00", "12:00", key="morning"),
        _shift(MONDAY, "14:00", "17:00", key="afternoon"),
    ])

    assert _kinds(findings) == ["coverage_gap"]
    assert findings[0]["window"] == {"start": "12:00", "end": "14:00"}
    assert findings[0]["minutes"] == 120


def test_one_hole_spanning_the_prep_window_is_split_at_the_buffer_edge():
    """Missing the open prep is a different fix from being short during trade,
    so a single stretch of nobody-on is reported as both, not as one blur."""
    findings = _evaluate([_shift(MONDAY, "09:00", "17:00")], open_buffer_minutes=30)

    assert _kinds(findings) == ["open_buffer_uncovered", "coverage_gap"]
    assert findings[0]["window"] == {"start": "07:30", "end": "08:00"}
    assert findings[1]["window"] == {"start": "08:00", "end": "09:00"}


def test_an_unfilled_slot_does_not_count_as_coverage():
    """The whole failure this exists to catch: a shift the planner could not
    staff is still an empty floor."""
    unstaffed = _shift(MONDAY, "08:00", "17:00", staffed=0, required=2)

    assert _kinds(_evaluate([unstaffed])) == ["coverage_gap"]
    # ...but readiness judges the PATTERN, where nobody is assigned yet.
    assert _evaluate([unstaffed], headcount="required") == []


def test_published_shifts_count_as_the_floor_the_store_already_has():
    """A half-published week is the common state. Judging the proposal alone
    would report days that are genuinely staffed as empty."""
    published = {
        "id": "published-1", "status": "published",
        "starts_at": f"{MONDAY.isoformat()}T08:00:00",
        "ends_at": f"{MONDAY.isoformat()}T17:00:00",
        "required_staff": 1, "employee_ids": ["employee-9"],
    }

    assert _evaluate([], baseline_shifts=[published]) == []
    assert _kinds(_evaluate([])) == ["coverage_gap"]


def test_an_overnight_window_is_one_window_not_two_holes():
    findings = evaluate_week_coverage(
        plan_shifts=[_shift(MONDAY, "18:00", "02:00", end_day=TUESDAY)],
        operating_hours={"1": {"open": "18:00", "close": "02:00"}},
        week_start=WEEK_START,
    )
    assert findings == []


def test_a_day_with_no_saved_hours_is_reported_as_unchecked_not_as_clean():
    findings = _evaluate([_shift(TUESDAY, "08:00", "17:00")])

    kinds = _kinds(findings)
    assert "no_hours_known" in kinds
    unchecked = next(f for f in findings if f["kind"] == "no_hours_known")
    assert unchecked["day"] == TUESDAY.isoformat()
    assert unchecked["severity"] == "advisory"


def test_a_shift_on_an_explicitly_closed_day_is_called_out():
    findings = _evaluate(
        [_shift(TUESDAY, "08:00", "17:00")],
        operating_hours={**HOURS, "2": None},
    )

    assert "demand_on_closed_day" in _kinds(findings)
    assert "no_hours_known" not in _kinds(findings)


def test_a_shift_outside_the_open_window_is_advisory_not_a_gap():
    findings = _evaluate([
        _shift(MONDAY, "08:00", "17:00", key="core"),
        _shift(MONDAY, "20:00", "23:00", key="after"),
    ])

    outside = [f for f in findings if f["kind"] == "demand_outside_hours"]
    assert len(outside) == 1
    assert outside[0]["severity"] == "advisory"
    assert outside[0]["shift_key"] == "after"


def test_a_leader_is_only_reported_absent_when_someone_else_is_there():
    """A day with nobody on is already a gap; saying "and no lead either" twice
    about the same hole is noise."""
    covered_without_lead = _evaluate(
        [_shift(MONDAY, "07:30", "17:00")],
        open_buffer_minutes=30, leader_job_ids=[LEADER_JOB], leader_job_names=["Shift Lead"],
    )
    assert "leader_absent_at_open" in _kinds(covered_without_lead)
    assert "Shift Lead" in next(
        f for f in covered_without_lead if f["kind"] == "leader_absent_at_open"
    )["detail"]

    nobody_at_all = _evaluate(
        [], open_buffer_minutes=30, leader_job_ids=[LEADER_JOB], leader_job_names=["Shift Lead"],
    )
    assert "leader_absent_at_open" not in _kinds(nobody_at_all)


def test_a_lead_on_the_floor_at_open_produces_nothing():
    assert _evaluate(
        [_shift(MONDAY, "07:30", "17:00", job_id=LEADER_JOB)],
        open_buffer_minutes=30, close_buffer_minutes=0,
        leader_job_ids=[LEADER_JOB], leader_job_names=["Shift Lead"],
    ) == []


def test_a_day_that_opens_with_three_and_closes_with_one_is_flagged_thin():
    findings = _evaluate([
        _shift(MONDAY, "08:00", "17:00", key="all-day"),
        _shift(MONDAY, "08:00", "12:00", key="second"),
        _shift(MONDAY, "08:00", "12:00", key="third"),
    ])

    assert _kinds(findings) == ["thin_close"]
    assert findings[0]["severity"] == "advisory"


def test_a_store_that_runs_one_person_all_day_is_left_alone():
    assert _evaluate([_shift(MONDAY, "08:00", "17:00")]) == []


def test_no_hours_at_all_checks_nothing_and_says_so_per_day():
    findings = evaluate_week_coverage(
        plan_shifts=[_shift(MONDAY, "08:00", "17:00")],
        operating_hours={}, week_start=WEEK_START,
    )
    assert _kinds(findings) == ["no_hours_known"]


def test_gap_kinds_are_exactly_the_findings_marked_gap():
    findings = _evaluate([
        _shift(MONDAY, "09:00", "12:00", key="late-start"),
        _shift(TUESDAY, "09:00", "12:00", key="unknown-day"),
    ], open_buffer_minutes=30)

    for finding in findings:
        assert (finding["severity"] == "gap") == (finding["kind"] in GAP_KINDS)


def test_findings_are_json_safe_and_deterministically_ordered():
    shifts = [
        _shift(MONDAY, "09:00", "12:00", key="late-start"),
        _shift(TUESDAY, "09:00", "12:00", key="unknown-day"),
    ]
    first = _evaluate(shifts, open_buffer_minutes=30, close_buffer_minutes=15)
    second = _evaluate(list(reversed(shifts)), open_buffer_minutes=30, close_buffer_minutes=15)

    assert first == second
    # Persisted into schedule_generation_runs.proposal — a stray date or UUID
    # here fails json.dumps for the entire proposal.
    assert json.loads(json.dumps(first)) == first


@pytest.mark.parametrize("slice_minutes", [5, 15, 30])
def test_the_sampling_slice_does_not_change_a_clean_week(slice_minutes):
    assert _evaluate(
        [_shift(MONDAY, "07:30", "17:00")],
        open_buffer_minutes=30, slice_minutes=slice_minutes,
    ) == []


def test_a_shift_starting_outside_the_week_is_not_reported_as_an_unchecked_day():
    """An overnight shift can start on the last instant of the window; a
    finding dated outside the week the manager is looking at is noise."""
    next_sunday = WEEK_START + timedelta(days=7)
    findings = evaluate_week_coverage(
        plan_shifts=[_shift(next_sunday, "23:00", "07:00",
                            end_day=next_sunday + timedelta(days=1))],
        operating_hours=HOURS, week_start=WEEK_START,
    )

    assert [f["day"] for f in findings if f["kind"] == "no_hours_known"] == []


def test_an_unfilled_lead_slot_is_not_a_lead_on_the_floor():
    """The floor is covered by a barista, so no gap suppresses the check — but
    the lead shift nobody was assigned to must not answer it either."""
    findings = _evaluate(
        [
            _shift(MONDAY, "08:00", "17:00", key="floor"),
            _shift(MONDAY, "08:00", "12:00", key="lead", staffed=0, job_id=LEADER_JOB),
        ],
        leader_job_ids=[LEADER_JOB], leader_job_names=["Shift Lead"],
    )

    assert "leader_absent_at_open" in _kinds(findings)
    assert "leader_absent_at_close" in _kinds(findings)


def test_an_unfilled_lead_slot_does_answer_the_pattern_question():
    """`required` judges the shape before anyone is assigned to it, so a lead
    block existing in the pattern is exactly what is being asked about."""
    findings = _evaluate(
        [
            _shift(MONDAY, "08:00", "17:00", key="floor"),
            _shift(MONDAY, "08:00", "17:00", key="lead", staffed=0, job_id=LEADER_JOB),
        ],
        headcount="required",
        leader_job_ids=[LEADER_JOB], leader_job_names=["Shift Lead"],
    )

    assert "leader_absent_at_open" not in _kinds(findings)
    assert "leader_absent_at_close" not in _kinds(findings)


def test_any_one_of_several_leader_jobs_counts_as_lead_coverage():
    """The rule is a SET: a store that lets a shift lead OR an assistant
    manager open must not read the AM's open as "no lead"."""
    findings = _evaluate(
        [
            _shift(MONDAY, "08:00", "17:00", key="floor"),
            _shift(MONDAY, "08:00", "12:00", key="am-open", job_id=SECOND_LEADER_JOB),
            _shift(MONDAY, "12:00", "17:00", key="lead-close", job_id=LEADER_JOB),
        ],
        leader_job_ids=[LEADER_JOB, SECOND_LEADER_JOB],
        leader_job_names=["Shift Lead", "Assistant Manager"],
    )

    assert "leader_absent_at_open" not in _kinds(findings)
    assert "leader_absent_at_close" not in _kinds(findings)


def test_several_leader_jobs_absent_is_one_finding_naming_them_all():
    """One absence, one finding — never one per eligible job, which would
    report the same hole three times over."""
    findings = _evaluate(
        [_shift(MONDAY, "08:00", "17:00", key="floor")],
        leader_job_ids=[LEADER_JOB, SECOND_LEADER_JOB],
        leader_job_names=["Shift Lead", "Assistant Manager"],
    )

    at_open = [f for f in findings if f["kind"] == "leader_absent_at_open"]
    assert len(at_open) == 1
    assert "No Shift Lead or Assistant Manager is scheduled at open" in at_open[0]["detail"]
    # A finding names ONE job; with several eligible both the id and the name
    # stay blank rather than blaming the first, and `job_names` carries the
    # set. `job_name` is a real job's name everywhere else it is read — and
    # this list is persisted verbatim into `schedule_generation_runs.proposal`
    # — so the prose label lives in `detail` and nowhere else.
    assert at_open[0]["job_id"] is None
    assert at_open[0]["job_name"] is None
    assert at_open[0]["job_names"] == ["Shift Lead", "Assistant Manager"]


def test_a_single_leader_job_still_names_itself_on_the_finding():
    findings = _evaluate(
        [_shift(MONDAY, "08:00", "17:00", key="floor")],
        leader_job_ids=[LEADER_JOB], leader_job_names=["Shift Lead"],
    )
    at_open = next(f for f in findings if f["kind"] == "leader_absent_at_open")
    assert at_open["job_id"] == LEADER_JOB
    assert at_open["job_name"] == "Shift Lead"
    assert at_open["job_names"] == ["Shift Lead"]


def test_a_leader_set_with_no_resolved_names_leaves_the_job_fields_empty():
    """Names come from a join that can come back short. The sentence falls back
    to "shift lead"; the job fields do not — a placeholder in `job_name` reads
    as a job called "shift lead" to anything matching on it."""
    findings = _evaluate(
        [_shift(MONDAY, "08:00", "17:00", key="floor")],
        leader_job_ids=[LEADER_JOB], leader_job_names=[],
    )
    at_open = next(f for f in findings if f["kind"] == "leader_absent_at_open")
    assert "No shift lead is scheduled at open" in at_open["detail"]
    assert at_open["job_name"] is None
    assert at_open["job_names"] is None


def test_every_finding_carries_the_job_names_key():
    """One shape for every consumer: a key that exists on some findings and is
    absent on others is how a renderer starts guessing."""
    findings = _evaluate(
        [_shift(MONDAY, "10:00", "12:00", key="short")],
        leader_job_ids=[LEADER_JOB], leader_job_names=["Shift Lead"],
    )
    assert findings
    assert all("job_names" in finding for finding in findings)


def test_an_empty_leader_set_checks_nothing():
    assert _evaluate([_shift(MONDAY, "08:00", "17:00")], leader_job_ids=[], leader_job_names=[]) == []
