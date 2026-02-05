import json

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID

from ...matcha.dependencies import require_admin_or_client, get_client_company_id
from ...database import get_connection
from ..models.auth import CurrentUser
from ..models.compliance import (
    LocationCreate,
    LocationUpdate,
    RequirementResponse,
    AlertResponse,
    CheckLogEntry,
    UpcomingLegislationResponse,
    ComplianceSummary,
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
    run_compliance_check,
    run_compliance_check_stream,
    get_check_log,
    get_upcoming_legislation,
    record_verification_feedback,
    get_calibration_stats,
)

router = APIRouter()


async def resolve_company_id(current_user, company_id_override: str | None) -> UUID | None:
    """Resolve company ID, allowing admins to override via query param."""
    if current_user.role == "admin" and company_id_override:
        try:
            cid = UUID(company_id_override)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid company_id")
        async with get_connection() as conn:
            exists = await conn.fetchval("SELECT EXISTS(SELECT 1 FROM companies WHERE id = $1)", cid)
        if not exists:
            raise HTTPException(status_code=404, detail="Company not found")
        return cid
    return await get_client_company_id(current_user)


@router.get("/jurisdictions")
async def list_jurisdictions(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List jurisdictions that have requirement data in the repository."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT j.city, j.state, j.county,
                   COALESCE(jr.has_local_ordinance, false) AS has_local_ordinance
            FROM jurisdictions j
            LEFT JOIN jurisdiction_reference jr
                ON LOWER(jr.city) = LOWER(j.city) AND jr.state = j.state
            WHERE j.requirement_count > 0
              AND j.city <> ''
              AND j.city NOT LIKE '_county_%'
            ORDER BY j.state, j.city
            """
        )
    return [
        {
            "city": row["city"],
            "state": row["state"],
            "county": row["county"],
            "has_local_ordinance": row["has_local_ordinance"],
        }
        for row in rows
    ]


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

    location, has_repository_data = await create_location(company_id, data)

    # Only trigger background Gemini check if no repository data was found
    if not has_repository_data:
        background_tasks.add_task(run_compliance_check, location.id, company_id)

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

    async def event_stream():
        try:
            async for event in run_compliance_check_stream(loc_uuid, company_id):
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
    from ..services.compliance_service import get_location_counts

    result = []
    for loc in locations:
        counts = await get_location_counts(loc.id)
        result.append({
            "id": str(loc.id),
            "company_id": str(loc.company_id),
            "name": loc.name,
            "address": loc.address,
            "city": loc.city,
            "state": loc.state,
            "county": loc.county,
            "zipcode": loc.zipcode,
            "is_active": loc.is_active,
            "auto_check_enabled": loc.auto_check_enabled,
            "auto_check_interval_days": loc.auto_check_interval_days,
            "next_auto_check": loc.next_auto_check.isoformat() if loc.next_auto_check else None,
            "last_compliance_check": loc.last_compliance_check.isoformat() if loc.last_compliance_check else None,
            "created_at": loc.created_at.isoformat(),
            "has_local_ordinance": loc.has_local_ordinance,
            "requirements_count": counts["requirements_count"],
            "unread_alerts_count": counts["unread_alerts_count"],
        })
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
        "next_auto_check": location.next_auto_check.isoformat() if location.next_auto_check else None,
        "last_compliance_check": location.last_compliance_check.isoformat() if location.last_compliance_check else None,
        "created_at": location.created_at.isoformat(),
        "has_local_ordinance": location.has_local_ordinance,
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
        "last_compliance_check": location.last_compliance_check.isoformat() if location.last_compliance_check else None,
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


@router.get("/locations/{location_id}/requirements", response_model=List[RequirementResponse])
async def get_location_requirements_endpoint(
    location_id: str,
    category: Optional[str] = None,
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

    return await get_location_requirements(loc_uuid, company_id, category)






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


@router.get("/locations/{location_id}/upcoming-legislation", response_model=List[UpcomingLegislationResponse])
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


@router.get("/alerts", response_model=List[AlertResponse])
async def get_alerts_endpoint(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 50,
    company_id: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await resolve_company_id(current_user, company_id)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    return await get_company_alerts(company_id, status, severity, limit)


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
    correction_reason: Optional[str] = None  # "misread_date", "wrong_jurisdiction", "hallucination", "outdated_source"
    admin_notes: Optional[str] = None


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


@router.get("/summary", response_model=ComplianceSummary)
async def get_compliance_summary_endpoint(
    company_id: Optional[str] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await resolve_company_id(current_user, company_id)
    if company_id is None:
        raise HTTPException(status_code=403, detail="Access denied")

    return await get_compliance_summary(company_id)


# =====================================================
# Verification Calibration Endpoints (Phase 1.2)
# =====================================================


class VerificationFeedbackRequest(BaseModel):
    actual_is_change: bool
    admin_notes: Optional[str] = None
    correction_reason: Optional[str] = None  # "misread_date", "wrong_jurisdiction", "hallucination", etc.


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
        raise HTTPException(status_code=404, detail="No verification outcome found for this alert")

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
