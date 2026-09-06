"""Privacy-preserving DOB maintenance for employee compliance."""
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.models.auth import CurrentUser
from app.database import get_connection
from app.matcha.dependencies import get_client_company_id, require_admin_or_client
from app.workers.tasks.schedule_break_refresh import enqueue_employee_schedule_break_refresh

router = APIRouter()


class DateOfBirthUpdate(BaseModel):
    date_of_birth: date


def _minor_status(date_of_birth: date) -> str:
    today = date.today()
    age = today.year - date_of_birth.year - ((today.month, today.day) < (date_of_birth.month, date_of_birth.day))
    return "minor" if age < 18 else "adult"


@router.put("/{employee_id}/demographics/date-of-birth")
async def update_date_of_birth(
    employee_id: UUID,
    body: DateOfBirthUpdate,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Set or correct DOB without returning it through ordinary employee APIs."""
    if body.date_of_birth > date.today():
        raise HTTPException(status_code=422, detail="date_of_birth cannot be in the future")

    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        async with conn.transaction():
            employee_exists = await conn.fetchval(
                "SELECT 1 FROM employees WHERE id = $1 AND org_id = $2",
                employee_id,
                company_id,
            )
            if not employee_exists:
                raise HTTPException(status_code=404, detail="Employee not found")
            await conn.execute(
                """
                INSERT INTO employee_demographics
                    (employee_id, org_id, date_of_birth, source, created_at, updated_at)
                VALUES ($1, $2, $3, 'manual', NOW(), NOW())
                ON CONFLICT (employee_id) DO UPDATE
                SET date_of_birth = EXCLUDED.date_of_birth,
                    source = 'manual',
                    updated_at = NOW()
                """,
                employee_id,
                company_id,
                body.date_of_birth,
            )

        enqueue_employee_schedule_break_refresh(
            company_id=company_id, employee_id=employee_id,
            actor_user_id=current_user.id,
            source="employee_date_of_birth_update",
        )

    return {"minor_status": _minor_status(body.date_of_birth), "updated": True}
