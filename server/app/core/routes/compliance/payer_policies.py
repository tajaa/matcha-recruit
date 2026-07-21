"""payer_policies routes (L9 split)."""
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



@router.post("/payer-policies/ask")
async def ask_payer_policy_question(
    data: PayerPolicyQuestionRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Ask a natural language question about payer coverage criteria."""
    import os

    from app.core.services.ai_chat import get_ai_chat_service
    from app.core.services.embedding_service import EmbeddingService
    from app.core.services.payer_policy_rag import PayerPolicyRAGService
    from app.core.services.payer_policy_research import research_payer_policy
    from app.config import get_settings

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
    answer_parts: list[str] = []
    try:
        async for token in service.stream_response(messages, system_prompt):
            answer_parts.append(token)
    except Exception:
        logger.exception("payer policy ask: answer generation failed")
        answer_parts = ["I couldn't generate an answer just now. The matching "
                        "policy sources are listed below — please try again shortly."]

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
    from app.core.models.compliance import PayerPolicyResponse

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
    from app.core.services.payer_policy_research import research_payer_policy
    from app.core.models.compliance import PayerPolicyResponse

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




@router.post("/admin/payer-policies/ingest")
async def admin_ingest_cms_policies(
    data: CMSIngestRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Trigger CMS Medicare policy ingestion with change detection. Admin only."""
    from app.core.dependencies import require_admin as _check_admin
    from app.core.services.cms_coverage_api import CMSCoverageAPI

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
            from app.core.services.payer_policy_embedding_pipeline import embed_policies
            response["embedded"] = await embed_policies(conn, payer_name="Medicare")

    return response
