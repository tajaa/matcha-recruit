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

Budget and occupancy must describe the same floor.  ``required_staff`` belongs
to one shift row, but ``occupied`` carries breaks from every row sharing the
floor, so deriving the ceiling from the opened row alone compares a row-sized
budget against a location-sized occupancy — a row with two assignees would
refuse to place anything alongside a peer row's break even with eight spare
bodies on the floor.  Callers that pass ``occupied`` therefore pass ``floor``
too: the co-planned rows' own windows and headcounts, from which the ceiling
is read at each instant.  Without it the ceiling stays the opened row's, which
is the right answer for a caller planning one shift in isolation.

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
is policy, not law — it is never written into a ``BreakRequirement``, it
applies only where the rule set states no earliest of its own or states one as
a wall-clock time rather than an offset from the shift start (see
``_build_slot``), it yields both to the legal deadline and to coverage rather
than manufacturing a conflict of either kind, and a time a manager saved is
never re-judged against it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Literal, Sequence
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
class FloorWindow:
    """One shift row's contribution to the floor, over its own window.

    ``assigned`` bodies are there; ``required`` of them have to stay.  The
    difference is how many of that row's people may be off the floor at once,
    and the sum of those differences across the rows covering an instant is the
    whole floor's spare capacity at that instant.
    """

    start: datetime
    end: datetime
    assigned: int
    required: int


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
    floor_earliest: datetime
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

    * a requirement whose earliest is statute-silent OR wall-clock-anchored
      does not start before the policy floor (``policy_earliest``), and
    * nothing starts at the shift's first instant (``floor_earliest``), even
      where a rule set encodes an earliest offset of zero.

    The two live in separate fields because they answer to different things.
    ``policy_earliest`` is a preference: placement may drop below it when
    coverage leaves no other lawful time, which is why it must not narrow the
    legal window (that would cost the shift a placement, and only placement
    time knows how many breaks compete for the window).  ``floor_earliest``
    is not a preference — a suggestion equal to the shift's own start is
    never useful to anybody — so it bounds every candidate, including the
    ones policy discourages.  Both stay off the legal ``earliest`` itself,
    which still decides whether the break fits before its deadline.

    The floor reaches a wall-clock earliest but not an offset one, because the
    two say different things.  Washington's "no less than two hours from the
    beginning of the shift" already fixes the distance from shift start, and
    policy must not push a real statutory offset later.  New York's noon day
    period opens at 11 a.m. whatever time the shift began — 30 minutes into a
    10:30 shift — which is the case the floor exists for.  Either way the floor
    only reorders candidates; the legal window is never narrowed.
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
    floor_earliest = earliest
    if floor_earliest <= shift_start_local and shift_start_local + step <= latest_start:
        # A break at the moment the shift opens is never the answer, even where
        # a rule set encodes an earliest offset of zero.
        floor_earliest = shift_start_local + step
    policy_earliest = floor_earliest
    if requirement.earliest_local is None or requirement.earliest_clock_anchored:
        floor = shift_start_local + timedelta(minutes=max(0, placement_floor_minutes))
        if policy_earliest < floor <= latest_start:
            policy_earliest = floor
    window_too_short = latest_start < earliest
    if window_too_short:
        # A window too tight to hold the break at all: keep it anchored at the
        # earliest legal moment rather than inverting the interval.  The
        # placement that comes out of this necessarily runs past the deadline,
        # which is why the slot carries the flag rather than swallowing it —
        # a break the law cannot fit is not a `suggested` one.
        latest_start = earliest
    if floor_earliest > latest_start:
        floor_earliest = latest_start
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
        floor_earliest=floor_earliest,
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

    The walk covers the whole legal window down to ``floor_earliest`` and the
    placement policy only partitions it: the first tier is every time policy
    allows, the second the times it merely discourages, closest to the floor
    first.  Dropping the latter instead would make the policy cost placements —
    breaks serialize when a shift carries no spare headcount, so a window
    shortened by two hours holds four fewer of them, and the crew who no longer
    fit would be reported as `insufficient_coverage` rather than given the
    lawful early time they had before.  The tiers stay separate (rather than
    one concatenated list) so that `_choose_start` can exhaust every allowed
    time — clear ones, then shared ones — before it offers a discouraged one.

    Discouraged is not unbounded: the tier stops at ``floor_earliest``, so
    spilling below the policy floor can never reach the shift's own start.
    """

    step = timedelta(minutes=max(1, step_minutes))
    candidates: list[datetime] = [slot.preferred]
    seen = {slot.preferred}
    offset = step
    while True:
        later = slot.preferred + offset
        earlier = slot.preferred - offset
        later_ok = later <= slot.latest_start
        earlier_ok = earlier >= slot.floor_earliest
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
    for boundary in (slot.latest_start, slot.policy_earliest, slot.floor_earliest):
        if boundary not in seen and slot.floor_earliest <= boundary <= slot.latest_start:
            seen.add(boundary)
            candidates.append(boundary)
    allowed = [value for value in candidates if value >= slot.policy_earliest]
    discouraged = sorted(
        (value for value in candidates if value < slot.policy_earliest), reverse=True,
    )
    return allowed, discouraged


def _fit(
    start: datetime,
    duration: timedelta,
    placed: Sequence[_Placed],
    capacity: Callable[[datetime], int],
    *,
    employee_id: UUID,
) -> int | None:
    """Peak headcount off the floor during [start, start+duration), or None.

    The count includes this break, so ``1`` means nobody else is off the floor
    for any part of it and anything higher is how many bodies the floor is
    down at the worst instant.  ``None`` means it cannot be placed: it would
    put more people off the floor than the floor can spare.  Capacity and
    overlap counts are evaluated at each placed interval's start and at
    ``start`` itself, which is sufficient because both only ever change at an
    interval boundary.

    One person is not two bodies, so capacity is not the only constraint: a
    break can never overlap another break belonging to the same employee, no
    matter how much spare headcount the floor carries.
    """

    end = start + duration
    overlapping = [
        entry for entry in placed
        if entry.start < end and start < entry.end
    ]
    if not overlapping:
        return 1
    if any(entry.employee_id == employee_id for entry in overlapping):
        return None
    peak = 1
    for boundary in [start, *(entry.start for entry in overlapping)]:
        if boundary < start or boundary >= end:
            continue
        concurrent = 1 + sum(
            1 for entry in overlapping
            if entry.start <= boundary < entry.end
        )
        if concurrent > capacity(boundary):
            return None
        peak = max(peak, concurrent)
    return peak


def _choose_start(
    slot: _Slot,
    placed: Sequence[_Placed],
    capacity: Callable[[datetime], int],
    step_minutes: int,
) -> datetime | None:
    """The start to suggest for one slot, or ``None`` when nothing fits.

    Stagger first, crowd last.  Within each policy tier a candidate nobody
    else is off the floor for wins outright — even when the preferred time
    itself would fit alongside others.  Two openers on a 06:30 shift both told
    to break at 08:30 because a third person clocks in then is inside the
    budget and still the wrong answer: the floor is thinnest exactly when it
    need not be.

    When the tier holds no such time, the least crowded one wins, ties going
    to the candidate closest to preferred since the walk runs outward.  Only
    once every allowed time is exhausted does a discouraged one come into play
    — a lawful early break still beats no suggestion, and a doubled-up break
    after two hours of work still beats a lone one after twenty minutes.
    """

    duration = timedelta(minutes=slot.duration_minutes)
    for tier in _candidate_tiers(slot, step_minutes):
        crowded: tuple[int, datetime] | None = None
        for candidate in tier:
            peak = _fit(candidate, duration, placed, capacity, employee_id=slot.employee_id)
            if peak is None:
                continue
            if peak == 1:
                return candidate
            if crowded is None or peak < crowded[0]:
                crowded = (peak, candidate)
        if crowded is not None:
            return crowded[1]
    return None


def _floor_spare(floor: Sequence[FloorWindow]) -> Callable[[datetime], int]:
    """Spare bodies on the shared floor at an instant, as the roster has it.

    A row contributes its own spare headcount for as long as its window covers
    the instant, so a mid-morning arrival raises the number from the minute
    they clock in and lowers it again when they leave.  Zero and negative are
    real answers here — a fully-committed floor is the normal shape, and
    `coverage_shortfall` exists to say so — which is why the floor of one
    belongs to the ceiling derived from this, not to this.
    """

    def spare_at(instant: datetime) -> int:
        return sum(
            window.assigned - window.required
            for window in floor
            if window.start <= instant < window.end
        )

    return spare_at


def _tightest_spare(
    spare_at: Callable[[datetime], int],
    floor: Sequence[FloorWindow],
    shift_start_local: datetime,
    shift_end_local: datetime,
) -> int:
    """The thinnest the floor gets while this shift is on it.

    One number for a capacity that varies by instant, for the payload and the
    shortfall advisory.  Placement itself always reads the instant, so this is
    the conservative face of the same model, never the constraint applied.
    """

    boundaries = [shift_start_local, *(
        window.start for window in floor
        if shift_start_local < window.start < shift_end_local
    )]
    return min(spare_at(boundary) for boundary in boundaries)


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
    floor: Sequence[FloorWindow] = (),
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

    ``floor`` describes the crew those occupied breaks come off, and belongs
    with them: pass both or neither.  Given it, the ceiling is read from the
    whole floor at each instant; without it, from this shift's own headcount,
    which is the right answer only when nothing else shares the floor.
    """

    assigned_count = len(assignments)
    if floor:
        spare_at = _floor_spare(floor)
        spare = _tightest_spare(spare_at, floor, shift_start_local, shift_end_local)
    else:
        row_spare = assigned_count - max(0, required_staff)
        spare_at = lambda _instant: row_spare  # noqa: E731 - one expression
        spare = row_spare

    def capacity(instant: datetime) -> int:
        return max(1, spare_at(instant))

    max_concurrent = max(1, spare)
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

    # Reads the same capacity placement does, so a fully-committed floor is
    # reported once and a row that only LOOKS short (its own headcount equals
    # its requirement, but peers cover the floor) is not.
    if assigned_count and slots and spare <= 0:
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
        chosen = _choose_start(slot, placed, capacity, step_minutes)
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
