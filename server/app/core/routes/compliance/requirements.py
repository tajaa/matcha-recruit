"""requirements routes (L9 split)."""
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




@router.post("/ask")
async def ask_regulatory_question(
    data: RegulatoryQuestionRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Ask a natural language question about regulations for the company."""
    import asyncio
    import os

    from app.core.services.ai_chat import get_ai_chat_service
    from app.core.services.embedding_service import EmbeddingService
    from app.core.services.compliance_rag import ComplianceRAGService
    from app.config import get_settings

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

    # Generate answer using Gemini. Degrade gracefully — a model outage must not
    # 500; the matched regulatory sources are still worth returning.
    messages = [{"role": "user", "content": data.question}]

    answer_parts: list[str] = []
    try:
        async for token in service.stream_response(messages, context):
            answer_parts.append(token)
    except Exception:
        logger.exception("compliance ask: answer generation failed")
        answer_parts = ["I couldn't generate an answer just now. The matching "
                        "regulatory sources are listed below — please try again shortly."]

    answer = "".join(answer_parts)
    max_similarity = max((s.get("similarity", 0) for s in sources), default=0)

    return {
        "answer": answer,
        "sources": sources,
        "confidence": round(max_similarity, 2) if sources else 0,
    }




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
    from app.core.services.protocol_analysis_service import analyze_protocol

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
            query = (
                """
                SELECT cr.id, cr.category, cr.title, cr.description,
                       cr.current_value, cr.jurisdiction_level,
                       cr.jurisdiction_name, cr.source_url
                FROM compliance_requirements cr
                JOIN business_locations bl ON cr.location_id = bl.id
                LEFT JOIN jurisdiction_requirements cat
                  ON cat.id = cr.jurisdiction_requirement_id
                WHERE bl.company_id = $1
                """
                # The gap analysis compares the handbook against what we tell
                # the business it must do — that has to be the same list.
                + await codified_gate_sql("cat", conn=conn)
                + " ORDER BY cr.category, cr.jurisdiction_level"
            )
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
