"""Commercial-property routes (`/property`, feature `property`).

Tenant-facing Statement of Values: the company records its buildings (COPE +
values); the engine computes TIV, insurance-to-value, and a COPE grade. Property
LIMITS ride the existing limit-adequacy engine (`line='property'`) and property
LOSS RUNS ride the broker loss-development surface — this router owns the SOV.
Catastrophe enrichment (geocode + per-peril hazard) is layered on in Phase 3.
Business-facing, tenant-isolated.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from ...database import get_connection
from ..dependencies import require_admin_or_client, get_client_company_id
from ..services import property_sov as sov
from ..models.property import BuildingUpsert

router = APIRouter()


@router.get("/sov")
async def get_sov(current_user=Depends(require_admin_or_client)):
    """Full Statement of Values: buildings (COPE/ITV/perils) + company rollup."""
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        return await sov.build_sov(conn, company_id)


@router.get("/buildings")
async def list_buildings(current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        return {"buildings": await sov.list_buildings(conn, company_id)}


@router.post("/buildings")
async def create_building(body: BuildingUpsert, current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        await sov.upsert_building(conn, company_id, None, body.model_dump(), current_user.id)
        return await sov.build_sov(conn, company_id)


@router.put("/buildings/{building_id}")
async def update_building(building_id: UUID, body: BuildingUpsert,
                         current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        updated = await sov.upsert_building(conn, company_id, building_id, body.model_dump(), current_user.id)
        if updated is None:
            raise HTTPException(status_code=404, detail="Building not found")
        return await sov.build_sov(conn, company_id)


@router.delete("/buildings/{building_id}")
async def delete_building(building_id: UUID, current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        ok = await sov.delete_building(conn, company_id, building_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Building not found")
        return await sov.build_sov(conn, company_id)
