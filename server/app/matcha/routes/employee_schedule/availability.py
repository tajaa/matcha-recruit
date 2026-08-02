"""Admin view/edit of an employee's recurring weekly availability
(`/employee-schedule/availability/{employee_id}`). Portal counterpart —
the employee editing their own — lives at
routes/employee_portal/schedule.py's /me/schedule/availability."""

from uuid import UUID

from fastapi import APIRouter, Depends

from app.database import get_connection
from ...dependencies import require_admin_or_client
from app.matcha.models.scheduling.employee_schedule import AvailabilityReplace
from ._shared import require_company_id, log_audit, assert_employee_in_company

router = APIRouter()


@router.get("/availability/{employee_id}")
async def get_employee_availability(employee_id: UUID,
                                    current_user=Depends(require_admin_or_client)):
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        await assert_employee_in_company(conn, company_id, employee_id)
        rows = await conn.fetch(
            "SELECT weekday, start_time, end_time FROM schedule_employee_availability "
            "WHERE company_id = $1 AND employee_id = $2 ORDER BY weekday, start_time",
            company_id, employee_id,
        )
    return {"windows": [
        {"weekday": r["weekday"], "start_time": str(r["start_time"])[:5],
         "end_time": str(r["end_time"])[:5]} for r in rows]}


@router.put("/availability/{employee_id}")
async def replace_employee_availability(employee_id: UUID, body: AvailabilityReplace,
                                        current_user=Depends(require_admin_or_client)):
    """Full replacement. Empty windows list clears availability entirely
    (= back to fully available)."""
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        await assert_employee_in_company(conn, company_id, employee_id)
        async with conn.transaction():
            await conn.execute(
                "DELETE FROM schedule_employee_availability WHERE company_id = $1 AND employee_id = $2",
                company_id, employee_id,
            )
            for w in body.windows:
                await conn.execute(
                    "INSERT INTO schedule_employee_availability "
                    "(company_id, employee_id, weekday, start_time, end_time) "
                    "VALUES ($1,$2,$3,$4,$5)",
                    company_id, employee_id, w.weekday, w.start_time, w.end_time,
                )
            await log_audit(conn, company_id, "availability", employee_id,
                            current_user.id, "availability.update",
                            {"windows": len(body.windows), "actor": "admin"})
    return {"saved": len(body.windows)}
