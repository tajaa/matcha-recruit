"""IR-only onboarding wizard companion endpoints.

Drives the 4-step setup wizard for Matcha IR free-beta tenants
(`signup_source = 'ir_only_self_serve'`). Tracks completion via
`companies.ir_onboarding_completed_at` so the SPA can resume mid-flow.

Steps inferred from current state:
- company_info → no `business_locations` rows yet
- employees    → 0 employees
- anonymous    → no `report_email_token` set yet
- ready        → all of the above present (or completion stamp set)
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...database import get_connection
from ..dependencies import require_admin_or_client, get_client_company_id

router = APIRouter()


class IrLocationCreate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: str
    state: str
    zipcode: str


@router.get("/status")
async def get_onboarding_status(
    current_user=Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                ir_onboarding_completed_at,
                report_email_token IS NOT NULL AS anonymous_token_present,
                (SELECT COUNT(*) FROM employees WHERE org_id = $1) AS employees_count,
                (SELECT COUNT(*) FROM business_locations WHERE company_id = $1) AS locations_count
            FROM companies
            WHERE id = $1
            """,
            company_id,
        )

    if not row:
        raise HTTPException(status_code=404, detail="Company not found")

    completed_at: Optional[datetime] = row["ir_onboarding_completed_at"]
    locations_count = int(row["locations_count"] or 0)
    employees_count = int(row["employees_count"] or 0)
    anonymous_token_present = bool(row["anonymous_token_present"])

    if completed_at:
        step = "ready"
    elif locations_count == 0:
        step = "company_info"
    elif employees_count == 0:
        step = "employees"
    elif not anonymous_token_present:
        step = "anonymous"
    else:
        step = "ready"

    return {
        "step": step,
        "locations_count": locations_count,
        "employees_count": employees_count,
        "anonymous_token_present": anonymous_token_present,
        "completed_at": completed_at.isoformat() if completed_at else None,
    }


@router.post("/complete")
async def complete_onboarding(
    current_user=Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated")

    async with get_connection() as conn:
        await conn.execute(
            """
            UPDATE companies
               SET ir_onboarding_completed_at = COALESCE(ir_onboarding_completed_at, NOW())
             WHERE id = $1
            """,
            company_id,
        )
    return {"completed": True}


@router.post("/locations")
async def create_ir_location(
    data: IrLocationCreate,
    current_user=Depends(require_admin_or_client),
):
    """Minimal business_locations create for IR-only onboarding.

    The compliance router already exposes a richer /locations endpoint
    but it sits behind the compliance feature gate; IR-only tenants
    don't have that flag. This is a thin equivalent that writes the
    same table so any later upgrade flips a flag and the data carries
    over without migration.
    """
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO business_locations (
                company_id, name, address, city, state, zipcode, is_active
            )
            VALUES ($1, $2, $3, $4, $5, $6, true)
            RETURNING id, name, address, city, state, zipcode
            """,
            company_id,
            data.name,
            data.address,
            data.city.strip(),
            data.state.strip().upper(),
            data.zipcode.strip(),
        )
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "address": row["address"],
        "city": row["city"],
        "state": row["state"],
        "zipcode": row["zipcode"],
    }
