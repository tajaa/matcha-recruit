"""Employee-level incident endpoints.

Routes:
  GET /incident-counts       — company-wide employee_id → count map
  GET /{employee_id}/incidents — incidents involving a specific employee

`GET /incident-counts` is shadowed by crud's `GET /{employee_id}`
(crud registers first via _legacy.py, before any submodule include_router
call, so the shadow holds regardless of submodule order).
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.core.models.auth import CurrentUser
from app.database import get_connection
from app.matcha.dependencies import get_client_company_id, require_admin_or_client

router = APIRouter()


@router.get("/incident-counts")
async def get_employee_incident_counts(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Return a mapping of employee_id → incident count for the company."""
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT unnest(involved_employee_ids)::text AS eid, COUNT(*) AS cnt
               FROM ir_incidents
               WHERE company_id = $1
               GROUP BY eid""",
            company_id,
        )
    return {r["eid"]: r["cnt"] for r in rows}


@router.get("/{employee_id}/incidents")
async def get_employee_incidents(
    employee_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Return incidents involving a specific employee."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        # Verify employee belongs to company
        emp = await conn.fetchval(
            "SELECT id FROM employees WHERE id = $1 AND org_id = $2",
            employee_id, company_id,
        )
        if not emp:
            raise HTTPException(status_code=404, detail="Employee not found")

        rows = await conn.fetch(
            """SELECT i.id, i.incident_number, i.title, i.incident_type,
                      i.severity, i.status, i.occurred_at,
                      i.reported_by_name
               FROM ir_incidents i
               WHERE i.company_id = $1
                 AND $2::uuid = ANY(i.involved_employee_ids)
               ORDER BY i.occurred_at DESC""",
            company_id, str(employee_id),
        )

    return [
        {
            "id": str(r["id"]),
            "incident_number": r["incident_number"],
            "title": r["title"],
            "incident_type": r["incident_type"],
            "severity": r["severity"],
            "status": r["status"],
            "occurred_at": r["occurred_at"].isoformat() if r["occurred_at"] else None,
            "reported_by_name": r["reported_by_name"],
            "role": "involved",
        }
        for r in rows
    ]
