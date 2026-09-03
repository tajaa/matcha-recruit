"""Job-scoped credential configuration and employee requirement materialization."""
from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from uuid import UUID

from app.core.services.credential_template_service import find_hidden_credential_types


async def materialize_job_requirements(
    conn,
    *,
    company_id: UUID,
    job_id: UUID,
    employee_ids: Sequence[UUID] | None = None,
) -> int:
    """Create evidence rows for a job's assigned employees.

    Scheduling evaluates the live job rule, so this is safe to repeat and is
    primarily what makes the correct document upload slot visible immediately.
    Existing company-wide requirements keep that broader scope.
    """
    employees = list(employee_ids) if employee_ids is not None else [
        row["employee_id"] for row in await conn.fetch(
            "SELECT employee_id FROM schedule_job_employees WHERE company_id=$1 AND job_id=$2",
            company_id, job_id,
        )
    ]
    if not employees:
        return 0
    rows = await conn.fetch(
        """SELECT e.id AS employee_id, jr.credential_type_id, jr.is_required,
                  GREATEST(COALESCE(e.start_date, e.created_at::date), jr.effective_from)
                    + COALESCE(j.credential_grace_days, c.default_credential_grace_days) AS due_date
             FROM schedule_job_credential_requirements jr
             JOIN schedule_jobs j ON j.id=jr.job_id AND j.company_id=jr.company_id
             JOIN companies c ON c.id=jr.company_id
             JOIN employees e ON e.id = ANY($3::uuid[]) AND e.org_id=jr.company_id
            WHERE jr.company_id=$1 AND jr.job_id=$2 AND jr.is_required""",
        company_id, job_id, employees,
    )
    count = 0
    for row in rows:
        # The cross join above produces a row for each employee/type.  This
        # UPSERT intentionally does not clear document/verification history.
        await conn.execute(
            """INSERT INTO employee_credential_requirements
                   (employee_id, credential_type_id, status, is_required, due_date, applies_company_wide)
               SELECT e.id, $3, 'pending', $4, $5, false
                 FROM employees e WHERE e.id=$1 AND e.org_id=$2
               ON CONFLICT (employee_id, credential_type_id) DO UPDATE
                  SET is_required=true,
                      due_date=LEAST(COALESCE(employee_credential_requirements.due_date, EXCLUDED.due_date), EXCLUDED.due_date),
                      updated_at=NOW()""",
            row["employee_id"], company_id, row["credential_type_id"], row["is_required"], row["due_date"],
        )
        count += 1
    return count


async def reconcile_company_job_requirements(conn, *, company_id: UUID) -> int:
    jobs = await conn.fetch("SELECT id FROM schedule_jobs WHERE company_id=$1", company_id)
    total = 0
    for job in jobs:
        total += await materialize_job_requirements(conn, company_id=company_id, job_id=job["id"])
    return total


async def replace_job_credential_requirements(
    conn,
    *,
    company_id: UUID,
    job_id: UUID,
    requirements: Sequence[dict],
    actor_user_id: UUID | None,
) -> list[dict]:
    """Replace a job's configured credential rules without resetting retained rules' effective date."""
    normalized: dict[UUID, dict] = {}
    for requirement in requirements:
        normalized[requirement["credential_type_id"]] = requirement
    if normalized:
        valid = await conn.fetch(
            """SELECT id FROM credential_types
               WHERE id = ANY($1::uuid[])
                 AND (company_id IS NULL OR company_id = $2)""",
            list(normalized), company_id,
        )
        if len(valid) != len(normalized):
            raise ValueError("One or more credential types do not exist")
    existing = await conn.fetch(
        "SELECT credential_type_id FROM schedule_job_credential_requirements WHERE company_id=$1 AND job_id=$2 FOR UPDATE",
        company_id, job_id,
    )
    existing_ids = {row["credential_type_id"] for row in existing}
    # Types the company removed from its dropdowns cannot be attached to a job
    # by a stale tab or a direct API call.  Retained rules are exempt so an
    # already-configured requirement stays editable and removable.
    hidden = await find_hidden_credential_types(
        conn, company_id=company_id, credential_type_ids=list(set(normalized) - existing_ids),
    )
    if hidden:
        raise ValueError("One or more credential types are not available to this company")
    remove_ids = list(existing_ids - set(normalized))
    if remove_ids:
        await conn.execute(
            "DELETE FROM schedule_job_credential_requirements WHERE company_id=$1 AND job_id=$2 AND credential_type_id = ANY($3::uuid[])",
            company_id, job_id, remove_ids,
        )
    for credential_type_id, item in normalized.items():
        await conn.execute(
            """INSERT INTO schedule_job_credential_requirements
                   (company_id, job_id, credential_type_id, is_required, schedule_blocking, notes, created_by)
               VALUES ($1,$2,$3,$4,$5,$6,$7)
               ON CONFLICT (job_id, credential_type_id) DO UPDATE
                  SET is_required=EXCLUDED.is_required,
                      schedule_blocking=EXCLUDED.schedule_blocking,
                      notes=EXCLUDED.notes,
                      updated_at=NOW()""",
            company_id, job_id, credential_type_id, item.get("is_required", True),
            item.get("schedule_blocking", True), item.get("notes"), actor_user_id,
        )
    await materialize_job_requirements(conn, company_id=company_id, job_id=job_id)
    return await fetch_job_credential_requirements(conn, company_id=company_id, job_ids=[job_id])


async def fetch_job_credential_requirements(conn, *, company_id: UUID, job_ids: Sequence[UUID]) -> list[dict]:
    if not job_ids:
        return []
    rows = await conn.fetch(
        """SELECT jr.id, jr.job_id, jr.credential_type_id, jr.is_required, jr.schedule_blocking,
                  jr.effective_from, jr.notes, ct.key AS credential_type_key,
                  ct.label AS credential_type_label, ct.has_expiration
             FROM schedule_job_credential_requirements jr
             JOIN credential_types ct ON ct.id=jr.credential_type_id
            WHERE jr.company_id=$1 AND jr.job_id = ANY($2::uuid[])
            ORDER BY ct.category, ct.label""",
        company_id, list(job_ids),
    )
    return [dict(row) for row in rows]


def job_restriction_starts_on(row, *, employee_start_date: date | None) -> date:
    anchor = max(employee_start_date or row["employee_created_on"], row["effective_from"])
    return anchor + timedelta(days=row["grace_days"])
