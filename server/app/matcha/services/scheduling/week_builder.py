"""Deterministic whole-week draft builder for the schedule Huume surface.

Huume interprets the manager's request; this module owns the actual staffing
decision.  It never publishes, never changes an existing assignment, and
never treats missing availability as permission to schedule someone.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Iterable
from uuid import UUID, uuid4

from app.database import connection_or_direct

from .assignment_guard import (
    POLICY_MAX_CONSECUTIVE_DAYS, POLICY_MAX_SHIFTS_PER_DAY, POLICY_MIN_REST_HOURS,
)
from .location_profile import (
    WEEKDAY_NAMES, get_location_profile, load_profile_bundle, missing_fields,
    profile_leader_job_ids, resolve_week_start_weekday, week_rules_refusal,
)
from .schedule_break_stagger import StaggerAssignment, stagger_shift_breaks
from .schedule_batch import BatchItem, MAX_BATCH_OPERATIONS, plan_batches, split_plan_message
from .schedule_breaks import reinterpret_schedule_wall_time
from .schedule_coverage import (
    GAP_KINDS, evaluate_week_coverage, make_finding, sort_findings,
)
from .schedule_guidance import resolve_week_break_plans
from .schedule_profiles import fetch_effective_job_employee_ids
from .schedule_review import jurisdiction_message
from .schedule_rules import align_week_start, availability_violations, template_windows
from .shift_compliance import check_shift_compliance, jurisdiction_rule_status
from .shift_writes import (
    apply_assignment_core,
    create_shift_core,
    fetch_availability,
    find_conflicts,
    lock_scheduling_employees,
    log_audit,
    resolve_job_by_name,
)


PLANNER_VERSION = "week-builder-v1"
_MAX_DEMAND_SHIFTS = 200
_MAX_ROSTER = 300
_MAX_PREVIEW_SHIFTS = 100
_MAX_COMPLIANCE_REPLANS = 3
# Findings are persisted with the proposal and echoed to the model, so both
# ends are bounded. The counts in `metrics.finding_counts` are NOT capped —
# truncating the list must never make the week look cleaner than it is.
_MAX_FINDINGS = 40
_FINDINGS_RETURNED = 20
# `coverage_shortfall` fires on every normally-staffed shift that owes a break,
# which is most of them. Reporting each one turns the card into a wall of amber
# and buries the real holes, so the per-day advisory is capped and the count
# carries the rest.
_MAX_THIN_BREAK_FINDINGS_PER_DAY = 2

logger = logging.getLogger(__name__)


def _iso(value: Any) -> Any:
    if isinstance(value, (date, datetime, time, UUID)):
        return value.isoformat() if not isinstance(value, UUID) else str(value)
    if isinstance(value, dict):
        return {str(key): _iso(item) for key, item in value.items()}
    if isinstance(value, set):
        # A set's iteration order depends on the process's string-hash seed,
        # which is randomized fresh per process start — `sort_keys=True` on
        # the eventual json.dumps only orders dict KEYS, never list elements,
        # so an unsorted set-to-list here makes `_input_hash` unstable across
        # any process restart between propose and confirm (dev's --reload
        # firing mid-edit, or propose/confirm landing on different prod
        # workers). Every real proposal then reads as "the schedule changed"
        # with nothing having changed at all. Sort by the serialized form so
        # this holds for sets of any JSON-safe element, not just strings.
        items = [_iso(item) for item in value]
        return sorted(items, key=lambda item: json.dumps(item, sort_keys=True, default=str))
    if isinstance(value, (list, tuple)):
        return [_iso(item) for item in value]
    return value


def _input_hash(snapshot: dict[str, Any]) -> str:
    raw = json.dumps(_iso(snapshot), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _coverage_sentence(metrics: dict[str, Any]) -> str:
    """The one sentence that says whether coverage was checked, and what it found."""
    if not metrics.get("operating_hours_known"):
        return (
            " This location's opening hours are not saved, so coverage at open and "
            "close was not checked."
        )
    counts = metrics.get("finding_counts") or {}
    total = sum(int(value) for value in counts.values())
    gaps = int(metrics.get("gap_count") or 0)
    advisories = max(0, total - gaps)
    if gaps:
        return (
            f" {gaps} coverage/break gap(s) and {advisories} advisory finding(s) "
            "need your review."
        )
    if advisories:
        return (
            f" No coverage gaps against this location's hours; {advisories} finding(s) "
            "are worth a look."
        )
    return " No coverage gaps found against this location's hours."


def _review_payload(
    *, plan: dict[str, Any], snapshot: dict[str, Any],
    source_mode: str, template_name: str | None,
) -> dict[str, Any]:
    """Build the persisted manager-facing view of a generated proposal."""
    metrics = plan["metrics"]
    employee_names = {
        employee["id"]: employee["name"] for employee in snapshot["employees"]
    }
    schedule_preview = []
    for shift in plan["shifts"][:_MAX_PREVIEW_SHIFTS]:
        fixed_names = [
            employee_names.get(employee_id, "Existing assignee")
            for employee_id in shift.get("fixed_employee_ids") or []
        ]
        proposed_names = [
            assignment.get("employee_name")
            or employee_names.get(assignment["employee_id"], "Employee")
            for assignment in shift.get("proposed_assignments") or []
        ]
        schedule_preview.append({
            "shift_key": shift["key"],
            "starts_at": shift["starts_at"],
            "ends_at": shift["ends_at"],
            "role": shift.get("role"),
            "required_staff": shift["required_staff"],
            "assignment_names": fixed_names + proposed_names,
            "existing_assignment_count": len(fixed_names),
        })
    source_label = (
        "the existing draft shifts"
        if source_mode == "existing"
        else f'template "{template_name}"'
    )
    summary = (
        f"Built a draft proposal from {source_label}: {metrics['filled_positions']} of "
        f"{metrics['required_positions']} positions filled across {metrics['shift_count']} shifts"
        f"; {metrics['open_positions']} position(s) remain open."
    )
    # Never the word "compliant": positions filled says nothing about whether
    # the doors are covered at open, whether the close is staffed, or whether
    # anyone can be relieved for a legally required break. Saying what still
    # needs review is the honest ending; saying the week is compliant is a
    # claim this planner is not in a position to make.
    summary += _coverage_sentence(metrics)
    return {
        "summary": summary,
        "schedule_preview": schedule_preview,
        "preview_truncated": len(plan["shifts"]) > len(schedule_preview),
    }


def _overlaps(left: tuple[datetime, datetime], right: tuple[datetime, datetime]) -> bool:
    return left[0] < right[1] and left[1] > right[0]


def _consecutive_day_count(days: set[date], candidate: date) -> int:
    combined = set(days)
    combined.add(candidate)
    before = candidate
    while before - timedelta(days=1) in combined:
        before -= timedelta(days=1)
    after = candidate
    while after + timedelta(days=1) in combined:
        after += timedelta(days=1)
    return (after - before).days + 1


def _min_rest_gap_hours(
    windows: list[tuple[datetime, datetime]], starts_at: datetime, ends_at: datetime,
) -> float | None:
    """Hours between this shift and the nearest NON-overlapping window the
    person already holds; None when they hold nothing adjacent. Overlaps are
    the overlap check's business, not a rest gap."""
    gaps = []
    for w_start, w_end in windows:
        if w_end <= starts_at:
            gaps.append((starts_at - w_end).total_seconds() / 3600.0)
        elif w_start >= ends_at:
            gaps.append((w_start - ends_at).total_seconds() / 3600.0)
    return min(gaps) if gaps else None


def _is_unavailable(employee_id: str, shift_date: date, ranges: dict[str, list[tuple[date, date]]]) -> bool:
    return any(start <= shift_date <= end for start, end in ranges.get(employee_id, []))


def _job_qualified(
    employee: dict[str, Any], job_id: str | None, shift_date: date,
    gated_job_ids: set[str],
) -> bool:
    """Whether this employee may work a shift carrying ``job_id``.

    An EMPTY roster means ungated, matching
    ``routes/employee_schedule/_shared.check_job_qualification`` and
    ``schedule_profiles.fetch_effective_job_employee_ids``. Without it, the
    first whole-week build on a tenant that defined jobs but has not filled in
    the qualified lists (a separate tab, and the common state) reports every
    position open — and `apply_week_draft`'s recheck, which uses the shared
    helper, would then disagree with the plan it is confirming.
    """
    if not job_id or job_id not in gated_job_ids:
        return True
    for job in employee.get("jobs") or []:
        if job["job_id"] != job_id or job["qualification_status"] != "active":
            continue
        if job.get("qualified_from") and shift_date < job["qualified_from"]:
            continue
        if job.get("qualified_until") and shift_date > job["qualified_until"]:
            continue
        return True
    return False


def _candidate_reason(employee: dict[str, Any], before_minutes: int, after_minutes: int) -> str:
    target = employee.get("target_weekly_minutes")
    if target is not None:
        return (
            f"Available and qualified; moves from {before_minutes / 60:g}h "
            f"to {after_minutes / 60:g}h toward a {target / 60:g}h target."
        )
    return f"Available and qualified; scheduled hours become {after_minutes / 60:g}h."


def build_plan(
    *, demand: list[dict[str, Any]], employees: list[dict[str, Any]],
    availability: dict[str, dict[int, list[tuple[time, time]]]],
    existing_assignments: list[dict[str, Any]],
    unavailable_ranges: dict[str, list[tuple[date, date]]],
    exclude_employee_ids: set[str], employee_hour_caps: dict[str, int],
    gated_job_ids: set[str],
    blocked_pairs: set[tuple[str, str]] | None = None,
    allow_split_shift: bool = False,
    adjacent_assignments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Pure, deterministic scarcity-first assignment planner.

    Policy guardrails (operational defaults, not statute — see
    `assignment_guard`): one shift per person per day unless the manager
    asked for splits (`allow_split_shift`), at least `POLICY_MIN_REST_HOURS`
    between a person's shifts, and `POLICY_MAX_CONSECUTIVE_DAYS` when the
    profile sets no `max_consecutive_days`. They are hard skips here, with a
    `policy:`-prefixed reason in `unfilled.exclusions`, because a planner
    that stacks the only qualified lead onto every lead block is the failure
    this exists to stop. Among eligible candidates, fewer shifts this week
    wins before fewer minutes, so demand spreads across the roster.

    Existing assignments are fixed inputs.  Open slots are processed by the
    size of their feasible candidate pool, then by time/id; this prevents a
    flexible opener from consuming the only person who can cover a later
    licensed role.

    ``gated_job_ids`` is required rather than defaulted: an omitted set would
    silently mean "gate nothing", which is the opposite failure from the one
    this argument exists to fix and would be invisible until a real roster
    stopped being enforced.
    """
    blocked_pairs = blocked_pairs or set()
    by_id = {employee["id"]: employee for employee in employees}
    busy: dict[str, list[tuple[datetime, datetime]]] = defaultdict(list)
    minutes: dict[str, int] = defaultdict(int)
    scheduled_days: dict[str, set[date]] = defaultdict(set)
    shifts_by_day: dict[str, Counter] = defaultdict(Counter)
    shift_count: dict[str, int] = defaultdict(int)
    # Adjacent weeks affect rest and consecutive days, but never this week's
    # hours, target progress, or fairness score.
    for assignment in adjacent_assignments or []:
        employee_id = assignment["employee_id"]
        busy[employee_id].append((assignment["starts_at"], assignment["ends_at"]))
        scheduled_days[employee_id].add(assignment["starts_at"].date())
    for assignment in existing_assignments:
        employee_id = assignment["employee_id"]
        busy[employee_id].append((assignment["starts_at"], assignment["ends_at"]))
        minutes[employee_id] += assignment["worked_minutes"]
        scheduled_days[employee_id].add(assignment["starts_at"].date())
        shifts_by_day[employee_id][assignment["starts_at"].date()] += 1
        shift_count[employee_id] += 1

    def refusal(employee: dict[str, Any], shift: dict[str, Any]) -> str | None:
        employee_id = employee["id"]
        shift_key = shift["key"]
        shift_date = shift["starts_at"].date()
        if employee_id in exclude_employee_ids:
            return "manager exclusion"
        if (shift_key, employee_id) in blocked_pairs:
            return "compliance or eligibility block"
        if employee.get("availability_state") == "unconfirmed":
            return "availability unconfirmed"
        if not _job_qualified(employee, shift.get("job_id"), shift_date, gated_job_ids):
            return "not qualified for the shift job"
        if _is_unavailable(employee_id, shift_date, unavailable_ranges):
            return "approved time away"
        if availability_violations(
            availability.get(employee_id, {}), shift["starts_at"], shift["ends_at"],
        ):
            return "outside confirmed availability"
        if any(_overlaps(window, (shift["starts_at"], shift["ends_at"])) for window in busy[employee_id]):
            return "overlapping assignment"
        if not allow_split_shift and shifts_by_day[employee_id][shift_date] >= POLICY_MAX_SHIFTS_PER_DAY:
            return "policy: second shift that day"
        rest_windows = busy[employee_id]
        if allow_split_shift:
            # The manager allowed doubles: the rest rule still holds between
            # DAYS, not between the two halves of the split day they asked for.
            rest_windows = [window for window in rest_windows if window[0].date() != shift_date]
        rest_gap = _min_rest_gap_hours(rest_windows, shift["starts_at"], shift["ends_at"])
        if rest_gap is not None and rest_gap < POLICY_MIN_REST_HOURS:
            return f"policy: less than {POLICY_MIN_REST_HOURS:g}h rest"
        max_days = employee.get("max_consecutive_days")
        if max_days is None:
            max_days = POLICY_MAX_CONSECUTIVE_DAYS
        if _consecutive_day_count(scheduled_days[employee_id], shift_date) > max_days:
            return "maximum consecutive days"
        new_minutes = minutes[employee_id] + shift["worked_minutes"]
        explicit_cap = employee_hour_caps.get(employee_id)
        stored_cap = employee.get("max_weekly_minutes")
        cap = min(value for value in (explicit_cap, stored_cap) if value is not None) \
            if explicit_cap is not None or stored_cap is not None else None
        if cap is not None and new_minutes > cap:
            return "weekly hour cap"
        if not employee.get("allow_overtime") and new_minutes > 2400:
            return "overtime not allowed"
        return None

    def candidate_score(employee: dict[str, Any], shift: dict[str, Any]) -> tuple[Any, ...]:
        employee_id = employee["id"]
        before = minutes[employee_id]
        after = minutes[employee_id] + shift["worked_minutes"]
        target = employee.get("target_weekly_minutes")
        if target is None:
            target = employee.get("min_weekly_minutes")
        target_overshoot = max(0, after - target) if target is not None else 0
        target_shortfall = max(0, target - before) if target is not None else 0
        extra_hours_bonus = -1 if employee.get("prefer_extra_hours") else 0
        return (
            target_overshoot,
            -target_shortfall,
            extra_hours_bonus,
            shift_count[employee_id],
            minutes[employee_id],
            employee.get("name") or "",
            employee_id,
        )

    slots: list[tuple[dict[str, Any], int]] = []
    fixed_by_shift: dict[str, set[str]] = {}
    for shift in demand:
        fixed = {str(employee_id) for employee_id in shift.get("fixed_employee_ids") or []}
        fixed_by_shift[shift["key"]] = fixed
        for index in range(max(0, int(shift["required_staff"]) - len(fixed))):
            slots.append((shift, index))

    def static_candidate_count(item: tuple[dict[str, Any], int]) -> tuple[Any, ...]:
        shift, index = item
        count = sum(
            1 for employee in employees
            if employee["id"] not in fixed_by_shift[shift["key"]]
            and refusal(employee, shift) is None
        )
        return count, shift["starts_at"], shift["key"], index

    slots.sort(key=static_candidate_count)
    proposed_by_shift: dict[str, list[dict[str, Any]]] = defaultdict(list)
    unfilled: list[dict[str, Any]] = []
    for shift, _slot_index in slots:
        already = fixed_by_shift[shift["key"]] | {
            item["employee_id"] for item in proposed_by_shift[shift["key"]]
        }
        reasons = Counter()
        candidates = []
        for employee in employees:
            if employee["id"] in already:
                continue
            reason = refusal(employee, shift)
            if reason:
                reasons[reason] += 1
            else:
                candidates.append(employee)
        if not candidates:
            unfilled.append({
                "shift_key": shift["key"],
                "starts_at": shift["starts_at"].isoformat(),
                "role": shift.get("role"),
                "reason": reasons.most_common(1)[0][0] if reasons else "no eligible employees",
                "exclusions": dict(sorted(reasons.items())),
            })
            continue
        candidates.sort(key=lambda employee: candidate_score(employee, shift))
        chosen = candidates[0]
        employee_id = chosen["id"]
        before = minutes[employee_id]
        after = before + shift["worked_minutes"]
        proposed_by_shift[shift["key"]].append({
            "employee_id": employee_id,
            "employee_name": chosen.get("name"),
            "reason": _candidate_reason(chosen, before, after),
        })
        busy[employee_id].append((shift["starts_at"], shift["ends_at"]))
        minutes[employee_id] = after
        scheduled_days[employee_id].add(shift["starts_at"].date())
        shifts_by_day[employee_id][shift["starts_at"].date()] += 1
        shift_count[employee_id] += 1

    proposal_shifts = []
    for shift in sorted(demand, key=lambda item: (item["starts_at"], item["key"])):
        proposal_shifts.append({
            **{key: _iso(value) for key, value in shift.items() if key != "fixed_employee_ids"},
            "fixed_employee_ids": sorted(fixed_by_shift[shift["key"]]),
            "proposed_assignments": proposed_by_shift.get(shift["key"], []),
        })
    required_positions = sum(int(shift["required_staff"]) for shift in demand)
    fixed_positions = sum(
        min(len(shift.get("fixed_employee_ids") or []), int(shift["required_staff"]))
        for shift in demand
    )
    overstaffed_positions = sum(
        max(0, len(shift.get("fixed_employee_ids") or []) - int(shift["required_staff"]))
        for shift in demand
    )
    proposed_positions = sum(len(items) for items in proposed_by_shift.values())
    return {
        "shifts": proposal_shifts,
        "unfilled": unfilled,
        "hours_by_employee": {
            employee_id: minutes[employee_id] for employee_id in sorted(by_id)
        },
        "metrics": {
            "shift_count": len(demand),
            "required_positions": required_positions,
            "fixed_positions": fixed_positions,
            "overstaffed_positions": overstaffed_positions,
            "proposed_positions": proposed_positions,
            "filled_positions": fixed_positions + proposed_positions,
            "open_positions": len(unfilled),
        },
    }


async def _preflight_compliance_blocks(
    conn, *, company_id: UUID, location_id: UUID, plan: dict[str, Any],
) -> set[tuple[str, str]]:
    """Return selected employee/shift pairs that hit a current hard block.

    The planner handles availability, qualifications, conflicts, time away,
    hour caps, and consecutive days in memory. This pass adds the shared
    statutory/credential eligibility gate before a manager sees the proposal.
    Application still repeats the same check under row locks.
    """
    blocked: set[tuple[str, str]] = set()
    for shift in plan.get("shifts") or []:
        for assignment in shift.get("proposed_assignments") or []:
            try:
                violations = await check_shift_compliance(
                    conn, company_id,
                    location_id=location_id,
                    job_id=UUID(shift["job_id"]) if shift.get("job_id") else None,
                    starts_at=datetime.fromisoformat(shift["starts_at"]),
                    ends_at=datetime.fromisoformat(shift["ends_at"]),
                    break_minutes=int(shift.get("break_minutes") or 0),
                    employee_id=UUID(assignment["employee_id"]),
                    exclude_shift_id=(
                        UUID(shift["source_shift_id"])
                        if shift.get("source_shift_id") else None
                    ),
                    shift_kind=shift.get("kind") or "work",
                    training_requirement_id=(
                        UUID(shift["training_requirement_id"])
                        if shift.get("training_requirement_id") else None
                    ),
                    lapse_items=[],
                )
            except Exception:
                # Application performs the authoritative locked recheck. A
                # transient preview failure should stay visible in logs, not
                # make the whole scheduling assistant unusable.
                logger.exception(
                    "week builder compliance preflight failed for shift %s employee %s",
                    shift.get("key"), assignment.get("employee_id"),
                )
                continue
            if any(item.get("severity") == "block" for item in violations):
                blocked.add((shift["key"], assignment["employee_id"]))
    return blocked


def _trim_thin_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Cap the per-day `break_relief_thin` advisories in the LIST only.

    The counts are taken before this runs, so the card stays readable while
    `finding_counts` still reports every shift that has no spare cover. Trimming
    before counting would make a week look cleaner the busier it is.
    """
    kept: list[dict[str, Any]] = []
    seen: Counter = Counter()
    for finding in findings:
        if finding.get("kind") != "break_relief_thin":
            kept.append(finding)
            continue
        day = finding.get("day")
        seen[day] += 1
        if seen[day] <= _MAX_THIN_BREAK_FINDINGS_PER_DAY:
            kept.append(finding)
    return kept


def _cap_findings(
    findings: list[dict[str, Any]], limit: int = _MAX_FINDINGS,
) -> list[dict[str, Any]]:
    """Bound a findings list without letting the cap decide by calendar order.

    The list arrives sorted day-then-time, so a plain slice drops Saturday's
    real holes to make room for Sunday's advisories. Gaps are what the manager
    has to act on, so they claim the budget first; the kept set is re-sorted so
    the card still reads in day order.

    Used at every boundary that truncates — the persisted list, the shorter one
    returned to the model, and readiness `pattern_findings` — because a slice at
    any of them buries the same holes.
    """
    if len(findings) <= limit:
        return list(findings)
    gaps = [item for item in findings if item.get("kind") in GAP_KINDS]
    rest = [item for item in findings if item.get("kind") not in GAP_KINDS]
    kept = gaps[:limit]
    kept.extend(rest[:limit - len(kept)])
    return sort_findings(kept)


def _break_relief_finding(
    *, code: str, shift: dict[str, Any], day: date, assigned: int,
    employee_name: str | None, duration: int, reason: str | None,
) -> dict[str, Any] | None:
    """Turn one stagger outcome into a manager-facing finding.

    The stagger engine's own vocabulary is about placement; a manager cares
    about the floor. The split between "solo" and "thin" is the whole point:
    on a one-person shift the break leaves NOBODY on, which is a hole; on a
    three-person shift it is a dip worth knowing about and nothing more.
    """
    window = (
        datetime.fromisoformat(shift["starts_at"]),
        datetime.fromisoformat(shift["ends_at"]),
    )
    who = employee_name or "the person on"
    common = {
        "day": day, "window": window, "shift_key": shift.get("key"),
        "job_id": shift.get("job_id"), "job_name": shift.get("role"),
        "employee_name": employee_name,
    }
    if code == "coverage_shortfall" and assigned <= 1:
        return make_finding(
            "break_relief_uncovered", "gap",
            f"Nobody can relieve {who} for their {duration}-minute break on this shift, "
            f"so the floor is empty while they take it.",
            minutes=duration, **common,
        )
    if code == "coverage_shortfall":
        return make_finding(
            "break_relief_thin", "advisory",
            f"This shift has no spare cover, so the floor drops to {assigned - 1} "
            f"while each break is taken.",
            minutes=duration, **common,
        )
    if code == "insufficient_coverage":
        return make_finding(
            "break_relief_impossible", "gap",
            reason or "A required break cannot be scheduled on this shift without "
                      "dropping coverage further.",
            minutes=duration, **common,
        )
    if code == "deadline_conflict":
        return make_finding(
            "break_window_conflict", "advisory",
            reason or "A required break does not fit inside its legal window on this shift.",
            minutes=duration, **common,
        )
    if code == "unresolved":
        return make_finding(
            "break_rules_unresolved", "advisory",
            f"A required {duration}-minute break for {who} could not be evaluated on "
            f"this shift. "
            + (reason or "Break requirements could not be resolved; verify manually."),
            minutes=duration, **common,
        )
    return None


async def _break_relief_findings(
    conn, *, company_id: UUID, location_id: UUID, plan: dict[str, Any],
    employee_names: dict[str, str],
) -> list[dict[str, Any]]:
    """Can the crew actually be relieved for the breaks the law requires?

    The planner fills headcount and stops. A shift staffed to exactly its
    requirement has nobody spare, so every legally required break either drops
    the floor below that requirement or does not happen — and a proposal that
    reports 20/20 while hiding that is the failure this pass exists to catch.

    Runs on the IN-MEMORY plan: `stagger_shift_breaks` is pure and needs no
    shift row, so nothing has to be written before the manager can see it.
    Break rules themselves come from the compliance catalog, never from here.

    Never raises — same contract as `_preflight_compliance_blocks`. A findings
    pass that could fail a build would be worse than the silence it replaces.
    """
    try:
        by_key: dict[str, dict[str, Any]] = {}
        windows: list[tuple[str, datetime, datetime, list[UUID]]] = []
        for shift in plan.get("shifts") or []:
            employee_ids = [
                *(shift.get("fixed_employee_ids") or []),
                *(
                    assignment["employee_id"]
                    for assignment in shift.get("proposed_assignments") or []
                ),
            ]
            if not employee_ids:
                # An unstaffed slot is already reported as an open position;
                # there is no break to relieve.
                continue
            by_key[shift["key"]] = shift
            windows.append((
                shift["key"],
                datetime.fromisoformat(shift["starts_at"]),
                datetime.fromisoformat(shift["ends_at"]),
                [UUID(str(value)) for value in employee_ids],
            ))
        if not windows:
            return []

        location_timezone, plans_by_shift, unmapped_dates = await resolve_week_break_plans(
            conn, company_id, location_id=location_id, shifts=windows,
        )

        findings: list[dict[str, Any]] = []
        for key, starts_at, ends_at, employee_ids in windows:
            per_employee = plans_by_shift.get(key) or {}
            assignments = [
                StaggerAssignment(employee_id=employee_id, plan=per_employee[employee_id])
                for employee_id in employee_ids if employee_id in per_employee
            ]
            if not assignments:
                continue
            shift = by_key[key]
            stagger = stagger_shift_breaks(
                shift_start_local=reinterpret_schedule_wall_time(starts_at, location_timezone),
                shift_end_local=reinterpret_schedule_wall_time(ends_at, location_timezone),
                required_staff=int(shift.get("required_staff") or 0),
                assignments=assignments,
            )
            day = starts_at.date()
            assigned = len(assignments)
            duration = max(
                (result.duration_minutes for result in stagger.results), default=0,
            )
            solo_name = (
                employee_names.get(str(employee_ids[0])) if assigned == 1 else None
            )
            if any(item.get("code") == "coverage_shortfall" for item in stagger.advisories):
                finding = _break_relief_finding(
                    code="coverage_shortfall", shift=shift, day=day, assigned=assigned,
                    employee_name=solo_name, duration=duration, reason=None,
                )
                if finding:
                    findings.append(finding)
            # A plan that never resolved yields `unresolved` results and NO
            # placed slot, which silences the coverage advisories above — so a
            # solo shift owing a meal break, worked by somebody with no date of
            # birth on file against age-specific rules, would otherwise report
            # nothing at all. One per person per shift; a whole date being
            # unmapped is already said once by `break_rules_unmapped` below.
            unresolved_seen: set[UUID] = set()
            for result in stagger.results:
                if result.status == "unresolved":
                    if day in unmapped_dates or result.employee_id in unresolved_seen:
                        continue
                    unresolved_seen.add(result.employee_id)
                    finding = _break_relief_finding(
                        code="unresolved", shift=shift, day=day, assigned=assigned,
                        employee_name=employee_names.get(str(result.employee_id)),
                        duration=result.duration_minutes, reason=result.reason,
                    )
                    if finding:
                        findings.append(finding)
                    continue
                if result.status not in ("insufficient_coverage", "deadline_conflict"):
                    continue
                finding = _break_relief_finding(
                    code=result.status, shift=shift, day=day, assigned=assigned,
                    employee_name=employee_names.get(str(result.employee_id)),
                    duration=result.duration_minutes, reason=result.reason,
                )
                if finding:
                    findings.append(finding)

        if unmapped_dates:
            dates = ", ".join(value.isoformat() for value in sorted(unmapped_dates))
            findings.append(make_finding(
                "break_rules_unmapped", "advisory",
                f"Break rules could not be resolved for this location on {dates}; "
                f"break coverage on those days was not checked.",
            ))
        return findings
    except Exception:
        logger.exception(
            "week builder break-relief pass failed for location %s", location_id,
        )
        return []


async def _load_roster_context(conn, *, company_id: UUID, location_id: UUID,
                               week_start: date) -> dict[str, Any]:
    week_end = week_start + timedelta(days=6)
    employees_rows = await conn.fetch(
        """
        SELECT e.id, e.first_name, e.last_name, e.job_title,
               COALESCE(p.availability_state, 'unconfirmed') AS availability_state,
               p.min_weekly_minutes, p.target_weekly_minutes, p.max_weekly_minutes,
               p.max_consecutive_days, COALESCE(p.allow_overtime, false) AS allow_overtime,
               COALESCE(p.prefer_extra_hours, false) AS prefer_extra_hours
        FROM employees e
        LEFT JOIN employee_schedule_profiles p
          ON p.employee_id=e.id AND p.company_id=e.org_id
        WHERE e.org_id=$1 AND e.work_location_id=$2
          AND COALESCE(e.employment_status, 'active') NOT IN ('terminated','offboarded')
        ORDER BY e.first_name, e.last_name, e.id
        LIMIT $3
        """,
        company_id, location_id, _MAX_ROSTER,
    )
    employees = []
    for row in employees_rows:
        item = dict(row)
        item["id"] = str(item["id"])
        item["name"] = " ".join(filter(None, [item.pop("first_name"), item.pop("last_name")]))
        item["jobs"] = []
        employees.append(item)
    employee_ids = [UUID(employee["id"]) for employee in employees]
    jobs = await conn.fetch(
        """
        SELECT employee_id, job_id, qualification_status, qualified_from, qualified_until
        FROM schedule_job_employees
        WHERE company_id=$1 AND employee_id=ANY($2::uuid[])
        ORDER BY employee_id, job_id
        """,
        company_id, employee_ids,
    ) if employee_ids else []
    employees_by_id = {employee["id"]: employee for employee in employees}
    for row in jobs:
        employees_by_id[str(row["employee_id"])]["jobs"].append({
            "job_id": str(row["job_id"]),
            "qualification_status": row["qualification_status"],
            "qualified_from": row["qualified_from"],
            "qualified_until": row["qualified_until"],
        })

    availability_raw = await fetch_availability(conn, company_id, employee_ids)
    availability = {str(key): value for key, value in availability_raw.items()}
    for windows_by_day in availability.values():
        for windows in windows_by_day.values():
            windows.sort(key=lambda window: (window[0], window[1]))
    lo = datetime.combine(week_start, time.min, tzinfo=timezone.utc)
    hi = lo + timedelta(days=7)
    context_days = max(
        [POLICY_MAX_CONSECUTIVE_DAYS]
        + [employee.get("max_consecutive_days") or POLICY_MAX_CONSECUTIVE_DAYS for employee in employees]
    )
    assignment_rows = await conn.fetch(
        """
        SELECT a.employee_id, s.id AS shift_id, s.starts_at, s.ends_at,
               s.break_minutes, s.location_id, s.status
        FROM schedule_shift_assignments a
        JOIN schedule_shifts s ON s.id=a.shift_id
        WHERE s.company_id=$1 AND s.status <> 'cancelled'
          AND s.starts_at < $3 AND s.ends_at > $2
          AND (a.employee_id = ANY($4::uuid[]) OR (s.starts_at < $6 AND s.ends_at > $5))
        ORDER BY s.starts_at, s.id, a.employee_id
        """,
        company_id, lo - timedelta(days=context_days), hi + timedelta(days=context_days),
        employee_ids, lo, hi,
    )
    all_assignments = [{
        "employee_id": str(row["employee_id"]),
        "shift_id": str(row["shift_id"]),
        "starts_at": row["starts_at"], "ends_at": row["ends_at"],
        "worked_minutes": max(
            0, int((row["ends_at"] - row["starts_at"]).total_seconds() // 60)
            - int(row["break_minutes"] or 0),
        ),
        "location_id": str(row["location_id"]) if row["location_id"] else None,
        "status": row["status"],
    } for row in assignment_rows]
    existing_assignments = [
        item for item in all_assignments if item["starts_at"] < hi and item["ends_at"] > lo
    ]
    adjacent_assignments = [
        item for item in all_assignments
        if item["employee_id"] in employees_by_id
        and not (item["starts_at"] < hi and item["ends_at"] > lo)
    ]

    unavailable: dict[str, list[tuple[date, date]]] = defaultdict(list)
    request_rows = await conn.fetch(
        """
        SELECT employee_id, unavailable_start AS start_date, unavailable_end AS end_date
        FROM schedule_requests
        WHERE company_id=$1 AND request_type='unavailable' AND status='approved'
          AND unavailable_start <= $3 AND unavailable_end >= $2
        UNION ALL
        SELECT p.employee_id, p.start_date, p.end_date
        FROM pto_requests p JOIN employees e ON e.id=p.employee_id
        WHERE e.org_id=$1 AND p.status='approved' AND p.start_date <= $3 AND p.end_date >= $2
        UNION ALL
        SELECT l.employee_id, l.start_date, COALESCE(l.end_date, l.expected_return_date, $3)
        FROM leave_requests l
        WHERE l.org_id=$1 AND l.status IN ('approved','active')
          AND l.start_date <= $3 AND COALESCE(l.end_date, l.expected_return_date, $3) >= $2
        """,
        company_id, week_start, week_end,
    )
    for row in request_rows:
        unavailable[str(row["employee_id"])].append((row["start_date"], row["end_date"]))
    for ranges in unavailable.values():
        ranges.sort()
    # Jobs somebody has been named qualified for, company-wide — the same
    # EXISTS check `_shared.check_job_qualification` does, and deliberately not
    # filtered to this location: a job whose roster lives at another store is
    # still opted into gating.
    gated_rows = await conn.fetch(
        "SELECT DISTINCT job_id FROM schedule_job_employees WHERE company_id=$1",
        company_id,
    )
    return {
        "employees": employees,
        "availability": availability,
        "existing_assignments": existing_assignments,
        "adjacent_assignments": adjacent_assignments,
        "unavailable_ranges": dict(unavailable),
        "gated_job_ids": {str(row["job_id"]) for row in gated_rows},
    }


async def _coverage_profile(conn, *, company_id: UUID, location_id: UUID) -> dict[str, Any]:
    """The profile fields the coverage evaluator needs, plus the leaders' names.

    The leader jobs' NAMES cost one extra fetch and are what make a finding
    readable ("No Shift Lead or Assistant Manager is scheduled at open")
    instead of uuids. An id that no longer resolves to a job is dropped: the
    FK on the mirror column nulls itself on job delete, but nothing can do
    that inside the array, and a rule naming only a deleted job is no rule.
    """
    profile = await get_location_profile(
        conn, company_id=company_id, location_id=location_id,
    ) or {}
    leader_ids = profile_leader_job_ids(profile)
    names_by_id: dict[str, str] = {}
    if leader_ids:
        rows = await conn.fetch(
            "SELECT id, name FROM schedule_jobs WHERE company_id=$1 AND id = ANY($2::uuid[])",
            company_id, leader_ids,
        )
        names_by_id = {str(row["id"]): row["name"] for row in rows}
    leader_job_ids = [str(job_id) for job_id in leader_ids if str(job_id) in names_by_id]
    return {
        "operating_hours": profile.get("operating_hours") or {},
        "open_buffer_minutes": int(profile.get("open_buffer_minutes") or 0),
        "close_buffer_minutes": int(profile.get("close_buffer_minutes") or 0),
        "leader_job_ids": leader_job_ids,
        "leader_job_names": [names_by_id[job_id] for job_id in leader_job_ids],
    }


async def _week_rules_gate(
    conn, *, company_id: UUID, location_id: UUID, location_name: str | None = None,
) -> dict[str, Any] | None:
    """`None` when this location's week-set rules are established, else the
    clarify to return INSTEAD of planning a week.

    Runs before demand resolution on purpose: draft shifts are demand, not
    bounds. A store with two stray drafts and no saved hours used to produce a
    full week that nothing had checked — `operating_hours_known=false` said so
    in the metrics and nobody reads metrics.
    """
    if location_name is None:
        location_name = await conn.fetchval(
            "SELECT name FROM business_locations WHERE id=$1 AND company_id=$2",
            location_id, company_id,
        ) or "This location"
    bundle = await load_profile_bundle(
        conn, company_id=company_id, location_id=location_id,
    )
    message = week_rules_refusal(bundle, location_name=location_name)
    if message is None:
        return None
    return {
        "status": "clarify",
        "message": message,
        "setup_missing": missing_fields(bundle),
    }


async def _attach_findings(
    conn, *, company_id: UUID, location_id: UUID, week_start: date,
    plan: dict[str, Any], snapshot: dict[str, Any],
) -> None:
    """Add `findings` and the finding metrics to a built plan, in place.

    Never raises — same contract as `_break_relief_findings`, which only
    covered its own half. The profile read and the coverage evaluator are on
    the same path, so an error there used to turn a week that built fine into
    a failed Huume turn. The fallback metrics say coverage was NOT checked
    (`_coverage_sentence` reads them), never that the week came back clean.
    """
    plan["findings"] = []
    plan["metrics"]["finding_counts"] = {}
    plan["metrics"]["gap_count"] = 0
    plan["metrics"]["operating_hours_known"] = False
    try:
        await _attach_findings_core(
            conn, company_id=company_id, location_id=location_id,
            week_start=week_start, plan=plan, snapshot=snapshot,
        )
    except Exception:
        logger.exception(
            "week builder findings pass failed for location %s", location_id,
        )


async def _attach_findings_core(
    conn, *, company_id: UUID, location_id: UUID, week_start: date,
    plan: dict[str, Any], snapshot: dict[str, Any],
) -> None:
    profile = await _coverage_profile(
        conn, company_id=company_id, location_id=location_id,
    )
    hours = profile["operating_hours"]
    coverage = evaluate_week_coverage(
        plan_shifts=plan["shifts"],
        # A half-published week (the common state: the manager published
        # Monday–Wednesday and wants the rest filled) already has a floor.
        # Judging the proposal alone would report those days as empty.
        baseline_shifts=[
            shift for shift in snapshot.get("week_shift_state") or []
            if shift.get("status") == "published"
        ],
        operating_hours=hours,
        open_buffer_minutes=profile["open_buffer_minutes"],
        close_buffer_minutes=profile["close_buffer_minutes"],
        leader_job_ids=profile["leader_job_ids"],
        leader_job_names=profile["leader_job_names"],
        week_start=week_start,
    )
    breaks = await _break_relief_findings(
        conn, company_id=company_id, location_id=location_id, plan=plan,
        employee_names={
            employee["id"]: employee["name"] for employee in snapshot["employees"]
        },
    )
    all_findings = sort_findings([*coverage, *breaks])
    counts = Counter(finding["kind"] for finding in all_findings)
    plan["findings"] = _cap_findings(_trim_thin_findings(all_findings))
    # A plain dict, not the Counter: `metrics` is its own JSONB column and
    # json.dumps has no Counter branch that survives a round trip cleanly.
    plan["metrics"]["finding_counts"] = dict(sorted(counts.items()))
    plan["metrics"]["gap_count"] = sum(
        1 for finding in all_findings if finding["kind"] in GAP_KINDS
    )
    plan["metrics"]["operating_hours_known"] = bool(hours)


async def _load_existing_demand(conn, *, company_id: UUID, location_id: UUID,
                                week_start: date) -> list[dict[str, Any]]:
    lo = datetime.combine(week_start, time.min, tzinfo=timezone.utc)
    hi = lo + timedelta(days=7)
    rows = await conn.fetch(
        """
        SELECT s.id, s.role, s.department, s.starts_at, s.ends_at,
               s.break_minutes, s.required_staff, s.color, s.notes, s.kind,
               s.template_id, s.job_id, s.training_requirement_id,
               COALESCE(array_agg(a.employee_id ORDER BY a.employee_id)
                        FILTER (WHERE a.employee_id IS NOT NULL), ARRAY[]::uuid[]) AS employee_ids
        FROM schedule_shifts s
        LEFT JOIN schedule_shift_assignments a ON a.shift_id=s.id
        WHERE s.company_id=$1 AND s.location_id=$2 AND s.status='draft'
          AND s.starts_at >= $3 AND s.starts_at < $4
        GROUP BY s.id ORDER BY s.starts_at, s.id
        LIMIT $5
        """,
        company_id, location_id, lo, hi, _MAX_DEMAND_SHIFTS,
    )
    return [{
        "key": str(row["id"]), "source_shift_id": str(row["id"]),
        "role": row["role"], "department": row["department"],
        "starts_at": row["starts_at"], "ends_at": row["ends_at"],
        "break_minutes": row["break_minutes"] or 0,
        "required_staff": row["required_staff"], "color": row["color"],
        "notes": row["notes"], "kind": row["kind"],
        "template_id": str(row["template_id"]) if row["template_id"] else None,
        "job_id": str(row["job_id"]) if row["job_id"] else None,
        "training_requirement_id": str(row["training_requirement_id"]) if row["training_requirement_id"] else None,
        "fixed_employee_ids": [str(employee_id) for employee_id in row["employee_ids"]],
        "worked_minutes": max(
            0, int((row["ends_at"] - row["starts_at"]).total_seconds() // 60)
            - int(row["break_minutes"] or 0),
        ),
    } for row in rows]


async def _load_vacant_demand(
    conn, *, company_id: UUID, location_id: UUID, week_start: date,
    week_end: date | None = None, job_ids: list[UUID] | None = None,
    shift_ids: list[UUID] | None = None, role_ilike: str | None = None,
    statuses: tuple[str, ...] = ("draft", "published"),
) -> list[dict[str, Any]]:
    """Existing shifts in the week with an OPEN seat, as planner demand
    (same shape as `_load_existing_demand`; current assignees ride as
    `fixed_employee_ids`). Drafts AND published — an assignment onto a
    published shift is a routine edit (`_apply_edit_ops` does it today), and
    a store's open published shifts are exactly what "fill the vacant ones"
    means."""
    lo = datetime.combine(week_start, time.min, tzinfo=timezone.utc)
    hi = datetime.combine(week_end + timedelta(days=1), time.min, tzinfo=timezone.utc) if week_end else lo + timedelta(days=7)
    rows = await conn.fetch(
        """
        SELECT s.id, s.role, s.department, s.starts_at, s.ends_at,
               s.break_minutes, s.required_staff, s.color, s.notes, s.kind,
               s.template_id, s.job_id, s.training_requirement_id,
               COALESCE(array_agg(a.employee_id ORDER BY a.employee_id)
                        FILTER (WHERE a.employee_id IS NOT NULL), ARRAY[]::uuid[]) AS employee_ids
        FROM schedule_shifts s
        LEFT JOIN schedule_shift_assignments a ON a.shift_id=s.id
        WHERE s.company_id=$1 AND s.location_id=$2 AND s.status = ANY($3::text[])
          AND s.starts_at >= $4 AND s.starts_at < $5
          AND ($6::uuid[] IS NULL OR s.job_id = ANY($6::uuid[]))
          AND ($7::uuid[] IS NULL OR s.id = ANY($7::uuid[]))
          AND ($8::text IS NULL OR s.role ILIKE '%' || $8 || '%')
        GROUP BY s.id
        HAVING COUNT(a.employee_id) < COALESCE(s.required_staff, 1)
        ORDER BY s.starts_at, s.id
        LIMIT $9
        """,
        company_id, location_id, list(statuses), lo, hi,
        job_ids or None, shift_ids or None, role_ilike, _MAX_DEMAND_SHIFTS,
    )
    return [{
        "key": str(row["id"]), "source_shift_id": str(row["id"]),
        "role": row["role"], "department": row["department"],
        "starts_at": row["starts_at"], "ends_at": row["ends_at"],
        "break_minutes": row["break_minutes"] or 0,
        "required_staff": row["required_staff"], "color": row["color"],
        "notes": row["notes"], "kind": row["kind"],
        "template_id": str(row["template_id"]) if row["template_id"] else None,
        "job_id": str(row["job_id"]) if row["job_id"] else None,
        "training_requirement_id": str(row["training_requirement_id"]) if row["training_requirement_id"] else None,
        "fixed_employee_ids": [str(employee_id) for employee_id in row["employee_ids"]],
        "worked_minutes": max(
            0, int((row["ends_at"] - row["starts_at"]).total_seconds() // 60)
            - int(row["break_minutes"] or 0),
        ),
    } for row in rows]


async def plan_vacant_fill(
    conn, *, company_id: UUID, location_id: UUID, week_start: date,
    week_end: date | None = None, job_ids: list[UUID] | None = None,
    role_hint: str | None = None, shift_ids: list[UUID] | None = None,
    only_employee_ids: list[UUID] | None = None,
    exclude_employee_ids: list[UUID] | None = None,
    allow_split_shift: bool = False,
) -> dict[str, Any]:
    """Server-side "fill the open shifts": the same deterministic planner the
    week builder uses (`build_plan` + the compliance preflight), pointed at
    the week's OPEN seats instead of a template, with NO week-rules gate —
    the demand is the shifts that already exist, so the store's hours and
    pattern are irrelevant. Nothing is persisted here: the caller turns
    `assignments` into an edit proposal (thread Huume / the REST preview),
    which is what makes a preview a free simulation.

    `only_employee_ids` narrows the roster to the people named ("fill them
    with Dana") — the planner then refuses, per slot and with a reason, the
    ones that person cannot lawfully or sensibly take, instead of the model
    multiplying one name across every shift."""
    role_ilike = None
    if role_hint and (role_hint or "").strip():
        matched = await resolve_job_by_name(conn, company_id, role_hint.strip(), location_id=location_id)
        if matched:
            job_ids = list(job_ids or []) + [matched["id"]]
        else:
            role_ilike = role_hint.strip()
    demand = await _load_vacant_demand(
        conn, company_id=company_id, location_id=location_id, week_start=week_start,
        week_end=week_end, job_ids=job_ids, shift_ids=shift_ids, role_ilike=role_ilike,
    )
    jurisdiction = jurisdiction_message(
        await jurisdiction_rule_status(conn, company_id, location_id),
    )
    if not demand:
        scope = f" matching \"{role_hint}\"" if role_hint else ""
        return {
            "status": "clarify",
            "message": f"There are no open shifts{scope} in this week to fill.",
            "assignments": [], "unfilled": [], "jurisdiction": jurisdiction,
        }
    roster = await _load_roster_context(
        conn, company_id=company_id, location_id=location_id, week_start=week_start,
    )
    employees = roster["employees"]
    if only_employee_ids:
        keep = {str(value) for value in only_employee_ids}
        employees = [employee for employee in employees if employee["id"] in keep]
    if exclude_employee_ids:
        drop = {str(value) for value in exclude_employee_ids}
        employees = [employee for employee in employees if employee["id"] not in drop]
    if not employees:
        return {
            "status": "refused",
            "message": "No active employees at this location match that request.",
            "assignments": [], "unfilled": [], "jurisdiction": jurisdiction,
        }

    def _build(blocked_pairs: set[tuple[str, str]]) -> dict[str, Any]:
        return build_plan(
            demand=demand, employees=employees, availability=roster["availability"],
            existing_assignments=roster["existing_assignments"],
            adjacent_assignments=roster.get("adjacent_assignments", []),
            unavailable_ranges=roster["unavailable_ranges"],
            exclude_employee_ids=set(), employee_hour_caps={},
            gated_job_ids=roster["gated_job_ids"], blocked_pairs=blocked_pairs,
            allow_split_shift=allow_split_shift,
        )

    blocked_pairs: set[tuple[str, str]] = set()
    plan = _build(blocked_pairs)
    for _attempt in range(_MAX_COMPLIANCE_REPLANS):
        newly_blocked = await _preflight_compliance_blocks(
            conn, company_id=company_id, location_id=location_id, plan=plan,
        ) - blocked_pairs
        if not newly_blocked:
            break
        blocked_pairs.update(newly_blocked)
        plan = _build(blocked_pairs)

    by_key = {shift["key"]: shift for shift in demand}
    assignments = [
        {
            "shift_id": shift["key"], "role": shift.get("role"),
            "starts_at": shift["starts_at"], "ends_at": shift["ends_at"],
            "employee_id": item["employee_id"], "employee_name": item["employee_name"],
            "reason": item["reason"],
        }
        for shift in plan["shifts"]
        for item in shift.get("proposed_assignments") or []
    ]
    unfilled = [
        {
            "shift_id": item["shift_key"], "role": item.get("role"),
            "starts_at": item["starts_at"],
            "ends_at": _iso(by_key[item["shift_key"]]["ends_at"]) if item["shift_key"] in by_key else None,
            "reason": item["reason"], "exclusions": item.get("exclusions") or {},
        }
        for item in plan["unfilled"]
    ]
    return {
        "status": "ready",
        "assignments": assignments,
        "unfilled": unfilled,
        "hours_by_employee": plan["hours_by_employee"],
        "metrics": plan["metrics"],
        "roster_size": len(employees),
        "demand_size": len(demand),
        "jurisdiction": jurisdiction,
    }


def vacant_fill_edit_requests(assignments: list[dict[str, Any]]) -> tuple[list[dict], str | None]:
    """Adapt a server-selected fill without losing identities or the review cap."""
    if len(assignments) > MAX_BATCH_OPERATIONS:
        items = [BatchItem(day=date.fromisoformat(str(_iso(item["starts_at"]))[:10])) for item in assignments]
        return [], split_plan_message(len(items), plan_batches(items), MAX_BATCH_OPERATIONS)
    return [
        {"kind": "assign", "target_shift_id": str(item["shift_id"]),
         "to_employee_id": str(item["employee_id"]), "to_employee_name": item["employee_name"]}
        for item in assignments
    ], None


async def _week_shift_counts(conn, *, company_id: UUID, location_id: UUID,
                             week_start: date) -> dict[str, int]:
    lo = datetime.combine(week_start, time.min, tzinfo=timezone.utc)
    hi = lo + timedelta(days=7)
    row = await conn.fetchrow(
        """SELECT COUNT(*) FILTER (WHERE status='draft') AS draft_count,
                  COUNT(*) FILTER (WHERE status='published') AS published_count
             FROM schedule_shifts
            WHERE company_id=$1 AND location_id=$2
              AND starts_at >= $3 AND starts_at < $4""",
        company_id, location_id, lo, hi,
    )
    return {
        "draft": int(row["draft_count"] or 0),
        "published": int(row["published_count"] or 0),
    }


async def _load_week_shift_state(conn, *, company_id: UUID, location_id: UUID,
                                 week_start: date) -> list[dict[str, Any]]:
    """Return deterministic live week state for proposal staleness checks."""
    lo = datetime.combine(week_start, time.min, tzinfo=timezone.utc)
    hi = lo + timedelta(days=7)
    rows = await conn.fetch(
        """
        SELECT s.id, s.status, s.role, s.department, s.starts_at, s.ends_at,
               s.break_minutes, s.required_staff, s.color, s.notes, s.kind,
               s.template_id, s.job_id, s.training_requirement_id,
               COALESCE(array_agg(a.employee_id ORDER BY a.employee_id)
                        FILTER (WHERE a.employee_id IS NOT NULL), ARRAY[]::uuid[]) AS employee_ids
        FROM schedule_shifts s
        LEFT JOIN schedule_shift_assignments a ON a.shift_id=s.id
        WHERE s.company_id=$1 AND s.location_id=$2
          AND s.status IN ('draft', 'published')
          AND s.starts_at >= $3 AND s.starts_at < $4
        GROUP BY s.id
        ORDER BY s.starts_at, s.id
        """,
        company_id, location_id, lo, hi,
    )
    return [{
        "id": str(row["id"]), "status": row["status"], "role": row["role"],
        "department": row["department"], "starts_at": row["starts_at"],
        "ends_at": row["ends_at"], "break_minutes": row["break_minutes"] or 0,
        "required_staff": row["required_staff"], "color": row["color"],
        "notes": row["notes"], "kind": row["kind"],
        "template_id": str(row["template_id"]) if row["template_id"] else None,
        "job_id": str(row["job_id"]) if row["job_id"] else None,
        "training_requirement_id": (
            str(row["training_requirement_id"]) if row["training_requirement_id"] else None
        ),
        "employee_ids": [str(employee_id) for employee_id in row["employee_ids"]],
    } for row in rows]


async def _list_templates(conn, *, company_id: UUID, location_id: UUID) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        SELECT w.id, w.name, w.location_id, COUNT(b.id) AS block_count
        FROM schedule_week_templates w
        LEFT JOIN schedule_shift_templates b ON b.week_template_id=w.id
        WHERE w.company_id=$1 AND (w.location_id=$2 OR w.location_id IS NULL)
        GROUP BY w.id ORDER BY w.name, w.id
        """,
        company_id, location_id,
    )
    return [{**dict(row), "id": str(row["id"]),
             "location_id": str(row["location_id"]) if row["location_id"] else None}
            for row in rows]


async def _misaligned_week(conn, *, company_id: UUID, location_id: UUID,
                           week_start: date) -> dict[str, Any] | None:
    """Refusal when the requested week does not start on the location's own
    start day.

    Everything downstream (`template_windows`, the seven-day demand load, the
    editor grid) assumes `week_start` IS the first day of the week, so a
    Sunday date for a Monday-start store silently plans a window that matches
    no grid the manager can see. The assistant session gates its own week the
    same way; this covers every other caller.
    """
    weekday = await resolve_week_start_weekday(
        conn, company_id=company_id, location_id=location_id,
    )
    aligned = align_week_start(week_start, weekday)
    if aligned == week_start:
        return None
    return {
        "status": "refused",
        "message": (
            f"This location's weeks start on {WEEKDAY_NAMES[weekday]}. "
            f"Use {aligned.isoformat()} as the week start."
        ),
    }


async def _default_template_id(conn, *, company_id: UUID, location_id: UUID) -> UUID | None:
    """The week template this location's scheduling profile points at."""
    return await conn.fetchval(
        "SELECT default_week_template_id FROM schedule_location_profiles "
        "WHERE company_id=$1 AND location_id=$2",
        company_id, location_id,
    )


async def _load_template_demand(conn, *, company_id: UUID, location_id: UUID,
                                week_start: date, template_id: UUID) -> tuple[str, list[dict[str, Any]]]:
    template = await conn.fetchrow(
        """SELECT id, name FROM schedule_week_templates
           WHERE id=$1 AND company_id=$2 AND (location_id=$3 OR location_id IS NULL)""",
        template_id, company_id, location_id,
    )
    if not template:
        raise ValueError("That week template is not available for this location.")
    rows = await conn.fetch(
        """
        SELECT id, name, role, department, start_time, end_time, break_minutes,
               required_staff, days_of_week, color, notes, job_id
        FROM schedule_shift_templates
        WHERE week_template_id=$1 ORDER BY start_time, id
        """,
        template_id,
    )
    demand = []
    for row in rows:
        days = row["days_of_week"]
        if isinstance(days, str):
            days = json.loads(days)
        starts, ends = template_windows(
            week_start, week_start + timedelta(days=6), set(days or []),
            row["start_time"], row["end_time"],
        )
        for starts_at, ends_at in zip(starts, ends):
            demand.append({
                "key": f"template:{row['id']}:{starts_at.date().isoformat()}",
                "source_shift_id": None, "role": row["role"] or row["name"],
                "department": row["department"], "starts_at": starts_at, "ends_at": ends_at,
                "break_minutes": row["break_minutes"] or 0,
                "required_staff": row["required_staff"], "color": row["color"],
                "notes": row["notes"], "kind": "work", "template_id": str(row["id"]),
                "job_id": str(row["job_id"]) if row["job_id"] else None,
                "training_requirement_id": None, "fixed_employee_ids": [],
                "worked_minutes": max(
                    0, int((ends_at - starts_at).total_seconds() // 60)
                    - int(row["break_minutes"] or 0),
                ),
            })
    if len(demand) > _MAX_DEMAND_SHIFTS:
        raise ValueError(f"That template creates more than {_MAX_DEMAND_SHIFTS} shifts in one week.")
    return template["name"], demand


async def _planning_snapshot(
    conn, *, company_id: UUID, location_id: UUID, week_start: date,
    source_mode: str, week_template_id: UUID | None,
) -> tuple[dict[str, Any], list[dict[str, Any]], str | None]:
    roster = await _load_roster_context(
        conn, company_id=company_id, location_id=location_id, week_start=week_start,
    )
    week_shift_state = await _load_week_shift_state(
        conn, company_id=company_id, location_id=location_id, week_start=week_start,
    )
    template_name = None
    if source_mode == "existing":
        demand = await _load_existing_demand(
            conn, company_id=company_id, location_id=location_id, week_start=week_start,
        )
    elif source_mode == "template" and week_template_id is not None:
        template_name, demand = await _load_template_demand(
            conn, company_id=company_id, location_id=location_id,
            week_start=week_start, template_id=week_template_id,
        )
    else:
        raise ValueError("Choose existing draft shifts or a week template as the schedule source.")
    snapshot = {
        "location_id": str(location_id), "week_start": week_start.isoformat(),
        "source_mode": source_mode,
        "week_template_id": str(week_template_id) if week_template_id else None,
        "demand": demand, "week_shift_state": week_shift_state, **roster,
    }
    return snapshot, demand, template_name


async def get_week_build_readiness(
    *, company_id: UUID, location_id: UUID, week_start: date,
    week_template_id: UUID | None = None,
) -> dict[str, Any]:
    async with connection_or_direct() as conn:
        location = await conn.fetchrow(
            "SELECT id, name FROM business_locations WHERE id=$1 AND company_id=$2 AND is_active IS NOT FALSE",
            location_id, company_id,
        )
        if not location:
            return {"status": "refused", "message": "That schedule location is not available."}
        misaligned = await _misaligned_week(
            conn, company_id=company_id, location_id=location_id, week_start=week_start,
        )
        if misaligned:
            return misaligned
        roster = await _load_roster_context(
            conn, company_id=company_id, location_id=location_id, week_start=week_start,
        )
        demand = await _load_existing_demand(
            conn, company_id=company_id, location_id=location_id, week_start=week_start,
        )
        shift_counts = await _week_shift_counts(
            conn, company_id=company_id, location_id=location_id, week_start=week_start,
        )
        templates = await _list_templates(conn, company_id=company_id, location_id=location_id)
        default_id = await _default_template_id(
            conn, company_id=company_id, location_id=location_id,
        )
        profile = await _coverage_profile(
            conn, company_id=company_id, location_id=location_id,
        )
        # Readiness has to agree with the builder about whether a week can be
        # built at all — the model is told to call this first, and "ready" here
        # followed by a refusal there is the loop this surface exists to end.
        rules_bundle = await load_profile_bundle(
            conn, company_id=company_id, location_id=location_id,
        )
        # Judge the PATTERN, before anyone is assigned to it: `required` asks
        # "would this shape cover the day even with everybody showing up?".
        # A hole here is something to fix in the interview, so it is reported
        # and deliberately NOT added to `blockers` — refusing to build over it
        # is the dead end this whole surface exists to end.
        pattern_source = demand
        if not pattern_source:
            pattern_template_id = week_template_id or default_id
            if pattern_template_id:
                try:
                    _name, pattern_source = await _load_template_demand(
                        conn, company_id=company_id, location_id=location_id,
                        week_start=week_start, template_id=UUID(str(pattern_template_id)),
                    )
                except (ValueError, TypeError):
                    pattern_source = []
        published_shifts = [
            shift for shift in await _load_week_shift_state(
                conn, company_id=company_id, location_id=location_id, week_start=week_start,
            ) if shift["status"] == "published"
        ]
    pattern_findings = evaluate_week_coverage(
        plan_shifts=pattern_source, baseline_shifts=published_shifts,
        operating_hours=profile["operating_hours"],
        open_buffer_minutes=profile["open_buffer_minutes"],
        close_buffer_minutes=profile["close_buffer_minutes"],
        leader_job_ids=profile["leader_job_ids"],
        leader_job_names=profile["leader_job_names"],
        week_start=week_start, headcount="required",
    ) if pattern_source else []
    pattern_findings = _cap_findings(pattern_findings, _FINDINGS_RETURNED)
    default_template = next(
        (template for template in templates
         if str(template["id"]) == str(default_id) and template["block_count"]), None,
    ) if default_id else None
    confirmed = [employee for employee in roster["employees"] if employee["availability_state"] != "unconfirmed"]
    unconfirmed = [employee for employee in roster["employees"] if employee["availability_state"] == "unconfirmed"]
    existing_positions = sum(int(shift["required_staff"]) for shift in demand)
    if demand:
        recommendation = "existing"
    elif shift_counts["published"]:
        recommendation = None
    elif default_template is not None:
        recommendation = "template"
    elif len(templates) == 1 and templates[0]["block_count"]:
        recommendation = "template"
    else:
        recommendation = None
    rules_missing = missing_fields(rules_bundle)
    blockers = []
    # First, because it is the one blocker the manager can act on without any
    # roster or template work — and the one the builder itself enforces.
    rules_refusal = week_rules_refusal(rules_bundle, location_name=location["name"])
    if rules_refusal:
        blockers.append(rules_refusal)
    if not roster["employees"]:
        blockers.append("No active employees are assigned to this location.")
    if not confirmed:
        blockers.append("No employee has confirmed scheduling availability.")
    selected_template = next(
        (template for template in templates if str(template["id"]) == str(week_template_id)), None,
    ) if week_template_id else None
    if week_template_id and (not selected_template or not selected_template["block_count"]):
        blockers.append("The selected week template is unavailable or has no shift blocks.")
    elif not demand and not any(template["block_count"] for template in templates):
        blockers.append("Add draft shifts or a week template to define the store's staffing needs.")
    if not demand and shift_counts["published"]:
        blockers.append(
            "This week already has published shifts. Add only the remaining staffing needs as drafts before asking Huume to fill them."
        )
    usable_templates = [template for template in templates if template["block_count"]]
    if (
        not demand and not week_template_id
        and default_template is None and len(usable_templates) > 1
    ):
        blockers.append("Choose which saved week template Huume should use as staffing demand.")
    return {
        "status": "ok", "ready": not blockers, "location_name": location["name"],
        "default_week_template_id": str(default_template["id"]) if default_template else None,
        "week_start": week_start.isoformat(), "week_end": (week_start + timedelta(days=6)).isoformat(),
        "roster_count": len(roster["employees"]), "confirmed_availability_count": len(confirmed),
        "unconfirmed_availability": [
            {"employee_id": employee["id"], "name": employee["name"]} for employee in unconfirmed
        ],
        "existing_draft_shift_count": len(demand),
        "published_shift_count": shift_counts["published"],
        "existing_required_positions": existing_positions,
        "week_templates": templates, "recommended_source": recommendation,
        "blockers": blockers,
        "week_rules_missing": rules_missing,
        "operating_hours_known": bool(profile["operating_hours"]),
        "open_buffer_minutes": profile["open_buffer_minutes"],
        "close_buffer_minutes": profile["close_buffer_minutes"],
        # The rule is a set; the scalar is its first entry for readers that
        # predate the set.
        "leader_job_ids": profile["leader_job_ids"],
        "leader_job_names": profile["leader_job_names"],
        "leader_job_name": profile["leader_job_names"][0] if profile["leader_job_names"] else None,
        "pattern_findings": pattern_findings,
        "employees": [
            {"employee_id": employee["id"], "name": employee["name"],
             "availability_state": employee["availability_state"],
             "target_weekly_minutes": employee["target_weekly_minutes"],
             "max_weekly_minutes": employee["max_weekly_minutes"]}
            for employee in roster["employees"]
        ],
    }


def _coerce_constraints(exclude_employee_ids: Iterable[str] | None,
                        employee_hour_caps: Iterable[dict[str, Any]] | None) -> dict[str, Any]:
    excluded = []
    for value in exclude_employee_ids or []:
        try:
            excluded.append(str(UUID(str(value))))
        except (TypeError, ValueError) as exc:
            raise ValueError("Every excluded employee must use a valid employee id.") from exc
    caps: dict[str, int] = {}
    for row in employee_hour_caps or []:
        try:
            employee_id = str(UUID(str(row.get("employee_id"))))
            minutes = int(row.get("max_weekly_minutes"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError("Every employee hour cap needs a valid employee id and minute value.") from exc
        if not 0 <= minutes <= 10080:
            raise ValueError("Employee hour caps must be between 0 and 10,080 minutes.")
        caps[employee_id] = minutes
    return {"exclude_employee_ids": sorted(set(excluded)), "employee_hour_caps": caps}


async def propose_week_draft(
    *, company_id: UUID, actor_user_id: UUID | None, thread_id: UUID | None,
    location_id: UUID, week_start: date, source_mode: str = "auto",
    week_template_id: str | None = None,
    exclude_employee_ids: Iterable[str] | None = None,
    employee_hour_caps: Iterable[dict[str, Any]] | None = None,
    origin: str = "manual",
) -> dict[str, Any]:
    if origin not in {"manual", "automatic"}:
        return {"status": "refused", "message": "Unknown schedule generation origin."}
    try:
        constraints = _coerce_constraints(exclude_employee_ids, employee_hour_caps)
    except ValueError as exc:
        return {"status": "clarify", "message": str(exc)}
    async with connection_or_direct() as conn:
        misaligned = await _misaligned_week(
            conn, company_id=company_id, location_id=location_id, week_start=week_start,
        )
        if misaligned:
            return misaligned
        gate = await _week_rules_gate(
            conn, company_id=company_id, location_id=location_id,
        )
        if gate:
            return gate
        existing = await _load_existing_demand(
            conn, company_id=company_id, location_id=location_id, week_start=week_start,
        )
        shift_counts = await _week_shift_counts(
            conn, company_id=company_id, location_id=location_id, week_start=week_start,
        )
        templates = await _list_templates(conn, company_id=company_id, location_id=location_id)
        template_uuid: UUID | None = None
        selected_source = (source_mode or "auto").strip().lower()
        if selected_source == "auto":
            if existing:
                selected_source = "existing"
            elif shift_counts["published"]:
                return {
                    "status": "refused",
                    "message": (
                        "This week already has published shifts. Add the remaining staffing needs "
                        "as draft shifts so I can fill them without creating duplicates."
                    ),
                }
            elif week_template_id:
                selected_source = "template"
            else:
                usable = [template for template in templates if template["block_count"]]
                # The location's own default is an explicit answer to "which
                # template?" — asking again when the manager already set one is
                # the loop this feature exists to end.
                default_id = await _default_template_id(
                    conn, company_id=company_id, location_id=location_id,
                )
                default_usable = next(
                    (t for t in usable if str(t["id"]) == str(default_id)), None,
                ) if default_id else None
                if default_usable is not None:
                    selected_source = "template"
                    week_template_id = default_usable["id"]
                elif len(usable) != 1:
                    return {
                        "status": "clarify",
                        "message": "Choose which week template to use." if usable else
                                   "Add draft shifts or a week template before I build the week.",
                        "week_templates": usable,
                    }
                else:
                    selected_source = "template"
                    week_template_id = usable[0]["id"]
        if selected_source not in {"existing", "template"}:
            return {"status": "clarify", "message": "Use source_mode existing, template, or auto."}
        if selected_source == "template":
            if shift_counts["published"]:
                return {
                    "status": "refused",
                    "message": (
                        "This week already has published shifts. I won't apply a full-week template "
                        "on top of them because that could create duplicates."
                    ),
                }
            try:
                template_uuid = UUID(str(week_template_id))
            except (TypeError, ValueError):
                return {"status": "clarify", "message": "Choose a week_template_id from the readiness list."}
            if existing:
                return {
                    "status": "refused",
                    "message": "This week already has draft shifts. Use those as the source so I don't create duplicates.",
                }
        try:
            snapshot, demand, template_name = await _planning_snapshot(
                conn, company_id=company_id, location_id=location_id, week_start=week_start,
                source_mode=selected_source, week_template_id=template_uuid,
            )
        except ValueError as exc:
            return {"status": "clarify", "message": str(exc)}
        if not demand:
            return {"status": "clarify", "message": "There are no draft shifts to staff in this week."}
        if not snapshot["employees"]:
            return {"status": "refused", "message": "No active employees are assigned to this location."}
        roster_ids = {employee["id"] for employee in snapshot["employees"]}
        constrained_ids = set(constraints["exclude_employee_ids"]) | set(
            constraints["employee_hour_caps"]
        )
        if constrained_ids - roster_ids:
            return {
                "status": "clarify",
                "message": (
                    "One or more scheduling constraints reference an employee outside this "
                    "location's active roster. Check readiness again and use its employee ids."
                ),
            }
        blocked_pairs: set[tuple[str, str]] = set()
        needs_final_rebuild = False
        for _attempt in range(_MAX_COMPLIANCE_REPLANS):
            plan = build_plan(
                demand=demand, employees=snapshot["employees"], availability=snapshot["availability"],
                existing_assignments=snapshot["existing_assignments"],
                adjacent_assignments=snapshot.get("adjacent_assignments", []),
                unavailable_ranges=snapshot["unavailable_ranges"],
                exclude_employee_ids=set(constraints["exclude_employee_ids"]),
                employee_hour_caps=constraints["employee_hour_caps"],
                gated_job_ids=snapshot["gated_job_ids"],
                blocked_pairs=blocked_pairs,
            )
            newly_blocked = await _preflight_compliance_blocks(
                conn, company_id=company_id, location_id=location_id, plan=plan,
            ) - blocked_pairs
            if not newly_blocked:
                needs_final_rebuild = False
                break
            blocked_pairs.update(newly_blocked)
            needs_final_rebuild = True
        if needs_final_rebuild:
            plan = build_plan(
                demand=demand, employees=snapshot["employees"], availability=snapshot["availability"],
                existing_assignments=snapshot["existing_assignments"],
                adjacent_assignments=snapshot.get("adjacent_assignments", []),
                unavailable_ranges=snapshot["unavailable_ranges"],
                exclude_employee_ids=set(constraints["exclude_employee_ids"]),
                employee_hour_caps=constraints["employee_hour_caps"],
                gated_job_ids=snapshot["gated_job_ids"],
                blocked_pairs=blocked_pairs,
            )
        # Coverage + break relief run on the FINAL plan, and their output lives
        # on the plan rather than on `review`: the automatic worker path
        # rebuilds its staged action from `proposal["unfilled"]`, never from
        # `review`, so findings parked in the review payload would be invisible
        # on exactly the runs nobody is watching.
        #
        # The profile is read here and deliberately NOT added to the snapshot:
        # `_input_hash` hashes the snapshot, so a manager editing a buffer
        # minute would otherwise stale an otherwise-good proposal at confirm.
        await _attach_findings(
            conn, company_id=company_id, location_id=location_id,
            week_start=week_start, plan=plan, snapshot=snapshot,
        )
        review = _review_payload(
            plan=plan, snapshot=snapshot, source_mode=selected_source,
            template_name=template_name,
        )
        persisted_plan = {**plan, "review": review}
        run_id = uuid4()
        input_hash = _input_hash(snapshot)
        insert_result = await conn.execute(
            """
            INSERT INTO schedule_generation_runs(
                id, company_id, location_id, week_start, thread_id, source_mode,
                week_template_id, origin, input_hash, planner_version, constraints,
                proposal, metrics, created_by
            ) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11::jsonb,$12::jsonb,$13::jsonb,$14)
            ON CONFLICT DO NOTHING
            """,
            run_id, company_id, location_id, week_start, thread_id, selected_source,
            template_uuid, origin, input_hash, PLANNER_VERSION, json.dumps(constraints),
            json.dumps(_iso(persisted_plan)), json.dumps(plan["metrics"]), actor_user_id,
        )
        if insert_result == "INSERT 0 0":
            return {
                "status": "skipped",
                "message": "A schedule suggestion already exists for this location and week.",
            }
    metrics = plan["metrics"]
    return {
        "status": "ready", "generation_run_id": str(run_id), "source_mode": selected_source,
        "week_template_id": str(template_uuid) if template_uuid else None,
        "origin": origin, "summary": review["summary"], "metrics": metrics,
        "unfilled": plan["unfilled"][:20],
        "findings": _cap_findings(plan.get("findings") or [], _FINDINGS_RETURNED),
        "schedule_preview": review["schedule_preview"],
        "preview_truncated": review["preview_truncated"],
    }


async def _reconcile_warnings_best_effort(company_id: UUID, shift_ids: list[UUID]) -> None:
    try:
        from .schedule_warning_events import reconcile_schedule_warning_events
        async with connection_or_direct() as conn:
            await reconcile_schedule_warning_events(conn, company_id, shift_ids=shift_ids)
    except Exception:
        # Warning fan-out is advisory and must not roll back a confirmed draft.
        return


async def cancel_week_draft(*, company_id: UUID, generation_run_id: UUID) -> None:
    """Mark an unused proposal cancelled when its Huume action is cancelled."""
    async with connection_or_direct() as conn:
        await conn.execute(
            """UPDATE schedule_generation_runs
               SET status='cancelled', updated_at=NOW()
               WHERE id=$1 AND company_id=$2 AND status='proposed'""",
            generation_run_id, company_id,
        )


async def apply_week_draft(
    *, company_id: UUID, actor_user_id: UUID | None, generation_run_id: UUID,
    location_id: UUID, week_start: date,
) -> dict[str, Any]:
    created_shift_ids: list[UUID] = []
    touched_shift_ids: list[UUID] = []
    dropped: list[dict[str, Any]] = []
    async with connection_or_direct() as conn:
        async with conn.transaction():
            run = await conn.fetchrow(
                """SELECT * FROM schedule_generation_runs
                   WHERE id=$1 AND company_id=$2 FOR UPDATE""",
                generation_run_id, company_id,
            )
            if not run or run["location_id"] != location_id or run["week_start"] != week_start:
                return {"status": "error", "message": "That week proposal is outside this schedule workspace."}
            if run["status"] == "applied":
                return {"status": "created", "record_id": str(generation_run_id),
                        "message": "That generated draft was already applied."}
            if run["status"] != "proposed":
                return {"status": "error", "message": "That week proposal is no longer available."}
            # Re-checked at confirm for the same reason availability and
            # qualifications are: the rules can be edited away in the Week
            # setup pane between staging and approval.
            gate = await _week_rules_gate(
                conn, company_id=company_id, location_id=location_id,
            )
            if gate:
                return {"status": "error", "message": gate["message"]}
            if run["source_mode"] == "template":
                shift_counts = await _week_shift_counts(
                    conn, company_id=company_id, location_id=location_id, week_start=week_start,
                )
                if shift_counts["draft"] or shift_counts["published"]:
                    await conn.execute(
                        "UPDATE schedule_generation_runs SET status='stale', updated_at=NOW() WHERE id=$1",
                        generation_run_id,
                    )
                    return {
                        "status": "error",
                        "message": (
                            "This week gained shifts after the template proposal was built. "
                            "Ask me to rebuild it so I don't create duplicates."
                        ),
                    }
            snapshot, _demand, _template_name = await _planning_snapshot(
                conn, company_id=company_id, location_id=location_id, week_start=week_start,
                source_mode=run["source_mode"], week_template_id=run["week_template_id"],
            )
            if _input_hash(snapshot) != run["input_hash"]:
                await conn.execute(
                    "UPDATE schedule_generation_runs SET status='stale', updated_at=NOW() WHERE id=$1",
                    generation_run_id,
                )
                return {
                    "status": "error",
                    "message": "The schedule, roster, or availability changed after this proposal was built. Ask me to rebuild it.",
                }
            proposal = run["proposal"]
            if isinstance(proposal, str):
                proposal = json.loads(proposal)
            shift_id_by_key: dict[str, UUID] = {}
            series_id = uuid4()
            for shift in proposal.get("shifts") or []:
                source_shift_id = shift.get("source_shift_id")
                if source_shift_id:
                    live = await conn.fetchrow(
                        """SELECT id, starts_at, ends_at, status, kind, role, location_id,
                                  job_id, break_minutes, required_staff, training_requirement_id
                           FROM schedule_shifts
                           WHERE id=$1 AND company_id=$2 AND location_id=$3 FOR UPDATE""",
                        UUID(source_shift_id), company_id, location_id,
                    )
                    if not live or live["status"] != "draft":
                        await conn.execute(
                            "UPDATE schedule_generation_runs SET status='stale', updated_at=NOW() WHERE id=$1",
                            generation_run_id,
                        )
                        return {
                            "status": "error",
                            "message": "A source shift changed after this proposal was built. Ask me to rebuild it.",
                        }
                    shift_id_by_key[shift["key"]] = live["id"]
                    touched_shift_ids.append(live["id"])
                    continue
                job_id = UUID(shift["job_id"]) if shift.get("job_id") else None
                if job_id is None:
                    # A legacy block with a free-text role and no job still
                    # names a real job often enough to be worth resolving —
                    # generated shifts then match what the REST path writes.
                    matched_job = await resolve_job_by_name(
                        conn, company_id, shift.get("role"), location_id=location_id,
                    )
                    job_id = matched_job["id"] if matched_job else None
                new_id = await create_shift_core(
                    conn, company_id, location_id=location_id, role=shift.get("role"),
                    department=shift.get("department"), starts_at=datetime.fromisoformat(shift["starts_at"]),
                    ends_at=datetime.fromisoformat(shift["ends_at"]),
                    break_minutes=int(shift.get("break_minutes") or 0),
                    required_staff=int(shift["required_staff"]), color=shift.get("color"),
                    notes=shift.get("notes"), kind=shift.get("kind") or "work",
                    template_id=UUID(shift["template_id"]) if shift.get("template_id") else None,
                    series_id=series_id,
                    job_id=job_id,
                    training_requirement_id=(
                        UUID(shift["training_requirement_id"])
                        if shift.get("training_requirement_id") else None
                    ),
                    employee_ids=[], created_by=actor_user_id, status="draft",
                    audit_details={"source": "huume_week_builder", "generation_run_id": str(generation_run_id)},
                )
                shift_id_by_key[shift["key"]] = new_id
                created_shift_ids.append(new_id)
                touched_shift_ids.append(new_id)

            employee_ids = sorted({
                UUID(assignment["employee_id"])
                for shift in proposal.get("shifts") or []
                for assignment in shift.get("proposed_assignments") or []
            })
            # find_conflicts retains transaction advisory locks.  Acquire the
            # whole set in one stable order before the proposal-order loop so
            # concurrent week applies cannot deadlock on inverse rosters.
            await lock_scheduling_employees(conn, company_id, employee_ids)
            availability = await fetch_availability(conn, company_id, employee_ids)
            for shift in proposal.get("shifts") or []:
                shift_id = shift_id_by_key[shift["key"]]
                for assignment in shift.get("proposed_assignments") or []:
                    employee_id = UUID(assignment["employee_id"])
                    live = await conn.fetchrow(
                        """SELECT id, starts_at, ends_at, status, kind, role, location_id,
                                  job_id, break_minutes, required_staff, training_requirement_id,
                                  published_at
                           FROM schedule_shifts WHERE id=$1 AND company_id=$2 FOR UPDATE""",
                        shift_id, company_id,
                    )
                    assigned_count = await conn.fetchval(
                        "SELECT COUNT(*) FROM schedule_shift_assignments WHERE shift_id=$1",
                        shift_id,
                    )
                    reason = None
                    if assigned_count >= live["required_staff"]:
                        reason = "shift already reached required staffing"
                    elif await find_conflicts(
                        conn, company_id, employee_id, live["starts_at"], live["ends_at"],
                        exclude_shift_id=shift_id,
                    ):
                        reason = "employee now has an overlapping shift"
                    elif availability_violations(
                        availability.get(employee_id, {}), live["starts_at"], live["ends_at"],
                    ):
                        reason = "employee is outside confirmed availability"
                    else:
                        qualified = await fetch_effective_job_employee_ids(
                            conn, company_id=company_id, job_id=live["job_id"],
                            employee_ids=[employee_id], as_of=live["starts_at"].date(),
                        )
                        if employee_id not in qualified:
                            reason = "employee is no longer qualified for this job"
                    if reason is None:
                        violations = await check_shift_compliance(
                            conn, company_id, location_id=live["location_id"], job_id=live["job_id"],
                            starts_at=live["starts_at"], ends_at=live["ends_at"],
                            break_minutes=live["break_minutes"] or 0, employee_id=employee_id,
                            exclude_shift_id=shift_id, shift_kind=live["kind"],
                            training_requirement_id=live["training_requirement_id"],
                        )
                        block = next((item for item in violations if item.get("severity") == "block"), None)
                        if block:
                            reason = block.get("message") or "hard scheduling compliance block"
                    if reason:
                        dropped.append({
                            "shift_id": str(shift_id), "employee_id": str(employee_id),
                            "employee_name": assignment.get("employee_name"), "reason": reason,
                        })
                        continue
                    await apply_assignment_core(
                        conn, company_id, shift_row=live, employee_id=employee_id,
                        actor_user_id=actor_user_id,
                        audit_details={"source": "huume_week_builder", "generation_run_id": str(generation_run_id)},
                    )
            await log_audit(
                conn, company_id, "schedule_generation", generation_run_id,
                actor_user_id, "schedule_generation.apply",
                {"source_mode": run["source_mode"], "created_shift_ids": [str(value) for value in created_shift_ids],
                 "dropped": dropped},
            )
            await conn.execute(
                """UPDATE schedule_generation_runs
                   SET status='applied', applied_by=$1, applied_at=NOW(), updated_at=NOW()
                   WHERE id=$2""",
                actor_user_id, generation_run_id,
            )
    await _reconcile_warnings_best_effort(company_id, touched_shift_ids)
    applied_assignments = sum(
        len(shift.get("proposed_assignments") or []) for shift in proposal.get("shifts") or []
    ) - len(dropped)
    message = (
        f"Applied the generated week as a draft: {len(created_shift_ids)} shift(s) created and "
        f"{applied_assignments} assignment(s) added."
    )
    if dropped:
        message += f" {len(dropped)} assignment(s) were left open after current-state rechecks."
    return {
        "status": "created", "record_id": str(generation_run_id), "message": message,
        "created_shift_ids": [str(value) for value in created_shift_ids],
        "touched_shift_ids": [str(value) for value in touched_shift_ids], "dropped": dropped,
    }
