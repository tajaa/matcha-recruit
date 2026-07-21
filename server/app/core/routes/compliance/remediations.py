"""remediations routes (L9 split)."""
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
        ok = await dismiss_issue(conn, company_id, data.issue_key, data.reason.strip(), current_user.id)
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
        ok = await annotate_issue(conn, company_id, data.issue_key, (data.note or "").strip(), current_user.id)
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
        ok = await reopen_issue(conn, company_id, data.issue_key, current_user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="No dismissed issue with that key")
    return {"status": "open", "issue_key": data.issue_key}
