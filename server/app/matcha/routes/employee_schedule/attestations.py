"""Manager attestations that affect individualized schedule guidance."""

from datetime import date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException

from app.database import get_connection
from ...dependencies import require_admin_or_client
from ...models.scheduling.employee_schedule import (
    MealWaiverAttestationResponse,
    MealWaiverAttestationUpdate,
)
from app.workers.tasks.schedule_break_refresh import enqueue_employee_schedule_break_refresh
from ._shared import assert_employee_in_company, require_company_id

router = APIRouter()


@router.get("/employees/{employee_id}/meal-break-waiver", response_model=MealWaiverAttestationResponse)
async def get_meal_break_waiver(
    employee_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    """Return the waiver attestation effective today, without exposing history."""
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        await assert_employee_in_company(conn, company_id, employee_id)
        row = await conn.fetchrow(
            """
            SELECT a.value, a.effective_from, a.confirmed_at, a.note
            FROM employee_compliance_attestations a
            JOIN employees e ON e.id = a.employee_id
            LEFT JOIN business_locations l ON l.id = e.work_location_id
            WHERE a.company_id = $1 AND a.employee_id = $2
              AND a.attestation_type = 'meal_break_waiver_on_file'
              AND a.effective_from <= COALESCE((NOW() AT TIME ZONE l.timezone)::date, CURRENT_DATE)
            ORDER BY a.effective_from DESC, a.confirmed_at DESC
            LIMIT 1
            """,
            company_id, employee_id,
        )
    if not row:
        return MealWaiverAttestationResponse(employee_id=employee_id, on_file=False, attested=False)
    return MealWaiverAttestationResponse(
        employee_id=employee_id,
        on_file=bool(row["value"]),
        attested=True,
        effective_from=row["effective_from"],
        confirmed_at=row["confirmed_at"],
        note=row["note"],
    )


@router.put("/employees/{employee_id}/meal-break-waiver")
async def attest_meal_break_waiver(
    employee_id: UUID,
    body: MealWaiverAttestationUpdate,
    current_user=Depends(require_admin_or_client),
):
    """Append a manager's yes/no confirmation that a waiver is on file.

    This deliberately records an attestation, not the signed document itself;
    legal applicability remains determined by the reviewed jurisdiction rule.
    """
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        await assert_employee_in_company(conn, company_id, employee_id)
        effective_from = body.effective_from
        if effective_from is None:
            timezone_name = await conn.fetchval(
                """SELECT l.timezone FROM employees e
                   LEFT JOIN business_locations l ON l.id=e.work_location_id
                   WHERE e.id=$1 AND e.org_id=$2""",
                employee_id, company_id,
            )
            try:
                effective_from = datetime.now(ZoneInfo(timezone_name or "UTC")).date()
            except (ZoneInfoNotFoundError, ValueError):
                effective_from = date.today()
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO employee_compliance_attestations
                    (company_id, employee_id, attestation_type, value, effective_from, confirmed_by, note)
                VALUES ($1, $2, 'meal_break_waiver_on_file', $3, $4, $5, $6)
                RETURNING id, value, effective_from, confirmed_at, note
                """,
                company_id, employee_id, body.on_file, effective_from,
                current_user.id, body.note.strip() if body.note else None,
            )
        enqueue_employee_schedule_break_refresh(
            company_id=company_id, employee_id=employee_id,
            actor_user_id=current_user.id, source="meal_break_waiver_update",
            effective_from=effective_from,
        )
    return MealWaiverAttestationResponse(
        employee_id=employee_id,
        on_file=bool(row["value"]),
        attested=True,
        effective_from=row["effective_from"],
        confirmed_at=row["confirmed_at"],
        note=row["note"],
    )
