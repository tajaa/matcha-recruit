import json

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from datetime import date
from typing import List, Optional
from uuid import UUID

from ...matcha.dependencies import require_admin_or_client, get_client_company_id
from ...database import get_connection
from ..feature_flags import get_company_features
from ..services.redis_cache import check_rate_limit
from ..services.redis_cache import (
    get_redis_cache,
    cache_get,
    cache_set,
    cache_delete,
    jurisdictions_key,
    compliance_dashboard_key,
    pinned_requirements_key,
)
from ..models.auth import CurrentUser
from ..models.compliance import (
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
from ..services.compliance_risk import get_compliance_risk_summary
from ..services.compliance_remediation import (
    annotate_issue,
    dismiss_issue,
    fetch_recent_remediations,
    reopen_issue,
)
from ..services.compliance_service import (
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

router = APIRouter()

# Routes that must be accessible to all client tenants regardless of the
# `compliance` feature flag — e.g. matcha-lite gets the compliance calendar
# even though the full Compliance page is gated. Mounted separately in
# core/routes/__init__.py without `require_feature("compliance")`.
lite_router = APIRouter()

# Read-only viewers shared between Pro (full `compliance`) and Matcha-X's
# read-only `compliance_lite` taste. Mounted in core/routes/__init__.py under
# require_any_feature("compliance", "compliance_lite"). ONLY read-only GETs live
# here — every mutating / power-tool endpoint stays on `router` (compliance-only).
shared_router = APIRouter()


async def resolve_company_id(
    current_user, company_id_override: str | None
) -> UUID | None:
    """Resolve company ID, allowing admins to override via query param."""
    if current_user.role == "admin" and company_id_override:
        try:
            cid = UUID(company_id_override)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid company_id")
        async with get_connection() as conn:
            exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM companies WHERE id = $1)", cid
            )
        if not exists:
            raise HTTPException(status_code=404, detail="Company not found")
        return cid
    return await get_client_company_id(current_user)


@lite_router.get("/jurisdictions")
async def list_jurisdictions(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List jurisdictions that have requirement data in the repository."""
    redis = get_redis_cache()
    if redis:
        cached = await cache_get(redis, jurisdictions_key())
        if cached is not None:
            return cached

    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT j.city, j.state, j.county,
                   COALESCE(jr.has_local_ordinance, false) AS has_local_ordinance
            FROM jurisdictions j
            LEFT JOIN jurisdiction_reference jr
                ON LOWER(jr.city) = LOWER(j.city) AND jr.state = j.state
            WHERE (j.requirement_count > 0 OR j.last_verified_at IS NULL)
              AND j.city <> ''
              AND j.city NOT LIKE '_county_%'
            ORDER BY j.state, j.city
            """
        )
    result = [
        {
            "city": row["city"],
            "state": row["state"],
            "county": row["county"],
            "has_local_ordinance": row["has_local_ordinance"],
        }
        for row in rows
    ]

    if redis:
        await cache_set(redis, jurisdictions_key(), result, ttl=3600)

    return result


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

    from ..services.compliance_service import get_location_counts

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


@shared_router.get("/categories")
async def get_compliance_categories(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Returns all compliance categories from the DB table."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            'SELECT id, slug, name, description, domain::text, "group", '
            "industry_tag, sort_order FROM compliance_categories ORDER BY sort_order"
        )
    return [dict(row) for row in rows]


@router.get("/precedence-rules")
async def get_precedence_rules(
    state: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Returns precedence rules, optionally filtered by state."""
    async with get_connection() as conn:
        if state:
            rows = await conn.fetch(
                """SELECT pr.id, pr.precedence_type::text, pr.reasoning_text,
                          pr.legal_citation, pr.applies_to_all_children,
                          pr.status::text, pr.effective_date, pr.sunset_date,
                          cc.slug AS category_slug, cc.name AS category_name,
                          j_hi.display_name AS higher_jurisdiction_name,
                          j_lo.display_name AS lower_jurisdiction_name
                   FROM precedence_rules pr
                   JOIN compliance_categories cc ON cc.id = pr.category_id
                   JOIN jurisdictions j_hi ON j_hi.id = pr.higher_jurisdiction_id
                   LEFT JOIN jurisdictions j_lo ON j_lo.id = pr.lower_jurisdiction_id
                   WHERE j_hi.state = $1 AND pr.status = 'active'
                   ORDER BY cc.slug""",
                state.upper(),
            )
        else:
            rows = await conn.fetch(
                """SELECT pr.id, pr.precedence_type::text, pr.reasoning_text,
                          pr.legal_citation, pr.applies_to_all_children,
                          pr.status::text, pr.effective_date, pr.sunset_date,
                          cc.slug AS category_slug, cc.name AS category_name,
                          j_hi.display_name AS higher_jurisdiction_name,
                          j_lo.display_name AS lower_jurisdiction_name
                   FROM precedence_rules pr
                   JOIN compliance_categories cc ON cc.id = pr.category_id
                   JOIN jurisdictions j_hi ON j_hi.id = pr.higher_jurisdiction_id
                   LEFT JOIN jurisdictions j_lo ON j_lo.id = pr.lower_jurisdiction_id
                   WHERE pr.status = 'active'
                   ORDER BY cc.slug"""
            )
    return [dict(row) for row in rows]


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

    from ..services.compliance_service import get_employee_impact_for_location

    impact = await get_employee_impact_for_location(loc_uuid, company_id)
    all_violations = [v for vs in impact["violations_by_rate_type"].values() for v in vs]
    return {
        "location_id": location_id,
        "total_affected": impact["total_affected"],
        "violation_count": len(all_violations),
        "violations": all_violations,
        "violations_by_rate_type": impact["violations_by_rate_type"],
    }


@lite_router.get("/calendar", response_model=List[CalendarItem])
async def get_compliance_calendar(
    from_date: Optional[date] = Query(None, alias="from"),
    to_date: Optional[date] = Query(None, alias="to"),
    location_id: Optional[str] = Query(None),
    company_id: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Compliance-deadline calendar feed.

    Returns non-dismissed alerts with a deadline, sorted ascending,
    enriched with location + jurisdiction context and a status bucket
    (overdue / due_soon / upcoming / future). No new feature flag —
    accessible to any client tenant including matcha-lite.
    """
    company_id = await resolve_company_id(current_user, company_id)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    loc_uuid = None
    if location_id:
        try:
            loc_uuid = UUID(location_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid location_id")

    return await get_calendar_items(
        company_id=company_id,
        location_id=loc_uuid,
        from_date=from_date,
        to_date=to_date,
    )


@router.get("/alerts", response_model=List[AlertResponse])
async def get_alerts_endpoint(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 50,
    company_id: Optional[str] = Query(None),
    location_id: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await resolve_company_id(current_user, company_id)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    loc_uuid = None
    if location_id:
        try:
            loc_uuid = UUID(location_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid location_id")
    return await get_company_alerts(company_id, status, severity, limit, location_id=loc_uuid)


@lite_router.put("/alerts/{alert_id}/read")
async def mark_alert_read_endpoint(
    alert_id: str,
    company_id: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await resolve_company_id(current_user, company_id)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        alert_uuid = UUID(alert_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid alert ID")

    success = await mark_alert_read(alert_uuid, company_id)
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")

    return {"message": "Alert marked as read"}


class DismissAlertRequest(BaseModel):
    """Optional correction data when dismissing an alert (Phase 3.1)."""

    is_false_positive: bool = True  # True if the alert was incorrect/not a real change
    correction_reason: Optional[str] = (
        None  # "misread_date", "wrong_jurisdiction", "hallucination", "outdated_source"
    )
    admin_notes: Optional[str] = None


class ActionPlanUpdateRequest(BaseModel):
    action_owner_id: Optional[str] = None
    next_action: Optional[str] = None
    action_due_date: Optional[date] = None
    recommended_playbook: Optional[str] = None
    estimated_financial_impact: Optional[str] = None
    mark_actioned: Optional[bool] = None


@lite_router.put("/alerts/{alert_id}/dismiss")
async def dismiss_alert_endpoint(
    alert_id: str,
    data: Optional[DismissAlertRequest] = None,
    company_id: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await resolve_company_id(current_user, company_id)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        alert_uuid = UUID(alert_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid alert ID")

    # Record feedback if provided (Phase 3.1: Admin Feedback Loop)
    if data:
        await record_verification_feedback(
            alert_uuid,
            current_user.user_id,
            actual_is_change=not data.is_false_positive,
            admin_notes=data.admin_notes,
            correction_reason=data.correction_reason,
            company_id=company_id,
        )

    success = await dismiss_alert(alert_uuid, company_id)
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")

    return {"message": "Alert dismissed", "feedback_recorded": data is not None}


@router.put("/alerts/{alert_id}/action-plan")
async def update_alert_action_plan_endpoint(
    alert_id: str,
    data: ActionPlanUpdateRequest,
    company_id: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await resolve_company_id(current_user, company_id)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        alert_uuid = UUID(alert_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid alert ID")

    updates = data.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields supplied for update")

    if "action_owner_id" in updates and updates["action_owner_id"] is not None:
        try:
            updates["action_owner_id"] = UUID(updates["action_owner_id"])
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid action_owner_id")

    updated = await update_alert_action_plan(
        alert_uuid,
        company_id,
        updates,
        actor_user_id=current_user.user_id,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Alert not found")

    return {"message": "Action plan updated", **updated}


@shared_router.get("/summary", response_model=ComplianceSummary)
async def get_compliance_summary_endpoint(
    company_id: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await resolve_company_id(current_user, company_id)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    return await get_compliance_summary(company_id)


@shared_router.get("/risk-summary", response_model=ComplianceRiskSummary)
async def get_compliance_risk_summary_endpoint(
    company_id: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Manager risk cockpit — measured compliance risk (open issues by severity,
    dollar exposure, employees affected, next deadline) + the action queue and
    get-ahead lane. Company-scoped, deterministic, no Gemini."""
    company_id = await resolve_company_id(current_user, company_id)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    return await get_compliance_risk_summary(company_id)


@shared_router.get("/remediations", response_model=List[RemediationRecord])
async def list_remediations_endpoint(
    days: int = Query(90, ge=1, le=365),
    company_id: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Resolved + dismissed compliance issues — the documentation trail."""
    company_id = await resolve_company_id(current_user, company_id)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")
    async with get_connection() as conn:
        return await fetch_recent_remediations(conn, company_id, days=days)


@router.post("/remediations/dismiss")
async def dismiss_remediation_endpoint(
    data: RemediationDismissRequest,
    company_id: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Dismiss an open issue as a false positive (with a reason). It re-surfaces
    only if its underlying values later change."""
    company_id = await resolve_company_id(current_user, company_id)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")
    if not (data.reason or "").strip():
        raise HTTPException(status_code=400, detail="A reason is required to dismiss an issue")
    async with get_connection() as conn:
        ok = await dismiss_issue(conn, company_id, data.issue_key, data.reason.strip(), current_user.user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="No open issue with that key")
    return {"status": "dismissed", "issue_key": data.issue_key}


@router.post("/remediations/note")
async def annotate_remediation_endpoint(
    data: RemediationNoteRequest,
    company_id: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Record a resolution note/method against an issue for the trail."""
    company_id = await resolve_company_id(current_user, company_id)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")
    async with get_connection() as conn:
        ok = await annotate_issue(conn, company_id, data.issue_key, (data.note or "").strip(), current_user.user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Unknown issue key")
    return {"status": "noted", "issue_key": data.issue_key}


@router.post("/remediations/reopen")
async def reopen_remediation_endpoint(
    data: RemediationReopenRequest,
    company_id: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Undo a dismissal — return the issue to the active queue."""
    company_id = await resolve_company_id(current_user, company_id)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")
    async with get_connection() as conn:
        ok = await reopen_issue(conn, company_id, data.issue_key, current_user.user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="No dismissed issue with that key")
    return {"status": "open", "issue_key": data.issue_key}


@shared_router.get("/pending-research")
async def get_pending_research_endpoint(
    company_id: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """What we're still researching for this company — drives the tenant
    "We're working on this for you" panel on the Compliance page.

    Two sources, both read-only, NO Gemini:
    - `coverage_requests`: pending/in-progress `jurisdiction_coverage_requests`
      the company's build queued (real catalog gaps, human-readable in
      `admin_notes`).
    - `vertical`: industry-specialty cells (e.g. dental) not yet researched for
      the company's location chains (the vertical ledger's to-do), summarized as
      a count — filled by the vertical_coverage_sweep, which reprojects the tab
      and emails the admin when done.
    """
    cid = await resolve_company_id(current_user, company_id)
    if cid is None:
        raise HTTPException(status_code=403, detail="Access denied")

    from ..services import vertical_coverage

    async with get_connection() as conn:
        req_rows = await conn.fetch(
            """
            SELECT DISTINCT jcr.city, jcr.state, jcr.county, jcr.admin_notes,
                            jcr.created_at
            FROM jurisdiction_coverage_requests jcr
            WHERE jcr.status IN ('pending', 'in_progress')
              AND (
                jcr.requested_by_company_id = $1
                OR EXISTS (
                    SELECT 1 FROM business_locations bl
                    WHERE bl.company_id = $1 AND bl.is_active = true
                      AND LOWER(bl.city) = LOWER(jcr.city)
                      AND UPPER(bl.state) = UPPER(jcr.state)
                )
              )
            ORDER BY jcr.created_at DESC
            """,
            cid,
        )
        coverage_requests = [
            {
                "city": r["city"],
                "state": r["state"],
                "county": r["county"],
                "note": r["admin_notes"],
                "requested_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in req_rows
        ]

        vertical = None
        try:
            resolved = await vertical_coverage.resolve_vertical(conn, cid)
            if resolved:
                _parent, _slug, v_label, v_tag, _minted = resolved
                cat_rows = await conn.fetch(
                    "SELECT slug FROM compliance_categories WHERE industry_tag = $1",
                    v_tag,
                )
                v_categories = [r["slug"] for r in cat_rows]
                leaf_rows = await conn.fetch(
                    "SELECT jurisdiction_id FROM business_locations "
                    "WHERE company_id = $1 AND is_active = true AND jurisdiction_id IS NOT NULL",
                    cid,
                )
                leaf_ids = [r["jurisdiction_id"] for r in leaf_rows]
                areas = 0
                if v_categories and leaf_ids:
                    leaf_chains = await vertical_coverage.chains_for_leaves(conn, leaf_ids)
                    plan, _deferred = await vertical_coverage.plan_fill(
                        conn, leaf_chains, v_tag, v_categories
                    )
                    areas = len(plan)
                # Rows an admin staged for this vertical but hasn't approved yet.
                # Without this the panel would vanish the moment a staged run marks
                # the ledger cells covered (plan_fill → 0) while nothing is live —
                # tenant thinks it's done but the tab is still bare. Keep showing
                # "we're working on it" until approval publishes.
                in_review = 0
                if v_categories and leaf_ids:
                    in_review = await conn.fetchval(
                        """
                        WITH RECURSIVE chain AS (
                            SELECT id, parent_id FROM jurisdictions WHERE id = ANY($1::uuid[])
                            UNION ALL
                            SELECT j.id, j.parent_id FROM jurisdictions j JOIN chain c ON j.id = c.parent_id
                        )
                        SELECT COUNT(DISTINCT r.category) FROM jurisdiction_requirements r
                        JOIN chain c ON c.id = r.jurisdiction_id
                        WHERE r.status = 'pending'
                          AND r.category = ANY($2::text[])
                        """,
                        leaf_ids, v_categories,
                    ) or 0
                if areas or in_review:
                    vertical = {"label": v_label, "areas": areas, "in_review": in_review}
        except Exception:
            vertical = None

    return {"coverage_requests": coverage_requests, "vertical": vertical}


@router.get("/dashboard")
async def get_compliance_dashboard_endpoint(
    horizon_days: int = Query(
        90, ge=1, le=365, description="Look-ahead window in days (30/60/90/180/365)"
    ),
    company_id: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """
    Compliance impact dashboard for client admins.

    Returns KPI totals and a coming_up list of upcoming legislation items enriched with
    affected-employee counts derived from employees.work_state == location.state.
    Pass ?horizon_days=30|60|90 to filter the look-ahead window (default 90).
    """
    company_id = await resolve_company_id(current_user, company_id)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    redis = get_redis_cache()
    if redis:
        cached = await cache_get(redis, compliance_dashboard_key(company_id, horizon_days))
        if cached is not None:
            return cached

    result = await get_compliance_dashboard(company_id, horizon_days=horizon_days)

    if redis:
        await cache_set(redis, compliance_dashboard_key(company_id, horizon_days), result, ttl=180)

    return result


# =====================================================
# Verification Calibration Endpoints (Phase 1.2)
# =====================================================


class VerificationFeedbackRequest(BaseModel):
    actual_is_change: bool
    admin_notes: Optional[str] = None
    correction_reason: Optional[str] = (
        None  # "misread_date", "wrong_jurisdiction", "hallucination", etc.
    )


@router.post("/alerts/{alert_id}/feedback")
async def record_verification_feedback_endpoint(
    alert_id: str,
    data: VerificationFeedbackRequest,
    company_id: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Record admin feedback on whether a verification prediction was correct.

    This data is used to calibrate confidence thresholds and improve accuracy.
    """
    company_id = await resolve_company_id(current_user, company_id)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        alert_uuid = UUID(alert_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid alert ID")

    success = await record_verification_feedback(
        alert_uuid,
        current_user.user_id,
        data.actual_is_change,
        data.admin_notes,
        data.correction_reason,
        company_id=company_id,
    )
    if not success:
        raise HTTPException(
            status_code=404, detail="No verification outcome found for this alert"
        )

    return {"message": "Feedback recorded"}


@router.get("/calibration/stats")
async def get_calibration_stats_endpoint(
    category: Optional[str] = None,
    days: int = 30,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get confidence calibration statistics.

    Returns prediction accuracy grouped by confidence bucket.
    Useful for tuning confidence thresholds.
    """
    return await get_calibration_stats(category, days)


class LegislationAssignRequest(BaseModel):
    location_id: str
    action_owner_id: Optional[str] = None
    action_due_date: Optional[date] = None


@router.put("/legislation/{legislation_id}/assign")
async def assign_legislation_endpoint(
    legislation_id: str,
    data: LegislationAssignRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Find or create a compliance_alerts record for a legislation item and set assignment."""
    import json as _json

    company_id = await get_client_company_id(current_user)

    try:
        leg_uuid = UUID(legislation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid legislation_id")

    try:
        location_id = UUID(data.location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid location_id")

    async with get_connection() as conn:
        leg_row = await conn.fetchrow(
            "SELECT id, title, category FROM upcoming_legislation WHERE id = $1 AND company_id = $2",
            leg_uuid, company_id,
        )
        if not leg_row:
            raise HTTPException(status_code=404, detail="Legislation not found")

        if not await verify_location_ownership(conn, location_id, company_id):
            raise HTTPException(status_code=404, detail="Location not found")

        # Find existing alert for this legislation item
        alert_id = await conn.fetchval(
            """
            SELECT id FROM compliance_alerts
            WHERE company_id = $1
              AND location_id = $2
              AND alert_type = 'upcoming_legislation'
              AND status <> 'dismissed'
              AND metadata->>'legislation_id' = $3
            LIMIT 1
            """,
            company_id, location_id, legislation_id,
        )

        # Create one on-demand if none exists yet
        if not alert_id:
            metadata = {"legislation_id": legislation_id}
            alert_id = await conn.fetchval(
                """
                INSERT INTO compliance_alerts
                (location_id, company_id, requirement_id, title, message, severity, status,
                 category, action_required, alert_type, metadata)
                VALUES ($1, $2, NULL, $3, $4, 'info', 'unread', $5, 'Review upcoming legislation',
                        'upcoming_legislation', $6::jsonb)
                RETURNING id
                """,
                location_id, company_id,
                leg_row["title"],
                "Upcoming legislation requires review and assignment.",
                leg_row["category"],
                _json.dumps(metadata),
            )

    # Apply owner / due-date updates via service (uses its own connection)
    updates = {}
    if data.action_owner_id is not None:
        updates["action_owner_id"] = data.action_owner_id or None
    if data.action_due_date is not None:
        updates["action_due_date"] = data.action_due_date.isoformat()

    if updates:
        await update_alert_action_plan(alert_id, company_id, updates)

    return {"alert_id": str(alert_id)}


@router.get("/assignable-users")
async def get_assignable_users_endpoint(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Return users (clients + admins) that can be assigned compliance actions."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT u.id, u.email, c.name, 'client' AS role
            FROM clients c
            JOIN users u ON u.id = c.user_id
            WHERE c.company_id = $1 AND u.is_active = TRUE

            UNION

            SELECT u.id, u.email, u.email AS name, 'admin' AS role
            FROM users u
            WHERE u.role = 'admin' AND u.is_active = TRUE
            ORDER BY name
            """,
            company_id,
        )

    return [
        {"id": str(row["id"]), "name": row["name"], "email": row["email"], "role": row["role"]}
        for row in rows
    ]


@router.post("/requirements/{requirement_id}/pin")
async def pin_requirement_endpoint(
    requirement_id: str,
    data: PinRequirementRequest,
    company_id: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await resolve_company_id(current_user, company_id)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        req_uuid = UUID(requirement_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid requirement ID")

    result = await set_requirement_pinned(req_uuid, company_id, data.is_pinned)
    if not result:
        raise HTTPException(status_code=404, detail="Requirement not found")

    redis = get_redis_cache()
    if redis:
        await cache_delete(redis, pinned_requirements_key(company_id))

    return result


@router.get("/pinned-requirements")
async def get_pinned_requirements_endpoint(
    company_id: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await resolve_company_id(current_user, company_id)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    redis = get_redis_cache()
    if redis:
        cached = await cache_get(redis, pinned_requirements_key(company_id))
        if cached is not None:
            return cached

    result = await get_pinned_requirements(company_id)

    if redis:
        await cache_set(redis, pinned_requirements_key(company_id), result, ttl=300)

    return result


@router.get("/search")
async def search_requirements_endpoint(
    q: str = Query(..., min_length=1, description="Search query"),
    location_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    company_id: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Search across all compliance requirements for a company."""
    company_id = await resolve_company_id(current_user, company_id)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    loc_uuid = None
    if location_id:
        try:
            loc_uuid = UUID(location_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid location_id")

    async with get_connection() as conn:
        results = await search_company_requirements(
            conn, company_id, q, location_id=loc_uuid, limit=limit
        )

    return results


async def _fetch_company_credentials(conn, company_id: UUID, *, kind: str) -> List[dict]:
    """Join a company's certs/licenses to their catalog row. kind ∈ {'certification','license'}.

    These back the Certifications & Licenses tab and surface the gap-analysis
    wizard's finalize output (company_certifications / company_licenses).
    """
    if kind == "certification":
        rows = await conn.fetch(
            """
            SELECT cc.id, cc.certification_id AS catalog_id, cat.slug, cat.name,
                   cat.issuing_authority, cat.scope_level, cat.industry_tag,
                   cat.renewal_months, cat.description, cat.source_url,
                   cc.location_id, cc.source, cc.status, cc.added_at
            FROM company_certifications cc
            JOIN certifications_catalog cat ON cat.id = cc.certification_id
            WHERE cc.company_id = $1
            ORDER BY cat.name
            """,
            company_id,
        )
    else:
        rows = await conn.fetch(
            """
            SELECT cl.id, cl.license_id AS catalog_id, cat.slug, cat.name,
                   cat.issuing_authority, cat.scope_level, cat.industry_tag,
                   cat.renewal_months, cat.description, cat.source_url,
                   cl.location_id, cl.source, cl.status, cl.added_at
            FROM company_licenses cl
            JOIN licenses_catalog cat ON cat.id = cl.license_id
            WHERE cl.company_id = $1
            ORDER BY cat.name
            """,
            company_id,
        )
    out: List[dict] = []
    for r in rows:
        d = dict(r)
        d["id"] = str(d["id"])
        d["catalog_id"] = str(d["catalog_id"])
        d["location_id"] = str(d["location_id"]) if d["location_id"] is not None else None
        out.append(d)
    return out


@router.get("/certifications", response_model=List[CompanyCertificationResponse])
async def list_company_certifications(
    company_id: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Per-company certifications, joined to the catalog (admins may pass ?company_id=)."""
    cid = await resolve_company_id(current_user, company_id)
    if cid is None:
        raise HTTPException(status_code=403, detail="Access denied")
    async with get_connection() as conn:
        return await _fetch_company_credentials(conn, cid, kind="certification")


@router.get("/licenses", response_model=List[CompanyLicenseResponse])
async def list_company_licenses(
    company_id: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Per-company licenses, joined to the catalog (admins may pass ?company_id=)."""
    cid = await resolve_company_id(current_user, company_id)
    if cid is None:
        raise HTTPException(status_code=403, detail="Access denied")
    async with get_connection() as conn:
        return await _fetch_company_credentials(conn, cid, kind="license")


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


# ── Regulatory Q&A ────────────────────────────────────────


class RegulatoryQuestionRequest(BaseModel):
    question: str
    location_id: Optional[str] = None


@router.post("/ask")
async def ask_regulatory_question(
    data: RegulatoryQuestionRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Ask a natural language question about regulations for the company."""
    import asyncio
    import os

    from ..services.ai_chat import get_ai_chat_service
    from ..services.embedding_service import EmbeddingService
    from ..services.compliance_rag import ComplianceRAGService
    from ...config import get_settings

    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company found")

    await check_rate_limit(str(company_id), "compliance_ask", 10, 3600)

    location_id = None
    if data.location_id:
        try:
            location_id = UUID(data.location_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid location ID")

    service = get_ai_chat_service()
    context, sources = await service.build_regulatory_context(
        company_id, data.question, location_id=location_id,
    )

    # Generate answer using the chat model
    messages = [{"role": "user", "content": data.question}]

    answer_parts = []
    async for token in service.stream_response(messages, context):
        answer_parts.append(token)

    answer = "".join(answer_parts)
    max_similarity = max((s.get("similarity", 0) for s in sources), default=0)

    return {
        "answer": answer,
        "sources": sources,
        "confidence": round(max_similarity, 2) if sources else 0,
    }


# ── Payer Medical Policy Navigator ────────────────────────────────────────


class PayerPolicyQuestionRequest(BaseModel):
    question: str
    location_id: Optional[str] = None
    payer_name: Optional[str] = None


class PayerPolicyResearchRequest(BaseModel):
    payer_name: str
    procedure: str


@router.post("/payer-policies/ask")
async def ask_payer_policy_question(
    data: PayerPolicyQuestionRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Ask a natural language question about payer coverage criteria."""
    import os

    from ..services.ai_chat import get_ai_chat_service
    from ..services.embedding_service import EmbeddingService
    from ..services.payer_policy_rag import PayerPolicyRAGService
    from ..services.payer_policy_research import research_payer_policy
    from ...config import get_settings

    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company found")

    await check_rate_limit(str(company_id), "compliance_payer_ask", 10, 3600)

    location_id = None
    if data.location_id:
        try:
            location_id = UUID(data.location_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid location ID")

    settings = get_settings()
    api_key = os.getenv("GEMINI_API_KEY") or settings.gemini_api_key

    context = ""
    sources: list[dict] = []

    async with get_connection() as conn:
        # RAG search
        if api_key:
            embedding_service = EmbeddingService(api_key=api_key)
            rag_service = PayerPolicyRAGService(embedding_service)
            context, sources = await rag_service.get_context_for_query(
                query=data.question,
                conn=conn,
                company_id=company_id,
                location_id=location_id,
                payer_name=data.payer_name,
            )

        # Auto-research if no local data found
        if not sources and data.payer_name:
            try:
                await research_payer_policy(
                    data.payer_name, data.question, conn
                )
                # Re-search after research populated data
                if api_key:
                    context, sources = await rag_service.get_context_for_query(
                        query=data.question,
                        conn=conn,
                        company_id=company_id,
                        location_id=location_id,
                        payer_name=data.payer_name,
                    )
            except Exception as e:
                print(f"[Payer Policy] Auto-research failed: {e}")

    # Build system prompt
    system_parts = [
        "You are a medical policy expert assistant.",
        "Answer the physician's question about payer coverage criteria using the policy data below.",
        "",
        "RULES:",
        "- Cite specific clinical criteria and documentation requirements.",
        "- State whether prior authorization is required.",
        "- Include the payer's policy number and source URL when available.",
        "- If the data doesn't contain an answer, say so clearly.",
        "- Be specific about what must be documented for approval.",
    ]
    if context:
        system_parts.append(f"\n## Payer Policy Data\n{context}")
    else:
        system_parts.append(
            "\n## No matching payer policy data found in the local database."
            "\nAnswer based on general knowledge but clearly indicate this is not from verified policy data."
        )

    system_prompt = "\n".join(system_parts)
    messages = [{"role": "user", "content": data.question}]

    service = get_ai_chat_service()
    answer_parts = []
    async for token in service.stream_response(messages, system_prompt):
        answer_parts.append(token)

    answer = "".join(answer_parts)
    max_similarity = max((s.get("similarity", 0) for s in sources), default=0)

    return {
        "answer": answer,
        "sources": sources,
        "confidence": round(max_similarity, 2) if sources else 0,
    }


@router.get("/payer-policies")
async def list_payer_policies(
    payer_name: Optional[str] = Query(None),
    procedure_code: Optional[str] = Query(None),
    requires_prior_auth: Optional[bool] = Query(None),
    coverage_status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List payer medical policies, filtered by company's payer contracts."""
    from ..models.compliance import PayerPolicyResponse

    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company found")

    async with get_connection() as conn:
        # Resolve company's payer contracts
        payer_rows = await conn.fetch(
            """SELECT DISTINCT jsonb_array_elements_text(facility_attributes->'payer_contracts') AS payer
               FROM business_locations
               WHERE company_id = $1 AND is_active = true
                 AND facility_attributes IS NOT NULL
                 AND facility_attributes->'payer_contracts' IS NOT NULL""",
            company_id,
        )
        company_payers = [r["payer"] for r in payer_rows] if payer_rows else []

        # Build query
        conditions = []
        params: list = []
        idx = 1

        if payer_name:
            conditions.append(f"payer_name ILIKE ${idx}")
            params.append(f"%{payer_name}%")
            idx += 1
        elif company_payers:
            # Normalize: facility stores "medicare", DB stores "Medicare".
            # Shared map — Medicaid programs must not be searched as Medicare.
            from app.core.services.payer_policy_rag import normalize_payer_names
            conditions.append(f"payer_name = ANY(${idx}::text[])")
            params.append(normalize_payer_names(company_payers))
            idx += 1

        if procedure_code:
            conditions.append(f"${idx} = ANY(procedure_codes)")
            params.append(procedure_code)
            idx += 1

        if requires_prior_auth is not None:
            conditions.append(f"requires_prior_auth = ${idx}")
            params.append(requires_prior_auth)
            idx += 1

        if coverage_status:
            conditions.append(f"coverage_status = ${idx}")
            params.append(coverage_status)
            idx += 1

        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        rows = await conn.fetch(
            f"""SELECT id, payer_name, payer_type, policy_number, policy_title,
                       procedure_codes, procedure_description, coverage_status,
                       requires_prior_auth, clinical_criteria,
                       documentation_requirements, medical_necessity_criteria,
                       age_restrictions, frequency_limits, source_url, source_document,
                       effective_date, last_reviewed
                FROM payer_medical_policies
                {where}
                ORDER BY payer_name, policy_title
                LIMIT ${idx} OFFSET ${idx + 1}""",
            *params, limit, offset,
        )

    return [
        PayerPolicyResponse(
            id=str(r["id"]),
            payer_name=r["payer_name"],
            payer_type=r["payer_type"],
            policy_number=r["policy_number"],
            policy_title=r["policy_title"],
            procedure_codes=r["procedure_codes"] or [],
            procedure_description=r["procedure_description"],
            coverage_status=r["coverage_status"],
            requires_prior_auth=r["requires_prior_auth"] or False,
            clinical_criteria=r["clinical_criteria"],
            documentation_requirements=r["documentation_requirements"],
            medical_necessity_criteria=r["medical_necessity_criteria"],
            age_restrictions=r["age_restrictions"],
            frequency_limits=r["frequency_limits"],
            source_url=r["source_url"],
            source_document=r["source_document"],
            effective_date=r["effective_date"].isoformat() if r["effective_date"] else None,
            last_reviewed=r["last_reviewed"].isoformat() if r["last_reviewed"] else None,
        )
        for r in rows
    ]


@router.post("/payer-policies/research")
async def research_payer_policy_endpoint(
    data: PayerPolicyResearchRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Trigger Gemini research for a specific payer + procedure."""
    from ..services.payer_policy_research import research_payer_policy
    from ..models.compliance import PayerPolicyResponse

    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company found")

    await check_rate_limit(str(company_id), "compliance_payer_research", 10, 3600)

    async with get_connection() as conn:
        result = await research_payer_policy(data.payer_name, data.procedure, conn)
        if not result:
            raise HTTPException(status_code=422, detail="Could not research this policy")

        # Fetch the full row within the same connection
        row = await conn.fetchrow(
            """SELECT * FROM payer_medical_policies WHERE id = $1""",
            result["id"],
        )

    if not row:
        raise HTTPException(status_code=422, detail="Policy was not stored")

    return PayerPolicyResponse(
        id=str(row["id"]),
        payer_name=row["payer_name"],
        payer_type=row["payer_type"],
        policy_number=row["policy_number"],
        policy_title=row["policy_title"],
        procedure_codes=row["procedure_codes"] or [],
        procedure_description=row["procedure_description"],
        coverage_status=row["coverage_status"],
        requires_prior_auth=row["requires_prior_auth"] or False,
        clinical_criteria=row["clinical_criteria"],
        documentation_requirements=row["documentation_requirements"],
        medical_necessity_criteria=row["medical_necessity_criteria"],
        age_restrictions=row["age_restrictions"],
        frequency_limits=row["frequency_limits"],
        source_url=row["source_url"],
        source_document=row["source_document"],
        effective_date=row["effective_date"].isoformat() if row["effective_date"] else None,
        last_reviewed=row["last_reviewed"].isoformat() if row["last_reviewed"] else None,
    )


# ── Admin: CMS Policy Ingestion ────────────────────────────────────────


class CMSIngestRequest(BaseModel):
    source: str = "all"  # "ncds", "lcds", "all"
    state: Optional[str] = None
    embed: bool = True


@router.post("/admin/payer-policies/ingest")
async def admin_ingest_cms_policies(
    data: CMSIngestRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Trigger CMS Medicare policy ingestion with change detection. Admin only."""
    from ..dependencies import require_admin as _check_admin
    from ..services.cms_coverage_api import CMSCoverageAPI

    # Enforce admin-only (not just client)
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    api = CMSCoverageAPI()
    await api.get_license_token()

    response = {
        "total": 0,
        "new": 0,
        "updated": 0,
        "unchanged": 0,
        "failed": 0,
        "changes": [],
        "embedded": 0,
    }

    async with get_connection() as conn:
        if data.source in ("ncds", "all"):
            ncd_summary = await api.ingest_all_ncds(conn)
            for k in ("total", "new", "updated", "unchanged", "failed"):
                response[k] += ncd_summary.get(k, 0)
            response["changes"].extend(ncd_summary.get("changes", []))

        if data.source in ("lcds", "all"):
            lcd_summary = await api.ingest_all_lcds(conn, state=data.state)
            for k in ("total", "new", "updated", "unchanged", "failed"):
                response[k] += lcd_summary.get(k, 0)
            response["changes"].extend(lcd_summary.get("changes", []))

        if data.embed and response["total"] > 0:
            from ..services.payer_policy_embedding_pipeline import embed_policies
            response["embedded"] = await embed_policies(conn, payer_name="Medicare")

    return response


# ──────────────────────────────────────────────────────────────────────────────
# Protocol Gap Analysis
# ──────────────────────────────────────────────────────────────────────────────


class ProtocolAnalysisRequest(BaseModel):
    protocol_text: str
    location_id: Optional[str] = None
    categories: Optional[List[str]] = None


@router.post("/protocol-analysis")
async def protocol_analysis(
    data: ProtocolAnalysisRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Analyze a protocol document against regulatory requirements.

    Compares the provided protocol text against the company's compliance
    requirements and returns a gap analysis: which requirements are
    covered, partially covered, or missing from the protocol.
    """
    from ..services.protocol_analysis_service import analyze_protocol

    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company found")

    await check_rate_limit(str(company_id), "compliance_protocol_analysis", 10, 3600)

    # Resolve optional location_id
    location_id = None
    if data.location_id:
        try:
            location_id = UUID(data.location_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid location_id")

    # Fetch requirements — scoped to location if provided, otherwise all company requirements
    if location_id:
        # Use existing function for location-scoped requirements (returns RequirementResponse models)
        req_rows = await get_location_requirements(location_id, company_id)
        requirements = [
            {
                "requirement_key": r.id,
                "title": r.title or "",
                "description": r.description or "",
                "category": r.category or "",
                "current_value": r.current_value or "",
                "jurisdiction_level": r.jurisdiction_level or "",
                "jurisdiction_name": r.jurisdiction_name or "",
            }
            for r in req_rows
        ]
    else:
        async with get_connection() as conn:
            # Fetch all requirements across all company locations
            query = """
                SELECT cr.id, cr.category, cr.title, cr.description,
                       cr.current_value, cr.jurisdiction_level,
                       cr.jurisdiction_name, cr.source_url
                FROM compliance_requirements cr
                JOIN business_locations bl ON cr.location_id = bl.id
                WHERE bl.company_id = $1
                ORDER BY cr.category, cr.jurisdiction_level
            """
            rows = await conn.fetch(query, company_id)
            requirements = [
                {
                    "requirement_key": str(row["id"]),
                    "title": row["title"] or "",
                    "description": row["description"] or "",
                    "category": row["category"] or "",
                    "current_value": row["current_value"] or "",
                    "jurisdiction_level": row["jurisdiction_level"] or "",
                    "jurisdiction_name": row["jurisdiction_name"] or "",
                }
                for row in rows
            ]

    # Filter by categories if specified
    if data.categories:
        categories_lower = [c.lower() for c in data.categories]
        requirements = [
            r for r in requirements
            if (r.get("category") or "").lower() in categories_lower
        ]

    if not requirements:
        return {
            "covered": [],
            "gaps": [],
            "partial": [],
            "summary": "No applicable requirements found for this company/location.",
            "requirements_analyzed": 0,
        }

    # Build optional company context
    company_context = None
    async with get_connection() as conn:
        company = await conn.fetchrow(
            "SELECT name, industry FROM companies WHERE id = $1", company_id
        )
        if company:
            parts = []
            if company["name"]:
                parts.append(f"Company: {company['name']}")
            if company["industry"]:
                parts.append(f"Industry: {company['industry']}")
            if parts:
                company_context = ". ".join(parts)

    try:
        result = await analyze_protocol(
            protocol_text=data.protocol_text,
            requirements=requirements,
            company_context=company_context,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
