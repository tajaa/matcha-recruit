"""assignment_guard — pure tests, no DB.

    cd server && ./venv/bin/python -m pytest tests/employee_schedule/test_assignment_guard.py -q

The reported failure: "fill the vacant shift-leader shifts" put one employee
on nine shifts, some overlapping. The guard evaluates a batch as a SET, so
the nine-shift request comes back as "these N are staged, these M are not,
and here is why" — before the manager confirms anything.
"""

from datetime import datetime, timedelta, timezone

from app.matcha.services.scheduling.assignment_guard import (
    POLICY_DEFAULT_WEEKLY_CAP_MINUTES, POLICY_MAX_CONSECUTIVE_DAYS, POLICY_MIN_REST_HOURS,
    EmployeeLedger, ProposedAssignment, consecutive_day_count, evaluate_batch,
)

UTC = timezone.utc
DANA = "e-dana"


def _at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 8, day, hour, minute, tzinfo=UTC)


def _shift(op_index: int, day: int, start_hour: int, end_hour: int, *, employee=DANA, label="Shift Lead", shift_id=None):
    starts, ends = _at(day, start_hour), _at(day, end_hour)
    return ProposedAssignment(
        op_index=op_index, shift_id=shift_id or f"s{op_index}", employee_id=employee,
        starts_at=starts, ends_at=ends, worked_minutes=int((ends - starts).total_seconds() // 60),
        employee_name="Dana Reyes", shift_label=label,
    )


def _codes(verdict):
    return [reason["code"] for reason in verdict.reasons]


class TestNineShiftsOneEmployee:
    """4 leader blocks a day (06-14, 10-18, 14-22, 18-02) across Sun–Mon plus
    one Tuesday: nine shifts requested for one person."""

    def _batch(self):
        items = []
        index = 0
        for day in (23, 24):
            for start, end in ((6, 14), (10, 18), (14, 22)):
                items.append(_shift(index, day, start, end))
                index += 1
            # 18:00 → 02:00 next day
            starts, ends = _at(day, 18), _at(day + 1, 2)
            items.append(ProposedAssignment(index, f"s{index}", DANA, starts, ends, 480, "Dana Reyes", "Shift Lead"))
            index += 1
        items.append(_shift(index, 25, 8, 18))  # 10h: pushes the accepted week to 42h
        return items

    def test_overlaps_within_the_batch_are_blocked_and_name_the_earlier_shift(self):
        verdicts = evaluate_batch(self._batch(), {DANA: EmployeeLedger(name="Dana Reyes")})
        blocked = {i for i, v in verdicts.items() if v.verdict == "blocked"}
        accepted = {i for i, v in verdicts.items() if v.verdict != "blocked"}
        # Sunday: 06-14 accepted; 10-18 overlaps it; 14-22 accepted; 18-02 overlaps 14-22.
        assert 0 in accepted and 1 in blocked and 2 in accepted and 3 in blocked
        assert _codes(verdicts[1]) == ["intra_batch_overlap"]
        assert "Sun Aug 23 06:00–14:00" in verdicts[1].reasons[0]["message"]
        assert "earlier in this batch" in verdicts[1].reasons[0]["message"]
        assert verdicts[1].reasons[0]["policy"] is False
        # Monday follows the same shape; Tuesday's single shift stands.
        assert 4 in accepted and 5 in blocked and 6 in accepted and 7 in blocked and 8 in accepted
        assert len(accepted) == 5 and len(blocked) == 4

    def test_the_accepted_shifts_still_carry_policy_warnings(self):
        verdicts = evaluate_batch(self._batch(), {DANA: EmployeeLedger(name="Dana Reyes")})
        # Sunday 14-22 is a second shift the same day with 0h rest after 06-14.
        assert verdicts[2].verdict == "warn"
        assert {"second_shift_same_day", "rest_gap"} <= set(_codes(verdicts[2]))
        assert all(reason["policy"] for reason in verdicts[2].reasons)
        # By Tuesday the week is over 40h with no overtime allowance.
        assert "weekly_overtime_policy" in _codes(verdicts[8])

    def test_blocked_ops_do_not_consume_capacity(self):
        verdicts = evaluate_batch(self._batch(), {DANA: EmployeeLedger(name="Dana Reyes")})
        # The blocked 10-18 shift must not count toward Dana's hours or days.
        assert verdicts[1].after == verdicts[1].before
        assert verdicts[2].before["minutes"] == 480  # only the 06-14 shift so far


class TestExistingOverlap:
    def test_a_shift_already_in_the_database_blocks_with_its_own_copy(self):
        ledger = EmployeeLedger(name="Dana Reyes", intervals=[(_at(23, 8), _at(23, 16), "db-1", "Opener")])
        verdicts = evaluate_batch([_shift(0, 23, 12, 20)], {DANA: ledger})
        assert verdicts[0].verdict == "blocked"
        assert _codes(verdicts[0]) == ["existing_overlap"]
        assert "already on the Opener Sun Aug 23 08:00–16:00 shift" in verdicts[0].reasons[0]["message"]

    def test_the_target_shift_itself_is_ignored_when_reassigning_onto_it(self):
        # A reassign's destination shift can already be in the ledger (the
        # person moving off it is someone else); the target must not read as
        # a self-overlap.
        ledger = EmployeeLedger(intervals=[(_at(23, 8), _at(23, 16), "s0", "Opener")])
        verdicts = evaluate_batch([_shift(0, 23, 8, 16, shift_id="s0")], {DANA: ledger})
        assert verdicts[0].verdict == "ok"


class TestPolicyWarnings:
    def test_back_to_back_is_a_warning_not_a_block(self):
        verdicts = evaluate_batch([_shift(0, 23, 6, 14), _shift(1, 23, 14, 22)], {DANA: EmployeeLedger()})
        assert verdicts[1].verdict == "warn"
        assert "second_shift_same_day" in _codes(verdicts[1])
        rest = next(r for r in verdicts[1].reasons if r["code"] == "rest_gap")
        assert "0.0h rest" in rest["message"] and f"{POLICY_MIN_REST_HOURS:g}h minimum" in rest["message"]

    def test_split_shift_permission_silences_the_same_day_warning_only(self):
        verdicts = evaluate_batch(
            [_shift(0, 23, 6, 10), _shift(1, 23, 16, 20)], {DANA: EmployeeLedger()}, allow_split_shift=True,
        )
        assert "second_shift_same_day" not in _codes(verdicts[1])
        assert "rest_gap" in _codes(verdicts[1])  # 6h gap is still under policy

    def test_seventh_consecutive_day_warns_using_profile_or_default(self):
        ledger = EmployeeLedger(intervals=[(_at(d, 9), _at(d, 13), f"db-{d}", "Shift") for d in range(17, 23)])
        verdicts = evaluate_batch([_shift(0, 23, 9, 13)], {DANA: ledger})
        assert "consecutive_days" in _codes(verdicts[0])
        assert f"{POLICY_MAX_CONSECUTIVE_DAYS} max" in next(r["message"] for r in verdicts[0].reasons if r["code"] == "consecutive_days")
        ledger.max_consecutive_days = 7
        verdicts = evaluate_batch([_shift(0, 23, 9, 13)], {DANA: ledger})
        assert "consecutive_days" not in _codes(verdicts[0])

    def test_weekly_cap_uses_the_profile_when_set(self):
        ledger = EmployeeLedger(max_weekly_minutes=1800)  # 30h
        batch = [_shift(i, 23 + i, 9, 17) for i in range(4)]  # 4 × 8h = 32h
        verdicts = evaluate_batch(batch, {DANA: ledger})
        assert "weekly_cap" not in _codes(verdicts[2])
        assert "weekly_cap" in _codes(verdicts[3])
        assert "30h cap" in next(r["message"] for r in verdicts[3].reasons if r["code"] == "weekly_cap")

    def test_forty_hour_policy_applies_only_without_overtime_permission(self):
        batch = [_shift(i, 23 + i, 8, 17) for i in range(5)]  # 5 × 9h = 45h
        strict = evaluate_batch(batch, {DANA: EmployeeLedger(allow_overtime=False)})
        assert "weekly_overtime_policy" in _codes(strict[4])
        assert f"{POLICY_DEFAULT_WEEKLY_CAP_MINUTES / 60:g}h" in next(
            r["message"] for r in strict[4].reasons if r["code"] == "weekly_overtime_policy")
        relaxed = evaluate_batch(batch, {DANA: EmployeeLedger(allow_overtime=True)})
        assert relaxed[4].verdict == "ok"

    def test_week_totals_honour_the_location_week_start(self):
        # Week starts Monday: a Sunday shift + a Monday shift are in different weeks.
        batch = [_shift(0, 23, 8, 17), _shift(1, 24, 8, 17)]  # Aug 23 2026 is a Sunday
        verdicts = evaluate_batch(batch, {DANA: EmployeeLedger()}, week_start_weekday=1)
        assert verdicts[1].before["minutes"] == 0


class TestPreBlockedAndDeterminism:
    def test_pre_blocked_ops_are_reported_blocked_and_free_the_slot(self):
        pre = {0: [{"code": "not_qualified", "message": "not qualified", "policy": False}]}
        verdicts = evaluate_batch([_shift(0, 23, 6, 14), _shift(1, 23, 6, 14, shift_id="s9")], {DANA: EmployeeLedger()}, pre_blocked=pre)
        assert verdicts[0].verdict == "blocked" and _codes(verdicts[0]) == ["not_qualified"]
        # Because op 0 never landed, op 1 (same window) does not overlap it.
        assert verdicts[1].verdict == "ok"

    def test_same_input_same_output(self):
        batch = [_shift(0, 23, 6, 14), _shift(1, 23, 10, 18), _shift(2, 24, 6, 14)]
        first = evaluate_batch(batch, {DANA: EmployeeLedger()})
        second = evaluate_batch(list(reversed(batch)), {DANA: EmployeeLedger()})
        assert {i: (v.verdict, _codes(v)) for i, v in first.items()} == {i: (v.verdict, _codes(v)) for i, v in second.items()}

    def test_consecutive_day_count(self):
        days = {_at(20, 9).date(), _at(21, 9).date(), _at(23, 9).date()}
        assert consecutive_day_count(days, _at(22, 9).date()) == 4
        assert consecutive_day_count(days, _at(25, 9).date()) == 1
        assert consecutive_day_count(set(), (_at(22, 9) + timedelta(days=1)).date()) == 1
