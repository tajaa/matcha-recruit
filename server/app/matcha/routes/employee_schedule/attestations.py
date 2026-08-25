"""Manager attestations that affect individualized schedule guidance."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.database import get_connection
from ...dependencies import require_admin_or_client
from ...models.scheduling.employee_schedule import (
    MealWaiverAttestationResponse,
    MealWaiverAttestationUpdate,
)
from ...services.scheduling.schedule_guidance import refresh_assignment_break_guidance
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
            SELECT value, effective_from, confirmed_at, note
            FROM employee_compliance_attestations
            WHERE company_id = $1 AND employee_id = $2
              AND attestation_type = 'meal_break_waiver_on_file'
              AND effective_from <= CURRENT_DATE
            ORDER BY effective_from DESC, confirmed_at DESC
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
    effective_from = body.effective_from or date.today()
    async with get_connection() as conn:
        await assert_employee_in_company(conn, company_id, employee_id)
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
        future_assignments = await conn.fetch(
            """
            SELECT s.id AS shift_id, s.location_id, s.starts_at, s.ends_at
            FROM schedule_shift_assignments a
            JOIN schedule_shifts s ON s.id = a.shift_id
            WHERE a.company_id = $1 AND a.employee_id = $2
              AND s.status <> 'cancelled' AND s.starts_at::date >= $3
            """,
            company_id, employee_id, effective_from,
        )
        for assignment in future_assignments:
            await refresh_assignment_break_guidance(
                conn, company_id, shift_id=assignment["shift_id"], employee_id=employee_id,
                location_id=assignment["location_id"], starts_at=assignment["starts_at"],
                ends_at=assignment["ends_at"],
            )
    return MealWaiverAttestationResponse(
        employee_id=employee_id,
        on_file=bool(row["value"]),
        attested=True,
        effective_from=row["effective_from"],
        confirmed_at=row["confirmed_at"],
        note=row["note"],
    )
