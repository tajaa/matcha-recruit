"""OIG Exclusion Screening endpoints.

Routes:
  GET  /oig-summary               — company-wide screening status
  GET  /{employee_id}/oig-status  — per-employee status
  POST /{employee_id}/oig-screen  — queue a single screen
  POST /oig-batch-screen          — queue a full company re-screen

`GET /oig-summary` is shadowed by crud's `GET /{employee_id}` (registration
order preserved by the package `__init__.py` include_router chain).
"""
import logging
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.core.models.auth import CurrentUser
from app.database import get_connection
from app.matcha.dependencies import get_client_company_id, require_admin_or_client

from ._shared import _perform_oig_screening

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/oig-summary")
async def get_oig_summary(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get company-wide OIG screening summary."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE ec.oig_status = 'cleared') AS cleared,
                COUNT(*) FILTER (WHERE ec.oig_status = 'excluded') AS excluded,
                COUNT(*) FILTER (WHERE ec.oig_status = 'review_needed') AS review_needed,
                COUNT(*) FILTER (WHERE ec.oig_status = 'not_checked' OR ec.oig_status IS NULL) AS not_checked,
                MIN(ec.oig_last_checked) AS oldest_check
            FROM employees e
            LEFT JOIN employee_credentials ec ON ec.employee_id = e.id AND ec.org_id = e.org_id
            WHERE e.org_id = $1 AND e.status != 'terminated'
            """,
            company_id,
        )
        r = rows[0]
        return {
            "total": r["total"],
            "cleared": r["cleared"],
            "excluded": r["excluded"],
            "review_needed": r["review_needed"],
            "not_checked": r["not_checked"],
            "oldest_check": r["oldest_check"].isoformat() if r["oldest_check"] else None,
        }


@router.get("/{employee_id}/oig-status")
async def get_employee_oig_status(
    employee_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get OIG screening status for a single employee."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT e.first_name, e.last_name,
                   COALESCE(ec.oig_status, 'not_checked') AS oig_status,
                   ec.oig_last_checked
            FROM employees e
            LEFT JOIN employee_credentials ec ON ec.employee_id = e.id AND ec.org_id = e.org_id
            WHERE e.id = $1 AND e.org_id = $2
            """,
            employee_id, company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Employee not found")

        return {
            "employee_id": str(employee_id),
            "name": f"{row['first_name']} {row['last_name']}".strip(),
            "oig_status": row["oig_status"],
            "oig_last_checked": row["oig_last_checked"].isoformat() if row["oig_last_checked"] else None,
        }


@router.post("/{employee_id}/oig-screen")
async def screen_employee_oig(
    employee_id: UUID,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Manually trigger OIG screening for an employee."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT first_name, last_name FROM employees WHERE id = $1 AND org_id = $2",
            employee_id, company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Employee not found")

    background_tasks.add_task(
        _perform_oig_screening,
        employee_id=employee_id,
        org_id=company_id,
        first_name=row["first_name"],
        last_name=row["last_name"],
    )

    return {"status": "screening_queued", "employee_id": str(employee_id)}


@router.post("/oig-batch-screen")
async def batch_screen_oig(
    background_tasks: BackgroundTasks,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Re-screen all active employees against OIG LEIE."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        employees = await conn.fetch(
            "SELECT id, first_name, last_name FROM employees WHERE org_id = $1 AND status != 'terminated'",
            company_id,
        )

    for emp in employees:
        background_tasks.add_task(
            _perform_oig_screening,
            employee_id=emp["id"],
            org_id=company_id,
            first_name=emp["first_name"],
            last_name=emp["last_name"],
        )

    return {"status": "batch_screening_queued", "employee_count": len(employees)}
