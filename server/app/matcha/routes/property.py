"""Commercial-property routes (`/property`, feature `property`).

Tenant-facing Statement of Values: the company records its buildings (COPE +
values); the engine computes TIV, insurance-to-value, and a COPE grade. Property
LIMITS ride the existing limit-adequacy engine (`line='property'`) and property
LOSS RUNS ride the broker loss-development surface — this router owns the SOV.
Catastrophe enrichment (geocode + per-peril hazard) is layered on in Phase 3.
Business-facing, tenant-isolated.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from ...database import get_connection
from ..dependencies import require_admin_or_client, get_client_company_id
from ..services import property_sov as sov
from ..services import submission_readiness as sr
from ..models.property import BuildingUpsert

logger = logging.getLogger(__name__)
router = APIRouter()


def _trigger_cat(building_id) -> None:
    """Best-effort: queue geocode + catastrophe enrichment for a building. Never
    inline (external calls) and never fatal — if the broker/worker is down the
    periodic ``property_cat_refresh`` sweep picks it up later."""
    try:
        from app.workers.tasks.property_cat_refresh import refresh_property_cat
        refresh_property_cat.delay(building_id=str(building_id))
    except Exception as exc:  # noqa: BLE001
        logger.warning("property: could not queue cat refresh for %s: %s", building_id, exc)


@router.get("/sov")
async def get_sov(current_user=Depends(require_admin_or_client)):
    """Full Statement of Values: buildings (COPE/ITV/perils) + company rollup +
    submission-readiness completeness block."""
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        payload = await sov.build_sov(conn, company_id)
        payload["readiness"] = await sr.compute_property_readiness(conn, company_id, sov=payload)
    return payload


@router.get("/buildings")
async def list_buildings(current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        return {"buildings": await sov.list_buildings(conn, company_id)}


@router.post("/buildings")
async def create_building(body: BuildingUpsert, current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        created = await sov.upsert_building(conn, company_id, None, body.model_dump(), current_user.id)
        result = await sov.build_sov(conn, company_id)
    if created:
        _trigger_cat(created["id"])
    return result


@router.put("/buildings/{building_id}")
async def update_building(building_id: UUID, body: BuildingUpsert,
                         current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        updated = await sov.upsert_building(conn, company_id, building_id, body.model_dump(), current_user.id)
        if updated is None:
            raise HTTPException(status_code=404, detail="Building not found")
        result = await sov.build_sov(conn, company_id)
    _trigger_cat(building_id)
    return result


@router.delete("/buildings/{building_id}")
async def delete_building(building_id: UUID, current_user=Depends(require_admin_or_client)):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        ok = await sov.delete_building(conn, company_id, building_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Building not found")
        return await sov.build_sov(conn, company_id)
