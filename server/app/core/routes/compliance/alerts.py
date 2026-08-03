"""alerts routes (L9 split)."""
from typing import List, Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Query

from app.core.models.auth import CurrentUser
from app.core.models.compliance import AlertResponse
from app.core.services.compliance_service import (
    dismiss_alert,
    get_company_alerts,
    mark_alert_read,
    record_verification_feedback,
    update_alert_action_plan,
)
from app.matcha.dependencies import require_admin_or_client

from ._shared import (
    ActionPlanUpdateRequest,
    DismissAlertRequest,
    VerificationFeedbackRequest,
    lite_router,
    resolve_company_id,
    router,
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
    feedback_recorded = False
    if data:
        feedback_recorded = await record_verification_feedback(
            alert_uuid,
            current_user.id,
            actual_is_change=not data.is_false_positive,
            admin_notes=data.admin_notes,
            correction_reason=data.correction_reason,
            company_id=company_id,
        )

    success = await dismiss_alert(alert_uuid, company_id)
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")

    return {"message": "Alert dismissed", "feedback_recorded": feedback_recorded}




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
        actor_user_id=current_user.id,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Alert not found")

    return {"message": "Action plan updated", **updated}




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
        current_user.id,
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
