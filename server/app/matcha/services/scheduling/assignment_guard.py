"""Whole-batch review for agent/planner assignment paths.

Every Huume-originated assignment (thread edits, the bulk vacant-shift fill,
and — later — the server-side planner) passes through here BEFORE it is
staged, so the manager reviews a batch that has already been checked as a
set: op 7 is evaluated against ops 1–6, not just against the database. The
per-op statutory check (`shift_compliance.check_shift_compliance`) is
unchanged and still runs; this module adds what it structurally cannot see —
time overlap (with existing shifts AND within the batch), cumulative weekly
load, rest between shifts, same-day doubles, and consecutive days.

**POLICY, not law.** The `POLICY_*` constants below are the operational
defaults a careful manager would apply by hand. They are deliberately NOT in
`schedule_compliance._SCHEDULING_RULES` and carry no statute: statutory
thresholds live in the compliance catalog (`schedule_rule_extractions`,
curated states) and are cited verbatim; these are labelled `policy=True` in
every reason they produce so the pill, the audit row and the model can tell
the two apart. They apply ONLY to agent/planner paths — the manual REST
routes and their `force` semantics are untouched (see
`routes/employee_schedule/assignments.py`).

Severity model: an op is `blocked` when it can never be right — it overlaps
another shift the person is already on (in the DB or earlier in this batch),
the shift is full, the person is outside their availability, unqualified, or
on approved time away. A blocked op is REMOVED from the proposal at stage
time and listed under "Not staged" with the reason; it is never silently
dropped at confirm. An op is `warn` when it is lawful-but-unwise by policy
(second shift that day, under 8h rest, 7th consecutive day, over the weekly
cap) — it stays in the proposal with the warning in the pill, and confirming
is the manager's acknowledgment.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Literal, Optional
from uuid import UUID

from .schedule_rules import align_week_start

POLICY_MIN_REST_HOURS = 8.0
POLICY_MAX_SHIFTS_PER_DAY = 1
POLICY_MAX_CONSECUTIVE_DAYS = 6
POLICY_DEFAULT_WEEKLY_CAP_MINUTES = 2400  # 40h — unless allow_overtime / a stored max_weekly_minutes

POLICY_DEFAULTS = {
    "min_rest_hours": POLICY_MIN_REST_HOURS,
    "max_shifts_per_day": POLICY_MAX_SHIFTS_PER_DAY,
    "max_consecutive_days": POLICY_MAX_CONSECUTIVE_DAYS,
    "default_weekly_cap_minutes": POLICY_DEFAULT_WEEKLY_CAP_MINUTES,
}


@dataclass(frozen=True)
class ProposedAssignment:
    """One assign/reassign op's destination side, in batch order."""
    op_index: int
    shift_id: str
    employee_id: str
    starts_at: datetime
    ends_at: datetime
    worked_minutes: int
    employee_name: str = ""
    shift_label: str = "shift"
    from_employee_id: Optional[str] = None


@dataclass(frozen=True)
class ProposedRemoval:
    """An unassign (phase one) or cancellation (in operation order).

    A missing employee means cancel the entire shift. Reassignment removals
    are carried by ProposedAssignment so a rejection can restore its source.
    """
    op_index: int
    shift_id: str
    employee_id: Optional[str] = None
    before_batch: bool = False


@dataclass
class EmployeeLedger:
    """What the database already knows about one employee's week: every
    non-cancelled shift they are on (start, end, shift_id, label) inside the
    review window, plus their scheduling-profile caps. `build_ledgers` fills
    it; tests construct it directly."""
    name: str = ""
    intervals: list[tuple[datetime, datetime, str, str]] = field(default_factory=list)
    max_weekly_minutes: Optional[int] = None
    allow_overtime: bool = False
    max_consecutive_days: Optional[int] = None
    # Net minutes are separate from the full interval: breaks reduce hours,
    # but never make a person available for an overlapping shift.
    worked_minutes: dict[str, int] = field(default_factory=dict)


@dataclass
class GuardVerdict:
    verdict: Literal["ok", "warn", "blocked"]
    reasons: list[dict[str, Any]]
    before: dict[str, Any]
    after: dict[str, Any]


def _reason(code: str, message: str, *, policy: bool) -> dict[str, Any]:
    return {"code": code, "message": message, "policy": policy}


def _overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return a_start < b_end and a_end > b_start


def _fmt_when(starts_at: datetime, ends_at: datetime) -> str:
    return f"{starts_at.strftime('%a %b')} {starts_at.day} {starts_at.strftime('%H:%M')}–{ends_at.strftime('%H:%M')}"


def consecutive_day_count(days: set[date], candidate: date) -> int:
    """Length of the run of scheduled days that would contain `candidate`."""
    combined = set(days)
    combined.add(candidate)
    before = candidate
    while before - timedelta(days=1) in combined:
        before -= timedelta(days=1)
    after = candidate
    while after + timedelta(days=1) in combined:
        after += timedelta(days=1)
    return (after - before).days + 1


def _week_key(moment: datetime, week_start_weekday: int) -> date:
    return align_week_start(moment.date(), week_start_weekday)


def _minutes(starts_at: datetime, ends_at: datetime, break_minutes: int = 0) -> int:
    return max(0, int((ends_at - starts_at).total_seconds() // 60) - int(break_minutes or 0))


def evaluate_batch(
    assignments: list[ProposedAssignment],
    ledgers: dict[str, EmployeeLedger],
    *,
    week_start_weekday: int = 0,
    allow_split_shift: bool = False,
    pre_blocked: Optional[dict[int, list[dict[str, Any]]]] = None,
    removals: Optional[list[ProposedRemoval]] = None,
    headroom: Optional[dict[str, int]] = None,
) -> dict[int, GuardVerdict]:
    """Pure review, matching confirm's removal phase then ordered additions.

    Reassignments tentatively free their sources so two people can exchange
    overlapping shifts. If one is rejected, re-run without its removal:
    dependent assignments must not rely on a seat or interval it never freed.
    Each repeat rejects at least one more reassignment, so this is bounded by
    the batch size. Inputs are never mutated; blocked ops consume no capacity.
    """
    blocked = {index: reasons for index, reasons in (pre_blocked or {}).items() if reasons}
    while True:
        verdicts = _evaluate_batch(
            assignments, ledgers, week_start_weekday=week_start_weekday,
            allow_split_shift=allow_split_shift, pre_blocked=blocked,
            removals=removals or [], headroom=headroom or {},
        )
        newly_blocked = [
            item for item in assignments if item.from_employee_id
            and item.op_index not in blocked and verdicts[item.op_index].verdict == "blocked"
        ]
        if not newly_blocked:
            return verdicts
        for item in newly_blocked:
            blocked[item.op_index] = verdicts[item.op_index].reasons


def _evaluate_batch(
    assignments: list[ProposedAssignment], ledgers: dict[str, EmployeeLedger], *,
    week_start_weekday: int, allow_split_shift: bool,
    pre_blocked: dict[int, list[dict[str, Any]]],
    removals: list[ProposedRemoval], headroom: dict[str, int],
) -> dict[int, GuardVerdict]:
    pre_blocked = pre_blocked or {}
    headroom = dict(headroom)
    # Working sets start as the DB ledger and grow with accepted batch ops.
    intervals: dict[str, list[tuple[datetime, datetime, str, str, bool, int]]] = defaultdict(list)
    for employee_id, ledger in ledgers.items():
        for starts_at, ends_at, shift_id, label in ledger.intervals:
            minutes = ledger.worked_minutes.get(shift_id, _minutes(starts_at, ends_at))
            intervals[employee_id].append((starts_at, ends_at, shift_id, label, False, minutes))

    def remove(shift_id: str, employee_id: Optional[str]) -> None:
        for eid in ([employee_id] if employee_id is not None else list(intervals)):
            rows = intervals.get(eid, [])
            kept = [row for row in rows if row[2] != shift_id]
            if len(kept) != len(rows) and shift_id in headroom:
                headroom[shift_id] += len(rows) - len(kept)
            intervals[eid] = kept

    for removal in removals:
        if removal.before_batch:
            remove(removal.shift_id, removal.employee_id)
    for item in sorted(assignments, key=lambda a: a.op_index):
        if item.from_employee_id and not pre_blocked.get(item.op_index):
            remove(item.shift_id, item.from_employee_id)
    pending_removals = iter(sorted(
        (r for r in removals if not r.before_batch), key=lambda r: r.op_index,
    ))
    next_removal = next(pending_removals, None)
    cancelled: set[str] = set()

    def snapshot(employee_id: str, week: date) -> dict[str, Any]:
        rows = intervals.get(employee_id, [])
        minutes = sum(
            minutes for s, _e, _sid, _label, _batch, minutes in rows
            if _week_key(s, week_start_weekday) == week
        )
        return {
            "minutes": minutes,
            "shifts": sum(1 for s, *_ in rows if _week_key(s, week_start_weekday) == week),
            "days": len({s.date() for s, *_ in rows if _week_key(s, week_start_weekday) == week}),
        }

    verdicts: dict[int, GuardVerdict] = {}
    for item in sorted(assignments, key=lambda a: a.op_index):
        while next_removal is not None and next_removal.op_index < item.op_index:
            remove(next_removal.shift_id, next_removal.employee_id)
            if next_removal.employee_id is None:
                cancelled.add(next_removal.shift_id)
            next_removal = next(pending_removals, None)
        ledger = ledgers.get(item.employee_id) or EmployeeLedger(name=item.employee_name)
        week = _week_key(item.starts_at, week_start_weekday)
        before = snapshot(item.employee_id, week)
        reasons: list[dict[str, Any]] = list(pre_blocked.get(item.op_index) or [])
        existing = [row for row in intervals.get(item.employee_id, []) if row[2] == item.shift_id]
        if item.shift_id in cancelled:
            reasons.append(_reason("shift_cancelled", "that shift is cancelled earlier in this batch", policy=False))
        elif not existing and headroom.get(item.shift_id, 1) <= 0:
            reasons.append(_reason("shift_full", "that shift is already fully staffed", policy=False))
        blocked = bool(reasons)

        own = [row for row in intervals.get(item.employee_id, []) if row[2] != item.shift_id]
        for starts_at, ends_at, _shift_id, label, from_batch, _worked in own:
            if not _overlaps(item.starts_at, item.ends_at, starts_at, ends_at):
                continue
            if from_batch:
                reasons.append(_reason(
                    "intra_batch_overlap",
                    f"would overlap the {label} {_fmt_when(starts_at, ends_at)} shift earlier in this batch",
                    policy=False,
                ))
            else:
                reasons.append(_reason(
                    "existing_overlap",
                    f"already on the {label} {_fmt_when(starts_at, ends_at)} shift",
                    policy=False,
                ))
            blocked = True
            break

        if blocked:
            # A restored-source pass may discover the original refusal again.
            unique_reasons: list[dict[str, Any]] = []
            for reason in reasons:
                if reason not in unique_reasons:
                    unique_reasons.append(reason)
            verdicts[item.op_index] = GuardVerdict("blocked", unique_reasons, before, before)
            continue

        # ── Policy warnings (lawful-but-unwise) ──
        same_day = [row for row in own if row[0].date() == item.starts_at.date()]
        if same_day and len(same_day) >= POLICY_MAX_SHIFTS_PER_DAY and not allow_split_shift:
            other = same_day[0]
            reasons.append(_reason(
                "second_shift_same_day",
                f"second shift that day — already on {_fmt_when(other[0], other[1])} (policy: one shift per day unless you ask for a split)",
                policy=True,
            ))

        gaps: list[float] = []
        for starts_at, ends_at, *_ in own:
            if ends_at <= item.starts_at:
                gaps.append((item.starts_at - ends_at).total_seconds() / 3600.0)
            elif starts_at >= item.ends_at:
                gaps.append((starts_at - item.ends_at).total_seconds() / 3600.0)
        if gaps and min(gaps) < POLICY_MIN_REST_HOURS:
            reasons.append(_reason(
                "rest_gap",
                f"only {min(gaps):.1f}h rest next to another shift (policy: {POLICY_MIN_REST_HOURS:g}h minimum)",
                policy=True,
            ))

        days = {row[0].date() for row in own}
        max_days = ledger.max_consecutive_days if ledger.max_consecutive_days is not None else POLICY_MAX_CONSECUTIVE_DAYS
        run = consecutive_day_count(days, item.starts_at.date())
        if run > max_days:
            reasons.append(_reason(
                "consecutive_days",
                f"{run} days in a row (policy: {max_days} max)",
                policy=True,
            ))

        after_minutes = before["minutes"] + item.worked_minutes - sum(row[5] for row in existing)
        if ledger.max_weekly_minutes is not None and after_minutes > ledger.max_weekly_minutes:
            reasons.append(_reason(
                "weekly_cap",
                f"{after_minutes / 60:g}h this week — above their {ledger.max_weekly_minutes / 60:g}h cap",
                policy=True,
            ))
        elif (
            ledger.max_weekly_minutes is None
            and not ledger.allow_overtime
            and after_minutes > POLICY_DEFAULT_WEEKLY_CAP_MINUTES
        ):
            reasons.append(_reason(
                "weekly_overtime_policy",
                f"{after_minutes / 60:g}h this week — over {POLICY_DEFAULT_WEEKLY_CAP_MINUTES / 60:g}h and overtime isn't enabled for them",
                policy=True,
            ))

        intervals[item.employee_id] = own + [
            (item.starts_at, item.ends_at, item.shift_id, item.shift_label, True, item.worked_minutes)
        ]
        if not existing and item.shift_id in headroom:
            headroom[item.shift_id] -= 1
        after = snapshot(item.employee_id, week)
        verdicts[item.op_index] = GuardVerdict("warn" if reasons else "ok", reasons, before, after)
    return verdicts


async def build_ledgers(
    conn, company_id: UUID, *, employee_ids: list[UUID],
    window_start: datetime, window_end: datetime,
) -> dict[str, EmployeeLedger]:
    """DB half: expand the operation window for weekly/rest/consecutive-day
    context, then load non-cancelled shifts (same predicate as
    `shift_writes.find_conflicts`, one query for the
    whole batch instead of one per op) plus their `employee_schedule_profiles`
    caps. Employees with no profile row get the defaults — the same
    `PROFILE_DEFAULTS` the week builder reads."""
    ids = list(dict.fromkeys(employee_ids))
    ledgers: dict[str, EmployeeLedger] = {str(eid): EmployeeLedger() for eid in ids}
    if not ids:
        return ledgers
    people = await conn.fetch(
        """
        SELECT e.id, e.first_name, e.last_name,
               p.max_weekly_minutes, p.max_consecutive_days,
               COALESCE(p.allow_overtime, false) AS allow_overtime
        FROM employees e
        LEFT JOIN employee_schedule_profiles p
          ON p.employee_id = e.id AND p.company_id = e.org_id
        WHERE e.org_id = $1 AND e.id = ANY($2::uuid[])
        """,
        company_id, ids,
    )
    for row in people:
        ledger = ledgers.setdefault(str(row["id"]), EmployeeLedger())
        ledger.name = " ".join(filter(None, [row["first_name"], row["last_name"]]))
        ledger.max_weekly_minutes = row["max_weekly_minutes"]
        ledger.max_consecutive_days = row["max_consecutive_days"]
        ledger.allow_overtime = bool(row["allow_overtime"])
    context_days = max(8, max(
        (ledger.max_consecutive_days or POLICY_MAX_CONSECUTIVE_DAYS) + 1
        for ledger in ledgers.values()
    ))
    window_start -= timedelta(days=context_days)
    window_end += timedelta(days=context_days)
    rows = await conn.fetch(
        """
        SELECT a.employee_id, s.id AS shift_id, s.starts_at, s.ends_at, s.role, s.break_minutes
        FROM schedule_shift_assignments a
        JOIN schedule_shifts s ON s.id = a.shift_id
        WHERE s.company_id = $1 AND a.employee_id = ANY($2::uuid[])
          AND s.status <> 'cancelled'
          AND s.starts_at < $4 AND s.ends_at > $3
        ORDER BY s.starts_at, s.id
        """,
        company_id, ids, window_start, window_end,
    )
    for row in rows:
        ledger = ledgers.setdefault(str(row["employee_id"]), EmployeeLedger())
        ledger.intervals.append(
            (row["starts_at"], row["ends_at"], str(row["shift_id"]), (row["role"] or "shift").title())
        )
        ledger.worked_minutes[str(row["shift_id"])] = _minutes(row["starts_at"], row["ends_at"], row["break_minutes"])
    return ledgers
