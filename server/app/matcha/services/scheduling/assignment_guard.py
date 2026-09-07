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
) -> dict[int, GuardVerdict]:
    """Pure. Walk the batch in op order, growing a per-employee working set as
    ops are accepted, so later ops see earlier ones. `pre_blocked` carries
    DB-derived hard refusals the caller already established for an op index
    (unqualified, outside availability, shift full) — those ops are reported
    blocked and never consume capacity. Returns a verdict per op_index."""
    pre_blocked = pre_blocked or {}
    # Working sets start as the DB ledger and grow with accepted batch ops.
    intervals: dict[str, list[tuple[datetime, datetime, str, str, bool]]] = defaultdict(list)
    for employee_id, ledger in ledgers.items():
        for starts_at, ends_at, shift_id, label in ledger.intervals:
            intervals[employee_id].append((starts_at, ends_at, shift_id, label, False))

    def snapshot(employee_id: str, week: date) -> dict[str, Any]:
        rows = intervals.get(employee_id, [])
        minutes = sum(
            _minutes(s, e) for s, e, _sid, _label, _batch in rows
            if _week_key(s, week_start_weekday) == week
        )
        return {
            "minutes": minutes,
            "shifts": sum(1 for s, *_ in rows if _week_key(s, week_start_weekday) == week),
            "days": len({s.date() for s, *_ in rows if _week_key(s, week_start_weekday) == week}),
        }

    verdicts: dict[int, GuardVerdict] = {}
    for item in sorted(assignments, key=lambda a: a.op_index):
        ledger = ledgers.get(item.employee_id) or EmployeeLedger(name=item.employee_name)
        week = _week_key(item.starts_at, week_start_weekday)
        before = snapshot(item.employee_id, week)
        reasons: list[dict[str, Any]] = list(pre_blocked.get(item.op_index) or [])
        blocked = bool(reasons)

        own = [row for row in intervals.get(item.employee_id, []) if row[2] != item.shift_id]
        for starts_at, ends_at, _shift_id, label, from_batch in own:
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
            verdicts[item.op_index] = GuardVerdict("blocked", reasons, before, before)
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

        after_minutes = before["minutes"] + item.worked_minutes
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

        intervals[item.employee_id].append(
            (item.starts_at, item.ends_at, item.shift_id, item.shift_label, True)
        )
        after = snapshot(item.employee_id, week)
        verdicts[item.op_index] = GuardVerdict("warn" if reasons else "ok", reasons, before, after)
    return verdicts


async def build_ledgers(
    conn, company_id: UUID, *, employee_ids: list[UUID],
    window_start: datetime, window_end: datetime,
) -> dict[str, EmployeeLedger]:
    """DB half: every non-cancelled shift each employee is on inside the
    window (same predicate as `shift_writes.find_conflicts`, one query for the
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
    rows = await conn.fetch(
        """
        SELECT a.employee_id, s.id AS shift_id, s.starts_at, s.ends_at, s.role
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
        ledgers.setdefault(str(row["employee_id"]), EmployeeLedger()).intervals.append(
            (row["starts_at"], row["ends_at"], str(row["shift_id"]), (row["role"] or "shift").title())
        )
    return ledgers
