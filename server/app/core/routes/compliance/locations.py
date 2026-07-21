"""locations routes (L9 split)."""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from datetime import date
from typing import List, Optional
from uuid import UUID

from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.database import get_connection
from app.core.feature_flags import get_company_features
from app.core.services.redis_cache import check_rate_limit
from app.core.services.redis_cache import (
    get_redis_cache,
    cache_get,
    cache_set,
    cache_delete,
    jurisdictions_key,
    compliance_dashboard_key,
    pinned_requirements_key,
)
from app.core.models.auth import CurrentUser
from app.core.models.compliance import (
    LocationCreate,
    LocationUpdate,
    FacilityAttributesUpdate,
    RequirementResponse,
    AlertResponse,
    CalendarItem,
    CheckLogEntry,
    UpcomingLegislationResponse,
    ComplianceSummary,
    PinRequirementRequest,
    HierarchicalComplianceResponse,
    CompanyCertificationResponse,
    CompanyLicenseResponse,
    ComplianceRiskSummary,
    RemediationRecord,
    RemediationDismissRequest,
    RemediationNoteRequest,
    RemediationReopenRequest,
)
from app.core.services.compliance_risk import get_compliance_risk_summary
from app.core.services.compliance_remediation import (
    annotate_issue,
    dismiss_issue,
    fetch_recent_remediations,
    reopen_issue,
)
from app.core.services.compliance_service import (
    codified_gate_sql,
    create_location,
    get_locations,
    get_location,
    update_location,
    delete_location,
    get_location_requirements,
    get_company_alerts,
    get_calendar_items,
    mark_alert_read,
    dismiss_alert,
    get_compliance_summary,
    get_compliance_dashboard,
    update_alert_action_plan,
    run_compliance_check_background,
    run_compliance_check_stream,
    project_location_from_catalog,
    get_check_log,
    get_upcoming_legislation,
    record_verification_feedback,
    get_calibration_stats,
    _missing_required_categories,
    set_requirement_pinned,
    get_pinned_requirements,
    get_hierarchical_requirements,
    update_facility_attributes,
    get_facility_attributes,
    search_company_requirements,
    verify_location_ownership,
)

from app.core.routes.compliance._shared import *  # noqa: F401,F403  (router objects + shared models/consts)
logger = logging.getLogger(__name__)



@router.post("/locations", response_model=dict)
async def create_location_endpoint(
    data: LocationCreate,
    background_tasks: BackgroundTasks,
    company_id: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await resolve_company_id(current_user, company_id)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company found")

    await check_rate_limit(str(company_id), "compliance_create_location", 30, 3600)

    location, has_complete_repository_coverage = await create_location(company_id, data)

    # Trigger background research when repository coverage is missing/partial.
    # Live Gemini research only for tenants with the full `compliance` feature
    # (this route sits behind require_feature("compliance") already, but the
    # flag is resolved and passed explicitly as defense in depth — resolve_company_id
    # lets an admin operate on a different company_id than the gate checked).
    if not has_complete_repository_coverage:
        features = await get_company_features(company_id)
        background_tasks.add_task(
            run_compliance_check_background,
            location.id,
            company_id,
            allow_live_research=features.get("compliance", False),
        )

    return {
        "id": str(location.id),
        "company_id": str(location.company_id),
        "name": location.name,
        "address": location.address,
        "city": location.city,
        "state": location.state,
        "county": location.county,
        "zipcode": location.zipcode,
        "is_active": location.is_active,
        "facility_attributes": location.facility_attributes,
        "created_at": location.created_at.isoformat(),
    }




@router.post("/locations/{location_id}/check")
async def check_location_compliance_endpoint(
    location_id: str,
    company_id: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await resolve_company_id(current_user, company_id)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    await check_rate_limit(str(company_id), "compliance_location_check", 10, 3600)

    try:
        loc_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid location ID")

    location = await get_location(loc_uuid, company_id)
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    location_name = location.name or f"{location.city}, {location.state}"
    is_admin = current_user.role == "admin"

    if not is_admin:
        # Tenants never reach the research-capable stream. This isn't a flag
        # gate on run_compliance_check_stream — it's a different function whose
        # only calls are the catalog-projection helpers, with no code path to
        # Gemini at all (see project_location_from_catalog's docstring). A
        # customer's button click structurally cannot trigger research; catalog
        # freshness is our job, on our own schedule (legislation_watch /
        # structured_data_fetch / admin refresh / vertical_coverage_sweep).
        async def projection_stream():
            try:
                yield f"data: {json.dumps({'type': 'started', 'location': location_name})}\n\n"
                async with get_connection() as conn:
                    result = await project_location_from_catalog(
                        conn, company_id, loc_uuid, create_alerts=True,
                    )
                yield f"data: {json.dumps({'type': 'processing', 'message': f'Refreshing {location_name} from the compliance library...'})}\n\n"
                yield f"data: {json.dumps({'type': 'completed', 'location': location_name, **result})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            projection_stream(),
            media_type="text/event-stream",
            headers={"X-Accel-Buffering": "no"},
        )

    # Admin: the deliberate white-glove path — may trigger live Gemini research
    # (Tier 3) and the shared-jurisdiction gap-fill when the catalog has a gap,
    # plus vertical fill for an existing company onboarded before its industry
    # was scoped.
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT r.category
            FROM business_locations bl
            LEFT JOIN jurisdiction_requirements r
                ON r.jurisdiction_id = bl.jurisdiction_id AND r.status = 'active'
            WHERE bl.id = $1
            """,
            loc_uuid,
        )
    repository_requirements = [
        {"category": row["category"]} for row in rows if row["category"]
    ]
    missing_categories = _missing_required_categories(repository_requirements)
    allow_live = len(missing_categories) > 0

    async def event_stream():
        try:
            async for event in run_compliance_check_stream(
                loc_uuid,
                company_id,
                allow_live_research=allow_live,
                allow_repository_refresh=True,
                include_vertical_fill=True,
            ):
                if event.get("type") == "heartbeat":
                    yield ": heartbeat\n\n"
                else:
                    yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no"},
    )




@lite_router.get("/locations", response_model=List[dict])
async def get_locations_endpoint(
    company_id: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await resolve_company_id(current_user, company_id)
    if company_id is None:
        return []

    locations = await get_locations(company_id)

    result = []
    for loc in locations:
        next_check = loc.get("next_auto_check")
        last_check = loc.get("last_compliance_check")
        created = loc.get("created_at")
        result.append(
            {
                "id": str(loc["id"]),
                "company_id": str(loc["company_id"]),
                "name": loc.get("name"),
                "address": loc.get("address"),
                "city": loc["city"],
                "state": loc["state"],
                "county": loc.get("county"),
                "zipcode": loc.get("zipcode", ""),
                "is_active": loc.get("is_active", True),
                "auto_check_enabled": loc.get("auto_check_enabled", True),
                "auto_check_interval_days": loc.get("auto_check_interval_days", 7),
                "next_auto_check": next_check.isoformat() if next_check else None,
                "last_compliance_check": last_check.isoformat() if last_check else None,
                "created_at": created.isoformat() if created else None,
                "has_local_ordinance": loc.get("has_local_ordinance"),
                "source": loc.get("source", "manual"),
                "coverage_status": loc.get("coverage_status", "covered"),
                "employee_count": loc.get("employee_count", 0),
                "employee_names": list(loc.get("employee_names") or []),
                "requirements_count": loc.get("requirements_count", 0),
                "unread_alerts_count": loc.get("unread_alerts_count", 0),
                "data_status": loc.get("data_status", "needs_research"),
                "facility_attributes": json.loads(loc["facility_attributes"]) if isinstance(loc.get("facility_attributes"), str) else loc.get("facility_attributes"),
            }
        )
    return result




@lite_router.get("/locations/{location_id}", response_model=dict)
async def get_location_endpoint(
    location_id: str,
    company_id: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await resolve_company_id(current_user, company_id)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        loc_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid location ID")

    location = await get_location(loc_uuid, company_id)
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    from app.core.services.compliance_service import get_location_counts

    counts = await get_location_counts(loc_uuid)

    return {
        "id": str(location.id),
        "company_id": str(location.company_id),
        "name": location.name,
        "address": location.address,
        "city": location.city,
        "state": location.state,
        "county": location.county,
        "zipcode": location.zipcode,
        "is_active": location.is_active,
        "auto_check_enabled": location.auto_check_enabled,
        "auto_check_interval_days": location.auto_check_interval_days,
        "next_auto_check": location.next_auto_check.isoformat()
        if location.next_auto_check
        else None,
        "last_compliance_check": location.last_compliance_check.isoformat()
        if location.last_compliance_check
        else None,
        "created_at": location.created_at.isoformat(),
        "has_local_ordinance": location.has_local_ordinance,
        "facility_attributes": location.facility_attributes,
        "requirements_count": counts["requirements_count"],
        "unread_alerts_count": counts["unread_alerts_count"],
    }




@router.put("/locations/{location_id}", response_model=dict)
async def update_location_endpoint(
    location_id: str,
    data: LocationUpdate,
    company_id: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await resolve_company_id(current_user, company_id)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        loc_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid location ID")

    location = await update_location(loc_uuid, company_id, data)
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    return {
        "id": str(location.id),
        "company_id": str(location.company_id),
        "name": location.name,
        "address": location.address,
        "city": location.city,
        "state": location.state,
        "county": location.county,
        "zipcode": location.zipcode,
        "is_active": location.is_active,
        "last_compliance_check": location.last_compliance_check.isoformat()
        if location.last_compliance_check
        else None,
        "created_at": location.created_at.isoformat(),
    }




@router.delete("/locations/{location_id}")
async def delete_location_endpoint(
    location_id: str,
    company_id: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await resolve_company_id(current_user, company_id)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        loc_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid location ID")

    success = await delete_location(loc_uuid, company_id)
    if not success:
        raise HTTPException(status_code=404, detail="Location not found")

    return {"message": "Location deleted successfully"}




@shared_router.get("/locations/{location_id}/requirements")
async def get_location_requirements_endpoint(
    location_id: str,
    category: Optional[str] = None,
    view: Optional[str] = Query(None, description="'flat' (default) or 'hierarchical'"),
    company_id: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await resolve_company_id(current_user, company_id)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        loc_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid location ID")

    if view == "hierarchical":
        result = await get_hierarchical_requirements(loc_uuid, company_id, category)
        if result is None:
            raise HTTPException(status_code=404, detail="Location not found")
        return result

    return await get_location_requirements(loc_uuid, company_id, category)




@router.get("/locations/{location_id}/jurisdiction-stack")
async def get_jurisdiction_stack_endpoint(
    location_id: str,
    company_id: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Raw jurisdiction stack resolution for admin/debug."""
    company_id = await resolve_company_id(current_user, company_id)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        loc_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid location ID")

    result = await get_hierarchical_requirements(loc_uuid, company_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Location not found")
    return result




@router.get("/locations/{location_id}/check-log", response_model=List[CheckLogEntry])
async def get_check_log_endpoint(
    location_id: str,
    limit: int = 20,
    company_id: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await resolve_company_id(current_user, company_id)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        loc_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid location ID")

    return await get_check_log(loc_uuid, company_id, limit)




@shared_router.get(
    "/locations/{location_id}/upcoming-legislation",
    response_model=List[UpcomingLegislationResponse],
)
async def get_upcoming_legislation_endpoint(
    location_id: str,
    company_id: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await resolve_company_id(current_user, company_id)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        loc_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid location ID")

    return await get_upcoming_legislation(loc_uuid, company_id)




@router.get("/locations/{location_id}/wage-violations")
async def get_wage_violations_endpoint(
    location_id: str,
    company_id: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get detailed minimum wage violation data for employees at a location."""
    company_id = await resolve_company_id(current_user, company_id)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        loc_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid location ID")

    from app.core.services.compliance_service import get_employee_impact_for_location

    impact = await get_employee_impact_for_location(loc_uuid, company_id)
    all_violations = [v for vs in impact["violations_by_rate_type"].values() for v in vs]
    return {
        "location_id": location_id,
        "total_affected": impact["total_affected"],
        "violation_count": len(all_violations),
        "violations": all_violations,
        "violations_by_rate_type": impact["violations_by_rate_type"],
    }




@router.patch("/locations/{location_id}/facility-attributes")
async def update_facility_attributes_endpoint(
    location_id: str,
    data: FacilityAttributesUpdate,
    company_id: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await resolve_company_id(current_user, company_id)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        loc_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid location ID")

    attrs = data.model_dump(exclude_none=False)
    # Only send fields that were explicitly provided
    attrs = {k: v for k, v in attrs.items() if v is not None or k in data.model_fields_set}

    result = await update_facility_attributes(loc_uuid, company_id, attrs)
    if result is None:
        raise HTTPException(status_code=404, detail="Location not found")

    return {"facility_attributes": result}




@lite_router.get("/locations/{location_id}/facility-attributes")
async def get_facility_attributes_endpoint(
    location_id: str,
    company_id: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await resolve_company_id(current_user, company_id)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        loc_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid location ID")

    result = await get_facility_attributes(loc_uuid, company_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Location not found")

    return {"facility_attributes": result}
