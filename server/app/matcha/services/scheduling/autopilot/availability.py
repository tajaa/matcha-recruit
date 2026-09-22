"""Who can actually be scheduled, slot by slot, in an Autopilot week.

Capacity used to be every employee at the location for their full weekly
target — including people whose availability is unconfirmed (the planner
refuses every one of them), people on approved time away, and people whose
weekly windows end at noon. A curve sized on that roster asks for seats the
planner can never fill.

This applies the planner's OWN rules to each 30-minute slot. The job rule is
`week_builder._job_qualified`, imported rather than copied: scheduling's
CLAUDE.md records three places that decide qualification and how badly they
went when they drifted, and a fourth private copy here is exactly that.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from ..schedule_rules import availability_violations
from .policy import POLICY_SLOT_MINUTES
from .windows import DayWindow, slot_start


@dataclass(frozen=True)
class SlotAvailability:
    # Available schedulable headcount per slot of each open day's window.
    by_day: dict[date, list[int]]
    # The same, restricted to people qualified for the job that day.
    by_job_day: dict[str, dict[date, list[int]]]
    # Minutes each schedulable employee is available inside the open windows.
    minutes_by_employee: dict[str, int]
    # Jobs each schedulable employee is qualified for and available to work.
    jobs_by_employee: dict[str, frozenset[str]]

    def qualified_by_job(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for jobs in self.jobs_by_employee.values():
            for job_id in jobs:
                counts[job_id] += 1
        return dict(counts)


def slot_availability(
    windows: Sequence[DayWindow], roster: Mapping, job_ids: Sequence[str],
    gated_job_ids: set[str],
) -> SlotAvailability:
    # Lazy: week_builder imports autopilot.policy at module import, so a
    # top-level import here would be circular.
    from ..week_builder import _is_unavailable, _job_qualified

    availability = roster.get("availability") or {}
    unavailable = roster.get("unavailable_ranges") or {}
    employees = [
        employee for employee in sorted(roster.get("employees") or [], key=lambda e: str(e.get("id")))
        if employee.get("availability_state") != "unconfirmed"
    ]
    step = timedelta(minutes=POLICY_SLOT_MINUTES)
    by_day: dict[date, list[int]] = {}
    by_job_day: dict[str, dict[date, list[int]]] = {job_id: {} for job_id in job_ids}
    minutes: dict[str, int] = defaultdict(int)
    jobs_by_employee: dict[str, set[str]] = defaultdict(set)
    for window in windows:
        if window.closed or not window.slot_count or window.starts_at is None:
            continue
        counts = [0] * window.slot_count
        job_counts = {job_id: [0] * window.slot_count for job_id in job_ids}
        for employee in employees:
            employee_id = str(employee["id"])
            weekly = availability.get(employee_id) or {}
            # Fast path: most rosters log no windows, or windows that cover
            # the whole day — one check instead of one per slot.
            whole_day = not availability_violations(weekly, window.starts_at, window.ends_at)
            qualified = [
                job_id for job_id in job_ids
                if _job_qualified(employee, job_id, window.day, gated_job_ids)
            ]
            available_any = False
            for index in range(window.slot_count):
                starts = slot_start(window, index)
                if _is_unavailable(employee_id, starts.date(), unavailable):
                    continue
                if not whole_day and availability_violations(weekly, starts, starts + step):
                    continue
                available_any = True
                counts[index] += 1
                minutes[employee_id] += POLICY_SLOT_MINUTES
                for job_id in qualified:
                    job_counts[job_id][index] += 1
            if available_any:
                jobs_by_employee[employee_id].update(qualified)
        by_day[window.day] = counts
        for job_id, values in job_counts.items():
            by_job_day[job_id][window.day] = values
    return SlotAvailability(
        by_day, by_job_day, dict(minutes),
        {employee_id: frozenset(jobs) for employee_id, jobs in jobs_by_employee.items()},
    )
