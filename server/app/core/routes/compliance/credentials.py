"""credentials routes (L9 split)."""
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
