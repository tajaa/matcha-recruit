"""Job qualification management (`/employee-schedule/jobs`).

Jobs are company-scoped labels such as Box Office or Concessions. A job may be
limited to one location, and its qualified employee list is replaced as one
atomic roster operation.
"""

from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import get_connection
from ...dependencies import require_admin_or_client
from app.matcha.models.scheduling.employee_schedule import (
    EmployeeJobsReplace, JobCreate, JobCredentialRequirementsReplace,
    JobEmployeesReplace, JobUpdate,
)
from ...services.scheduling.job_credential_requirements import (
    fetch_job_credential_requirements,
    materialize_job_requirements,
    replace_job_credential_requirements,
)
from ...services.scheduling.schedule_rules import build_patch
from ...services.scheduling.schedule_profiles import (
    fetch_employee_jobs, replace_employee_jobs_core,
)
from ._shared import (
    assert_employee_in_company, assert_location_in_company, log_audit,
    require_company_id, serialize_job,
)

router = APIRouter()

_JOB_COLS = "id, company_id, location_id, name, color, notes, credential_grace_days, created_by, created_at, updated_at"


async def _fetch_job(conn, company_id: UUID, job_id: UUID):
    row = await conn.fetchrow(
        f"SELECT {_JOB_COLS} FROM schedule_jobs WHERE id = $1 AND company_id = $2",
        job_id, company_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    employee_rows = await conn.fetch(
        """
        SELECT employee_id FROM schedule_job_employees
        WHERE job_id = $1 AND company_id = $2 ORDER BY employee_id
        """,
        job_id, company_id,
    )
    return row, [str(r["employee_id"]) for r in employee_rows]


async def _serialize_job(conn, company_id: UUID, row, employee_ids: list[str]) -> dict:
    requirements = await fetch_job_credential_requirements(
        conn, company_id=company_id, job_ids=[row["id"]],
    )
    return serialize_job(row, employee_ids, requirements)


async def _validate_employee_ids(conn, company_id: UUID, employee_ids: list[UUID]) -> list[UUID]:
    unique_ids = list(dict.fromkeys(employee_ids))
    for employee_id in unique_ids:
        await assert_employee_in_company(conn, company_id, employee_id)
    return unique_ids


@router.get("/employees/{employee_id}/jobs")
async def get_employee_jobs(employee_id: UUID, current_user=Depends(require_admin_or_client)):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        await assert_employee_in_company(conn, company_id, employee_id)
        assignments = await fetch_employee_jobs(
            conn, company_id=company_id, employee_id=employee_id,
        )
    return {"employee_id": str(employee_id), "assignments": assignments}


@router.put("/employees/{employee_id}/jobs")
async def replace_employee_jobs(
    employee_id: UUID, body: EmployeeJobsReplace,
    current_user=Depends(require_admin_or_client),
):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        await assert_employee_in_company(conn, company_id, employee_id)
        try:
            async with conn.transaction():
                assignments = await replace_employee_jobs_core(
                    conn, company_id=company_id, employee_id=employee_id,
                    assignments=body.assignments, actor_user_id=current_user.id,
                )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except asyncpg.UniqueViolationError as exc:
            raise HTTPException(
                status_code=409, detail="Employee already has another active primary job",
            ) from exc
    return {"employee_id": str(employee_id), "assignments": assignments}


@router.get("/jobs")
async def list_jobs(
    location: UUID | None = Query(None),
    current_user=Depends(require_admin_or_client),
):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        await assert_location_in_company(conn, company_id, location)
        if location is None:
            rows = await conn.fetch(
                f"SELECT {_JOB_COLS} FROM schedule_jobs WHERE company_id = $1 ORDER BY name ASC",
                company_id,
            )
        else:
            rows = await conn.fetch(
                f"SELECT {_JOB_COLS} FROM schedule_jobs "
                "WHERE company_id = $1 AND (location_id = $2 OR location_id IS NULL) "
                "ORDER BY name ASC",
                company_id, location,
            )
        employee_rows = await conn.fetch(
            """
            SELECT job_id, employee_id FROM schedule_job_employees
            WHERE company_id = $1
            ORDER BY job_id, employee_id
            """,
            company_id,
        )
        requirements = await fetch_job_credential_requirements(
            conn, company_id=company_id, job_ids=[row["id"] for row in rows],
        )
    employees_by_job: dict[str, list[str]] = {}
    for row in employee_rows:
        employees_by_job.setdefault(str(row["job_id"]), []).append(str(row["employee_id"]))
    requirements_by_job: dict[str, list[dict]] = {}
    for requirement in requirements:
        requirements_by_job.setdefault(str(requirement["job_id"]), []).append(requirement)
    return {"jobs": [serialize_job(
        row, employees_by_job.get(str(row["id"]), []), requirements_by_job.get(str(row["id"]), []),
    ) for row in rows]}


@router.post("/jobs")
async def create_job(body: JobCreate, current_user=Depends(require_admin_or_client)):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        await assert_location_in_company(conn, company_id, body.location_id)
        employee_ids = await _validate_employee_ids(conn, company_id, body.employee_ids)
        async with conn.transaction():
            row = await conn.fetchrow(
                f"""
                INSERT INTO schedule_jobs
                    (company_id, location_id, name, color, notes, credential_grace_days, created_by)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING {_JOB_COLS}
                """,
                company_id, body.location_id, body.name.strip(), body.color, body.notes,
                body.credential_grace_days, current_user.id,
            )
            for employee_id in employee_ids:
                await conn.execute(
                    """
                    INSERT INTO schedule_job_employees
                        (job_id, employee_id, company_id, created_by)
                    VALUES ($1, $2, $3, $4)
                    """,
                    row["id"], employee_id, company_id, current_user.id,
                )
            await replace_job_credential_requirements(
                conn, company_id=company_id, job_id=row["id"],
                requirements=[item.model_dump() for item in body.credential_requirements],
                actor_user_id=current_user.id,
            )
            await log_audit(
                conn, company_id, "schedule_job", row["id"], current_user.id,
                "schedule_job.create", {"name": body.name, "employees": len(employee_ids)},
            )
        return await _serialize_job(conn, company_id, row, [str(employee_id) for employee_id in employee_ids])


@router.get("/jobs/{job_id}")
async def get_job(job_id: UUID, current_user=Depends(require_admin_or_client)):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        row, employee_ids = await _fetch_job(conn, company_id, job_id)
        return await _serialize_job(conn, company_id, row, employee_ids)


@router.put("/jobs/{job_id}")
async def update_job(
    job_id: UUID, body: JobUpdate, current_user=Depends(require_admin_or_client),
):
    company_id = await require_company_id(current_user)
    patch = body.model_dump(exclude_unset=True)
    if "name" in patch:
        patch["name"] = patch["name"].strip()
    async with get_connection() as conn:
        if "location_id" in patch:
            await assert_location_in_company(conn, company_id, patch["location_id"])
        if not patch:
            row, employee_ids = await _fetch_job(conn, company_id, job_id)
            return await _serialize_job(conn, company_id, row, employee_ids)
        set_sql, params = build_patch(patch, first_param=3)
        async with conn.transaction():
            row = await conn.fetchrow(
                f"""
                UPDATE schedule_jobs SET {set_sql}, updated_at = NOW()
                WHERE id = $1 AND company_id = $2
                RETURNING {_JOB_COLS}
                """,
                job_id, company_id, *params,
            )
            if not row:
                raise HTTPException(status_code=404, detail="Job not found")
            await log_audit(
                conn, company_id, "schedule_job", job_id, current_user.id,
                "schedule_job.update", {"fields": sorted(patch)},
            )
            employee_rows = await conn.fetch(
                """
                SELECT employee_id FROM schedule_job_employees
                WHERE job_id = $1 AND company_id = $2 ORDER BY employee_id
                """,
                job_id, company_id,
            )
        return await _serialize_job(conn, company_id, row, [str(r["employee_id"]) for r in employee_rows])


@router.put("/jobs/{job_id}/employees")
async def replace_job_employees(
    job_id: UUID, body: JobEmployeesReplace,
    current_user=Depends(require_admin_or_client),
):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        await _fetch_job(conn, company_id, job_id)
        employee_ids = await _validate_employee_ids(conn, company_id, body.employee_ids)
        async with conn.transaction():
            existing_rows = await conn.fetch(
                "SELECT employee_id FROM schedule_job_employees WHERE job_id=$1 AND company_id=$2 FOR UPDATE",
                job_id, company_id,
            )
            existing_ids = {row["employee_id"] for row in existing_rows}
            requested_ids = set(employee_ids)
            removed_ids = list(existing_ids - requested_ids)
            if removed_ids:
                await conn.execute(
                    "DELETE FROM schedule_job_employees WHERE job_id=$1 AND company_id=$2 AND employee_id=ANY($3::uuid[])",
                    job_id, company_id, removed_ids,
                )
            added_ids = list(requested_ids - existing_ids)
            for employee_id in added_ids:
                await conn.execute(
                    """
                    INSERT INTO schedule_job_employees
                        (job_id, employee_id, company_id, created_by)
                    VALUES ($1, $2, $3, $4)
                    """,
                    job_id, employee_id, company_id, current_user.id,
                )
            await materialize_job_requirements(
                conn, company_id=company_id, job_id=job_id, employee_ids=added_ids,
            )
            await log_audit(
                conn, company_id, "schedule_job", job_id, current_user.id,
                "schedule_job.employees.replace", {"employees": len(employee_ids)},
            )
    return {"job_id": str(job_id), "employee_ids": [str(employee_id) for employee_id in employee_ids]}


@router.put("/jobs/{job_id}/credential-requirements")
async def replace_job_credentials(
    job_id: UUID, body: JobCredentialRequirementsReplace,
    current_user=Depends(require_admin_or_client),
):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        await _fetch_job(conn, company_id, job_id)
        try:
            async with conn.transaction():
                requirements = await replace_job_credential_requirements(
                    conn, company_id=company_id, job_id=job_id,
                    requirements=[item.model_dump() for item in body.requirements],
                    actor_user_id=current_user.id,
                )
                await log_audit(
                    conn, company_id, "schedule_job", job_id, current_user.id,
                    "schedule_job.credential_requirements.replace", {"requirements": len(requirements)},
                )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"job_id": str(job_id), "credential_requirements": requirements}


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: UUID, current_user=Depends(require_admin_or_client)):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT id, name FROM schedule_jobs WHERE id = $1 AND company_id = $2 FOR UPDATE",
                job_id, company_id,
            )
            if not row:
                raise HTTPException(status_code=404, detail="Job not found")
            await conn.execute(
                "DELETE FROM schedule_jobs WHERE id = $1 AND company_id = $2",
                job_id, company_id,
            )
            await log_audit(
                conn, company_id, "schedule_job", job_id, current_user.id,
                "schedule_job.delete", {"name": row["name"]},
            )
    return {"ok": True, "id": str(job_id)}
