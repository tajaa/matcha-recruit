"""Manager-attested minor work-permit records."""
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.models.auth import CurrentUser
from app.database import get_connection
from app.matcha.dependencies import get_client_company_id, require_admin_or_client

router = APIRouter()


class WorkPermitCreate(BaseModel):
    location_id: UUID
    issued_at: date | None = None
    expires_at: date
    confirmed_on_file: bool


@router.get("/{employee_id}/work-permits")
async def list_work_permits(employee_id: UUID, current_user: CurrentUser = Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT id, location_id, issued_at, expires_at, status, confirmed_on_file, created_at
               FROM employee_work_permits WHERE company_id=$1 AND employee_id=$2
               ORDER BY created_at DESC""", company_id, employee_id)
    return {"permits": [{**dict(row), "id": str(row["id"]), "location_id": str(row["location_id"]) if row["location_id"] else None} for row in rows]}


@router.post("/{employee_id}/work-permits")
async def create_work_permit(employee_id: UUID, body: WorkPermitCreate,
                             current_user: CurrentUser = Depends(require_admin_or_client)):
    if not body.confirmed_on_file:
        raise HTTPException(status_code=422, detail="Confirm that the work permit is on file before scheduling a minor")
    if body.issued_at and body.issued_at > body.expires_at:
        raise HTTPException(status_code=422, detail="issued_at must be on or before expires_at")
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        async with conn.transaction():
            employee = await conn.fetchval("SELECT 1 FROM employees WHERE id=$1 AND org_id=$2", employee_id, company_id)
            location = await conn.fetchval("SELECT 1 FROM business_locations WHERE id=$1 AND company_id=$2", body.location_id, company_id)
            if not employee or not location:
                raise HTTPException(status_code=404, detail="Employee or location not found")
            previous = await conn.fetchval("""SELECT id FROM employee_work_permits
                WHERE company_id=$1 AND employee_id=$2 AND location_id=$3 AND status='active'
                ORDER BY created_at DESC LIMIT 1 FOR UPDATE""", company_id, employee_id, body.location_id)
            if previous:
                await conn.execute("UPDATE employee_work_permits SET status='superseded', updated_at=NOW() WHERE id=$1", previous)
            permit = await conn.fetchrow("""INSERT INTO employee_work_permits
                (company_id, employee_id, location_id, issued_at, expires_at, status, confirmed_on_file, confirmed_by, confirmed_at, supersedes_id)
                VALUES ($1,$2,$3,$4,$5,'active',true,$6,NOW(),$7)
                RETURNING id, location_id, issued_at, expires_at, status, confirmed_on_file, created_at""",
                company_id, employee_id, body.location_id, body.issued_at, body.expires_at, current_user.id, previous)
    return {**dict(permit), "id": str(permit["id"]), "location_id": str(permit["location_id"])}
