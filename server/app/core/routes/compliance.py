import json

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from datetime import date
from typing import List, Optional
from uuid import UUID

from ...matcha.dependencies import require_admin_or_client, get_client_company_id
from ...database import get_connection
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
    CheckLogEntry,
    UpcomingLegislationResponse,
    ComplianceSummary,
    PinRequirementRequest,
    HierarchicalComplianceResponse,
)
from ..services.compliance_service import (
    create_location,
    get_locations,
    get_location,
    update_location,
    delete_location,
    get_location_requirements,
    get_company_alerts,
    mark_alert_read,
    dismiss_alert,
    get_compliance_summary,
    get_compliance_dashboard,
    update_alert_action_plan,
    run_compliance_check_background,
    run_compliance_check_stream,
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
)

router = APIRouter()


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


@router.get("/jurisdictions")
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

    location, has_complete_repository_coverage = await create_location(company_id, data)

    # Trigger background research when repository coverage is missing/partial.
    if not has_complete_repository_coverage:
        background_tasks.add_task(
            run_compliance_check_background, location.id, company_id
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

    try:
        loc_uuid = UUID(location_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid location ID")

    location = await get_location(loc_uuid, company_id)
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    # Only admin can trigger live Gemini research (Tier 3).
    # Clients can only sync from existing repository data.
    is_admin = current_user.role == "admin"

    allow_live = False
    if is_admin:
        async with get_connection() as conn:
            rows = await conn.fetch(
                """
                SELECT r.category
                FROM business_locations bl
                LEFT JOIN jurisdiction_requirements r ON r.jurisdiction_id = bl.jurisdiction_id
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


@router.get("/locations", response_model=List[dict])
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


@router.get("/locations/{location_id}", response_model=dict)
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


@router.get("/locations/{location_id}/requirements")
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


@router.get("/categories")
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


@router.get(
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


@router.put("/alerts/{alert_id}/read")
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


@router.put("/alerts/{alert_id}/dismiss")
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


@router.get("/summary", response_model=ComplianceSummary)
async def get_compliance_summary_endpoint(
    company_id: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await resolve_company_id(current_user, company_id)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    return await get_compliance_summary(company_id)


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


@router.get("/locations/{location_id}/facility-attributes")
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
