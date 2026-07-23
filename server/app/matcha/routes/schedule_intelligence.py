"""Schedule Intelligence routes (`/schedule-intelligence`, feature `schedule_intelligence`).

Four read-only analytics endpoints over the `employee_schedule` data: incident
correlation, Fair Workweek exposure, a discipline "pretext shield", and
per-shift qualified coverage. See `services/schedule_intelligence.py` for the
orchestration and `services/schedule_intelligence_stats.py` /
`services/fair_workweek.py` for the underlying pure math.

Mounted on `schedule_intelligence` alone (not double-gated with
`employee_schedule`, which would trip the wrong upsell) — each endpoint checks
`employee_schedule` itself and returns `{"available": false, ...}` when it's
off, so the frontend can render "turn on Employee Scheduling first" instead of
a blank error.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from ...database import get_connection
from ...core.feature_flags import get_company_features
from ..dependencies import require_admin_or_client, get_client_company_id
from ..services import schedule_intelligence as si

router = APIRouter()


async def _company_and_features(current_user) -> tuple[UUID, dict]:
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=403, detail="No company associated with this account")
    features = await get_company_features(company_id)
    return company_id, features


def _unavailable() -> dict:
    return {"available": False, "reason": "employee_schedule_required"}


@router.get("/overview")
async def get_overview(current_user=Depends(require_admin_or_client)):
    company_id, features = await _company_and_features(current_user)
    if not features.get("employee_schedule"):
        return _unavailable()
    async with get_connection() as conn:
        data = await si.build_overview(
            conn, company_id,
            credential_templates_enabled=bool(features.get("credential_templates")),
            training_enabled=bool(features.get("training")),
        )
    return {"available": True, **data}


@router.get("/incident-correlation")
async def get_incident_correlation(
    days: int = Query(180, ge=1, le=365),
    current_user=Depends(require_admin_or_client),
):
    company_id, features = await _company_and_features(current_user)
    if not features.get("employee_schedule"):
        return _unavailable()
    async with get_connection() as conn:
        data = await si.build_incident_correlation(conn, company_id, days=days)
    return {"available": True, **data}


@router.get("/fair-workweek")
async def get_fair_workweek(
    days: int = Query(90, ge=1, le=365),
    current_user=Depends(require_admin_or_client),
):
    company_id, features = await _company_and_features(current_user)
    if not features.get("employee_schedule"):
        return _unavailable()
    async with get_connection() as conn:
        data = await si.build_fair_workweek_exposure(conn, company_id, days=days)
    return {"available": True, **data}


@router.get("/pretext-shield")
async def get_pretext_shield(
    months: int = Query(6, ge=1, le=24),
    current_user=Depends(require_admin_or_client),
):
    company_id, features = await _company_and_features(current_user)
    if not features.get("employee_schedule"):
        return _unavailable()
    async with get_connection() as conn:
        data = await si.build_pretext_shield(conn, company_id, months=months)
    return {"available": True, **data}


@router.get("/qualified-coverage")
async def get_qualified_coverage(
    days: int = Query(14, ge=1, le=60),
    current_user=Depends(require_admin_or_client),
):
    company_id, features = await _company_and_features(current_user)
    if not features.get("employee_schedule"):
        return _unavailable()
    async with get_connection() as conn:
        data = await si.build_qualified_coverage(
            conn, company_id,
            credential_templates_enabled=bool(features.get("credential_templates")),
            training_enabled=bool(features.get("training")),
            days=days,
        )
    return {"available": True, **data}
