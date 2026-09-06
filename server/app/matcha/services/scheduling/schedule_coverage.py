"""Does this week's staffing actually cover the days the store is open?

The whole-week planner answers a headcount question: fill each shift block to
its ``required_staff``.  It has no idea when the doors open, that somebody has
to be in before them and after they shut, or that a day can be fully "filled"
and still leave the last hour to one person.  A proposal that reports 20/20 and
hides a two-hour hole at close is worse than one that reports the hole, because
the manager reads the first as done.

This module is the check the planner does not do.  It is pure — no database, no
shift ids, no writes — and it never changes a plan: it produces FINDINGS the
card, the state block and the readiness payload relay verbatim.

Two vocabularies stay apart on purpose:

* ``severity`` here is ``gap`` or ``advisory``.  It is deliberately NOT
  ``block``, which everywhere else in scheduling means "this cannot be staged".
  Nothing found here prevents staging — a manager may knowingly run a thin
  close, and the answer to that is to say so, not to refuse.
* buffer minutes and the sampling slice are OPERATIONAL POLICY, not law.  Break
  and meal rules come from the compliance catalog through
  ``schedule_break_rule_store``; how long your open takes is your own call.

Times are UTC-tagged wall clock, like every other schedule timestamp: the
characters are the local time, so they are compared against ``operating_hours``
as clock faces and never converted.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Iterable, Literal, Optional, Sequence

from .location_profile import parse_clock


# Operational policy: how finely the day is sampled when looking for holes.
# 15 minutes is short enough that a missed quarter-hour at close still shows,
# and long enough that a week is a few hundred samples rather than thousands.
SLICE_MINUTES = 15

# A real hole somebody has to fix, as opposed to something worth a look.
GAP_KINDS = frozenset({
    "coverage_gap",
    "open_buffer_uncovered",
    "close_buffer_uncovered",
    "break_relief_uncovered",
    "break_relief_impossible",
})

Headcount = Literal["assigned", "required"]

_DAY_LABELS = ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")


def sunday_weekday(day: date) -> int:
    """Sun=0 … Sat=6 — the index `operating_hours` and `days_of_week` use."""
    return (day.weekday() + 1) % 7


def _clock(value: Any) -> Optional[datetime]:
    """A schedule timestamp as a naive wall-clock datetime.

    Plan shifts carry ISO strings (they have been through ``_iso``); the live
    week-state rows carry real datetimes.  Both are wall clock wearing a UTC
    tag, so the tag is dropped rather than converted.
    """
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value).replace(tzinfo=None)
        except ValueError:
            return None
    return None


def _hhmm(value: datetime) -> str:
    return value.strftime("%H:%M")


def _headcount(shift: dict[str, Any], mode: Headcount) -> int:
    """How many bodies this shift puts on the floor.

    ``required`` judges the PATTERN — readiness asks "would this week's shape
    cover the day even if everyone showed up?".  ``assigned`` judges the PLAN,
    and an unfilled slot contributes nothing: the whole point is that a hole
    the planner could not fill is still a hole.
    """
    if mode == "required":
        try:
            return max(0, int(shift.get("required_staff") or 0))
        except (TypeError, ValueError):
            return 0
    return (
        len(shift.get("fixed_employee_ids") or [])
        + len(shift.get("proposed_assignments") or [])
        # Live published rows name their staffing this way; plan shifts never
        # carry the key, so the three never double-count each other.
        + len(shift.get("employee_ids") or [])
    )


class _Interval:
    __slots__ = ("start", "end", "staff", "job_id", "key", "role")

    def __init__(self, *, start: datetime, end: datetime, staff: int,
                 job_id: Optional[str], key: Optional[str], role: Optional[str]):
        self.start = start
        self.end = end
        self.staff = staff
        self.job_id = job_id
        self.key = key
        self.role = role

    def covers(self, moment: datetime) -> bool:
        return self.start <= moment < self.end

    def overlaps(self, start: datetime, end: datetime) -> bool:
        return self.start < end and self.end > start


def _intervals(shifts: Iterable[dict[str, Any]], mode: Headcount) -> list[_Interval]:
    out: list[_Interval] = []
    for shift in shifts or ():
        start = _clock(shift.get("starts_at"))
        end = _clock(shift.get("ends_at"))
        if start is None or end is None or end <= start:
            continue
        job_id = shift.get("job_id")
        out.append(_Interval(
            start=start, end=end, staff=_headcount(shift, mode),
            job_id=str(job_id) if job_id else None,
            key=str(shift.get("key") or shift.get("id") or "") or None,
            role=shift.get("role"),
        ))
    return out


def make_finding(
    kind: str, severity: str, detail: str, *, day: Optional[date] = None,
    window: Optional[tuple[datetime, datetime]] = None,
    shift_key: Optional[str] = None, job_id: Optional[str] = None,
    job_name: Optional[str] = None, employee_name: Optional[str] = None,
    minutes: Optional[int] = None,
) -> dict[str, Any]:
    """One finding, in the single shape every consumer renders.

    Public because the break-relief pass in ``week_builder`` emits findings
    too: a second hand-rolled dict there is how a key quietly goes missing on
    one kind and the card renders a blank row.  Every value is JSON-safe — the
    whole list is persisted into ``schedule_generation_runs.proposal``.
    """
    return {
        "kind": kind,
        "severity": severity,
        "day": day.isoformat() if day else None,
        "weekday": sunday_weekday(day) if day else None,
        "window": (
            {"start": _hhmm(window[0]), "end": _hhmm(window[1])} if window else None
        ),
        "shift_key": shift_key,
        "job_id": job_id,
        "job_name": job_name,
        "employee_name": employee_name,
        "minutes": minutes,
        "detail": detail,
    }


def sort_findings(findings: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stable, day-then-time order so the same week always reads the same."""
    return sorted(
        findings,
        key=lambda item: (
            item.get("day") or "",
            (item.get("window") or {}).get("start") or "",
            item.get("kind") or "",
            item.get("shift_key") or "",
        ),
    )


def _zero_runs(
    grid: list[datetime], staffed: list[int], slice_delta: timedelta, window_end: datetime,
) -> list[tuple[datetime, datetime]]:
    """Contiguous stretches of the sampled day with nobody on."""
    runs: list[tuple[datetime, datetime]] = []
    run_start: Optional[datetime] = None
    for index, moment in enumerate(grid):
        if staffed[index] == 0:
            if run_start is None:
                run_start = moment
            continue
        if run_start is not None:
            runs.append((run_start, moment))
            run_start = None
    if run_start is not None:
        runs.append((run_start, min(grid[-1] + slice_delta, window_end)))
    return runs


def _split_run(
    run: tuple[datetime, datetime], *, window_start: datetime, open_dt: datetime,
    close_dt: datetime, window_end: datetime,
) -> list[tuple[str, datetime, datetime]]:
    """Attribute one uncovered stretch to prep / open hours / cleanup.

    A single run can straddle two of them (nobody in from 07:30 until 09:00 on
    an 08:00 open), and reporting that as one undifferentiated hole loses the
    distinction the manager acts on: missing the prep window is a different
    fix from being short during trade.
    """
    segments: list[tuple[str, datetime, datetime]] = []
    for kind, lo, hi in (
        ("open_buffer_uncovered", window_start, open_dt),
        ("coverage_gap", open_dt, close_dt),
        ("close_buffer_uncovered", close_dt, window_end),
    ):
        start = max(run[0], lo)
        end = min(run[1], hi)
        if start < end:
            segments.append((kind, start, end))
    return segments


def _leader_findings(
    *, intervals: list[_Interval], leader_job_id: str, leader_job_name: Optional[str],
    day: date, window_start: datetime, open_dt: datetime, close_dt: datetime,
    window_end: datetime, slice_delta: timedelta, uncovered: list[tuple[datetime, datetime]],
) -> list[dict[str, Any]]:
    """A set leader rule that nobody satisfies at open or close.

    Advisory, not a gap: somebody IS on the floor (a gap would have been
    reported instead, and is suppressed here so the same hole is not read
    twice), they just are not the person who can open the till or lock up.
    """
    label = leader_job_name or "shift lead"
    findings: list[dict[str, Any]] = []
    checks = (
        ("leader_absent_at_open", window_start, open_dt + slice_delta, "at open"),
        ("leader_absent_at_close", close_dt - slice_delta, window_end, "at close"),
    )
    for kind, lo, hi, phrase in checks:
        if any(gap_start < hi and gap_end > lo for gap_start, gap_end in uncovered):
            continue
        if any(
            item.job_id == leader_job_id and item.overlaps(lo, hi)
            for item in intervals
        ):
            continue
        findings.append(make_finding(
            kind, "advisory",
            f"No {label} is scheduled {phrase} on {_DAY_LABELS[sunday_weekday(day)]}.",
            day=day, window=(lo, hi), job_id=leader_job_id, job_name=leader_job_name,
        ))
    return findings


def evaluate_week_coverage(
    *,
    plan_shifts: Sequence[dict[str, Any]],
    baseline_shifts: Sequence[dict[str, Any]] = (),
    operating_hours: Optional[dict[str, Any]],
    open_buffer_minutes: int = 0,
    close_buffer_minutes: int = 0,
    leader_job_id: Optional[str] = None,
    leader_job_name: Optional[str] = None,
    week_start: date,
    headcount: Headcount = "assigned",
    slice_minutes: int = SLICE_MINUTES,
) -> list[dict[str, Any]]:
    """Findings for one week of staffing against the store's own hours.

    ``baseline_shifts`` are shifts that already exist and are not part of the
    proposal — the published half of a partly-built week.  They are floor the
    store already has, so leaving them out would report a store that is
    genuinely covered as empty for most of the week.

    Returns ``[]`` when everything checks out, and one ``no_hours_known``
    finding per day the store has never said anything about — silence about a
    day is never reported as green.
    """
    hours = operating_hours or {}
    slice_delta = timedelta(minutes=max(1, int(slice_minutes)))
    open_buffer = timedelta(minutes=max(0, int(open_buffer_minutes or 0)))
    close_buffer = timedelta(minutes=max(0, int(close_buffer_minutes or 0)))
    leader = str(leader_job_id) if leader_job_id else None

    plan_intervals = _intervals(plan_shifts, headcount)
    # A published shift's staffing is whoever is on it; "required" is a
    # question about the pattern being proposed, not about work already
    # committed, so the baseline always counts real bodies.
    intervals = plan_intervals + _intervals(baseline_shifts, "assigned")
    findings: list[dict[str, Any]] = []

    days = [week_start + timedelta(days=offset) for offset in range(7)]
    windows: dict[date, tuple[datetime, datetime, datetime, datetime]] = {}
    for day in days:
        window = hours.get(str(sunday_weekday(day)))
        if not isinstance(window, dict):
            continue
        try:
            opens = parse_clock(window["open"])
            closes = parse_clock(window["close"])
        except (KeyError, TypeError, ValueError):
            continue
        open_dt = datetime.combine(day, opens)
        close_dt = datetime.combine(day, closes)
        if close_dt <= open_dt:
            # Overnight (a bar that shuts at 02:00) — the close belongs to the
            # next calendar day, and the whole window is still this day's.
            close_dt += timedelta(days=1)
        windows[day] = (open_dt - open_buffer, open_dt, close_dt, close_dt + close_buffer)

    for day in days:
        bounds = windows.get(day)
        if bounds is None:
            continue
        window_start, open_dt, close_dt, window_end = bounds
        grid: list[datetime] = []
        moment = window_start
        while moment < window_end:
            grid.append(moment)
            moment += slice_delta
        if not grid:
            continue
        staffed = [
            sum(item.staff for item in intervals if item.covers(sample))
            for sample in grid
        ]
        runs = _zero_runs(grid, staffed, slice_delta, window_end)
        for run in runs:
            for kind, start, end in _split_run(
                run, window_start=window_start, open_dt=open_dt,
                close_dt=close_dt, window_end=window_end,
            ):
                minutes = int((end - start).total_seconds() // 60)
                if kind == "open_buffer_uncovered":
                    detail = (
                        f"Nobody is scheduled for the open prep on "
                        f"{_DAY_LABELS[sunday_weekday(day)]} "
                        f"({_hhmm(start)}–{_hhmm(end)}, {minutes} min before the doors open)."
                    )
                elif kind == "close_buffer_uncovered":
                    detail = (
                        f"Nobody is scheduled to close on "
                        f"{_DAY_LABELS[sunday_weekday(day)]} "
                        f"({_hhmm(start)}–{_hhmm(end)}, {minutes} min after the doors shut)."
                    )
                else:
                    detail = (
                        f"Nobody is scheduled {_hhmm(start)}–{_hhmm(end)} on "
                        f"{_DAY_LABELS[sunday_weekday(day)]} while the store is open "
                        f"({minutes} min uncovered)."
                    )
                findings.append(make_finding(
                    kind, "gap", detail, day=day, window=(start, end), minutes=minutes,
                ))

        if leader:
            findings.extend(_leader_findings(
                intervals=intervals, leader_job_id=leader, leader_job_name=leader_job_name,
                day=day, window_start=window_start, open_dt=open_dt, close_dt=close_dt,
                window_end=window_end, slice_delta=slice_delta, uncovered=runs,
            ))

        # Thin-at-one-end: the day is covered, but everyone is rostered onto
        # the same half of it.  Only reported against a genuinely busier other
        # end, so a store that runs one person all day is left alone.
        first_hour = max(
            (count for sample, count in zip(grid, staffed)
             if sample < window_start + timedelta(hours=1)),
            default=0,
        )
        last_hour = max(
            (count for sample, count in zip(grid, staffed)
             if sample >= window_end - timedelta(hours=1)),
            default=0,
        )
        if first_hour >= 2 and last_hour == 1:
            findings.append(make_finding(
                "thin_close", "advisory",
                f"{_DAY_LABELS[sunday_weekday(day)]} opens with {first_hour} on but closes "
                f"with one — check the last hour is really a one-person job.",
                day=day, window=(window_end - timedelta(hours=1), window_end),
            ))
        elif last_hour >= 2 and first_hour == 1:
            findings.append(make_finding(
                "thin_open", "advisory",
                f"{_DAY_LABELS[sunday_weekday(day)]} opens with one on but closes with "
                f"{last_hour} — check the first hour is really a one-person job.",
                day=day, window=(window_start, window_start + timedelta(hours=1)),
            ))

    # Demand the hours cannot explain. A shift is judged against EVERY day's
    # window, not just its own start date, so an overnight shift covering the
    # next morning's prep is not reported as scheduled outside hours.
    unknown_days: set[date] = set()
    for item in plan_intervals:
        if any(item.overlaps(lo, hi) for lo, _open, _close, hi in windows.values()):
            continue
        day = item.start.date()
        key = str(sunday_weekday(day))
        if key not in hours:
            # Handled by the no_hours_known pass below — an absent key is
            # "nobody has said", which `hours.get(key) is None` would otherwise
            # read as "closed that day".
            continue
        label = f"{_hhmm(item.start)}–{_hhmm(item.end)}"
        if hours.get(key) is None:
            findings.append(make_finding(
                "demand_on_closed_day", "advisory",
                f"A shift is scheduled {label} on {_DAY_LABELS[sunday_weekday(day)]}, "
                f"which is set as a closed day.",
                day=day, window=(item.start, item.end), shift_key=item.key, job_id=item.job_id,
            ))
        else:
            findings.append(make_finding(
                "demand_outside_hours", "advisory",
                f"A shift runs {label} on {_DAY_LABELS[sunday_weekday(day)]}, outside the "
                f"store's opening hours and buffers.",
                day=day, window=(item.start, item.end), shift_key=item.key, job_id=item.job_id,
            ))
    # Every day carrying work but no saved hours, whether or not that work
    # happens to line up with a neighbouring day's window: an unchecked day is
    # reported as unchecked.
    week_days = set(days)
    for item in plan_intervals:
        day = item.start.date()
        # Clamped to the seven days being judged: an overnight shift can start
        # on the last instant of the window, and a finding dated outside the
        # week the manager is looking at is noise.
        if day in week_days and str(sunday_weekday(day)) not in hours:
            unknown_days.add(day)
    for day in sorted(unknown_days):
        findings.append(make_finding(
            "no_hours_known", "advisory",
            f"{_DAY_LABELS[sunday_weekday(day)]} has shifts but no saved opening hours, "
            f"so coverage was not checked for it.",
            day=day,
        ))

    return sort_findings(findings)
