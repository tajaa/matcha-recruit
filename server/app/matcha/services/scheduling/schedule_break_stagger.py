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

The budget is a ceiling, not a target.  Two openers sent off the floor at the
same minute "technically work" whenever a third person has just clocked in,
and it is still the wrong suggestion: the floor runs with the fewest bodies it
lawfully can, at the same instant, for no reason.  Placement therefore prefers
a time nobody else is on break — anywhere in the legal window — and spends the
concurrency budget only when the window cannot hold another serialized break.

Times in and out are location-local wall-clock datetimes, matching
``BreakRequirement.earliest_local`` / ``recommended_local`` / ``deadline_local``
as produced by ``evaluate_break_plan``.  This module has no database or FastAPI
dependency.

Placement policy vs. law: some jurisdictions fix only a deadline and say
nothing about how early a break may start — California is the case in point
(Cal. Lab. Code § 512(a) and *Brinker Restaurant Corp. v. Superior Court*
(2012) 53 Cal.4th 1004 make a first-hour meal lawful).  Suggesting the shift's
own start time is legal there and useless everywhere: nobody has worked yet.
``DEFAULT_PLACEMENT_FLOOR_MINUTES`` is this module's operational answer, and it
is policy, not law — it is never written into a ``BreakRequirement``, it only
ever applies where the rule set states no earliest of its own, it yields both
to the legal deadline and to coverage rather than manufacturing a conflict of
either kind, and a time a manager saved is never re-judged against it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal, Sequence
from uuid import UUID

from .schedule_breaks import BreakKind, BreakPlan, BreakRequirement


StaggerStatus = Literal[
    "suggested", "saved", "deadline_conflict", "unresolved", "insufficient_coverage",
]

DEFAULT_PLACEMENT_FLOOR_MINUTES = 120

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
class LockedBreak:
    """A break time a manager already reviewed and saved.

    Suggestions are re-derived every time a shift is opened, so without these
    the placement would compute around a fiction: an accepted-then-edited time
    is real state the floor will actually run on, and everything still
    unreviewed has to be placed around it, not around what was suggested for
    that person before the edit.
    """

    employee_id: UUID
    kind: BreakKind
    ordinal: int
    start: datetime
    duration_minutes: int


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
    policy_earliest: datetime
    latest_start: datetime
    preferred: datetime
    deadline: datetime
    deadline_known: bool
    window_too_short: bool


@dataclass(frozen=True)
class _Placed:
    """An interval already committed to the floor, and whose it is."""

    start: datetime
    end: datetime
    employee_id: UUID


def _build_slot(
    requirement: BreakRequirement,
    *,
    employee_id: UUID,
    shift_start_local: datetime,
    shift_end_local: datetime,
    step_minutes: int,
    placement_floor_minutes: int,
) -> _Slot:
    """Flatten one requirement into a placeable interval request.

    A rule set that carries no offsets still deserves a suggestion, so the
    shift's own window is the fallback envelope.  That envelope opens at the
    shift's first instant, which is a legal time and a worthless suggestion, so
    two placement rules narrow it — both subordinate to the rule's own window,
    and neither able to create a conflict the law does not have:

    * a statute-silent requirement does not start before the policy floor, and
    * nothing starts at the shift's first instant, even where a rule set
      encodes an earliest offset of zero.

    The result is ``policy_earliest``, kept SEPARATE from the legal ``earliest``
    because policy is a preference and law is a bound.  Narrowing the legal
    window itself would be wrong twice over: it applies only while the break
    still fits before its deadline (checked here), and it must not cost the
    shift a placement (checked at placement time, since only there is it known
    how many breaks are competing for the same window).
    """

    duration = timedelta(minutes=requirement.duration_minutes)
    step = timedelta(minutes=max(1, step_minutes))
    earliest = requirement.earliest_local or shift_start_local
    deadline_known = requirement.deadline_local is not None
    deadline = requirement.deadline_local or shift_end_local
    latest_start = deadline - duration

    if earliest < shift_start_local:
        earliest = shift_start_local
    if latest_start > shift_end_local - duration:
        latest_start = shift_end_local - duration
    policy_earliest = earliest
    if requirement.earliest_local is None:
        floor = shift_start_local + timedelta(minutes=max(0, placement_floor_minutes))
        if policy_earliest < floor <= latest_start:
            policy_earliest = floor
    if policy_earliest <= shift_start_local and shift_start_local + step <= latest_start:
        # A break at the moment the shift opens is never the answer, even where
        # a rule set encodes an earliest offset of zero.
        policy_earliest = shift_start_local + step
    window_too_short = latest_start < earliest
    if window_too_short:
        # A window too tight to hold the break at all: keep it anchored at the
        # earliest legal moment rather than inverting the interval.  The
        # placement that comes out of this necessarily runs past the deadline,
        # which is why the slot carries the flag rather than swallowing it —
        # a break the law cannot fit is not a `suggested` one.
        latest_start = earliest
    if policy_earliest > latest_start:
        policy_earliest = latest_start

    preferred = requirement.recommended_local or policy_earliest
    if preferred < policy_earliest:
        preferred = policy_earliest
    if preferred > latest_start:
        preferred = latest_start
    return _Slot(
        employee_id=employee_id,
        kind=requirement.kind,
        ordinal=requirement.ordinal,
        duration_minutes=requirement.duration_minutes,
        earliest=earliest,
        policy_earliest=policy_earliest,
        latest_start=latest_start,
        preferred=preferred,
        deadline=deadline,
        deadline_known=deadline_known,
        window_too_short=window_too_short,
    )


def _candidate_tiers(slot: _Slot, step_minutes: int) -> tuple[list[datetime], list[datetime]]:
    """Candidate starts, walking outward from the preferred time, in two tiers.

    Preferring the recommended time and only then drifting keeps the first
    employee placed where the rule actually wants the break, and pushes later
    employees off it only as far as coverage forces.

    The walk covers the whole LEGAL window and the placement policy only
    partitions it: the first tier is every time policy allows, the second the
    times it merely discourages, closest to the floor first.  Dropping the
    latter instead would make the policy cost placements — breaks serialize
    when a shift carries no spare headcount, so a window shortened by two hours
    holds four fewer of them, and the crew who no longer fit would be reported
    as `insufficient_coverage` rather than given the lawful early time they had
    before.  The tiers stay separate (rather than one concatenated list) so
    that `_choose_start` can exhaust every allowed time — clear ones, then
    shared ones — before it offers a discouraged one.
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
    # The walk only ever lands on the grid, so a window whose own bounds are
    # off-grid (a 12:00–12:12 window with a 6-minute break) would never try the
    # one start that fits and would report insufficient_coverage for a slot
    # that is schedulable.  Boundaries go last: they are the fallback after
    # every preferred-adjacent option has been tried.
    for boundary in (slot.latest_start, slot.policy_earliest, slot.earliest):
        if boundary not in seen and slot.earliest <= boundary <= slot.latest_start:
            seen.add(boundary)
            candidates.append(boundary)
    allowed = [value for value in candidates if value >= slot.policy_earliest]
    discouraged = sorted(
        (value for value in candidates if value < slot.policy_earliest), reverse=True,
    )
    return allowed, discouraged


_Fit = Literal["clear", "shared"]


def _fit(
    start: datetime,
    duration: timedelta,
    placed: Sequence[_Placed],
    max_concurrent: int,
    *,
    employee_id: UUID,
) -> _Fit | None:
    """How [start, start+duration) sits against what is already off the floor.

    ``clear`` — nobody else is on break for any part of it; the floor loses
    exactly one body.  ``shared`` — it overlaps other breaks but stays inside
    the concurrency budget: a new break may overlap at most
    ``max_concurrent - 1`` of them at any instant.  ``None`` — it cannot be
    placed.  Overlap counts are evaluated at each placed interval's start and
    at ``start`` itself, which is sufficient because concurrency only ever
    rises at an interval boundary.

    One person is not two bodies, so the budget is not the only constraint: a
    break can never overlap another break belonging to the same employee, no
    matter how much spare headcount the shift carries.
    """

    end = start + duration
    overlapping = [
        entry for entry in placed
        if entry.start < end and start < entry.end
    ]
    if not overlapping:
        return "clear"
    if any(entry.employee_id == employee_id for entry in overlapping):
        return None
    if max_concurrent <= 1:
        return None
    for boundary in [start, *(entry.start for entry in overlapping)]:
        if boundary < start or boundary >= end:
            continue
        concurrent = 1 + sum(
            1 for entry in overlapping
            if entry.start <= boundary < entry.end
        )
        if concurrent > max_concurrent:
            return None
    return "shared"


def _choose_start(
    slot: _Slot,
    placed: Sequence[_Placed],
    max_concurrent: int,
    step_minutes: int,
) -> datetime | None:
    """The start to suggest for one slot, or ``None`` when nothing fits.

    Stagger first, share the budget last.  Within each policy tier the first
    ``clear`` candidate wins outright — even when the preferred time itself is
    ``shared`` and lawful.  Two openers on a 06:30 shift both told to break at
    08:30 because a third person clocks in then is inside the budget and still
    the wrong answer: the floor is thinnest exactly when it need not be.  Only
    when the tier holds no clear time at all does the earliest ``shared`` one
    (closest to preferred, since the walk is outward) get used, and only after
    both outcomes are exhausted for every allowed time does a discouraged time
    come into play — a lawful early break still beats no suggestion, and a
    doubled-up break after two hours of work still beats one after twenty
    minutes.
    """

    duration = timedelta(minutes=slot.duration_minutes)
    for tier in _candidate_tiers(slot, step_minutes):
        shared: datetime | None = None
        for candidate in tier:
            fit = _fit(candidate, duration, placed, max_concurrent, employee_id=slot.employee_id)
            if fit == "clear":
                return candidate
            if fit == "shared" and shared is None:
                shared = candidate
        if shared is not None:
            return shared
    return None


def _collision_reason(slot: _Slot) -> str:
    window = "its legal window" if slot.deadline_known else "the shift window"
    return (
        f"No {slot.duration_minutes}-minute slot inside {window} keeps enough "
        "staff on the floor; other breaks already fill every option."
    )


def _deadline_reason(slot: _Slot, end: datetime) -> str:
    overrun = int((end - slot.deadline).total_seconds() // 60)
    window = "its legal deadline" if slot.deadline_known else "the end of the shift"
    return (
        f"A {slot.duration_minutes}-minute break does not fit before "
        f"{window} ({slot.deadline.strftime('%H:%M')}); this time runs "
        f"{overrun} minute(s) past it. Shorten the shift, move the break "
        "window, or record why it could not be taken."
    )


def stagger_shift_breaks(
    *,
    shift_start_local: datetime,
    shift_end_local: datetime,
    required_staff: int,
    assignments: Sequence[StaggerAssignment],
    locked: Sequence[LockedBreak] = (),
    occupied: Sequence[LockedBreak] = (),
    step_minutes: int = 5,
    placement_floor_minutes: int = DEFAULT_PLACEMENT_FLOOR_MINUTES,
) -> StaggerPlan:
    """Spread one shift's required breaks apart in time, deterministically.

    Waived requirements need no slot and produce no result.  Assignees whose
    plan never resolved produce ``unresolved`` results carrying the plan's own
    advisory wording — this module never guesses a time for a rule it could not
    evaluate.

    ``locked`` holds times a manager already reviewed for these assignments.
    They are not re-placed; they occupy the floor before anything else is
    placed around them, and the placement policy above does not judge them.

    ``occupied`` holds break times belonging to other shifts on the same
    floor.  They consume the same coverage budget without being mistaken for a
    saved answer to this shift's requirement.  Keeping the two inputs separate
    matters when one employee works two shifts and therefore has the same
    ``(kind, ordinal)`` key twice in one day.
    """

    assigned_count = len(assignments)
    max_concurrent = max(1, assigned_count - max(0, required_staff))
    advisories: list[dict[str, Any]] = []
    results: list[StaggerResult] = []
    slots: list[_Slot] = []
    locked_by_key = {
        (entry.employee_id, entry.kind, entry.ordinal): entry for entry in locked
    }
    placed: list[_Placed] = [
        _Placed(
            start=entry.start,
            end=entry.start + timedelta(minutes=entry.duration_minutes),
            employee_id=entry.employee_id,
        )
        for entry in (*locked, *occupied)
    ]

    for assignment in sorted(assignments, key=lambda value: str(value.employee_id)):
        plan = assignment.plan
        unresolved_reason = UNRESOLVED_REASONS.get(plan.status)
        for requirement in plan.requirements:
            if requirement.waived:
                continue
            saved = locked_by_key.get(
                (assignment.employee_id, requirement.kind, requirement.ordinal)
            )
            if saved is not None:
                results.append(StaggerResult(
                    employee_id=assignment.employee_id,
                    kind=requirement.kind,
                    ordinal=requirement.ordinal,
                    status="saved",
                    suggested_start=saved.start,
                    suggested_end=saved.start + timedelta(minutes=saved.duration_minutes),
                    duration_minutes=saved.duration_minutes,
                ))
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
            slots.append(_build_slot(
                requirement,
                employee_id=assignment.employee_id,
                shift_start_local=shift_start_local,
                shift_end_local=shift_end_local,
                step_minutes=step_minutes,
                placement_floor_minutes=placement_floor_minutes,
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
    for slot in ordered:
        duration = timedelta(minutes=slot.duration_minutes)
        chosen = _choose_start(slot, placed, max_concurrent, step_minutes)
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
        placed.append(_Placed(
            start=chosen, end=chosen + duration, employee_id=slot.employee_id,
        ))
        overruns_deadline = slot.window_too_short or chosen + duration > slot.deadline
        results.append(StaggerResult(
            employee_id=slot.employee_id,
            kind=slot.kind,
            ordinal=slot.ordinal,
            status="deadline_conflict" if overruns_deadline else "suggested",
            suggested_start=chosen,
            suggested_end=chosen + duration,
            duration_minutes=slot.duration_minutes,
            reason=_deadline_reason(slot, chosen + duration) if overruns_deadline else None,
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

    if any(result.status == "deadline_conflict" for result in results):
        advisories.append({
            "check": "break_stagger",
            "code": "deadline_conflict",
            "severity": "advisory",
            "message": (
                "One or more required breaks cannot be taken inside their legal "
                "window on this shift. The suggested times run past the "
                "deadline — review the flagged assignments."
            ),
        })

    results.sort(key=lambda result: (str(result.employee_id), result.kind, result.ordinal))
    return StaggerPlan(
        results=tuple(results),
        advisories=tuple(advisories),
        max_concurrent_breaks=max_concurrent,
    )


def _clock(value: datetime) -> datetime:
    """The wall-clock face of a schedule timestamp, zone stripped.

    Saved break times carry the location offset while shift windows are
    UTC-tagged wall clock; comparing them as instants would move an early
    shift onto the previous day.  The characters are the local time on both
    sides, so compare those.
    """

    return value.replace(tzinfo=None)


def prune_planned_breaks(
    planned: Sequence[dict[str, Any]] | None,
    *,
    requirements: Sequence[BreakRequirement],
    shift_start_local: datetime,
    shift_end_local: datetime,
) -> list[dict[str, Any]]:
    """Drop saved break times the current shift and rules no longer support.

    A manager's reviewed time is kept across every write that does not
    invalidate it.  It stops being an answer at all when the requirement it
    satisfies is gone (retimed out, waived, rules changed) or when it no longer
    lands inside the shift — a break at noon on a shift that now starts at 6 PM
    is not stale advice, it is wrong advice, and the employee portal renders it
    verbatim.
    """

    if not planned:
        return []
    live = {
        (requirement.kind, requirement.ordinal)
        for requirement in requirements
        if not requirement.waived
    }
    window_start = _clock(shift_start_local)
    window_end = _clock(shift_end_local)
    survivors: list[dict[str, Any]] = []
    for entry in planned:
        if not isinstance(entry, dict):
            continue
        if (entry.get("kind"), entry.get("ordinal")) not in live:
            continue
        raw_start = entry.get("start_local")
        duration = entry.get("duration_minutes")
        if not isinstance(raw_start, str) or not isinstance(duration, int):
            continue
        try:
            start = _clock(datetime.fromisoformat(raw_start))
        except ValueError:
            continue
        if start < window_start or start + timedelta(minutes=duration) > window_end:
            continue
        survivors.append(entry)
    return survivors


def validate_planned_breaks(
    planned: Sequence[Any],
    *,
    requirements: Sequence[BreakRequirement],
    shift_start_local: datetime,
    shift_end_local: datetime,
) -> str | None:
    """Return an error message when a submitted break plan is not saveable.

    Pydantic only types the fields; it cannot know that ordinal 1 of a `meal`
    is a real requirement on THIS shift, that the time lands inside the shift,
    or that a second row for the same (kind, ordinal) makes one of the two
    permanently unreachable through a keyed lookup.  Everything the employee
    portal renders verbatim gets checked here.
    """

    live = {
        (requirement.kind, requirement.ordinal): requirement
        for requirement in requirements
        if not requirement.waived
    }
    window_start = _clock(shift_start_local)
    window_end = _clock(shift_end_local)
    seen: set[tuple[str, int]] = set()
    for entry in planned:
        key = (entry.kind, entry.ordinal)
        label = f"{entry.kind} break {entry.ordinal}"
        if key in seen:
            return f"Duplicate entry for {label}."
        seen.add(key)
        requirement = live.get(key)
        if requirement is None:
            return (
                f"{label} is not a required, unwaived break on this shift."
            ).capitalize()
        if entry.duration_minutes < requirement.duration_minutes:
            return (
                f"{label} must be at least {requirement.duration_minutes} minutes."
            ).capitalize()
        start = _clock(entry.start_local)
        if start < window_start:
            return f"{label} starts before the shift.".capitalize()
        if start + timedelta(minutes=entry.duration_minutes) > window_end:
            return f"{label} runs past the end of the shift.".capitalize()
    return None


def locked_breaks_from_planned(
    planned: Sequence[dict[str, Any]] | None,
    *,
    employee_id: UUID,
    timezone: Any,
) -> list[LockedBreak]:
    """Read saved rows back as placement inputs, in the plan's own zone."""

    locked: list[LockedBreak] = []
    for entry in planned or ():
        if not isinstance(entry, dict):
            continue
        kind = entry.get("kind")
        ordinal = entry.get("ordinal")
        raw_start = entry.get("start_local")
        duration = entry.get("duration_minutes")
        if kind not in ("meal", "rest") or not isinstance(ordinal, int):
            continue
        if not isinstance(raw_start, str) or not isinstance(duration, int):
            continue
        try:
            start = datetime.fromisoformat(raw_start)
        except ValueError:
            continue
        locked.append(LockedBreak(
            employee_id=employee_id,
            kind=kind,
            ordinal=ordinal,
            start=start.replace(tzinfo=timezone),
            duration_minutes=duration,
        ))
    return locked


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
