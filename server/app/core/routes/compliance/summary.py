"""summary routes (L9 split)."""
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

    from app.core.services import vertical_coverage

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
