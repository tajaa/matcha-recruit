"""`PlanningInputs` — everything a scheduler (human or Huume) should be able to
SEE before deciding who works: each person's load this week, availability,
time away, caps, the open seats, the POLICY constants, whether the state's
law is on file, and the location's week-set rules.

One builder behind two readers: `schedule_assistant_context.get_schedule_overview`
gives the model the compact `roster_load` (until now it saw only a shift list
with names — no hours, no availability, no qualifications, which is how one
person ended up on nine shifts), and the REST `planning-inputs` route gives
the Schedule Pilot inputs rail the full shape. Reuses the week builder's
roster loader so the numbers here are the numbers the planner plans with.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from uuid import UUID

from .assignment_guard import POLICY_DEFAULTS
from .location_profile import bundle_leader_jobs, load_profile_bundle, missing_fields
from .schedule_review import jurisdiction_message
from .shift_compliance import jurisdiction_rule_status
from . import week_builder

_ROSTER_LOAD_CAP = 300


def _iso(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _windows_by_weekday(windows: dict[int, list[tuple[Any, Any]]]) -> dict[str, list[str]]:
    return {
        str(weekday): [f"{str(start)[:5]}–{str(end)[:5]}" for start, end in items]
        for weekday, items in sorted(windows.items())
    }


async def build_planning_inputs(
    conn, *, company_id: UUID, location_id: UUID, week_start: date,
) -> dict[str, Any]:
    week_end = week_start + timedelta(days=6)
    roster = await week_builder._load_roster_context(
        conn, company_id=company_id, location_id=location_id, week_start=week_start,
    )
    job_rows = await conn.fetch(
        "SELECT id, name FROM schedule_jobs WHERE company_id = $1", company_id,
    )
    job_names = {str(row["id"]): row["name"] for row in job_rows}

    load: dict[str, dict[str, Any]] = {}
    for assignment in roster["existing_assignments"]:
        day = assignment["starts_at"].date()
        if not (week_start <= day <= week_end):
            continue
        entry = load.setdefault(assignment["employee_id"], {"minutes": 0, "shifts": 0, "days": set()})
        entry["minutes"] += assignment["worked_minutes"]
        entry["shifts"] += 1
        entry["days"].add(day)

    people = []
    for employee in roster["employees"][:_ROSTER_LOAD_CAP]:
        entry = load.get(employee["id"], {"minutes": 0, "shifts": 0, "days": set()})
        people.append({
            "employee_id": employee["id"],
            "name": employee["name"],
            "job_title": employee.get("job_title"),
            "jobs": [
                job_names.get(job["job_id"], job["job_id"])
                for job in employee.get("jobs") or []
                if job.get("qualification_status") == "active"
            ],
            "availability_state": employee.get("availability_state"),
            "windows": _windows_by_weekday(roster["availability"].get(employee["id"], {})),
            "time_away": [
                {"start": start.isoformat(), "end": end.isoformat()}
                for start, end in roster["unavailable_ranges"].get(employee["id"], [])
            ],
            "caps": {
                "max_weekly_minutes": employee.get("max_weekly_minutes"),
                "target_weekly_minutes": employee.get("target_weekly_minutes"),
                "min_weekly_minutes": employee.get("min_weekly_minutes"),
                "allow_overtime": bool(employee.get("allow_overtime")),
                "max_consecutive_days": employee.get("max_consecutive_days"),
                "prefer_extra_hours": bool(employee.get("prefer_extra_hours")),
            },
            "load": {
                "minutes": entry["minutes"], "shifts": entry["shifts"],
                "days": sorted(day.isoformat() for day in entry["days"]),
            },
        })
    people.sort(key=lambda person: (-person["load"]["minutes"], person["name"]))

    demand = await week_builder._load_vacant_demand(
        conn, company_id=company_id, location_id=location_id, week_start=week_start, week_end=week_end,
    )
    open_slots = [
        {
            "shift_id": shift["key"], "role": shift.get("role"), "job_id": shift.get("job_id"),
            "starts_at": _iso(shift["starts_at"]), "ends_at": _iso(shift["ends_at"]),
            "required_staff": shift["required_staff"],
            "open": max(0, int(shift["required_staff"] or 1) - len(shift.get("fixed_employee_ids") or [])),
        }
        for shift in demand
    ]

    bundle = await load_profile_bundle(conn, company_id=company_id, location_id=location_id)
    missing = missing_fields(bundle)
    profile = bundle.get("profile") or {}
    return {
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "roster": people,
        "roster_truncated": len(roster["employees"]) > _ROSTER_LOAD_CAP,
        "open_slots": open_slots,
        "policy": dict(POLICY_DEFAULTS),
        "jurisdiction": jurisdiction_message(
            await jurisdiction_rule_status(conn, company_id, location_id),
        ),
        "week_rules": {"established": not missing, "missing": missing},
        "profile": {
            "operating_hours": profile.get("operating_hours") or {},
            "leader_required": profile.get("leader_required"),
            "leader_job_names": [job["name"] for job in bundle_leader_jobs(bundle)],
        },
    }


def compact_roster_load(inputs: dict[str, Any]) -> list[dict[str, Any]]:
    """The model-facing slice of `roster`: enough to pick a sensible person
    (load, jobs, availability state, caps) without the per-weekday windows."""
    return [
        {
            "employee_id": person["employee_id"],
            "name": person["name"],
            "jobs": person["jobs"],
            "availability_state": person["availability_state"],
            "scheduled_minutes": person["load"]["minutes"],
            "shift_count": person["load"]["shifts"],
            "days": person["load"]["days"],
            "time_away": person["time_away"],
            "max_weekly_minutes": person["caps"]["max_weekly_minutes"],
            "allow_overtime": person["caps"]["allow_overtime"],
        }
        for person in inputs.get("roster") or []
    ]
