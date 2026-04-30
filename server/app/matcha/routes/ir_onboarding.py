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
from uuid import UUID

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


class IrLocationUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zipcode: Optional[str] = None
    is_active: Optional[bool] = None


def _serialize_location(row) -> dict:
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "address": row["address"],
        "city": row["city"],
        "state": row["state"],
        "zipcode": row["zipcode"],
        "is_active": bool(row["is_active"]),
    }


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


@router.get("/locations")
async def list_ir_locations(
    include_inactive: bool = False,
    current_user=Depends(require_admin_or_client),
):
    """List business_locations for the caller's company.

    Mirrors the compliance router's GET /locations but lives outside the
    `compliance` feature gate so IR-only tenants can populate location
    pickers (e.g. the IR submit modal, the locations management page).
    """
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated")

    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT id, name, address, city, state, zipcode, is_active
            FROM business_locations
            WHERE company_id = $1
              AND ($2::bool OR is_active = true)
            ORDER BY is_active DESC, name NULLS LAST, city
            """,
            company_id,
            include_inactive,
        )
    return [_serialize_location(r) for r in rows]


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

    Idempotent on the existing UNIQUE (company_id, lower(city), upper(state))
    constraint — re-submitting the same city/state from the wizard reactivates
    rather than duplicating.
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
            ON CONFLICT (company_id, lower(city), upper(state)) DO UPDATE
                SET name = COALESCE(EXCLUDED.name, business_locations.name),
                    address = COALESCE(EXCLUDED.address, business_locations.address),
                    zipcode = COALESCE(EXCLUDED.zipcode, business_locations.zipcode),
                    is_active = true,
                    updated_at = NOW()
            RETURNING id, name, address, city, state, zipcode, is_active
            """,
            company_id,
            data.name,
            data.address,
            data.city.strip(),
            data.state.strip().upper(),
            data.zipcode.strip(),
        )
    return _serialize_location(row)


@router.patch("/locations/{location_id}")
async def update_ir_location(
    location_id: UUID,
    data: IrLocationUpdate,
    current_user=Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated")

    fields = data.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    if "state" in fields and fields["state"]:
        fields["state"] = fields["state"].strip().upper()
    for k in ("city", "zipcode", "name", "address"):
        if k in fields and isinstance(fields[k], str):
            fields[k] = fields[k].strip() or None

    # Defense-in-depth allowlist; pydantic already constrains to these
    # field names but we don't want a future model edit to silently widen
    # what becomes interpolatable into the SQL fragment below.
    ALLOWED = {"name", "address", "city", "state", "zipcode", "is_active"}
    set_parts = []
    values = []
    for i, (k, v) in enumerate(fields.items(), start=3):
        if k not in ALLOWED:
            raise HTTPException(status_code=400, detail=f"Unknown field: {k}")
        set_parts.append(f"{k} = ${i}")
        values.append(v)
    set_parts.append("updated_at = NOW()")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"""
            UPDATE business_locations
               SET {", ".join(set_parts)}
             WHERE id = $1 AND company_id = $2
            RETURNING id, name, address, city, state, zipcode, is_active
            """,
            location_id,
            company_id,
            *values,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Location not found")
    return _serialize_location(row)


@router.delete("/locations/{location_id}")
async def deactivate_ir_location(
    location_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    """Soft-delete: flip is_active=false.

    Hard-delete would orphan ir_incidents.location_id (no FK exists today
    but historical records still reference the row by uuid).
    """
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            UPDATE business_locations
               SET is_active = false, updated_at = NOW()
             WHERE id = $1 AND company_id = $2
            RETURNING id
            """,
            location_id,
            company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Location not found")
    return {"deactivated": True}
