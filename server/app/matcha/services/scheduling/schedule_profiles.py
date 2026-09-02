"""Shared employee scheduling-profile, availability, and job-assignment writes.

All writers are caller-owns-the-transaction so admin and portal routes cannot
drift. An absent profile is deliberately serialized as ``unconfirmed``; it is
never guessed from an empty legacy availability table.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from .job_credential_requirements import (
    fetch_job_credential_requirements, materialize_job_requirements,
)
from .shift_writes import log_audit


PROFILE_DEFAULTS = {
    "availability_state": "unconfirmed",
    "availability_confirmed_at": None,
    "availability_confirmed_by": None,
    "min_weekly_minutes": None,
    "target_weekly_minutes": None,
    "max_weekly_minutes": None,
    "max_consecutive_days": None,
    "allow_overtime": False,
    "prefer_extra_hours": False,
}


@dataclass(frozen=True)
class ScheduleProfile:
    employee_id: UUID
    availability_state: str
    availability_confirmed_at: datetime | None
    availability_confirmed_by: UUID | None
    min_weekly_minutes: int | None
    target_weekly_minutes: int | None
    max_weekly_minutes: int | None
    max_consecutive_days: int | None
    allow_overtime: bool
    prefer_extra_hours: bool


def serialize_schedule_profile(profile: ScheduleProfile) -> dict:
    return {**asdict(profile), "employee_id": str(profile.employee_id)}


def _schedule_profile(employee_id: UUID, row=None) -> ScheduleProfile:
    values = {**PROFILE_DEFAULTS, **(dict(row) if row else {})}
    return ScheduleProfile(
        employee_id=employee_id,
        availability_state=values["availability_state"],
        availability_confirmed_at=values["availability_confirmed_at"],
        availability_confirmed_by=values["availability_confirmed_by"],
        min_weekly_minutes=values["min_weekly_minutes"],
        target_weekly_minutes=values["target_weekly_minutes"],
        max_weekly_minutes=values["max_weekly_minutes"],
        max_consecutive_days=values["max_consecutive_days"],
        allow_overtime=values["allow_overtime"],
        prefer_extra_hours=values["prefer_extra_hours"],
    )


def effective_availability_state(
    requested_state: str | None, windows: Sequence[Any],
) -> Literal["always_available", "windows"]:
    """Resolve backward-compatible PUT semantics; never return unconfirmed."""
    return requested_state or ("windows" if windows else "always_available")


def validate_weekly_minutes(profile: dict) -> None:
    minimum = profile.get("min_weekly_minutes")
    target = profile.get("target_weekly_minutes")
    maximum = profile.get("max_weekly_minutes")
    if minimum is not None and target is not None and minimum > target:
        raise ValueError("min_weekly_minutes cannot exceed target_weekly_minutes")
    if target is not None and maximum is not None and target > maximum:
        raise ValueError("target_weekly_minutes cannot exceed max_weekly_minutes")
    if minimum is not None and maximum is not None and minimum > maximum:
        raise ValueError("min_weekly_minutes cannot exceed max_weekly_minutes")


async def fetch_effective_job_employee_ids(
    conn, *, company_id: UUID, job_id: UUID | None,
    employee_ids: Sequence[UUID], as_of: date,
) -> set[UUID]:
    """Employees actively qualified for ``job_id`` on the shift date.

    A jobless shift remains ungated. Qualification dates are evaluated against
    the scheduled work date rather than today's date so future scheduling and
    later retimes make the same decision.
    """
    unique_ids = list(dict.fromkeys(employee_ids))
    if job_id is None:
        return set(unique_ids)
    if not unique_ids:
        return set()
    rows = await conn.fetch(
        """SELECT je.employee_id
             FROM schedule_job_employees je
             JOIN schedule_jobs j ON j.id=je.job_id AND j.company_id=je.company_id
            WHERE je.company_id=$1 AND je.job_id=$2
              AND je.employee_id=ANY($3::uuid[])
              AND je.qualification_status='active'
              AND (je.qualified_from IS NULL OR je.qualified_from <= $4)
              AND (je.qualified_until IS NULL OR je.qualified_until >= $4)""",
        company_id, job_id, unique_ids, as_of,
    )
    return {row["employee_id"] for row in rows}


async def fetch_schedule_profile(
    conn, *, company_id: UUID, employee_id: UUID,
) -> ScheduleProfile:
    row = await conn.fetchrow(
        """SELECT availability_state, availability_confirmed_at,
                  availability_confirmed_by, min_weekly_minutes,
                  target_weekly_minutes, max_weekly_minutes,
                  max_consecutive_days, allow_overtime, prefer_extra_hours
             FROM employee_schedule_profiles
            WHERE company_id=$1 AND employee_id=$2""",
        company_id, employee_id,
    )
    return _schedule_profile(employee_id, row)


async def upsert_schedule_profile(
    conn, *, company_id: UUID, employee_id: UUID,
    values: Mapping[str, object], actor_user_id: UUID | None,
) -> ScheduleProfile:
    current = await fetch_schedule_profile(
        conn, company_id=company_id, employee_id=employee_id,
    )
    merged = {**asdict(current), **values}
    validate_weekly_minutes(merged)
    state_changed = "availability_state" in values
    availability_confirmed = state_changed and merged["availability_state"] != "unconfirmed"
    row = await conn.fetchrow(
        """INSERT INTO employee_schedule_profiles
               (company_id, employee_id, availability_state,
                availability_confirmed_at, availability_confirmed_by,
                min_weekly_minutes, target_weekly_minutes, max_weekly_minutes,
                max_consecutive_days, allow_overtime, prefer_extra_hours)
           VALUES ($1,$2,$3,
                   CASE WHEN $12 THEN NOW() WHEN $14 THEN NULL ELSE $4 END,
                   CASE WHEN $12 THEN $13::uuid WHEN $14 THEN NULL ELSE $5::uuid END,
                   $6,$7,$8,$9,$10,$11)
           ON CONFLICT (employee_id) DO UPDATE SET
               availability_state=EXCLUDED.availability_state,
               availability_confirmed_at=EXCLUDED.availability_confirmed_at,
               availability_confirmed_by=EXCLUDED.availability_confirmed_by,
               min_weekly_minutes=EXCLUDED.min_weekly_minutes,
               target_weekly_minutes=EXCLUDED.target_weekly_minutes,
               max_weekly_minutes=EXCLUDED.max_weekly_minutes,
               max_consecutive_days=EXCLUDED.max_consecutive_days,
               allow_overtime=EXCLUDED.allow_overtime,
               prefer_extra_hours=EXCLUDED.prefer_extra_hours,
               updated_at=NOW()
           RETURNING availability_state, availability_confirmed_at,
                     availability_confirmed_by, min_weekly_minutes,
                     target_weekly_minutes, max_weekly_minutes,
                     max_consecutive_days, allow_overtime, prefer_extra_hours""",
        company_id, employee_id, merged["availability_state"],
        merged["availability_confirmed_at"], merged["availability_confirmed_by"],
        merged["min_weekly_minutes"], merged["target_weekly_minutes"],
        merged["max_weekly_minutes"], merged["max_consecutive_days"],
        merged["allow_overtime"], merged["prefer_extra_hours"],
        availability_confirmed, actor_user_id, state_changed,
    )
    return _schedule_profile(employee_id, row)


async def fetch_availability_windows(
    conn, *, company_id: UUID, employee_id: UUID,
) -> list[dict]:
    rows = await conn.fetch(
        """SELECT weekday, start_time, end_time
             FROM schedule_employee_availability
            WHERE company_id=$1 AND employee_id=$2
            ORDER BY weekday, start_time""",
        company_id, employee_id,
    )
    return [
        {"weekday": row["weekday"], "start_time": str(row["start_time"])[:5],
         "end_time": str(row["end_time"])[:5]}
        for row in rows
    ]


async def replace_availability_core(
    conn, *, company_id: UUID, employee_id: UUID,
    windows: Sequence[Any], availability_state: str | None,
    actor_user_id: UUID | None, actor_kind: Literal["admin", "employee"],
) -> dict:
    resolved_state = effective_availability_state(availability_state, windows)
    await conn.execute(
        "DELETE FROM schedule_employee_availability WHERE company_id=$1 AND employee_id=$2",
        company_id, employee_id,
    )
    for window in windows:
        await conn.execute(
            """INSERT INTO schedule_employee_availability
                   (company_id, employee_id, weekday, start_time, end_time)
               VALUES ($1,$2,$3,$4,$5)""",
            company_id, employee_id, window.weekday, window.start_time, window.end_time,
        )
    profile = await upsert_schedule_profile(
        conn, company_id=company_id, employee_id=employee_id,
        values={"availability_state": resolved_state},
        actor_user_id=actor_user_id,
    )
    await log_audit(
        conn, company_id, "availability", employee_id, actor_user_id,
        "availability.update",
        {"windows": len(windows), "availability_state": resolved_state, "actor": actor_kind},
    )
    return {"saved": len(windows), "state": resolved_state, "profile": profile}


async def fetch_employee_jobs(
    conn, *, company_id: UUID, employee_id: UUID,
) -> list[dict]:
    rows = await conn.fetch(
        """SELECT je.job_id, j.name AS job_name, j.location_id, je.is_primary,
                  je.qualification_status, je.qualified_from,
                  je.qualified_until, je.notes
             FROM schedule_job_employees je
             JOIN schedule_jobs j ON j.id=je.job_id AND j.company_id=je.company_id
            WHERE je.company_id=$1 AND je.employee_id=$2
            ORDER BY je.is_primary DESC, j.name""",
        company_id, employee_id,
    )
    requirements = await fetch_job_credential_requirements(
        conn, company_id=company_id, job_ids=[row["job_id"] for row in rows],
    )
    by_job: dict[str, list[dict]] = {}
    for requirement in requirements:
        by_job.setdefault(str(requirement["job_id"]), []).append(requirement)
    return [
        {**dict(row), "job_id": str(row["job_id"]),
         "location_id": str(row["location_id"]) if row["location_id"] else None,
         "credential_requirements": by_job.get(str(row["job_id"]), [])}
        for row in rows
    ]


async def replace_employee_jobs_core(
    conn, *, company_id: UUID, employee_id: UUID,
    assignments: Sequence[Any], actor_user_id: UUID | None,
) -> list[dict]:
    employee_location_id = await conn.fetchval(
        "SELECT work_location_id FROM employees WHERE id=$1 AND org_id=$2",
        employee_id, company_id,
    )
    job_ids = [assignment.job_id for assignment in assignments]
    if job_ids:
        valid_rows = await conn.fetch(
            """SELECT id FROM schedule_jobs
                WHERE company_id=$1 AND id=ANY($2::uuid[])
                  AND (location_id IS NULL OR location_id=$3)""",
            company_id, job_ids, employee_location_id,
        )
        if {row["id"] for row in valid_rows} != set(job_ids):
            raise ValueError("One or more jobs do not belong to the employee's work location")
    existing = await conn.fetch(
        """SELECT job_id, qualification_status FROM schedule_job_employees
            WHERE company_id=$1 AND employee_id=$2 FOR UPDATE""",
        company_id, employee_id,
    )
    existing_ids = {row["job_id"] for row in existing}
    previously_active = {
        row["job_id"] for row in existing if row["qualification_status"] == "active"
    }
    requested_ids = set(job_ids)
    removed_ids = list(existing_ids - requested_ids)
    if removed_ids:
        await conn.execute(
            """DELETE FROM schedule_job_employees
                WHERE company_id=$1 AND employee_id=$2 AND job_id=ANY($3::uuid[])""",
            company_id, employee_id, removed_ids,
        )
    # Clear first so switching the primary job cannot transiently violate the
    # partial unique index before the old primary row is updated.
    await conn.execute(
        """UPDATE schedule_job_employees SET is_primary=false
            WHERE company_id=$1 AND employee_id=$2 AND is_primary""",
        company_id, employee_id,
    )
    assignment_by_job = {assignment.job_id: assignment for assignment in assignments}
    for job in assignments:
        await conn.execute(
            """INSERT INTO schedule_job_employees
                   (job_id, employee_id, company_id, created_by, is_primary,
                    qualification_status, qualified_from, qualified_until, notes)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
               ON CONFLICT (job_id, employee_id) DO UPDATE SET
                   is_primary=EXCLUDED.is_primary,
                   qualification_status=EXCLUDED.qualification_status,
                   qualified_from=EXCLUDED.qualified_from,
                   qualified_until=EXCLUDED.qualified_until,
                   notes=EXCLUDED.notes""",
            job.job_id, employee_id, company_id, actor_user_id, job.is_primary,
            job.qualification_status, job.qualified_from, job.qualified_until, job.notes,
        )
    newly_active = {
        job_id for job_id, assignment in assignment_by_job.items()
        if assignment.qualification_status == "active" and job_id not in previously_active
    }
    for job_id in newly_active:
        await materialize_job_requirements(
            conn, company_id=company_id, job_id=job_id, employee_ids=[employee_id],
        )
    await log_audit(
        conn, company_id, "schedule_job", employee_id, actor_user_id,
        "schedule_job.employee_assignments.replace",
        {"before_job_ids": sorted(str(job_id) for job_id in existing_ids),
         "after_job_ids": sorted(str(job_id) for job_id in requested_ids)},
    )
    return await fetch_employee_jobs(conn, company_id=company_id, employee_id=employee_id)
