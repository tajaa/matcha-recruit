"""Operational staggering of legally-required breaks across one shift's crew.

``schedule_breaks`` answers "what breaks does this employee owe, and when may
they be taken".  It answers that per employee, in isolation.  This module is the
operational layer on top: given every assignee's evaluated ``BreakPlan``, it
spreads the resulting break periods apart in time so the shift keeps as many
people on the floor as it can, and says so plainly when it cannot.

The two layers stay separate on purpose.  A ``BreakRequirement`` is the law; a
``StaggerResult`` is a recommendation about *when* to take it.  Nothing here
invents, moves, or clears a legal requirement — an unresolved plan comes back
as ``unresolved`` rather than a confident placement.

Concurrency budget: a shift's ``required_staff`` is the headcount it needs on
the floor, and assignment writes reject going above it (``shift_full``), so a
shift almost never carries spare headcount.  Refusing to place any break
without spare headcount would make every normal shift unplannable, so the
budget floors at one concurrent break — breaks are serialized — and a
``coverage_shortfall`` advisory reports that the floor dips while each break is
taken.  Under-covering for 30 minutes is the manager's call to make; hiding it
is not.

Times in and out are location-local wall-clock datetimes, matching
``BreakRequirement.earliest_local`` / ``recommended_local`` / ``deadline_local``
as produced by ``evaluate_break_plan``.  This module has no database or FastAPI
dependency.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal, Sequence
from uuid import UUID

from .schedule_breaks import BreakKind, BreakPlan, BreakRequirement


StaggerStatus = Literal["suggested", "unresolved", "insufficient_coverage"]

UNRESOLVED_REASONS: dict[str, str] = {
    "unmapped": "Break requirements could not be mapped for this location; verify manually.",
    "error": "Break requirements could not be fully evaluated; verify manually.",
}


@dataclass(frozen=True)
class StaggerAssignment:
    """One assignee and the break plan already evaluated for them."""

    employee_id: UUID
    plan: BreakPlan


@dataclass(frozen=True)
class StaggerResult:
    employee_id: UUID
    kind: BreakKind
    ordinal: int
    status: StaggerStatus
    suggested_start: datetime | None
    suggested_end: datetime | None
    duration_minutes: int
    reason: str | None = None


@dataclass(frozen=True)
class StaggerPlan:
    results: tuple[StaggerResult, ...]
    advisories: tuple[dict[str, Any], ...]
    max_concurrent_breaks: int


@dataclass(frozen=True)
class _Slot:
    """One requirement flattened into a placeable interval request."""

    employee_id: UUID
    kind: BreakKind
    ordinal: int
    duration_minutes: int
    earliest: datetime
    latest_start: datetime
    preferred: datetime
    deadline_known: bool


def _window_bounds(
    requirement: BreakRequirement,
    *,
    shift_start_local: datetime,
    shift_end_local: datetime,
) -> tuple[datetime, datetime, datetime, bool]:
    """Resolve (earliest, latest_start, preferred, deadline_known) for a slot.

    A rule set that carries no offsets still deserves a suggestion, so the
    shift's own window is the fallback envelope.
    """

    duration = timedelta(minutes=requirement.duration_minutes)
    earliest = requirement.earliest_local or shift_start_local
    deadline_known = requirement.deadline_local is not None
    deadline = requirement.deadline_local or shift_end_local
    latest_start = deadline - duration

    if earliest < shift_start_local:
        earliest = shift_start_local
    if latest_start > shift_end_local - duration:
        latest_start = shift_end_local - duration
    if latest_start < earliest:
        # A window too tight to hold the break at all: keep it anchored at the
        # earliest legal moment rather than inverting the interval.
        latest_start = earliest

    preferred = requirement.recommended_local or earliest
    if preferred < earliest:
        preferred = earliest
    if preferred > latest_start:
        preferred = latest_start
    return earliest, latest_start, preferred, deadline_known


def _candidate_starts(slot: _Slot, step_minutes: int) -> list[datetime]:
    """Candidate starts, walking outward from the preferred time.

    Preferring the recommended time and only then drifting keeps the first
    employee placed where the rule actually wants the break, and pushes later
    employees off it only as far as coverage forces.
    """

    step = timedelta(minutes=max(1, step_minutes))
    candidates: list[datetime] = [slot.preferred]
    seen = {slot.preferred}
    offset = step
    while True:
        later = slot.preferred + offset
        earlier = slot.preferred - offset
        later_ok = later <= slot.latest_start
        earlier_ok = earlier >= slot.earliest
        if not later_ok and not earlier_ok:
            break
        # Later first: drifting a break toward its deadline is normal, pulling
        # it earlier than recommended is the more surprising edit.
        for value in (later if later_ok else None, earlier if earlier_ok else None):
            if value is not None and value not in seen:
                seen.add(value)
                candidates.append(value)
        offset += step
    return candidates


def _fits(
    start: datetime,
    duration: timedelta,
    placed: Sequence[tuple[datetime, datetime]],
    max_concurrent: int,
) -> bool:
    """True when adding [start, start+duration) keeps concurrency in budget.

    Checked against every already-placed interval: a new break may overlap at
    most ``max_concurrent - 1`` of them at any instant.  Overlap counts are
    evaluated at each placed interval's start and at ``start`` itself, which is
    sufficient because concurrency only ever rises at an interval boundary.
    """

    end = start + duration
    overlapping = [
        (other_start, other_end)
        for other_start, other_end in placed
        if other_start < end and start < other_end
    ]
    if not overlapping:
        return True
    if max_concurrent <= 1:
        return False
    for boundary in [start, *(value[0] for value in overlapping)]:
        if boundary < start or boundary >= end:
            continue
        concurrent = 1 + sum(
            1 for other_start, other_end in overlapping
            if other_start <= boundary < other_end
        )
        if concurrent > max_concurrent:
            return False
    return True


def _collision_reason(slot: _Slot) -> str:
    window = "its legal window" if slot.deadline_known else "the shift window"
    return (
        f"No {slot.duration_minutes}-minute slot inside {window} keeps enough "
        "staff on the floor; other breaks already fill every option."
    )


def stagger_shift_breaks(
    *,
    shift_start_local: datetime,
    shift_end_local: datetime,
    required_staff: int,
    assignments: Sequence[StaggerAssignment],
    step_minutes: int = 5,
) -> StaggerPlan:
    """Spread one shift's required breaks apart in time, deterministically.

    Waived requirements need no slot and produce no result.  Assignees whose
    plan never resolved produce ``unresolved`` results carrying the plan's own
    advisory wording — this module never guesses a time for a rule it could not
    evaluate.
    """

    assigned_count = len(assignments)
    max_concurrent = max(1, assigned_count - max(0, required_staff))
    advisories: list[dict[str, Any]] = []
    results: list[StaggerResult] = []
    slots: list[_Slot] = []

    for assignment in sorted(assignments, key=lambda value: str(value.employee_id)):
        plan = assignment.plan
        unresolved_reason = UNRESOLVED_REASONS.get(plan.status)
        for requirement in plan.requirements:
            if requirement.waived:
                continue
            if unresolved_reason is not None:
                results.append(StaggerResult(
                    employee_id=assignment.employee_id,
                    kind=requirement.kind,
                    ordinal=requirement.ordinal,
                    status="unresolved",
                    suggested_start=None,
                    suggested_end=None,
                    duration_minutes=requirement.duration_minutes,
                    reason=unresolved_reason,
                ))
                continue
            earliest, latest_start, preferred, deadline_known = _window_bounds(
                requirement,
                shift_start_local=shift_start_local,
                shift_end_local=shift_end_local,
            )
            slots.append(_Slot(
                employee_id=assignment.employee_id,
                kind=requirement.kind,
                ordinal=requirement.ordinal,
                duration_minutes=requirement.duration_minutes,
                earliest=earliest,
                latest_start=latest_start,
                preferred=preferred,
                deadline_known=deadline_known,
            ))

    if assigned_count and slots and assigned_count <= max(0, required_staff):
        advisories.append({
            "check": "break_stagger",
            "code": "coverage_shortfall",
            "severity": "advisory",
            "message": (
                f"This shift has no spare staffing above its required "
                f"{required_staff}, so it drops below that level while each "
                "break is taken. Breaks are suggested one at a time."
            ),
        })

    # Earliest deadline first (classic interval scheduling): the break with the
    # least slack is placed while the floor is still empty.  The rest of the key
    # only exists to make the ordering total, so the same inputs always produce
    # the same suggestions for a manager reopening the shift.
    ordered = sorted(
        slots,
        key=lambda slot: (
            slot.latest_start, slot.earliest, str(slot.employee_id), slot.kind, slot.ordinal,
        ),
    )
    placed: list[tuple[datetime, datetime]] = []
    for slot in ordered:
        duration = timedelta(minutes=slot.duration_minutes)
        chosen: datetime | None = None
        for candidate in _candidate_starts(slot, step_minutes):
            if _fits(candidate, duration, placed, max_concurrent):
                chosen = candidate
                break
        if chosen is None:
            results.append(StaggerResult(
                employee_id=slot.employee_id,
                kind=slot.kind,
                ordinal=slot.ordinal,
                status="insufficient_coverage",
                suggested_start=None,
                suggested_end=None,
                duration_minutes=slot.duration_minutes,
                reason=_collision_reason(slot),
            ))
            continue
        placed.append((chosen, chosen + duration))
        results.append(StaggerResult(
            employee_id=slot.employee_id,
            kind=slot.kind,
            ordinal=slot.ordinal,
            status="suggested",
            suggested_start=chosen,
            suggested_end=chosen + duration,
            duration_minutes=slot.duration_minutes,
        ))

    if any(result.status == "insufficient_coverage" for result in results):
        advisories.append({
            "check": "break_stagger",
            "code": "insufficient_coverage",
            "severity": "advisory",
            "message": (
                "One or more required breaks could not be scheduled without "
                "dropping coverage further. Review the flagged assignments."
            ),
        })

    results.sort(key=lambda result: (str(result.employee_id), result.kind, result.ordinal))
    return StaggerPlan(
        results=tuple(results),
        advisories=tuple(advisories),
        max_concurrent_breaks=max_concurrent,
    )


def stagger_payload(plan: StaggerPlan) -> dict[str, Any]:
    """JSON shape returned by the read-time endpoint."""

    return {
        "schema_version": 1,
        "max_concurrent_breaks": plan.max_concurrent_breaks,
        "results": [
            {
                "employee_id": str(result.employee_id),
                "kind": result.kind,
                "ordinal": result.ordinal,
                "status": result.status,
                "duration_minutes": result.duration_minutes,
                "suggested_start": result.suggested_start.isoformat() if result.suggested_start else None,
                "suggested_end": result.suggested_end.isoformat() if result.suggested_end else None,
                "reason": result.reason,
            }
            for result in plan.results
        ],
        "advisories": list(plan.advisories),
    }
