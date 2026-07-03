"""Matcha Work — chat-driven AI workspace for HR document elements."""

import asyncio
import json
import logging
import math
import os
import urllib.parse

import httpx
import re
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Form, HTTPException, Query, Request, Response, UploadFile, File, status
from fastapi.responses import StreamingResponse

from app.core.models.auth import CurrentUser
from app.core.services.compliance_service import get_location_requirements, get_locations
from app.matcha.routes.matcha_work.ai_turn import (
    _apply_ai_updates_and_operations,
    _blog_mode_state_from_meta,
    _fetch_project_meta,
    _inject_recruiting_project_context,
    _inject_slide_context,
    _scope_slide_update,
)
from app.matcha.routes.matcha_work.pdf_export import (
    _pdf_title_from_markdown,
    _render_project_pdf,
)
from app.matcha.routes.matcha_work.projects import (
    ALLOWED_PROJECT_FILE_EXTENSIONS,
    PROJECT_FILE_MAX_BYTES,
)
from app.matcha.routes.matcha_work.elements import _list_project_elements
from app.matcha.routes.matcha_work._shared import (
    RESUME_UPLOAD_EXTENSIONS,
    RESUME_UPLOAD_MAX_BYTES,
    THREAD_FILE_EXTENSIONS,
    THREAD_FILE_MAX_BYTES,
    THREAD_FILE_TEXT_CAP,
    _build_thread_detail_response,
    _can_edit_project,
    _json_object,
    _project_company_id,
    _resolve_file_urls,
    _row_to_message,
    _sse_data,
    _strip_markdown,
    _verify_element_in_project,
    _verify_project_access,
)
from app.core.services.storage import get_storage
from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, require_company_member, get_client_company_id, require_feature
from app.matcha.services.escalation_service import should_escalate, create_escalation
from app.matcha.services.model_pricing import calculate_call_cost
from app.matcha.models.matcha_work import (
    CreateThreadRequest,
    CreateThreadResponse,
    DocumentVersionResponse,
    ElementListItem,
    FinalizeResponse,
    HandbookDocument,
    MWMessageOut,
    OnboardingDocument,
    PolicyDocument,
    PresentationDocument,
    ReviewDocument,
    RevertRequest,
    SaveDraftResponse,
    SendMessageRequest,
    SendMessageResponse,
    PinThreadRequest,
    NodeModeRequest,
    ComplianceModeRequest,
    PayerModeRequest,
    ThreadDetailResponse,
    ThreadListItem,
    OfferLetterDocument,
    UsageSummaryResponse,
    UpdateTitleRequest,
    SendReviewRequestsRequest,
    SendReviewRequestsResponse,
    ReviewRequestStatus,
    PublicReviewRequestResponse,
    PublicReviewSubmitRequest,
    PublicReviewSubmitResponse,
    SendHandbookSignaturesRequest,
    SendHandbookSignaturesResponse,
    GeneratePresentationResponse,
    ResumeBatchDocument,
    InventoryDocument,
    ProjectDocument,
    SendInterviewsRequest,
    RejectCandidateRequest,
    WorkbookDocument,
)
from app.matcha.services import matcha_work_document as doc_svc
from app.matcha.services import billing_service
from app.matcha.services import token_budget_service
from app.matcha.services.er_document_parser import ERDocumentParser
from app.matcha.services.matcha_work_handbook_upload import (
    AuditedLocation,
    MAX_RED_FLAGS,
    MAX_SECTION_PREVIEWS,
    _audit_location_group,
    _severity_rank,
    audit_uploaded_handbook,
    check_handbook_relevance,
    compute_coverage_summaries,
    derive_handbook_title,
    parse_handbook_sections,
)
from app.matcha.services.matcha_work_ai import get_ai_provider, _infer_skill_from_state, _build_company_context, compact_conversation, needs_live_web_context, fetch_live_web_context
from app.matcha.services.matcha_work_node import build_node_context, build_compliance_context, ComplianceContextResult
from app.matcha.services.onboarding_orchestrator import (
    PROVIDER_GOOGLE_WORKSPACE,
    PROVIDER_SLACK,
    start_google_workspace_onboarding,
    start_slack_onboarding,
)
from app.core.services.email import get_email_service
from app.core.services.handbook_service import HandbookService
from app.config import get_settings

logger = logging.getLogger(__name__)


async def _get_rag_context(content: str, company_id, max_tokens: int = 4000) -> str | None:
    """Fetch compliance RAG context for a user question. Returns None on failure."""
    try:
        from app.core.services.embedding_service import EmbeddingService
        from app.core.services.compliance_rag import ComplianceRAGService

        api_key = os.getenv("GEMINI_API_KEY") or get_settings().gemini_api_key
        if not api_key or not content:
            return None
        es = EmbeddingService(api_key=api_key)
        crag = ComplianceRAGService(es)
        async with get_connection() as conn:
            ctx, _ = await crag.get_context_for_question(
                query=content, conn=conn,
                company_id=company_id, max_tokens=max_tokens,
            )
        return ctx or None
    except Exception as e:
        logger.warning("RAG augmentation failed: %s", e)
        return None

router = APIRouter(dependencies=[Depends(require_feature("matcha_work"))])
public_router = APIRouter()



HANDBOOK_UPLOAD_EXTENSIONS = {".pdf", ".doc", ".docx"}
HANDBOOK_UPLOAD_MAX_BYTES = 10 * 1024 * 1024
RESUME_TEXT_CAP = 15_000






def _location_label(location: dict) -> str:
    city = str(location.get("city") or "").strip()
    state = str(location.get("state") or "").strip().upper()
    return f"{city}, {state}" if city else state


def _thread_accepts_handbook_upload(thread: dict) -> bool:
    current_state = thread.get("current_state") or {}
    current_skill = _infer_skill_from_state(current_state)
    if current_skill == "chat":
        return True
    if current_skill != "handbook":
        return False
    # Reject if an analysis is already in progress.
    if current_state.get("handbook_upload_status") == "analyzing":
        return False
    source_type = current_state.get("handbook_source_type")
    # Allow upload if already in upload mode OR if source type hasn't been
    # committed yet (user started chatting about a handbook but can still
    # switch to upload mode via the paperclip button).
    if source_type in ("upload", None):
        return True
    return False


def _build_handbook_block_message(location_labels: list[str]) -> str:
    if not location_labels:
        return (
            "Handbook upload audit is blocked because no active Compliance Locations were found. "
            "Add or sync company locations in /compliance first."
        )
    if len(location_labels) == 1:
        scoped = location_labels[0]
    else:
        scoped = ", ".join(location_labels[:6])
        if len(location_labels) > 6:
            scoped += f", and {len(location_labels) - 6} more"
    return (
        "Handbook upload audit is blocked because these active Compliance Locations are not fully synced: "
        f"{scoped}. Fix /compliance coverage first, then retry the upload."
    )


def _build_handbook_upload_summary(
    *,
    file_name: str,
    reviewed_locations: list[str],
    red_flags: list[dict],
    green_flags: list[dict] | None = None,
    jurisdiction_summaries: list[dict] | None = None,
    blocked_message: Optional[str] = None,
) -> str:
    if blocked_message:
        return blocked_message

    passing_count = len(green_flags or [])
    gap_count = len(red_flags)

    if not red_flags:
        return (
            f"Uploaded {file_name} and reviewed it against {len(reviewed_locations)} active Compliance Location(s). "
            f"{passing_count} requirement(s) covered, no jurisdiction coverage gaps detected."
        )

    counts = {"high": 0, "medium": 0, "low": 0}
    for row in red_flags:
        severity = str(row.get("severity") or "medium").lower()
        if severity in counts:
            counts[severity] += 1

    severity_bits = []
    for severity in ("high", "medium", "low"):
        count = counts[severity]
        if count:
            severity_bits.append(f"{count} {severity}")

    severity_summary = ", ".join(severity_bits) if severity_bits else f"{gap_count} issue(s)"

    # Per-jurisdiction coverage snippet
    jurisdiction_bits: list[str] = []
    for js in (jurisdiction_summaries or []):
        jurisdiction_bits.append(f"{js['location_label']} {js['covered_count']}/{js['total_count']}")
    jurisdiction_snippet = (" | ".join(jurisdiction_bits) + ".") if jurisdiction_bits else ""

    return (
        f"Uploaded {file_name} and reviewed it against {len(reviewed_locations)} active Compliance Location(s). "
        f"{passing_count} passing, {severity_summary} red flag(s). "
        + (f"Coverage: {jurisdiction_snippet} " if jurisdiction_snippet else "")
        + "Review the Preview panel for details."
    )




async def _get_affected_employees(
    company_id: UUID,
    metadata: dict,
) -> list[dict] | None:
    """Count employees affected per referenced compliance location.

    Cross-references Gemini's referenced_locations with the compliance
    reasoning chains to find matching business_location IDs, then counts
    employees at those locations (exact match via work_location_id, with
    work_state fallback for employees without a linked location).
    """
    referenced = metadata.get("referenced_locations", [])
    chains = metadata.get("compliance_reasoning", [])
    if not referenced or not chains:
        return None

    label_to_id: dict[str, str] = {c["location_label"]: c["location_id"] for c in chains}

    # Gemini may abbreviate labels — fuzzy match
    loc_ids: list[UUID] = []
    for ref in referenced:
        for label, lid in label_to_id.items():
            if ref == label or ref in label or label.startswith(ref):
                loc_ids.append(UUID(lid))
                break

    if not loc_ids:
        return None

    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT bl.id as loc_id, bl.name, bl.city, bl.state, COUNT(e.id) as count
            FROM employees e
            JOIN business_locations bl ON bl.id = e.work_location_id
            WHERE e.org_id = $1 AND e.termination_date IS NULL
              AND bl.id = ANY($2::uuid[])
            GROUP BY bl.id, bl.name, bl.city, bl.state
            """,
            company_id, loc_ids,
        )

        matched_loc_ids = {r["loc_id"] for r in rows}
        unmatched = [lid for lid in loc_ids if lid not in matched_loc_ids]

        state_rows: list = []
        if unmatched:
            loc_states = await conn.fetch(
                "SELECT id, state FROM business_locations WHERE id = ANY($1::uuid[])",
                unmatched,
            )
            states = [r["state"] for r in loc_states if r["state"]]
            if states:
                state_rows = await conn.fetch(
                    """
                    SELECT work_state as state, COUNT(*) as count
                    FROM employees
                    WHERE org_id = $1 AND termination_date IS NULL
                      AND work_state = ANY($2::text[])
                      AND (work_location_id IS NULL OR work_location_id != ALL($3::uuid[]))
                    GROUP BY work_state
                    """,
                    company_id, states, list(matched_loc_ids),
                )

    result = []
    for r in rows:
        result.append({
            "location": f"{r['name'] or r['city']}, {r['state']}",
            "count": r["count"],
            "match_type": "exact",
        })
    for r in state_rows:
        result.append({
            "location": r["state"],
            "count": r["count"],
            "match_type": "state",
        })

    return result if result else None


_GAP_KEYWORDS: dict[str, list[str]] = {
    "hipaa_privacy": ["hipaa", "privacy", "phi", "protected health"],
    "workplace_safety": ["safety", "osha", "workplace safety", "injury prevention"],
    "anti_discrimination": ["discrimination", "harassment", "equal employment", "eeo"],
    "sick_leave": ["sick leave", "paid sick", "illness"],
    "leave": ["leave", "fmla", "family leave", "medical leave"],
    "meal_breaks": ["meal", "break", "rest period"],
    "overtime": ["overtime", "hours worked", "flsa"],
    "minimum_wage": ["minimum wage", "wage"],
    "workers_comp": ["workers comp", "work injury", "occupational injury"],
    "cybersecurity": ["cybersecurity", "data security", "breach", "information security"],
    "emergency_preparedness": ["emergency", "disaster", "evacuation"],
    "clinical_safety": ["clinical", "patient safety", "infection control"],
    "billing_integrity": ["billing", "coding", "false claims", "anti-kickback"],
    "telehealth": ["telehealth", "telemedicine", "remote care"],
    "radiation_safety": ["radiation", "radiology", "nuclear"],
}


async def _detect_compliance_gaps(
    company_id: UUID,
    metadata: dict,
) -> list[dict] | None:
    """Detect gaps where jurisdiction requires a written policy but company lacks one."""
    chains = metadata.get("compliance_reasoning", [])
    if not chains:
        return None

    required_categories: set[str] = set()
    for loc in chains:
        for cat in loc.get("categories", []):
            for level in cat.get("all_levels", []):
                if level.get("requires_written_policy") and level.get("is_governing"):
                    required_categories.add(cat["category"])

    if not required_categories:
        return None

    async with get_connection() as conn:
        policies = await conn.fetch(
            "SELECT title FROM policies WHERE company_id = $1 AND status = 'active'",
            company_id,
        )
        handbook_sections = await conn.fetch("""
            SELECT hs.title FROM handbook_sections hs
            JOIN handbook_versions hv ON hv.id = hs.handbook_version_id
            JOIN handbooks h ON h.id = hv.handbook_id
            WHERE h.company_id = $1 AND h.status = 'active'
              AND hv.version_number = h.active_version
        """, company_id)

    all_titles = {
        p["title"].lower() for p in policies if p["title"]
    } | {
        s["title"].lower() for s in handbook_sections if s["title"]
    }

    gaps = []
    for cat in required_categories:
        keywords = _GAP_KEYWORDS.get(cat, [cat.replace("_", " ")])
        has_match = any(any(kw in title for kw in keywords) for title in all_titles)
        if not has_match:
            gaps.append({
                "category": cat,
                "label": cat.replace("_", " ").title(),
                "status": "missing",
            })

    return gaps if gaps else None


def _build_compliance_metadata(
    compliance_result: ComplianceContextResult | None,
    ai_resp,
) -> dict | None:
    """Merge pre-computed jurisdiction reasoning and Gemini's reasoning steps into message metadata."""
    chains = compliance_result.reasoning_chains if compliance_result else None
    ai_steps = ai_resp.compliance_reasoning if ai_resp else None
    if not chains and not ai_steps:
        return None
    metadata: dict = {}
    if chains:
        metadata["compliance_reasoning"] = chains
    if ai_steps:
        metadata["ai_reasoning_steps"] = ai_steps
    if ai_resp and ai_resp.referenced_categories:
        metadata["referenced_categories"] = ai_resp.referenced_categories
    if ai_resp and ai_resp.referenced_locations:
        metadata["referenced_locations"] = ai_resp.referenced_locations
    return metadata






# Phrases that reference UI surfaces that DO NOT EXIST for a plain thread:
# there is no project panel / project document / draft panel / canvas for a
# thread. The AI keeps hallucinating claims like "see the full draft in the
# project document" or "I've also initialized a project document" — scrub any
# sentence containing one of these phrases from replies on plain threads.


































@router.post("/threads", response_model=CreateThreadResponse, status_code=201)
async def create_thread(
    body: CreateThreadRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Create a new chat thread (optionally with an initial message)."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with this account")

    title = body.title or "New Chat"
    thread = await doc_svc.create_thread(company_id, current_user.id, title)
    thread_id = thread["id"]

    assistant_reply = None
    pdf_url = None

    if body.initial_message:
        # Save user message
        await doc_svc.add_message(thread_id, "user", body.initial_message)

        # Call AI with company context (profile already fetched during create_thread)
        ai_provider = get_ai_provider()
        profile = await doc_svc.get_company_profile_for_ai(company_id)
        ctx = _build_company_context(profile)
        messages = [{"role": "user", "content": body.initial_message}]
        ai_resp = await ai_provider.generate(messages, thread["current_state"], company_context=ctx)
        final_usage = ai_resp.token_usage

        new_version = thread["version"]
        (
            updated_state,
            new_version,
            pdf_url,
            changed,
            assistant_reply_text,
        ) = await _apply_ai_updates_and_operations(
            thread_id=thread_id,
            company_id=company_id,
            ai_resp=ai_resp,
            current_state=thread["current_state"],
            current_version=new_version,
            user_message=body.initial_message,
            current_user_id=current_user.id,
            project_id=thread.get("project_id"),
        )
        thread["current_state"] = updated_state

        await doc_svc.add_message(
            thread_id,
            "assistant",
            assistant_reply_text,
            version_created=new_version if changed else None,
        )
        try:
            await doc_svc.log_token_usage_event(
                company_id=company_id,
                user_id=current_user.id,
                thread_id=thread_id,
                token_usage=final_usage,
                operation="send_message",
            )
        except Exception as e:
            logger.warning("Failed to log Matcha Work token usage for thread %s: %s", thread_id, e)

        thread["version"] = new_version
        assistant_reply = assistant_reply_text

    return CreateThreadResponse(
        id=thread_id,
        title=thread["title"],
        status=thread["status"],
        current_state=thread["current_state"],
        version=thread["version"],
        task_type=_infer_skill_from_state(thread["current_state"]),
        is_pinned=thread.get("is_pinned", False),
        node_mode=thread.get("node_mode", False),
        compliance_mode=thread.get("compliance_mode", False),
        created_at=thread["created_at"],
        assistant_reply=assistant_reply,
        pdf_url=pdf_url,
    )


@router.post("/threads/{thread_id}/logo")
async def upload_thread_logo(
    thread_id: UUID,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Upload a company logo for an offer-letter thread and save it for the company."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    thread = await doc_svc.get_thread(thread_id, company_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    if _infer_skill_from_state(thread.get("current_state") or {}) != "offer_letter":
        raise HTTPException(status_code=400, detail="Logo upload is only available for offer letters")

    # Validate file type
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image files are allowed")

    try:
        content = await file.read()
        if len(content) > 5 * 1024 * 1024:  # 5MB limit
            raise HTTPException(status_code=400, detail="File size exceeds 5MB limit")

        # Upload to storage
        logo_url = await get_storage().upload_file(
            content,
            file.filename or "logo.png",
            prefix=f"company-logos/{company_id}",
            content_type=file.content_type,
        )

        # Update thread state
        await doc_svc.apply_update(
            thread_id,
            {"company_logo_url": logo_url},
            diff_summary="Uploaded company logo",
        )

        # Also update company logo for future use
        async with get_connection() as conn:
            await conn.execute(
                "UPDATE companies SET logo_url = $1 WHERE id = $2",
                logo_url,
                company_id,
            )

        return {"logo_url": logo_url}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to upload logo for thread %s: %s", thread_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to upload logo. Please try again.")


@router.post("/threads/{thread_id}/handbook/upload")
async def upload_thread_handbook(
    thread_id: UUID,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Upload an existing handbook and audit it against synced company jurisdictions.

    Returns JSON (ThreadDetailResponse) for blocked/rejected uploads, or an SSE
    stream with quarterly progress events for the happy-path analysis.
    """
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    thread = await doc_svc.get_thread(thread_id, company_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    if not _thread_accepts_handbook_upload(thread):
        raise HTTPException(
            status_code=400,
            detail="Handbook upload is only available in a new chat or an upload-mode handbook thread.",
        )

    filename = (file.filename or "handbook.pdf").strip() or "handbook.pdf"
    extension = os.path.splitext(filename)[1].lower()
    if extension not in HANDBOOK_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only PDF, DOCX, and DOC handbooks are supported")

    active_locations = [
        loc for loc in await get_locations(company_id)
        if loc.get("is_active", True)
    ]
    active_location_labels = [_location_label(loc) for loc in active_locations if _location_label(loc)]
    unsynced_labels = [
        _location_label(loc)
        for loc in active_locations
        if loc.get("data_status") != "synced" and _location_label(loc)
    ]
    if not active_locations or unsynced_labels:
        blocking_message = _build_handbook_block_message(
            unsynced_labels if unsynced_labels else active_location_labels
        )
        result = await doc_svc.apply_update(
            thread_id,
            {
                "handbook_source_type": "upload",
                "handbook_upload_status": "blocked",
                "handbook_title": thread.get("current_state", {}).get("handbook_title") or "Uploaded Employee Handbook",
                "handbook_status": "error",
                "handbook_uploaded_file_url": None,
                "handbook_uploaded_filename": None,
                "handbook_blocking_error": blocking_message,
                "handbook_review_locations": active_location_labels,
                "handbook_red_flags": [],
                "handbook_sections": [],
                "handbook_analysis_generated_at": datetime.now(timezone.utc).isoformat(),
                "handbook_error": None,
            },
            diff_summary="Blocked handbook upload audit",
        )
        await doc_svc.add_message(
            thread_id,
            "system",
            f"Handbook upload attempted for {filename}.",
            version_created=result["version"],
        )
        await doc_svc.add_message(
            thread_id,
            "assistant",
            blocking_message,
            version_created=result["version"],
        )
        return await _build_thread_detail_response(thread_id, company_id)

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded handbook file is empty")
    if len(content) > HANDBOOK_UPLOAD_MAX_BYTES:
        raise HTTPException(status_code=400, detail="Handbook file exceeds the 10 MB limit")

    try:
        extracted_text, _page_count = ERDocumentParser().extract_text_from_bytes(content, filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Failed to extract handbook upload text for thread %s: %s", thread_id, exc, exc_info=True)
        raise HTTPException(status_code=400, detail="Failed to read the uploaded handbook file") from exc

    if not extracted_text or not extracted_text.strip():
        raise HTTPException(status_code=400, detail="No readable handbook text was found in the uploaded file")

    # Quick relevance check — reject clearly wrong documents before expensive work.
    is_handbook, rejection_reason = await check_handbook_relevance(extracted_text, get_ai_provider().client)
    if not is_handbook:
        blocking_message = rejection_reason or (
            "This document does not appear to be an employee handbook. "
            "Please upload your company's employee handbook and try again."
        )
        result = await doc_svc.apply_update(
            thread_id,
            {
                "handbook_source_type": "upload",
                "handbook_upload_status": "blocked",
                "handbook_title": thread.get("current_state", {}).get("handbook_title") or "Uploaded Employee Handbook",
                "handbook_status": "error",
                "handbook_uploaded_file_url": None,
                "handbook_uploaded_filename": None,
                "handbook_blocking_error": blocking_message,
                "handbook_review_locations": [],
                "handbook_red_flags": [],
                "handbook_green_flags": [],
                "handbook_jurisdiction_summaries": [],
                "handbook_sections": [],
                "handbook_analysis_generated_at": datetime.now(timezone.utc).isoformat(),
                "handbook_error": None,
            },
            diff_summary="Rejected non-handbook upload",
        )
        await doc_svc.add_message(
            thread_id,
            "system",
            f"Uploaded file: {filename}.",
            version_created=result["version"],
        )
        await doc_svc.add_message(
            thread_id,
            "assistant",
            blocking_message,
            version_created=result["version"],
        )
        return await _build_thread_detail_response(thread_id, company_id)

    # --- Happy path: upload to S3, then stream incremental analysis via SSE ---

    storage = get_storage()
    uploaded_file_url = await storage.upload_file(
        content,
        filename,
        prefix=doc_svc.build_matcha_work_thread_storage_prefix(company_id, thread_id, "handbooks"),
        content_type=file.content_type,
    )
    await storage.upload_file(
        extracted_text.encode("utf-8"),
        f"{os.path.splitext(filename)[0] or 'handbook'}-extracted.txt",
        prefix=doc_svc.build_matcha_work_thread_storage_prefix(company_id, thread_id, "handbook-analysis"),
        content_type="text/plain",
    )

    # Pre-compute handbook metadata that stays constant across quarters.
    parsed_sections = parse_handbook_sections(extracted_text)
    if not parsed_sections:
        raise HTTPException(status_code=400, detail="No readable handbook text found in the uploaded file")

    handbook_title = derive_handbook_title(filename)
    all_states = sorted({str(loc.get("state") or "").strip().upper() for loc in active_locations if loc.get("state")})
    handbook_mode = "single_state" if len(set(all_states)) <= 1 else "multi_state"
    total_location_count = len(active_locations)
    all_location_labels = [_location_label(loc) for loc in active_locations if _location_label(loc)]
    section_previews = [
        {
            "section_key": section.section_key,
            "title": section.title,
            "content": section.content[:500],
            "section_type": section.section_type,
        }
        for section in parsed_sections[:MAX_SECTION_PREVIEWS]
    ]

    # Split locations into up to 4 quarter groups for incremental analysis.
    quarter_size = math.ceil(total_location_count / 4) if total_location_count else 1
    location_quarters: list[list[dict]] = [
        active_locations[i : i + quarter_size]
        for i in range(0, total_location_count, quarter_size)
    ]

    async def event_stream():
        try:
            # Mark thread as analyzing.
            await doc_svc.apply_update(
                thread_id,
                {
                    "handbook_source_type": "upload",
                    "handbook_upload_status": "analyzing",
                    "handbook_analysis_progress": 0,
                    "handbook_title": handbook_title,
                    "handbook_uploaded_file_url": uploaded_file_url,
                    "handbook_uploaded_filename": filename,
                    "handbook_mode": handbook_mode,
                    "handbook_states": all_states,
                    "handbook_sections": section_previews,
                    "handbook_review_locations": all_location_labels,
                    "handbook_blocking_error": None,
                    "handbook_error": None,
                },
                diff_summary="Started handbook analysis",
            )
            yield _sse_data({"type": "handbook_progress", "progress": 0, "status": "analyzing"})

            seen_flag_keys: set[str] = set()
            accumulated_red_flags: list[dict] = []
            accumulated_green_flags: list[dict] = []
            accumulated_coverage: dict[str, dict[str, set[str]]] = {}
            num_quarters = len(location_quarters)

            for q_idx, quarter_locs in enumerate(location_quarters, 1):
                # Fetch requirements for this quarter's locations sequentially
                # to avoid connection pool exhaustion.
                audited_locs: list[AuditedLocation] = []
                for loc in quarter_locs:
                    if not loc.get("id"):
                        continue
                    try:
                        requirements = await get_location_requirements(UUID(str(loc["id"])), company_id)
                    except Exception:
                        logger.error(
                            "Failed to load location requirements for handbook upload audit thread %s location %s",
                            thread_id,
                            loc.get("id"),
                            exc_info=True,
                        )
                        yield _sse_data({"type": "error", "message": "Failed to load synced compliance requirements."})
                        return
                    audited_locs.append(
                        AuditedLocation(
                            id=UUID(str(loc["id"])),
                            label=_location_label(loc),
                            state=str(loc.get("state") or "").strip().upper(),
                            city=str(loc.get("city") or "").strip() or None,
                            requirements=list(requirements),
                        )
                    )

                # Audit this quarter's locations.
                q_red, q_green, q_coverage = _audit_location_group(
                    parsed_sections=parsed_sections,
                    locations_subset=audited_locs,
                    all_states=all_states,
                    total_location_count=total_location_count,
                    seen_flag_keys=seen_flag_keys,
                )

                # Accumulate results.
                accumulated_red_flags.extend(q_red)
                accumulated_green_flags.extend(q_green)
                for loc_key, info in q_coverage.items():
                    if loc_key in accumulated_coverage:
                        accumulated_coverage[loc_key]["covered"] |= info["covered"]
                        accumulated_coverage[loc_key]["total"] |= info["total"]
                        accumulated_coverage[loc_key]["state"] |= info["state"]
                        accumulated_coverage[loc_key]["city"] |= info["city"]
                    else:
                        accumulated_coverage[loc_key] = info

                # Sort and cap red flags.
                sorted_red = sorted(
                    accumulated_red_flags,
                    key=lambda item: (_severity_rank(item["severity"]), item["jurisdiction"], item["section_title"]),
                )
                total_red_count = len(accumulated_red_flags)
                sorted_red = sorted_red[:MAX_RED_FLAGS]

                # Compute running summaries.
                jurisdiction_summaries, strength_score, strength_label = compute_coverage_summaries(accumulated_coverage)
                progress = q_idx / num_quarters

                partial_state = {
                    "handbook_source_type": "upload",
                    "handbook_upload_status": "analyzing",
                    "handbook_analysis_progress": progress,
                    "handbook_title": handbook_title,
                    "handbook_mode": handbook_mode,
                    "handbook_states": all_states,
                    "handbook_uploaded_file_url": uploaded_file_url,
                    "handbook_uploaded_filename": filename,
                    "handbook_blocking_error": None,
                    "handbook_error": None,
                    "handbook_sections": section_previews,
                    "handbook_review_locations": all_location_labels,
                    "handbook_red_flags": sorted_red,
                    "handbook_green_flags": accumulated_green_flags,
                    "handbook_jurisdiction_summaries": jurisdiction_summaries,
                    "handbook_strength_score": strength_score,
                    "handbook_strength_label": strength_label,
                    "handbook_analysis_generated_at": datetime.now(timezone.utc).isoformat(),
                    "handbook_total_red_flag_count": total_red_count,
                }

                await doc_svc.apply_update(
                    thread_id,
                    partial_state,
                    diff_summary=f"Handbook analysis quarter {q_idx}/{num_quarters}",
                )
                yield _sse_data({"type": "handbook_progress", "progress": progress, "partial_state": partial_state})

            # Final: mark as reviewed and add messages.
            final_state = {
                **partial_state,
                "handbook_upload_status": "reviewed",
                "handbook_analysis_progress": 1.0,
                "handbook_status": "ready",
            }
            result = await doc_svc.apply_update(
                thread_id,
                final_state,
                diff_summary=f"Uploaded handbook audit: {filename}",
            )

            summary_message = _build_handbook_upload_summary(
                file_name=filename,
                reviewed_locations=all_location_labels,
                red_flags=sorted_red,
                green_flags=accumulated_green_flags,
                jurisdiction_summaries=jurisdiction_summaries,
            )
            await doc_svc.add_message(
                thread_id,
                "system",
                f"Uploaded handbook file: {filename}.",
                version_created=result["version"],
            )
            await doc_svc.add_message(
                thread_id,
                "assistant",
                summary_message,
                version_created=result["version"],
            )

            detail = await _build_thread_detail_response(thread_id, company_id)
            yield _sse_data({"type": "complete", "data": detail.model_dump(mode="json")})
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.error("Handbook upload stream failed for thread %s: %s", thread_id, e, exc_info=True)
            yield _sse_data({"type": "error", "message": "Handbook analysis failed. Please try again."})

    return StreamingResponse(event_stream(), media_type="text/event-stream")






RESUME_EXTRACT_PROMPT = """Extract candidate information from this resume. Return ONLY valid JSON with these fields:
{"name":"...","email":"...","phone":"...","location":"...","current_title":"...","experience_years":0,"skills":["..."],"education":"highest degree - school","certifications":["..."],"summary":"1-2 sentence professional summary","strengths":["top 3 strengths"],"flags":["any concerns or gaps"]}

Resume text:
---
%s
---"""


# Kept in lockstep with ERDocumentParser.extract_text — every allowed type
# must be text-extractable so an attached file can actually feed the AI.
# (xlsx/xls excluded: no extractor; export to CSV instead.)
# Per-file cap on extracted text fed into the AI prompt. Keeps a single large
# PDF from blowing the context window; the user can ask follow-ups that target
# specific sections if a file is truncated.


async def _build_thread_file_attachment_meta(attachments) -> list[dict]:
    """For each uploaded file attachment, re-fetch its bytes from storage and
    extract capped text. Returns attachment metadata dicts (with a server-only
    `text` field) for message storage. `_row_to_message` strips `text` before
    any client response. Extraction failures degrade gracefully — the file
    still attaches, it just won't feed the AI."""
    if not attachments:
        return []
    from app.matcha.services.er_document_parser import ERDocumentParser
    storage = get_storage()
    parser = ERDocumentParser()
    out: list[dict] = []
    for att in attachments:
        meta: dict = {
            "url": att.url,
            "filename": att.filename,
            "content_type": att.content_type,
            "size": att.size,
            "kind": "file",
        }
        try:
            raw = await storage.download_file(att.url)
            text, _ = parser.extract_text_from_bytes(raw, att.filename)
            if text and text.strip():
                meta["text"] = text[:THREAD_FILE_TEXT_CAP]
        except Exception:
            logger.warning("Thread file text extraction failed: %s", att.filename, exc_info=True)
        out.append(meta)
    return out














# ── Project (top-level) endpoints ──












# ── Recruiting clients (hiring clients a recruiter works for) ──


@router.get("/recruiting-clients")
async def list_recruiting_clients_endpoint(
    include_archived: bool = Query(False),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    from app.matcha.services import recruiting_client_service as rc_svc
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return []
    return await rc_svc.list_clients(company_id, include_archived=include_archived)


@router.post("/recruiting-clients", status_code=201)
async def create_recruiting_client_endpoint(
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    from app.matcha.services import recruiting_client_service as rc_svc
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated")
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name required")
    return await rc_svc.create_client(
        company_id,
        current_user.id,
        name=name,
        website=body.get("website"),
        logo_url=body.get("logo_url"),
        notes=body.get("notes"),
    )


@router.get("/recruiting-clients/{client_id}")
async def get_recruiting_client_endpoint(
    client_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    from app.matcha.services import recruiting_client_service as rc_svc
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Not found")
    rc = await rc_svc.get_client(client_id, company_id)
    if not rc:
        raise HTTPException(status_code=404, detail="Not found")
    return rc


@router.patch("/recruiting-clients/{client_id}")
async def update_recruiting_client_endpoint(
    client_id: UUID,
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    from app.matcha.services import recruiting_client_service as rc_svc
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Not found")
    rc = await rc_svc.update_client(client_id, company_id, body)
    if not rc:
        raise HTTPException(status_code=404, detail="Not found")
    return rc


@router.post("/recruiting-clients/{client_id}/archive")
async def archive_recruiting_client_endpoint(
    client_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    from app.matcha.services import recruiting_client_service as rc_svc
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Not found")
    ok = await rc_svc.archive_client(client_id, company_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Not found")
    return {"status": "archived"}


@router.post("/recruiting-clients/{client_id}/unarchive")
async def unarchive_recruiting_client_endpoint(
    client_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    from app.matcha.services import recruiting_client_service as rc_svc
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Not found")
    ok = await rc_svc.unarchive_client(client_id, company_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Not found")
    return {"status": "active"}
















# ── Discipline project endpoints ───────────────────────────────────













# ── Blog endpoints (project_type == 'blog') ──
























# ── Note (section) comment endpoints ──










# ── Project file attachment endpoints ──


# Blog post media — images + video embedded inline in section markdown.
# Higher cap accounts for short videos; keep in sync with desktop toolbar.








# ── Project Files: folders + move ──























# ── Project-scoped kanban tasks (collab projects) ──




















@router.patch("/projects/{project_id}/pipeline-mode")
async def set_project_pipeline_mode_endpoint(
    project_id: UUID,
    body: dict = Body(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Toggle sales-pipeline mode for a collab project. Stored in
    mw_projects.project_data.pipeline_mode via a non-destructive merge so the
    board can render sales stages / deal fields. Other project_data keys are
    preserved."""
    from app.matcha.services import project_service as proj_svc

    await _verify_project_access(project_id, current_user)
    enabled = bool(body.get("enabled", False))
    return await proj_svc.update_project_data(project_id, {"pipeline_mode": enabled})




# ---------------------------------------------------------------------------
# Project Task Subtasks (checklist items under a kanban task)
# ---------------------------------------------------------------------------









# ---------------------------------------------------------------------------
# Project Elements
# ---------------------------------------------------------------------------











# ---------------------------------------------------------------------------
# Commit-driven subtask suggestions (Werk git-element bindings)
# Local Werk reads `git log`, posts commits here; we glob-match changed files
# against element repo_paths → open tickets → Gemini proposes completed
# subtasks. Suggestions are pending until the user Accepts/Dismisses; Accept
# flips is_done through the normal subtask path (history-logged).
# ---------------------------------------------------------------------------











# ---------------------------------------------------------------------------
# Element repo snapshot + "Prop" draft tickets (repo-grounded proposal chat)
# The connector syncs an element's code text here (FileManager, sandbox-safe);
# collaborators open a Prop (feat|fix draft), chat with an AI grounded on that
# code, then promote the draft to a real kanban ticket.
# ---------------------------------------------------------------------------









































# ── Element context repository: scoped files / folders / notes ──
# Element-scoped file uploads reuse POST /projects/{id}/files with the
# `element_id` form field; these endpoints cover listing + folder/note CRUD.







































# ── Research task endpoints ──




















# ── Diagram editing endpoints ──








# ── Project collaborator endpoints ──


@router.post("/projects/{project_id}/discussion-channel")
async def ensure_project_discussion_channel(
    project_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get or create the private channel for a collab project's discussion.

    Idempotent. The channel is shared by all active collaborators and is
    the recommended chat surface for the collab project type. Returns
    `{ "channel_id": "<uuid>" }` for collab projects, or 404 for any
    other project type.

    Authorisation: the caller is allowed if they own the project's
    company OR are an active collaborator. This mirrors the visibility
    rule used by list_projects.
    """
    from app.matcha.services import project_service as proj_svc

    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        proj = await conn.fetchrow(
            "SELECT company_id FROM mw_projects WHERE id = $1",
            project_id,
        )
        if not proj:
            raise HTTPException(status_code=404, detail="Project not found")

        is_owner_tenant = company_id is not None and proj["company_id"] == company_id
        is_collaborator = False
        if not is_owner_tenant:
            is_collaborator = bool(await conn.fetchval(
                """
                SELECT EXISTS(
                    SELECT 1 FROM mw_project_collaborators
                    WHERE project_id = $1 AND user_id = $2 AND status = 'active'
                )
                """,
                project_id, current_user.id,
            ))
        if not is_owner_tenant and not is_collaborator:
            raise HTTPException(status_code=404, detail="Project not found")

    channel_id = await proj_svc.ensure_discussion_channel(project_id, current_user.id)
    if channel_id is None:
        raise HTTPException(status_code=400, detail="Discussion channels are only available for collab projects")
    return {"channel_id": str(channel_id)}


@router.get("/projects/{project_id}/collaborators")
async def list_project_collaborators(
    project_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List collaborators on a project."""
    from app.matcha.services import project_service as proj_svc
    await _verify_project_access(project_id, current_user)
    return await proj_svc.list_collaborators(project_id)


@router.post("/projects/{project_id}/collaborators")
async def add_project_collaborator(
    project_id: UUID,
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Add a user as a collaborator. Only the project owner can invite."""
    from app.matcha.services import project_service as proj_svc
    _project, role = await _verify_project_access(project_id, current_user)
    if role != "owner":
        raise HTTPException(status_code=403, detail="Only the project owner can add collaborators")
    user_id = body.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    try:
        return await proj_svc.add_collaborator(project_id, UUID(user_id), current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/projects/{project_id}/collaborators/{user_id}")
async def remove_project_collaborator(
    project_id: UUID,
    user_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Remove a collaborator from a project. Only the owner can do this."""
    from app.matcha.services import project_service as proj_svc
    await _verify_project_access(project_id, current_user)
    try:
        return await proj_svc.remove_collaborator(project_id, user_id, current_user.id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/projects/{project_id}/invite")
async def invite_to_project(
    project_id: UUID,
    body: dict = Body(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Invite a user to a project by email. Creates pending collaborator + inbox notification + email."""
    from app.core.services.email import get_email_service

    await _verify_project_access(project_id, current_user)

    email = (body.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="email is required")

    async with get_connection() as conn:
        # Look up user by email
        invitee = await conn.fetchrow("SELECT id, email FROM users WHERE email = $1 AND is_active = true", email)
        if not invitee:
            raise HTTPException(status_code=404, detail="User not found. They need to create an account first.")

        invitee_id = invitee["id"]

        if invitee_id == current_user.id:
            raise HTTPException(status_code=400, detail="You cannot invite yourself")

        # Check if already a collaborator
        existing = await conn.fetchrow(
            "SELECT status FROM mw_project_collaborators WHERE project_id = $1 AND user_id = $2",
            project_id, invitee_id,
        )
        if existing:
            if existing["status"] == "active":
                raise HTTPException(status_code=400, detail="User is already a collaborator")
            # Was pending or removed — re-invite as pending
            await conn.execute(
                "UPDATE mw_project_collaborators SET status = 'pending', invited_by = $3, created_at = NOW() WHERE project_id = $1 AND user_id = $2",
                project_id, invitee_id, current_user.id,
            )
        else:
            await conn.execute(
                """INSERT INTO mw_project_collaborators (project_id, user_id, invited_by, role, status)
                   VALUES ($1, $2, $3, 'collaborator', 'pending')""",
                project_id, invitee_id, current_user.id,
            )

        # Get project title and inviter name for notifications
        project = await conn.fetchrow("SELECT title FROM mw_projects WHERE id = $1", project_id)
        inviter = await conn.fetchrow("SELECT email FROM users WHERE id = $1", current_user.id)
        inviter_client = await conn.fetchrow("SELECT name FROM clients WHERE user_id = $1", current_user.id)
        inviter_name = (inviter_client["name"] if inviter_client else None) or inviter["email"].split("@")[0]
        project_title = project["title"] if project else "a project"

        # Create inbox notification
        msg_content = f"**{inviter_name}** has invited you to join the project **{project_title}**. Go to your projects to accept or decline."
        conversation = await conn.fetchrow(
            """INSERT INTO inbox_conversations (title, is_group, created_by, last_message_at, last_message_preview)
               VALUES ($1, false, $2, NOW(), $3)
               RETURNING id""",
            f"Project Invite: {project_title}", current_user.id, msg_content[:100],
        )
        conv_id = conversation["id"]
        await conn.execute(
            "INSERT INTO inbox_participants (conversation_id, user_id) VALUES ($1, $2)", conv_id, current_user.id,
        )
        await conn.execute(
            "INSERT INTO inbox_participants (conversation_id, user_id) VALUES ($1, $2)", conv_id, invitee_id,
        )
        await conn.execute(
            """INSERT INTO inbox_messages (conversation_id, sender_id, content)
               VALUES ($1, $2, $3)""",
            conv_id, current_user.id, msg_content,
        )

    # Send email notification
    email_svc = get_email_service()
    if email_svc.is_configured():
        settings = get_settings()
        base_url = settings.app_base_url.rstrip("/")
        try:
            await email_svc.send_email(
                to_email=email,
                to_name=email.split("@")[0],
                subject=f"{inviter_name} invited you to a project on Matcha",
                html_content=f"""
                <div style="font-family: -apple-system, sans-serif; max-width: 480px; margin: 0 auto;">
                    <h2 style="color: #e4e4e7;">Project Invitation</h2>
                    <p style="color: #a1a1aa;"><strong>{inviter_name}</strong> invited you to join <strong>{project_title}</strong>.</p>
                    <a href="{base_url}/work"
                       style="display: inline-block; background: #10b981; color: white; padding: 12px 28px;
                              border-radius: 8px; text-decoration: none; font-size: 14px; font-weight: 600;">
                        View Projects
                    </a>
                </div>
                """,
            )
        except Exception as exc:
            logger.warning("Failed to send project invite email: %s", exc)

    # Create MW notification for the invitee
    try:
        from app.matcha.services import notification_service as notif_svc
        company_id = await get_client_company_id(current_user)
        await notif_svc.create_notification(
            user_id=invitee_id,
            company_id=company_id,
            type="project_invite",
            title=f"Project invite from {inviter_name}",
            body=f"You've been invited to join \"{project_title}\"",
            link=f"/work",
            metadata={"project_id": str(project_id), "invited_by": str(current_user.id)},
        )
    except Exception as e:
        logger.warning("Failed to create invite notification: %s", e)

    return {"invited": True, "email": email}


async def _create_inbox_dm(*, from_user_id: UUID, to_user_id: UUID, conv_title: str, content: str) -> None:
    """Create a 1:1 inbox conversation carrying a single message. Used for the
    project invite-accepted ("X joined") notice."""
    async with get_connection() as conn:
        conv = await conn.fetchrow(
            """INSERT INTO inbox_conversations (title, is_group, created_by, last_message_at, last_message_preview)
               VALUES ($1, false, $2, NOW(), $3) RETURNING id""",
            conv_title, from_user_id, content[:100],
        )
        cid = conv["id"]
        await conn.execute("INSERT INTO inbox_participants (conversation_id, user_id) VALUES ($1, $2)", cid, from_user_id)
        await conn.execute("INSERT INTO inbox_participants (conversation_id, user_id) VALUES ($1, $2)", cid, to_user_id)
        await conn.execute("INSERT INTO inbox_messages (conversation_id, sender_id, content) VALUES ($1, $2, $3)", cid, from_user_id, content)


@router.post("/projects/{project_id}/invite/accept")
async def accept_project_invite(
    project_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Accept a pending invite — join the project + its chat, and tell the
    creator/inviter you've joined (toast + inbox + bell)."""
    from app.matcha.services import project_service as proj_svc
    from app.matcha.services import notification_service as notif_svc

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """UPDATE mw_project_collaborators
               SET status = 'active'
               WHERE project_id = $1 AND user_id = $2 AND status = 'pending'
               RETURNING invited_by""",
            project_id, current_user.id,
        )
        if row is None:
            raise HTTPException(status_code=404, detail="No pending invitation found")
        invited_by = row["invited_by"]
        proj = await conn.fetchrow(
            "SELECT title, created_by, company_id FROM mw_projects WHERE id = $1", project_id
        )

    # Now active → join the discussion channel (the collab chat surface).
    try:
        await proj_svc.ensure_collaborator_in_discussion_channel(project_id, current_user.id)
    except Exception as e:
        logger.warning("add accepted collaborator to channel failed: %s", e)

    # Tell the creator + inviter that someone joined: bell + inbox now, and the
    # WS push behind create_notification drives the in-app toast on their client.
    joiner_name = await proj_svc._resolve_actor_name(current_user.id) or "Someone"
    title = proj["title"] if proj else "a project"
    company_id = proj["company_id"] if proj else None
    recipients = {
        r for r in [(proj["created_by"] if proj else None), invited_by]
        if r is not None and r != current_user.id
    }
    for rid in recipients:
        try:
            await notif_svc.create_notification(
                user_id=rid,
                company_id=company_id,
                type="collab_joined",
                title=f"{joiner_name} joined {title}",
                body=f"{joiner_name} has joined the collab",
                link="/work",
                metadata={"project_id": str(project_id), "project_title": title, "joiner_name": joiner_name},
            )
            await _create_inbox_dm(
                from_user_id=current_user.id, to_user_id=rid,
                conv_title=f"Joined: {title}",
                content=f"**{joiner_name}** has joined **{title}**.",
            )
        except Exception as e:
            logger.warning("collab_joined notify failed for %s: %s", rid, e)

    return {"accepted": True}


@router.post("/projects/{project_id}/invite/decline")
async def decline_project_invite(
    project_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Decline a pending project invitation."""
    async with get_connection() as conn:
        result = await conn.execute(
            """UPDATE mw_project_collaborators
               SET status = 'removed'
               WHERE project_id = $1 AND user_id = $2 AND status = 'pending'""",
            project_id, current_user.id,
        )
        if result.endswith("0"):
            raise HTTPException(status_code=404, detail="No pending invitation found")
    return {"declined": True}


@router.get("/project-invites")
async def list_pending_invites(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List all pending project invitations for the current user."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT c.project_id, p.title AS project_title,
                      u.email AS invited_by_email, cl.name AS invited_by_name,
                      c.created_at
               FROM mw_project_collaborators c
               JOIN mw_projects p ON p.id = c.project_id
               JOIN users u ON u.id = c.invited_by
               LEFT JOIN clients cl ON cl.user_id = c.invited_by
               WHERE c.user_id = $1 AND c.status = 'pending'
               ORDER BY c.created_at DESC""",
            current_user.id,
        )
    return [
        {
            "project_id": str(r["project_id"]),
            "project_title": r["project_title"],
            "invited_by": r["invited_by_name"] or r["invited_by_email"].split("@")[0],
            "invited_at": r["created_at"].isoformat() if r["created_at"] else None,
        }
        for r in rows
    ]


@router.get("/admin-users/search")
async def search_admin_users_endpoint(
    q: str = Query(..., min_length=2, max_length=100),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Search admin users for the collaborator invite picker."""
    from app.matcha.services import project_service as proj_svc
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can search admin users")
    return await proj_svc.search_admin_users(q, current_user.id)


@router.get("/projects/{project_id}/chats")
async def list_project_chats_endpoint(
    project_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List AI chat threads in a project visible to the current user.

    Private-per-person: returns threads the user created in this project plus
    any project thread shared with them. Access to the project itself is
    verified first.
    """
    from app.matcha.services import project_service as proj_svc
    project, _role = await _verify_project_access(project_id, current_user)
    company_id = project.get("company_id")
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated")
    return await proj_svc.list_project_chats(project_id, company_id, current_user.id)


@router.post("/projects/{project_id}/chats")
async def create_project_chat_endpoint(
    project_id: UUID,
    body: dict = {},
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Create a new chat within a project."""
    from app.matcha.services import project_service as proj_svc
    project, _role = await _verify_project_access(project_id, current_user)
    company_id = project.get("company_id")
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated")
    return await proj_svc.create_project_chat(project_id, company_id, current_user.id, body.get("title"))


@router.post("/projects/{project_id}/posting/from-chat")
async def populate_posting_from_chat(
    project_id: UUID,
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Extract structured posting fields from a chat message using AI."""
    from app.matcha.services import project_service as proj_svc

    project, _role = await _verify_project_access(project_id, current_user)

    content = body.get("content", "")
    if not content:
        raise HTTPException(status_code=400, detail="No content provided")

    # Use AI to extract structured fields
    ai_provider = get_ai_provider()
    prompt = (
        "Extract job posting fields from this text. Return ONLY valid JSON with these fields "
        "(use null for missing fields):\n"
        '{"title":"...","description":"...","requirements":"...","compensation":"...",'
        '"location":"...","employment_type":"full-time|part-time|contract"}\n\n'
        f"Text:\n---\n{content[:5000]}\n---"
    )
    ai_resp = await ai_provider.generate(
        [{"role": "user", "content": prompt}], {}, company_context=""
    )

    # Parse the AI response
    raw = ai_resp.assistant_reply.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        fields = json.loads(raw)
    except Exception:
        # Fallback: put everything in description
        fields = {"description": _strip_markdown(content)}

    # Merge with existing posting (don't overwrite non-null fields with null)
    existing = (project.get("project_data") or {}).get("posting") or {}
    merged = {**existing}
    for k, v in fields.items():
        if v is not None and str(v).strip():
            merged[k] = v

    result = await proj_svc.update_project_data(project_id, {"posting": merged})
    return result


@router.put("/projects/{project_id}/posting")
async def update_project_posting(
    project_id: UUID,
    body: dict,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Update the job posting data for a recruiting project."""
    from app.matcha.services import project_service as proj_svc
    await _verify_project_access(project_id, current_user)
    return await proj_svc.update_project_data(project_id, {"posting": body})


@router.post("/projects/{project_id}/shortlist/{candidate_id}")
async def toggle_project_shortlist(
    project_id: UUID,
    candidate_id: str,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Toggle a candidate on/off the shortlist."""
    from app.matcha.services import project_service as proj_svc
    await _verify_project_access(project_id, current_user)
    return await proj_svc.toggle_shortlist(project_id, candidate_id)


@router.post("/projects/{project_id}/dismiss/{candidate_id}")
async def toggle_project_dismiss(
    project_id: UUID,
    candidate_id: str,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Toggle a candidate on/off the dismissed list."""
    from app.matcha.services import project_service as proj_svc
    await _verify_project_access(project_id, current_user)
    return await proj_svc.toggle_dismiss(project_id, candidate_id)


@router.post("/projects/{project_id}/reject/{candidate_id}")
async def reject_project_candidate(
    project_id: UUID,
    candidate_id: str,
    body: RejectCandidateRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Reject a candidate, optionally sending a polite rejection email.

    When `send_email=false` this is equivalent to dismissing the candidate
    with a `status='rejected'` marker — no email goes out.
    """
    from app.matcha.services import project_service as proj_svc
    from app.core.services.email import EmailService

    project, _role = await _verify_project_access(project_id, current_user)
    data = project.get("project_data") or {}
    candidates = list(data.get("candidates") or [])

    candidate_idx = next(
        (i for i, c in enumerate(candidates) if c.get("id") == candidate_id),
        None,
    )
    if candidate_idx is None:
        raise HTTPException(status_code=404, detail="Candidate not found in project")

    candidate = candidates[candidate_idx]
    name = candidate.get("name") or candidate.get("filename", "Candidate")
    email = candidate.get("email")

    # Idempotency guard: if the candidate was already rejected + hidden, don't
    # re-send the email. Return the current project so the caller's state stays
    # in sync but the `email_sent` flag is honest.
    dismissed_ids = list(data.get("dismissed_ids") or [])
    already_rejected = (
        candidate.get("status") == "rejected" and candidate_id in dismissed_ids
    )
    if already_rejected:
        return {"project": project, "email_sent": False, "already_rejected": True}

    email_sent = False
    if body.send_email and email:
        company_id = project.get("company_id")
        async with get_connection() as conn:
            company_row = await conn.fetchrow(
                "SELECT name FROM companies WHERE id = $1", company_id
            )
        company_name = company_row["name"] if company_row else "the company"
        position_title = project.get("title") or "Open Position"

        email_svc = EmailService()
        try:
            email_sent = await email_svc.send_candidate_rejection_email(
                to_email=email,
                to_name=name,
                company_name=company_name,
                position_title=position_title,
                custom_message=body.custom_message,
            )
        except Exception as e:
            logger.error("Rejection email failed for %s: %s", email, e, exc_info=True)
            email_sent = False

    # Mutate candidate: mark rejected, store internal reason
    candidates[candidate_idx] = {
        **candidate,
        "status": "rejected",
        "rejection_reason": body.rejection_reason,
    }

    # Add to dismissed_ids so existing filters hide the candidate by default
    if candidate_id not in dismissed_ids:
        dismissed_ids.append(candidate_id)

    updated_project = await proj_svc.update_project_data(
        project_id,
        {"candidates": candidates, "dismissed_ids": dismissed_ids},
    )

    return {
        "project": updated_project,
        "email_sent": email_sent,
    }


@router.post("/projects/{project_id}/resume/upload")
async def upload_project_resumes(
    project_id: UUID,
    files: list[UploadFile] = File(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Upload resumes to a recruiting project — extract candidates into project_data."""
    from app.matcha.services import project_service as proj_svc

    project, _role = await _verify_project_access(project_id, current_user)

    # Require finalized posting before accepting resumes
    data = project.get("project_data") or {}
    posting = data.get("posting") or {}
    if not posting.get("finalized"):
        raise HTTPException(status_code=400, detail="Finalize the job posting before uploading resumes")

    # Validate files
    parsed_files: list[tuple[str, bytes, str]] = []
    for f in files:
        fname = f.filename or "resume"
        ext = os.path.splitext(fname)[1].lower()
        if ext not in RESUME_UPLOAD_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {fname}")
        raw = await f.read()
        if len(raw) > RESUME_UPLOAD_MAX_BYTES:
            raise HTTPException(status_code=400, detail=f"File exceeds 10 MB limit: {fname}")
        parsed_files.append((fname, raw, f.content_type or "application/octet-stream"))

    async def event_stream():
        try:
            from google import genai as _genai
            from google.genai import types as _types

            api_key = os.getenv("GEMINI_API_KEY") or get_settings().gemini_api_key
            client = _genai.Client(api_key=api_key)
            extract_model = "gemini-3.1-flash-lite"
            parser = ERDocumentParser()
            new_candidates = []

            for idx, (fname, raw, ct) in enumerate(parsed_files, 1):
                yield _sse_data({"type": "status", "message": f"Extracting text from {fname} ({idx}/{len(parsed_files)})..."})
                try:
                    text, _ = parser.extract_text_from_bytes(raw, fname)
                except Exception:
                    continue
                if not text or len(text.strip()) < 50:
                    continue

                yield _sse_data({"type": "status", "message": f"Analyzing {fname} ({idx}/{len(parsed_files)})..."})
                capped = text[:RESUME_TEXT_CAP]
                try:
                    resp = await asyncio.wait_for(
                        asyncio.to_thread(
                            lambda t=capped: client.models.generate_content(
                                model=extract_model,
                                contents=[_types.Content(role="user", parts=[_types.Part.from_text(text=RESUME_EXTRACT_PROMPT % t)])],
                                config=_types.GenerateContentConfig(temperature=0.1),
                            )
                        ),
                        timeout=60,
                    )
                    raw_json = (resp.text or "").strip()
                    if raw_json.startswith("```"):
                        raw_json = raw_json.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
                    data = json.loads(raw_json)
                    new_candidates.append({
                        "id": os.urandom(8).hex(),
                        "filename": fname,
                        "name": data.get("name"),
                        "email": data.get("email"),
                        "phone": data.get("phone"),
                        "location": data.get("location"),
                        "current_title": data.get("current_title"),
                        "experience_years": data.get("experience_years"),
                        "skills": data.get("skills"),
                        "education": data.get("education"),
                        "certifications": data.get("certifications"),
                        "summary": data.get("summary"),
                        "strengths": data.get("strengths"),
                        "flags": data.get("flags"),
                        "status": "analyzed",
                    })
                except Exception as e:
                    logger.warning("Resume extraction failed for %s: %s", fname, e)

            if new_candidates:
                yield _sse_data({"type": "status", "message": f"Adding {len(new_candidates)} candidates to project..."})
                result = await proj_svc.add_candidates_to_project(project_id, new_candidates)
                yield _sse_data({"type": "complete", "data": {"candidates_added": len(new_candidates), "project": result}})
            else:
                yield _sse_data({"type": "complete", "data": {"candidates_added": 0}})
        except Exception as e:
            logger.error("Project resume upload failed: %s", e, exc_info=True)
            yield _sse_data({"type": "error", "message": "Failed to process resumes."})
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/projects/placeholder-questions")
async def generate_placeholder_questions(
    body: dict,
    _current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Generate human-friendly questions for each placeholder using AI."""
    placeholders = body.get("placeholders") or []  # [{placeholder, label}]
    if not placeholders:
        return {"questions": []}

    items = "\n".join(
        f"- Placeholder: {p['placeholder']}, Context: \"{p.get('label', p['placeholder'])}\""
        for p in placeholders
    )

    try:
        from google import genai as _genai
        from google.genai import types as _types

        api_key = os.getenv("GEMINI_API_KEY") or get_settings().gemini_api_key
        client = _genai.Client(api_key=api_key)
        resp = await asyncio.to_thread(
            lambda: client.models.generate_content(
                model="gemini-3.1-flash-lite",
                contents=[_types.Content(role="user", parts=[_types.Part.from_text(
                    text=f"Generate a short, friendly question for each placeholder below. The question should help someone fill in the blank in a job posting. Return ONE question per line, in order, no numbering or bullets.\n\n{items}"
                )])],
                config=_types.GenerateContentConfig(temperature=0.3),
            )
        )
        lines = [l.strip() for l in (resp.text or "").strip().split("\n") if l.strip()]
        # Pair questions with placeholders
        questions = []
        for i, p in enumerate(placeholders):
            q = lines[i] if i < len(lines) else f"What's the {p['placeholder']}?"
            questions.append({"placeholder": p["placeholder"], "label": p.get("label", ""), "question": q})
        return {"questions": questions}
    except Exception as e:
        logger.warning("Placeholder question generation failed: %s", e)
        # Fallback to raw names
        return {"questions": [
            {"placeholder": p["placeholder"], "label": p.get("label", ""), "question": f"What's the {p['placeholder']}?"}
            for p in placeholders
        ]}


@router.post("/projects/extract-value")
async def extract_placeholder_value(
    body: dict,
    _current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Extract a clean replacement value from a user's natural-language answer."""
    user_input = (body.get("input") or "").strip()
    placeholder = body.get("placeholder") or ""
    context = body.get("context") or ""

    if not user_input:
        return {"value": user_input}

    # Simple case: short input (≤ 3 words) — use directly
    if len(user_input.split()) <= 3:
        return {"value": user_input}

    # Complex input: use Gemini flash lite to extract the actual value
    try:
        from google import genai as _genai
        from google.genai import types as _types

        api_key = os.getenv("GEMINI_API_KEY") or get_settings().gemini_api_key
        client = _genai.Client(api_key=api_key)
        resp = await asyncio.to_thread(
            lambda: client.models.generate_content(
                model="gemini-3.1-flash-lite",
                contents=[_types.Content(role="user", parts=[_types.Part.from_text(
                    text=f"Extract the exact value to fill in the placeholder {placeholder} from this user answer: \"{user_input}\"\n"
                         f"Context from the document: \"{context}\"\n"
                         f"Return ONLY the extracted value — no quotes, no explanation, just the value itself."
                )])],
                config=_types.GenerateContentConfig(temperature=0.0),
            )
        )
        extracted = (resp.text or "").strip().strip('"').strip("'")
        return {"value": extracted if extracted else user_input}
    except Exception as e:
        logger.warning("Value extraction failed, using raw input: %s", e)
        return {"value": user_input}


@router.post("/projects/{project_id}/resume/analyze")
async def analyze_project_candidates(
    project_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Rank candidates against the job posting using AI."""
    from app.matcha.services import project_service as proj_svc

    project, _role = await _verify_project_access(project_id, current_user)

    # Build posting text from sections (strip HTML tags for clean AI input)
    sections = project.get("sections") or []
    def _strip_html(html: str) -> str:
        return re.sub(r'<[^>]+>', '', html).strip()

    posting_text = "\n\n".join(
        f"{s.get('title', 'Untitled')}:\n{_strip_html(s.get('content', ''))}"
        for s in sections
    )
    if not posting_text.strip():
        raise HTTPException(status_code=400, detail="No posting content to analyze against")

    data = project.get("project_data") or {}
    candidates = data.get("candidates") or []
    if not candidates:
        raise HTTPException(status_code=400, detail="No candidates to analyze")

    # Build candidate summaries for the prompt
    candidate_entries = []
    for c in candidates:
        if c.get("status") not in ("analyzed", "interview_sent", "interview_completed", "interview_in_progress"):
            continue
        entry = f"ID: {c['id']}\nName: {c.get('name', 'Unknown')}\n"
        if c.get("current_title"):
            entry += f"Title: {c['current_title']}\n"
        if c.get("experience_years") is not None:
            entry += f"Experience: {c['experience_years']} years\n"
        if c.get("skills"):
            entry += f"Skills: {', '.join(c['skills'][:15])}\n"
        if c.get("education"):
            entry += f"Education: {c['education']}\n"
        if c.get("certifications"):
            entry += f"Certifications: {', '.join(c['certifications'])}\n"
        if c.get("summary"):
            entry += f"Summary: {c['summary']}\n"
        if c.get("strengths"):
            entry += f"Strengths: {', '.join(c['strengths'])}\n"
        if c.get("flags"):
            entry += f"Flags: {', '.join(c['flags'])}\n"
        candidate_entries.append(entry)

    if not candidate_entries:
        raise HTTPException(status_code=400, detail="No analyzed candidates to rank")

    try:
        from google import genai as _genai
        from google.genai import types as _types

        api_key = os.getenv("GEMINI_API_KEY") or get_settings().gemini_api_key
        client = _genai.Client(api_key=api_key)

        prompt = (
            "You are a recruiting analyst. Given the job posting and candidate profiles below, "
            "score each candidate on how well they match the posting (0-100). "
            "Return ONLY valid JSON — an array of objects with these exact fields:\n"
            '  [{"id": "<candidate_id>", "score": <0-100>, "summary": "<1-2 sentence reason>"}]\n'
            "Order by score descending (best match first).\n\n"
            f"=== JOB POSTING ===\n{posting_text}\n\n"
            f"=== CANDIDATES ===\n" + "\n---\n".join(candidate_entries)
        )

        resp = await asyncio.wait_for(
            asyncio.to_thread(
                lambda: client.models.generate_content(
                    model="gemini-3.1-flash-lite",
                    contents=[_types.Content(role="user", parts=[_types.Part.from_text(text=prompt)])],
                    config=_types.GenerateContentConfig(temperature=0.1),
                )
            ),
            timeout=60,
        )

        raw = (resp.text or "").strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        rankings = json.loads(raw)

        # Merge scores into candidates
        score_map = {r["id"]: r for r in rankings}
        updated_candidates = []
        for c in candidates:
            match = score_map.get(c["id"])
            if match:
                updated_candidates.append({
                    **c,
                    "match_score": match.get("score"),
                    "match_summary": match.get("summary"),
                })
            else:
                updated_candidates.append(c)

        # Sort by match_score descending
        updated_candidates.sort(key=lambda x: x.get("match_score") or 0, reverse=True)

        await proj_svc.update_project_data(project_id, {"candidates": updated_candidates})
        return {"analyzed": len(rankings), "candidates": updated_candidates}

    except json.JSONDecodeError as e:
        logger.error("Failed to parse ranking JSON: %s", e)
        raise HTTPException(status_code=500, detail="Failed to parse AI ranking response")
    except Exception as e:
        logger.error("Candidate analysis failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/projects/{project_id}/resume/send-interviews")
async def send_project_interviews(
    project_id: UUID,
    body: SendInterviewsRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Create screening interviews for selected project candidates and send invite emails."""
    import secrets as _secrets
    from app.matcha.services import project_service as proj_svc
    from app.core.services.email import EmailService

    project, _role = await _verify_project_access(project_id, current_user)

    data = project.get("project_data") or {}
    candidates = data.get("candidates") or []
    if not candidates:
        raise HTTPException(status_code=400, detail="No candidates in this project")

    company_id = project.get("company_id")
    async with get_connection() as conn:
        company_row = await conn.fetchrow("SELECT name FROM companies WHERE id = $1", company_id)
    company_name = company_row["name"] if company_row else "the company"

    position_title = body.position_title or project.get("title") or "Open Position"
    email_svc = EmailService()
    settings = get_settings()

    sent = []
    failed = []
    updated_candidates = list(candidates)

    for cid in body.candidate_ids:
        candidate = None
        candidate_idx = None
        for idx, c in enumerate(updated_candidates):
            if c.get("id") == cid:
                candidate = c
                candidate_idx = idx
                break

        if candidate is None:
            failed.append({"id": cid, "error": "Candidate not found in project"})
            continue

        email = candidate.get("email")
        name = candidate.get("name") or candidate.get("filename", "Candidate")
        if not email:
            failed.append({"id": cid, "error": f"No email for {name}"})
            continue

        try:
            invite_token = _secrets.token_urlsafe(32)
            interview_data = json.dumps({
                "invite_token": invite_token,
                "candidate_name": name,
                "candidate_email": email,
                "position_title": position_title,
                "company_name": company_name,
                "resume_batch_project_id": str(project_id),
                "resume_batch_candidate_id": cid,
            })

            async with get_connection() as interview_conn:
                interview_row = await interview_conn.fetchrow(
                    """
                    INSERT INTO interviews (id, company_id, interviewer_name, interview_type, raw_culture_data, status, created_at)
                    VALUES (gen_random_uuid(), $1, $2, 'screening', $3, 'pending', NOW())
                    RETURNING id
                    """,
                    company_id,
                    name,
                    interview_data,
                )
            interview_id = interview_row["id"]

            invite_url = f"{settings.app_base_url}/candidate-interview/{invite_token}"
            email_sent = await email_svc.send_candidate_interview_invite_email(
                to_email=email,
                to_name=name,
                company_name=company_name,
                position_title=position_title,
                invite_url=invite_url,
                custom_message=body.custom_message,
            )

            updated_candidates[candidate_idx] = {
                **candidate,
                "status": "interview_sent",
                "interview_id": str(interview_id),
            }

            sent.append({
                "id": cid,
                "name": name,
                "email": email,
                "interview_id": str(interview_id),
                "email_sent": email_sent,
            })
        except Exception as e:
            logger.error("Failed to create interview for project candidate %s: %s", cid, e, exc_info=True)
            failed.append({"id": cid, "error": str(e)})

    if sent:
        await proj_svc.update_project_data(project_id, {"candidates": updated_candidates})

    return {"sent": sent, "failed": failed}


@router.post("/projects/{project_id}/resume/sync-interviews")
async def sync_project_interviews(
    project_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Sync interview statuses back into project candidates."""
    from app.matcha.services import project_service as proj_svc

    project, _role = await _verify_project_access(project_id, current_user)

    data = project.get("project_data") or {}
    candidates = data.get("candidates") or []

    interview_ids = [c.get("interview_id") for c in candidates if c.get("interview_id")]
    if not interview_ids:
        return {"updated": 0}

    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT id, status, screening_analysis
            FROM interviews
            WHERE id = ANY($1::uuid[])
            """,
            interview_ids,
        )

    interview_map = {str(r["id"]): r for r in rows}
    updated = 0
    updated_candidates = list(candidates)

    for idx, c in enumerate(updated_candidates):
        iid = c.get("interview_id")
        if not iid or iid not in interview_map:
            continue
        row = interview_map[iid]
        new_status = c.get("status")
        interview_status = row["status"]

        # Treat analyzing as completed for UI purposes — interview is over,
        # only the AI analysis is still running. The review modal handles the
        # "no analysis yet" state gracefully.
        if interview_status in ("completed", "analyzed", "analyzing") and c.get("status") != "interview_completed":
            new_status = "interview_completed"
        elif interview_status == "in_progress" and c.get("status") == "interview_sent":
            new_status = "interview_in_progress"

        score = None
        summary = None
        analysis = row.get("screening_analysis")
        if analysis:
            if isinstance(analysis, str):
                analysis = json.loads(analysis)
            score = analysis.get("overall_score") or analysis.get("score")
            summary = analysis.get("summary") or analysis.get("overall_assessment")

        if new_status != c.get("status") or score or summary:
            updated_candidates[idx] = {
                **c,
                "status": new_status,
                "interview_status": interview_status,
                "interview_score": score,
                "interview_summary": summary,
            }
            updated += 1

    if updated > 0:
        await proj_svc.update_project_data(project_id, {"candidates": updated_candidates})

    return {"updated": updated}










# ── Thread-scoped project endpoints (legacy, kept for backward compat) ──
































# ── Agent endpoints (email) ──
















@router.get("/threads", response_model=list[ThreadListItem])
async def list_threads(
    status: Optional[str] = Query(None, pattern="^(active|finalized|archived)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List threads for the current company (includes threads where user is a collaborator)."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return []

    threads = await doc_svc.list_threads(company_id, status=status, limit=limit, offset=offset, user_id=current_user.id)
    return [ThreadListItem(**t) for t in threads]


@router.get("/elements", response_model=list[ElementListItem])
async def list_elements(
    status: Optional[str] = Query(None, pattern="^(active|finalized|archived)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List Matcha Work elements for the current company."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return []

    elements = await doc_svc.list_elements(company_id, status=status, limit=limit, offset=offset)
    return [ElementListItem(**e) for e in elements]


@router.get("/threads/{thread_id}", response_model=ThreadDetailResponse)
async def get_thread(
    thread_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get thread detail with all messages."""
    company_id = await get_client_company_id(current_user)
    # Don't 404 on missing company_id — collaborators (individuals invited to a
    # thread) may have no company of their own. Let _build_thread_detail_response
    # resolve access via the collaborator check in get_thread().
    return await _build_thread_detail_response(thread_id, company_id, user_id=current_user.id)


@router.post("/threads/{thread_id}/messages", response_model=SendMessageResponse)
async def send_message(
    thread_id: UUID,
    body: SendMessageRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Send a user message → AI response → state update → PDF."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    thread = await doc_svc.get_thread(thread_id, company_id, user_id=current_user.id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    if thread["status"] == "finalized":
        raise HTTPException(status_code=400, detail="Cannot send messages to a finalized thread")

    if thread["status"] == "archived":
        raise HTTPException(status_code=400, detail="Cannot send messages to an archived thread")

    if current_user.role != "admin":
        await token_budget_service.check_token_budget(company_id)

    # Persist attachments (images + non-image files with extracted text) on the
    # user message metadata, mirroring the streaming endpoint.
    image_atts = [{"url": u, "kind": "image"} for u in (body.image_urls or []) if isinstance(u, str) and u]
    file_atts = await _build_thread_file_attachment_meta(body.attachments)
    all_atts = image_atts + file_atts
    user_meta = {"attachments": all_atts} if all_atts else None
    is_file_only = bool(file_atts) and not (body.content or "").strip()

    # Save user message
    user_msg = await doc_svc.add_message(thread_id, "user", body.content, metadata=user_meta)

    # File-only send → ask for intent rather than auto-analyzing. File + text
    # already persisted, so the follow-up has context. No model call.
    if is_file_only:
        assistant_msg = await doc_svc.add_message(
            thread_id, "assistant", "Are you looking for analysis or something else?"
        )
        return SendMessageResponse(
            user_message=_row_to_message(user_msg),
            assistant_message=_row_to_message(assistant_msg),
            current_state=thread["current_state"],
            version=thread["version"],
            task_type=_infer_skill_from_state(thread["current_state"]),
            pdf_url=None,
            token_usage=None,
        )

    # Fetch message history + company profile + context summary in parallel
    messages, profile, (context_summary, summary_at_count) = await asyncio.gather(
        doc_svc.get_thread_messages(thread_id, limit=20),
        doc_svc.get_company_profile_for_ai(company_id),
        doc_svc.get_context_summary(thread_id),
    )
    msg_dicts = [{"role": m["role"], "content": m["content"]} for m in messages]
    # Collect extracted text from any file attachments in the window for AI context.
    _file_ctx_parts: list[str] = []
    for _m in messages:
        _meta = _m.get("metadata")
        if isinstance(_meta, str):
            try:
                _meta = json.loads(_meta)
            except Exception:
                _meta = None
        if isinstance(_meta, dict):
            for _a in (_meta.get("attachments") or []):
                if isinstance(_a, dict) and _a.get("kind") == "file" and _a.get("text"):
                    _file_ctx_parts.append(f"[{_a.get('filename') or 'file'}]\n{_a['text']}")

    # Inject selected slide content into the AI-facing message (not saved to DB)
    _inject_slide_context(msg_dicts, thread["current_state"], body.slide_index)

    # Call AI with company context
    ai_provider = get_ai_provider()
    ctx = _build_company_context(profile)
    if _file_ctx_parts:
        ctx += (
            "\n\n=== ATTACHED FILES ===\n"
            "The user attached the following file(s). Use their content only as "
            "the user's message directs — do not produce an unprompted full "
            "summary or analysis.\n\n" + "\n\n".join(_file_ctx_parts) + "\n"
        )

    # Inject project file attachments metadata
    if thread.get("project_id"):
        from app.matcha.services import project_file_service
        pfiles = await project_file_service.list_project_files(thread["project_id"])
        if pfiles:
            listing = "\n".join(f"- {f['filename']} ({f['content_type']}, {f['file_size']:,} bytes)" for f in pfiles)
            ctx += f"\n\n=== PROJECT ATTACHMENTS ===\nThe user has attached these files to the project. Reference them when relevant:\n{listing}\n"

    # Inject recruiting project context so AI generates posting sections in the right project
    ctx = await _inject_recruiting_project_context(ctx, thread, thread["current_state"])

    # No-project guard: prevent the AI from hallucinating a "project panel" for
    # plain chat threads. Without this, once current_state accumulates
    # project_title/project_sections from a prior reply, _infer_skill_from_state
    # locks skill="project" and the AI keeps claiming it updated a document the
    # user has no UI to see.
    if not thread.get("project_id"):
        ctx += (
            "\n\n=== PLAIN THREAD (NO PROJECT) ==="
            "\nThis is a plain chat thread. Per the Surface architecture section at the top of the system prompt: threads cannot contain projects, and no project is attached to this thread."
            "\n- Set mode=\"general\", skill=\"none\", operation=\"none\". Never emit project_title, project_sections, blog_outline, blog_section_draft, or blog_section_revision."
            "\n- There is no project panel / canvas / draft surface in this chat — don't reference one."
            "\n- Documents, memos, deal memos, briefs, reports, letters: WRITE THE COMPLETE DOCUMENT as well-structured Markdown directly in your reply (use # / ## headings, bullet lists, and tables as appropriate). This is fully supported."
            "\n- The user can export any of your replies to a downloadable PDF using the export button on the message. NEVER say you cannot create, generate, or export a PDF or a document. NEVER output raw SVG or HTML wireframes / mockups of a document — write the actual content as Markdown."
            "\n- Short-form content (LinkedIn posts, social captions, emails, summaries, cover letters): write it directly in your reply."
            "\n- Suggest creating a Project (+ next to Projects in the sidebar) ONLY when the user wants to iteratively edit a multi-section document over time — never as a reason to decline writing the content now."
        )

    # Grounded web search pre-pass for time-sensitive questions
    # (markets today, news, weather, scores, etc.) — fetches current facts via
    # Gemini Google Search grounding and injects them into the context.
    if needs_live_web_context(body.content):
        from app.config import get_settings as _get_settings
        live_ctx = await fetch_live_web_context(body.content, _get_settings())
        if live_ctx:
            ctx += live_ctx

    compliance_result: ComplianceContextResult | None = None
    if thread.get("node_mode"):
        node_ctx = await build_node_context(company_id)
        ctx += "\n\n" + node_ctx
    if thread.get("compliance_mode"):
        compliance_result = await build_compliance_context(company_id)
        ctx += "\n\n" + compliance_result.context_text

        # RAG augmentation — find requirements most relevant to the user's question
        rag_ctx = await _get_rag_context(body.content, company_id)
        if rag_ctx:
            ctx += "\n\n=== RELEVANT REGULATIONS (semantic search) ===\n" + rag_ctx

    # Payer mode — build dedicated medical policy prompt (separate from HR copilot)
    payer_prompt = None
    payer_sources: list[dict] = []
    if thread.get("payer_mode"):
        try:
            import os as _os
            from app.core.services.embedding_service import EmbeddingService
            from app.core.services.payer_policy_rag import PayerPolicyRAGService
            from app.config import get_settings as _get_settings
            from app.matcha.services.matcha_work_ai import PAYER_MODE_SYSTEM_PROMPT
            from datetime import date as _date

            user_msg = body.content or ""
            _api_key = _os.getenv("GEMINI_API_KEY") or _get_settings().gemini_api_key
            if _api_key and user_msg:
                _emb = EmbeddingService(api_key=_api_key)
                _rag = PayerPolicyRAGService(_emb)
                async with get_connection() as _pconn:
                    payer_ctx, payer_sources = await _rag.get_context_for_query(
                        query=user_msg, conn=_pconn,
                        company_id=company_id, max_tokens=6000,
                    )
                company_name = profile.get("name", "your company")
                payer_prompt = PAYER_MODE_SYSTEM_PROMPT.format(
                    company_name=company_name,
                    today=_date.today().isoformat(),
                    payer_context=payer_ctx or "No matching payer policy data found. Answer based on general knowledge but clearly state this is not from verified policy data.",
                )
        except Exception as _e:
            logger.warning("Failed to build payer policy prompt: %s", _e)

    # If no project is attached, scrub any leftover project_* state so
    # _infer_skill_from_state doesn't keep locking the AI into "project" skill.
    ai_facing_state = thread["current_state"]
    if not thread.get("project_id") and isinstance(ai_facing_state, dict):
        if "project_title" in ai_facing_state or "project_sections" in ai_facing_state:
            ai_facing_state = {
                k: v for k, v in ai_facing_state.items()
                if k not in ("project_title", "project_sections", "project_status")
            }

    project_meta = await _fetch_project_meta(thread.get("project_id"))
    blog_mode_state = _blog_mode_state_from_meta(project_meta)

    ai_resp = await ai_provider.generate(
        msg_dicts, ai_facing_state, company_context=ctx,
        slide_index=body.slide_index, context_summary=context_summary,
        payer_mode_prompt=payer_prompt,
        model_override=body.model,
        company_id=str(company_id) if company_id else "",
        user_id=str(current_user.id),
        compliance_mode=bool(thread.get("compliance_mode")),
        payer_mode=bool(thread.get("payer_mode")),
        node_mode=bool(thread.get("node_mode")),
        blog_mode_state=blog_mode_state,
        thread_id=str(thread_id),
    )
    _scope_slide_update(ai_resp, thread["current_state"], body.slide_index)
    final_usage = ai_resp.token_usage

    current_version = thread["version"]
    (
        current_state,
        current_version,
        pdf_url,
        changed,
        assistant_reply_text,
    ) = await _apply_ai_updates_and_operations(
        thread_id=thread_id,
        company_id=company_id,
        ai_resp=ai_resp,
        current_state=thread["current_state"],
        current_version=current_version,
        user_message=body.content,
        current_user_id=current_user.id,
        project_id=thread.get("project_id"),
        project_meta=project_meta,
    )

    # Build metadata from compliance reasoning chains + payer sources
    msg_metadata = _build_compliance_metadata(compliance_result, ai_resp)
    if ai_resp and getattr(ai_resp, "attachments", None):
        if msg_metadata is None:
            msg_metadata = {}
        msg_metadata["attachments"] = ai_resp.attachments
    if payer_sources:
        if msg_metadata is None:
            msg_metadata = {}
        msg_metadata["payer_sources"] = payer_sources

    # Cross-reference affected employees + detect policy gaps when both node + compliance are on
    if thread.get("node_mode") and thread.get("compliance_mode") and msg_metadata:
        if msg_metadata.get("referenced_locations"):
            affected = await _get_affected_employees(company_id, msg_metadata)
            if affected:
                msg_metadata["affected_employees"] = affected
        gaps = await _detect_compliance_gaps(company_id, msg_metadata)
        if gaps:
            msg_metadata["compliance_gaps"] = gaps

    # Annotate reply with change summary for conversation continuity
    if changed and ai_resp.structured_update and isinstance(ai_resp.structured_update, dict):
        update_slides = ai_resp.structured_update.get("slides")
        if update_slides and body.slide_index is not None and 0 <= body.slide_index < len(update_slides):
            changed_slide = update_slides[body.slide_index]
            if isinstance(changed_slide, dict):
                n_bullets = len(changed_slide.get("bullets", []))
                change_note = f"\n\n[Applied changes to Slide {body.slide_index + 1}: title=\"{changed_slide.get('title', '')}\", {n_bullets} bullets]"
                assistant_reply_text += change_note

    # Save assistant message
    assistant_msg = await doc_svc.add_message(
        thread_id,
        "assistant",
        assistant_reply_text,
        version_created=current_version if changed else None,
        metadata=msg_metadata,
    )

    # Escalate low-confidence queries for human review
    if should_escalate(ai_resp):
        try:
            await create_escalation(
                company_id=company_id,
                thread_id=thread_id,
                user_message_id=user_msg["id"],
                assistant_message_id=assistant_msg["id"],
                user_query=body.content,
                ai_resp=ai_resp,
            )
        except Exception:
            logger.exception("Failed to create escalation for thread %s", thread_id)

    cost = calculate_call_cost(
        model=str((final_usage or {}).get("model") or "unknown"),
        prompt_tokens=(final_usage or {}).get("prompt_tokens"),
        completion_tokens=(final_usage or {}).get("completion_tokens"),
    )
    if final_usage is not None:
        final_usage["cost_dollars"] = float(cost)

    try:
        await doc_svc.log_token_usage_event(
            company_id=company_id,
            user_id=current_user.id,
            thread_id=thread_id,
            token_usage=final_usage,
            operation="send_message",
            cost_dollars=float(cost),
        )
    except Exception as e:
        logger.warning("Failed to log Matcha Work token usage for thread %s: %s", thread_id, e)

    if current_user.role != "admin":
        total_tokens = (final_usage or {}).get("total_tokens") or 0
        if total_tokens > 0:
            try:
                async with get_connection() as conn:
                    async with conn.transaction():
                        await token_budget_service.deduct_tokens(conn, company_id, total_tokens)
            except HTTPException:
                logger.warning("Token budget exhausted during deduction for thread %s", thread_id)
            except Exception as exc:
                logger.warning("Failed to deduct tokens for thread %s: %s", thread_id, exc)

    # Trigger conversation compaction in the background if needed
    asyncio.create_task(_maybe_compact(thread_id, ai_provider, summary_at_count))

    return SendMessageResponse(
        user_message=_row_to_message(user_msg),
        assistant_message=_row_to_message(assistant_msg),
        current_state=current_state,
        version=current_version,
        task_type=_infer_skill_from_state(current_state),
        pdf_url=pdf_url,
        token_usage=final_usage,
    )


_compacting_threads: set[UUID] = set()  # simple guard against concurrent compaction
_COMPACTION_REFRESH_INTERVAL = 20  # re-compact after this many new messages


async def _maybe_compact(thread_id: UUID, ai_provider, summary_at_count: int | None) -> None:
    """Check message count and run compaction if threshold is exceeded or summary is stale."""
    if thread_id in _compacting_threads:
        return
    try:
        _compacting_threads.add(thread_id)
        msg_count = await doc_svc.get_thread_message_count(thread_id)
        if msg_count < 30:
            return
        # Skip if summary is recent enough
        if summary_at_count is not None and (msg_count - summary_at_count) < _COMPACTION_REFRESH_INTERVAL:
            return
        # Window of 15 + older cap of 200 = 215 max messages needed
        all_messages = await doc_svc.get_thread_messages(thread_id, limit=215)
        msg_dicts = [{"role": m["role"], "content": m["content"]} for m in all_messages]
        prior_summary, _ = await doc_svc.get_context_summary(thread_id)
        summary = await compact_conversation(msg_dicts, ai_provider.client, prior_summary=prior_summary)
        if summary:
            await doc_svc.save_context_summary(thread_id, summary, msg_count)
            logger.info("Compacted conversation for thread %s (%d messages)", thread_id, msg_count)
    except Exception:
        logger.warning("Background compaction failed for thread %s", thread_id, exc_info=True)
    finally:
        _compacting_threads.discard(thread_id)


@router.post("/threads/{thread_id}/messages/stream")
async def send_message_stream(
    thread_id: UUID,
    body: SendMessageRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Send message with SSE progress + token usage events."""
    caller_company_id = await get_client_company_id(current_user)
    # Don't 404 on None — collaborators (individuals invited to another user's
    # thread) may have no company of their own.
    thread = await doc_svc.get_thread(thread_id, caller_company_id, user_id=current_user.id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    # Use the thread's actual company for all downstream operations (AI profile,
    # token budget, etc.) so collaborators don't accidentally scope ops to their
    # own (possibly absent) company.
    company_id = thread["company_id"]

    if thread["status"] == "finalized":
        raise HTTPException(status_code=400, detail="Cannot send messages to a finalized thread")

    if thread["status"] == "archived":
        raise HTTPException(status_code=400, detail="Cannot send messages to an archived thread")

    if current_user.role != "admin":
        await token_budget_service.check_token_budget(company_id)

    # Check token quota. Structured detail so the Werk client can tell a
    # free-taste exhaustion apart from a generic error and raise the paywall.
    quota = await doc_svc.check_token_quota(current_user.id, company_id)
    if not quota["allowed"]:
        from app.matcha.services import entitlements_service

        plan = await entitlements_service.resolve_plan_for_user(current_user.id)
        raise HTTPException(
            status_code=429,
            detail={
                "code": "quota_exhausted",
                "plan": plan,
                "used": quota["used"],
                "limit": quota["limit"],
                "resets_at": quota["resets_at"],
                "message": f"Token limit reached ({quota['used']:,}/{quota['limit']:,} tokens used). Resets at {quota['resets_at']}.",
            },
        )

    # Normalize & persist attachment URLs on the user message metadata. Client
    # uploads images separately (stored in currentState["images"]) and sends the
    # URLs here so they become part of the message itself — visible in the
    # bubble and passed to the AI as multimodal parts.
    attach_urls: list[str] = []
    if body.image_urls:
        attach_urls = [u for u in body.image_urls if isinstance(u, str) and u]
    image_atts = [{"url": u, "kind": "image"} for u in attach_urls]
    # Non-image files: extract capped text now so it persists on the message
    # and feeds the AI on this turn AND on follow-ups (read back from metadata).
    file_atts = await _build_thread_file_attachment_meta(body.attachments)
    all_atts = image_atts + file_atts
    user_meta = {"attachments": all_atts} if all_atts else None

    # File-only send (attachments, no instruction) → don't analyze; ask what
    # they want. The file + its extracted text are persisted, so the follow-up
    # ("summarize it") has full context.
    is_file_only = bool(file_atts) and not (body.content or "").strip()

    # Save user message before streaming
    user_msg = await doc_svc.add_message(thread_id, "user", body.content, metadata=user_meta)

    # Once the attachments are persisted on the message itself, clear them from
    # thread state so they don't leak into the next send or get re-consumed by
    # the presentation skill.
    if attach_urls:
        try:
            await doc_svc.apply_update(thread_id, {"images": []}, diff_summary="Consumed inline chat attachments")
        except Exception:
            logger.warning("Failed to clear thread images after attaching to message %s", thread_id, exc_info=True)
        # apply_update persists to the DB but the in-memory `thread` dict we
        # fetched earlier still holds the old image URLs. Mirror the clear
        # locally so the complete event returns current_state.images == []
        # and the client doesn't re-render the attachments in the text box.
        if isinstance(thread.get("current_state"), dict):
            thread["current_state"]["images"] = []

    # Fetch message history + company profile + context summary in parallel
    messages, profile, (context_summary, summary_at_count) = await asyncio.gather(
        doc_svc.get_thread_messages(thread_id, limit=20),
        doc_svc.get_company_profile_for_ai(company_id),
        doc_svc.get_context_summary(thread_id),
    )
    msg_dicts = []
    file_context_parts: list[str] = []
    for m in messages:
        entry = {"role": m["role"], "content": m["content"]}
        meta = m.get("metadata")
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = None
        if isinstance(meta, dict):
            atts = meta.get("attachments") or []
            # Only image attachments go into the multimodal image path. File
            # attachments must NOT be sent as image parts.
            urls = [
                a.get("url") for a in atts
                if isinstance(a, dict) and a.get("url") and a.get("kind") != "file"
            ]
            if urls:
                entry["image_urls"] = urls
            for a in atts:
                if isinstance(a, dict) and a.get("kind") == "file" and a.get("text"):
                    file_context_parts.append(
                        f"[{a.get('filename') or 'file'}]\n{a['text']}"
                    )
        msg_dicts.append(entry)

    # Inject selected slide content into the AI-facing message (not saved to DB)
    _inject_slide_context(msg_dicts, thread["current_state"], body.slide_index)

    # Pre-fetch any image attachment bytes concurrently off the event loop so
    # the prompt builder (which runs in a thread pool) doesn't block on I/O.
    from app.matcha.services.matcha_work_ai import fetch_image_parts_for_messages
    await fetch_image_parts_for_messages(msg_dicts)

    ai_provider = get_ai_provider()
    ctx = _build_company_context(profile)

    # Inject project file attachments metadata
    if thread.get("project_id"):
        from app.matcha.services import project_file_service
        pfiles = await project_file_service.list_project_files(thread["project_id"])
        if pfiles:
            listing = "\n".join(f"- {f['filename']} ({f['content_type']}, {f['file_size']:,} bytes)" for f in pfiles)
            ctx += f"\n\n=== PROJECT ATTACHMENTS ===\nThe user has attached these files to the project. Reference them when relevant:\n{listing}\n"

    # Inject the text of files the user attached to chat messages. These are
    # reference material — the system-prompt note tells the model not to
    # volunteer a full analysis unless the user's message asks for it.
    if file_context_parts:
        joined = "\n\n".join(file_context_parts)
        ctx += (
            "\n\n=== ATTACHED FILES ===\n"
            "The user attached the following file(s). Use their content only as "
            "the user's message directs — do not produce an unprompted full "
            "summary or analysis.\n\n" + joined + "\n"
        )

    # Inject recruiting project context so AI generates posting sections in the right project
    ctx = await _inject_recruiting_project_context(ctx, thread, thread["current_state"])

    # Node/compliance context is built inside event_stream() so we can yield status events

    async def event_stream():
        nonlocal ctx
        compliance_result: ComplianceContextResult | None = None
        try:
            # File-only send → ask for intent instead of auto-analyzing. The
            # file is already persisted with extracted text, so the user's next
            # message has full context. No model call (deterministic + free).
            if is_file_only:
                canned = "Are you looking for analysis or something else?"
                assistant_msg = await doc_svc.add_message(thread_id, "assistant", canned)
                try:
                    from app.matcha.routes.thread_ws import thread_manager
                    asyncio.create_task(
                        thread_manager.broadcast_new_message(
                            str(thread_id),
                            [_row_to_message(user_msg).model_dump(mode="json"),
                             _row_to_message(assistant_msg).model_dump(mode="json")],
                            exclude_user=current_user.id,
                        )
                    )
                except Exception:
                    logger.warning("Thread WS broadcast failed (file-only) for thread %s", thread_id)
                guard_response = SendMessageResponse(
                    user_message=_row_to_message(user_msg),
                    assistant_message=_row_to_message(assistant_msg),
                    current_state=thread["current_state"],
                    version=thread["version"],
                    task_type=_infer_skill_from_state(thread["current_state"]),
                    pdf_url=None,
                    token_usage=None,
                )
                yield _sse_data({"type": "complete", "data": guard_response.model_dump(mode="json")})
                return
            # Build mode-specific context with status updates
            if thread.get("node_mode"):
                yield _sse_data({"type": "status", "message": "Loading internal company data..."})
                node_ctx = await build_node_context(company_id)
                ctx += "\n\n" + node_ctx

            if thread.get("compliance_mode"):
                yield _sse_data({"type": "status", "message": "Loading compliance data for your locations..."})
                compliance_result = await build_compliance_context(company_id)
                compliance_ctx = compliance_result.context_text
                cat_count = compliance_ctx.count("Decision path:")
                trigger_count = compliance_ctx.count("[trigger:")
                loc_count = compliance_ctx.count("FACILITY PROFILE")
                if cat_count > 0:
                    parts = [f"{cat_count} regulatory categories across {loc_count} location{'s' if loc_count != 1 else ''}"]
                    if trigger_count > 0:
                        parts.append(f"{trigger_count} triggered requirement{'s' if trigger_count != 1 else ''}")
                    yield _sse_data({"type": "status", "message": f"Found {' with '.join(parts)} — building reasoning chains..."})
                elif compliance_ctx.count("legacy format") > 0:
                    yield _sse_data({"type": "status", "message": "Loaded compliance data (legacy format) — cross-referencing..."})
                else:
                    yield _sse_data({"type": "status", "message": "No compliance data found — will suggest running a check..."})
                ctx += "\n\n" + compliance_ctx

                # RAG augmentation — find requirements most relevant to the question
                yield _sse_data({"type": "status", "message": "Searching relevant regulations..."})
                rag_ctx = await _get_rag_context(body.content, company_id)
                if rag_ctx:
                    ctx += "\n\n=== RELEVANT REGULATIONS (semantic search) ===\n" + rag_ctx

            # Payer mode — build payer prompt inside stream for status events
            stream_payer_prompt = None
            stream_payer_sources: list[dict] = []
            if thread.get("payer_mode"):
                yield _sse_data({"type": "status", "message": "Searching payer coverage data..."})
                try:
                    import os as _os2
                    from app.core.services.embedding_service import EmbeddingService as _ES2
                    from app.core.services.payer_policy_rag import PayerPolicyRAGService as _PRAG2
                    from app.config import get_settings as _gs2
                    from app.matcha.services.matcha_work_ai import PAYER_MODE_SYSTEM_PROMPT as _PMSP
                    from datetime import date as _d2

                    _ak2 = _os2.getenv("GEMINI_API_KEY") or _gs2().gemini_api_key
                    if _ak2 and body.content:
                        _e2 = _ES2(api_key=_ak2)
                        _r2 = _PRAG2(_e2)
                        async with get_connection() as _pc2:
                            _pctx, stream_payer_sources = await _r2.get_context_for_query(
                                query=body.content, conn=_pc2,
                                company_id=company_id, max_tokens=6000,
                            )
                        cn2 = profile.get("name", "your company")
                        stream_payer_prompt = _PMSP.format(
                            company_name=cn2,
                            today=_d2.today().isoformat(),
                            payer_context=_pctx or "No matching payer policy data found.",
                        )
                        if stream_payer_sources:
                            yield _sse_data({"type": "status", "message": f"Found {len(stream_payer_sources)} relevant payer policies"})
                except Exception as _pe:
                    logger.warning("Stream payer context failed: %s", _pe)

            estimated_usage = await ai_provider.estimate_usage(msg_dicts, thread["current_state"], company_context=ctx, slide_index=body.slide_index)
            yield _sse_data(
                {
                    "type": "usage",
                    "data": {
                        **estimated_usage,
                        "stage": "estimate",
                    },
                }
            )

            yield _sse_data({"type": "status", "message": "Generating response..."})
            import time as _time
            _t0 = _time.monotonic()
            # Run generation as a background task and emit keepalives every 15 s
            # so proxies with short read-timeouts (e.g. nginx default 60 s) don't
            # close the SSE connection while we wait for the AI to finish.
            stream_project_meta = await _fetch_project_meta(thread.get("project_id"))
            stream_blog_mode_state = _blog_mode_state_from_meta(stream_project_meta)
            _ai_task = asyncio.create_task(ai_provider.generate(
                msg_dicts, thread["current_state"], company_context=ctx,
                slide_index=body.slide_index, context_summary=context_summary,
                payer_mode_prompt=stream_payer_prompt,
                model_override=body.model,
                company_id=str(company_id),
                user_id=str(current_user.id),
                compliance_mode=bool(thread.get("compliance_mode")),
                payer_mode=bool(thread.get("payer_mode")),
                node_mode=bool(thread.get("node_mode")),
                blog_mode_state=stream_blog_mode_state,
                thread_id=str(thread_id),
            ))
            while True:
                done, _ = await asyncio.wait({_ai_task}, timeout=15.0)
                if done:
                    break
                yield _sse_data({"type": "keepalive"})
            ai_resp = await _ai_task
            logger.info("[TIMING] AI generate took %.2fs for thread %s", _time.monotonic() - _t0, thread_id)
            _scope_slide_update(ai_resp, thread["current_state"], body.slide_index)

            current_version = thread["version"]
            (
                current_state,
                current_version,
                pdf_url,
                changed,
                assistant_reply_text,
            ) = await _apply_ai_updates_and_operations(
                thread_id=thread_id,
                company_id=company_id,
                ai_resp=ai_resp,
                current_state=thread["current_state"],
                current_version=current_version,
                user_message=body.content,
                current_user_id=current_user.id,
                project_id=thread.get("project_id"),
                project_meta=stream_project_meta,
            )

            # Build metadata from compliance reasoning chains + payer sources
            msg_metadata = _build_compliance_metadata(compliance_result, ai_resp)
            if ai_resp and getattr(ai_resp, "attachments", None):
                if msg_metadata is None:
                    msg_metadata = {}
                msg_metadata["attachments"] = ai_resp.attachments
            if stream_payer_sources:
                if msg_metadata is None:
                    msg_metadata = {}
                msg_metadata["payer_sources"] = stream_payer_sources

            # Cross-reference affected employees + detect policy gaps when both node + compliance are on
            if thread.get("node_mode") and thread.get("compliance_mode") and msg_metadata:
                if msg_metadata.get("referenced_locations"):
                    affected = await _get_affected_employees(company_id, msg_metadata)
                    if affected:
                        msg_metadata["affected_employees"] = affected
                gaps = await _detect_compliance_gaps(company_id, msg_metadata)
                if gaps:
                    msg_metadata["compliance_gaps"] = gaps

            # Annotate reply with change summary for conversation continuity
            if changed and ai_resp.structured_update and isinstance(ai_resp.structured_update, dict):
                update_slides = ai_resp.structured_update.get("slides")
                if update_slides and body.slide_index is not None and 0 <= body.slide_index < len(update_slides):
                    changed_slide = update_slides[body.slide_index]
                    if isinstance(changed_slide, dict):
                        n_bullets = len(changed_slide.get("bullets", []))
                        change_note = f"\n\n[Applied changes to Slide {body.slide_index + 1}: title=\"{changed_slide.get('title', '')}\", {n_bullets} bullets]"
                        assistant_reply_text += change_note

            # Save assistant message
            assistant_msg = await doc_svc.add_message(
                thread_id,
                "assistant",
                assistant_reply_text,
                version_created=current_version if changed else None,
                metadata=msg_metadata,
            )

            # Broadcast new messages to collaborators via WS — fire-and-forget so
            # a CancelledError inside the lock doesn't kill the SSE generator before
            # the complete event is sent.
            try:
                from app.matcha.routes.thread_ws import thread_manager
                user_msg_dict = _row_to_message(user_msg).model_dump(mode="json")
                assistant_msg_dict = _row_to_message(assistant_msg).model_dump(mode="json")
                asyncio.create_task(
                    thread_manager.broadcast_new_message(
                        str(thread_id), [user_msg_dict, assistant_msg_dict], exclude_user=current_user.id
                    )
                )
            except Exception:
                logger.warning("Thread WS broadcast failed for thread %s", thread_id)

            # Escalate low-confidence queries for human review
            if should_escalate(ai_resp):
                try:
                    await create_escalation(
                        company_id=company_id,
                        thread_id=thread_id,
                        user_message_id=user_msg["id"],
                        assistant_message_id=assistant_msg["id"],
                        user_query=body.content,
                        ai_resp=ai_resp,
                    )
                except Exception:
                    logger.exception("Failed to create escalation for thread %s", thread_id)

            final_usage = ai_resp.token_usage or estimated_usage
            stream_cost = calculate_call_cost(
                model=str((final_usage or {}).get("model") or "unknown"),
                prompt_tokens=(final_usage or {}).get("prompt_tokens"),
                completion_tokens=(final_usage or {}).get("completion_tokens"),
            )
            if final_usage is not None:
                final_usage["cost_dollars"] = float(stream_cost)

            try:
                await doc_svc.log_token_usage_event(
                    company_id=company_id,
                    user_id=current_user.id,
                    thread_id=thread_id,
                    token_usage=final_usage,
                    operation="send_message",
                    cost_dollars=float(stream_cost),
                )
            except Exception as e:
                logger.warning("Failed to log Matcha Work token usage for thread %s: %s", thread_id, e)

            if current_user.role != "admin":
                total_tokens = (final_usage or {}).get("total_tokens") or 0
                if total_tokens > 0:
                    try:
                        async with get_connection() as conn:
                            async with conn.transaction():
                                await token_budget_service.deduct_tokens(conn, company_id, total_tokens)
                    except HTTPException:
                        logger.warning("Token budget exhausted during stream deduction for thread %s", thread_id)
                    except Exception as exc:
                        logger.warning("Failed to deduct tokens for thread %s: %s", thread_id, exc)

            if final_usage:
                yield _sse_data(
                    {
                        "type": "usage",
                        "data": {
                            **final_usage,
                            "stage": "final",
                        },
                    }
                )

            response = SendMessageResponse(
                user_message=_row_to_message(user_msg),
                assistant_message=_row_to_message(assistant_msg),
                current_state=current_state,
                version=current_version,
                task_type=_infer_skill_from_state(current_state),
                pdf_url=pdf_url,
                token_usage=final_usage,
            )

            yield _sse_data({"type": "complete", "data": response.model_dump(mode="json")})

            # Trigger compaction in the background if needed
            asyncio.create_task(_maybe_compact(thread_id, ai_provider, summary_at_count))
        except BaseException as e:
            logger.error("Matcha Work stream failed for thread %s: %s (%s)", thread_id, e, type(e).__name__, exc_info=True)
            try:
                yield _sse_data(
                    {
                        "type": "error",
                        "message": "Failed to process message. Please try again.",
                    }
                )
            except Exception:
                pass
            if not isinstance(e, Exception):
                raise
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")






@router.get("/threads/{thread_id}/versions", response_model=list[DocumentVersionResponse])
async def list_versions(
    thread_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List all document versions for a thread."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    thread = await doc_svc.get_thread(thread_id, company_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    versions = await doc_svc.list_versions(thread_id)
    return [DocumentVersionResponse(**v) for v in versions]


@router.post("/threads/{thread_id}/revert", response_model=SendMessageResponse)
async def revert_thread(
    thread_id: UUID,
    body: RevertRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Revert to a historical version (creates a new version with old state)."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    thread = await doc_svc.get_thread(thread_id, company_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    if thread["status"] == "finalized":
        raise HTTPException(status_code=400, detail="Cannot revert a finalized thread")
    if thread["status"] == "archived":
        raise HTTPException(status_code=400, detail="Cannot revert an archived thread")

    try:
        result = await doc_svc.revert_to_version(thread_id, body.version)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    new_version = result["version"]
    new_state = result["current_state"]

    system_msg = await doc_svc.add_message(
        thread_id,
        "system",
        f"Document reverted to version {body.version}.",
        version_created=new_version,
    )

    assistant_msg = await doc_svc.add_message(
        thread_id,
        "assistant",
        f"I've reverted the document to version {body.version}. You can continue editing from there.",
        version_created=new_version,
    )

    pdf_url = None
    if _infer_skill_from_state(new_state) == "offer_letter":
        pdf_url = await doc_svc.generate_pdf(
            new_state,
            thread_id,
            new_version,
            is_draft=True,
            company_id=company_id,
        )

    return SendMessageResponse(
        user_message=_row_to_message(system_msg),
        assistant_message=_row_to_message(assistant_msg),
        current_state=new_state,
        version=new_version,
        pdf_url=pdf_url,
    )


@router.post("/threads/{thread_id}/finalize", response_model=FinalizeResponse)
async def finalize_thread(
    thread_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Finalize the thread — lock status, generate final PDF without watermark."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    try:
        result = await doc_svc.finalize_thread(thread_id, company_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return FinalizeResponse(**result)


@router.post("/threads/{thread_id}/save-draft", response_model=SaveDraftResponse)
async def save_draft(
    thread_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Save the current Matcha Work state into offer_letters as a draft."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    thread = await doc_svc.get_thread(thread_id, company_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    if _infer_skill_from_state(thread.get("current_state") or {}) != "offer_letter":
        raise HTTPException(status_code=400, detail="Save draft is only available for offer letters")

    try:
        result = await doc_svc.save_offer_letter_draft(thread_id, company_id)
    except ValueError as e:
        detail = str(e)
        if detail == "Thread not found":
            raise HTTPException(status_code=404, detail=detail)
        raise HTTPException(status_code=400, detail=detail)

    return SaveDraftResponse(**result)


@router.get("/threads/{thread_id}/pdf")
async def get_pdf(
    thread_id: UUID,
    version: Optional[int] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get or generate the PDF for a thread (optionally a specific version)."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    thread = await doc_svc.get_thread(thread_id, company_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    if _infer_skill_from_state(thread.get("current_state") or {}) != "offer_letter":
        raise HTTPException(status_code=400, detail="PDF preview is only available for offer letters")

    target_version = version if version is not None else thread["version"]
    state = thread["current_state"]

    # If requesting a historical version, load that state
    if version is not None and version != thread["version"]:
        versions = await doc_svc.list_versions(thread_id)
        ver_map = {v["version"]: v for v in versions}
        if target_version not in ver_map:
            raise HTTPException(status_code=404, detail=f"Version {target_version} not found")
        state = ver_map[target_version]["state_json"]

    is_draft = thread["status"] != "finalized"
    pdf_url = await doc_svc.generate_pdf(
        state,
        thread_id,
        target_version,
        is_draft=is_draft,
        company_id=company_id,
    )

    if pdf_url is None:
        raise HTTPException(status_code=503, detail="PDF generation unavailable")

    return {"pdf_url": pdf_url, "version": target_version}


@router.get("/threads/{thread_id}/pdf/proxy")
async def proxy_pdf(
    thread_id: UUID,
    version: Optional[int] = Query(None),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Stream PDF bytes for same-origin iframe embedding (avoids cross-origin iframe blocking)."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    thread = await doc_svc.get_thread(thread_id, company_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    if _infer_skill_from_state(thread.get("current_state") or {}) != "offer_letter":
        raise HTTPException(status_code=400, detail="PDF preview is only available for offer letters")

    target_version = version if version is not None else thread["version"]
    state = thread["current_state"]

    if version is not None and version != thread["version"]:
        versions = await doc_svc.list_versions(thread_id)
        ver_map = {v["version"]: v for v in versions}
        if target_version not in ver_map:
            raise HTTPException(status_code=404, detail=f"Version {target_version} not found")
        state = ver_map[target_version]["state_json"]

    is_draft = thread["status"] != "finalized"
    pdf_url = await doc_svc.generate_pdf(
        state,
        thread_id,
        target_version,
        is_draft=is_draft,
        company_id=company_id,
    )

    if pdf_url is None:
        raise HTTPException(status_code=503, detail="PDF generation unavailable")

    try:
        pdf_bytes = await get_storage().download_file(pdf_url)
    except Exception as e:
        logger.error("Failed to fetch PDF for proxy: %s", e)
        raise HTTPException(status_code=503, detail="Failed to load PDF")

    safe_title = re.sub(r"[^\w\s-]", "", thread.get("title") or "offer-letter").strip().replace(" ", "-") or "offer-letter"
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{safe_title}.pdf"'},
    )


@router.delete("/threads/{thread_id}", status_code=204)
async def archive_thread(
    thread_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Archive (soft-delete) a thread."""
    from app.database import get_connection

    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    async with get_connection() as conn:
        result = await conn.execute(
            """
            UPDATE mw_threads
            SET status='archived', updated_at=NOW()
            WHERE id=$1 AND company_id=$2 AND status != 'archived'
            """,
            thread_id,
            company_id,
        )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Thread not found")
    await doc_svc.sync_element_record(thread_id)


@router.post("/threads/{thread_id}/unarchive", status_code=200)
async def unarchive_thread(
    thread_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Restore an archived thread to active status."""
    from app.database import get_connection

    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    async with get_connection() as conn:
        result = await conn.execute(
            """
            UPDATE mw_threads
            SET status='active', updated_at=NOW()
            WHERE id=$1 AND company_id=$2 AND status='archived'
            """,
            thread_id,
            company_id,
        )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Thread not found")
    await doc_svc.sync_element_record(thread_id)
    return {"status": "active"}


@router.get(
    "/threads/{thread_id}/review-requests",
    response_model=list[ReviewRequestStatus],
)
async def list_review_requests(
    thread_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List review request status rows for a review thread."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    try:
        rows = await doc_svc.list_review_requests(thread_id, company_id)
    except ValueError as e:
        detail = str(e)
        if detail == "Thread not found":
            raise HTTPException(status_code=404, detail=detail)
        raise HTTPException(status_code=400, detail=detail)

    return [ReviewRequestStatus(**row) for row in rows]


@router.post(
    "/threads/{thread_id}/review-requests/send",
    response_model=SendReviewRequestsResponse,
)
async def send_review_requests(
    thread_id: UUID,
    body: SendReviewRequestsRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """
    Send anonymous review request links to recipient emails and track expected responses.
    """
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    try:
        result = await doc_svc.send_review_requests(
            thread_id=thread_id,
            company_id=company_id,
            recipient_emails=body.recipient_emails,
            custom_message=body.custom_message,
        )
    except ValueError as e:
        detail = str(e)
        if detail == "Thread not found":
            raise HTTPException(status_code=404, detail=detail)
        raise HTTPException(status_code=400, detail=detail)

    return SendReviewRequestsResponse(**result)


@router.post(
    "/threads/{thread_id}/handbook/send-signatures",
    response_model=SendHandbookSignaturesResponse,
)
async def send_handbook_signatures(
    thread_id: UUID,
    body: SendHandbookSignaturesRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Send handbook acknowledgement signatures from a workbook thread."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    thread = await doc_svc.get_thread(thread_id, company_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    if thread["status"] == "archived":
        raise HTTPException(status_code=400, detail="Cannot send handbook signatures for an archived thread")
    if _infer_skill_from_state(thread.get("current_state") or {}) != "workbook":
        raise HTTPException(status_code=400, detail="Handbook signatures are only available for workbook threads")

    employee_ids = [str(employee_id) for employee_id in body.employee_ids] if body.employee_ids else None

    try:
        distributed = await HandbookService.distribute_to_employees(
            handbook_id=str(body.handbook_id),
            company_id=str(company_id),
            distributed_by=str(current_user.id),
            employee_ids=employee_ids,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if distributed is None:
        raise HTTPException(status_code=404, detail="Handbook not found")

    payload = distributed.model_dump() if hasattr(distributed, "model_dump") else dict(distributed)
    return SendHandbookSignaturesResponse(**payload)


@router.post(
    "/threads/{thread_id}/presentation/generate",
    response_model=GeneratePresentationResponse,
)
async def generate_workbook_presentation(
    thread_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Generate slide-ready presentation content from workbook sections."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    try:
        result = await doc_svc.generate_workbook_presentation(
            thread_id=thread_id,
            company_id=company_id,
        )
    except ValueError as e:
        detail = str(e)
        if detail == "Thread not found":
            raise HTTPException(status_code=404, detail=detail)
        raise HTTPException(status_code=400, detail=detail)

    return GeneratePresentationResponse(**result)


@router.get("/threads/{thread_id}/presentation/pdf")
async def get_presentation_pdf(
    thread_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Return the presentation PDF URL, generating it on demand."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    thread = await doc_svc.get_thread(thread_id, company_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    state = await doc_svc.ensure_matcha_work_thread_storage_scope(
        thread_id,
        company_id,
        thread.get("current_state") or {},
    )
    if _infer_skill_from_state(state) not in ("presentation", "workbook"):
        raise HTTPException(status_code=400, detail="Presentation PDF is only available for presentation and workbook threads")

    version = int(thread.get("version") or 0)
    # For workbook threads, use the nested presentation; for standalone presentations, use top-level state
    if _infer_skill_from_state(state) == "workbook":
        pres = state.get("presentation")
        if not pres or not pres.get("slides"):
            raise HTTPException(status_code=400, detail="No presentation slides found. Generate a presentation first.")
        pdf_state = {
            "presentation_title": pres.get("title"),
            "subtitle": pres.get("subtitle"),
            "slides": pres.get("slides", []),
            "cover_image_url": pres.get("cover_image_url"),
        }
    else:
        pdf_state = state

    pdf_url = await doc_svc.generate_presentation_pdf(
        pdf_state,
        thread_id,
        version,
        company_id=company_id,
    )
    if not pdf_url:
        raise HTTPException(status_code=500, detail="Failed to generate presentation PDF")

    return {"pdf_url": pdf_url}


@router.patch("/threads/{thread_id}", response_model=ThreadListItem)
async def update_thread_title(
    thread_id: UUID,
    body: UpdateTitleRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Update thread title."""
    from app.database import get_connection

    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            UPDATE mw_threads
            SET title=$1, updated_at=NOW()
            WHERE id=$2 AND company_id=$3
            RETURNING id, title, status, version, is_pinned, node_mode, compliance_mode, created_at, updated_at, current_state
            """,
            body.title,
            thread_id,
            company_id,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    await doc_svc.sync_element_record(thread_id)

    row_dict = dict(row)
    current_state = _json_object(row_dict.pop("current_state", {}))
    return ThreadListItem(
        **{
            **row_dict,
            "task_type": _infer_skill_from_state(current_state),
        }
    )


@router.post("/threads/{thread_id}/pin", response_model=ThreadListItem)
async def set_thread_pin(
    thread_id: UUID,
    body: PinThreadRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Pin or unpin a thread for faster access in chat history."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    row = await doc_svc.set_thread_pinned(thread_id, company_id, body.is_pinned)
    if row is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    return ThreadListItem(**row)


@router.post("/threads/{thread_id}/node-mode", response_model=ThreadListItem)
async def set_thread_node_mode(
    thread_id: UUID,
    body: NodeModeRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Enable or disable Node mode (internal data search) for a thread."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    row = await doc_svc.set_thread_node_mode(thread_id, company_id, body.node_mode)
    if row is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    row_dict = dict(row)
    current_state = _json_object(row_dict.pop("current_state", {}))
    return ThreadListItem(
        **{
            **row_dict,
            "task_type": _infer_skill_from_state(current_state),
        }
    )


@router.post("/threads/{thread_id}/compliance-mode", response_model=ThreadListItem)
async def set_thread_compliance_mode(
    thread_id: UUID,
    body: ComplianceModeRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Enable or disable Compliance mode (jurisdiction requirements context) for a thread."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    row = await doc_svc.set_thread_compliance_mode(thread_id, company_id, body.compliance_mode)
    if row is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    row_dict = dict(row)
    current_state = _json_object(row_dict.pop("current_state", {}))
    return ThreadListItem(
        **{
            **row_dict,
            "task_type": _infer_skill_from_state(current_state),
        }
    )


@router.post("/threads/{thread_id}/payer-mode", response_model=ThreadListItem)
async def set_thread_payer_mode(
    thread_id: UUID,
    body: PayerModeRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Enable or disable Payer mode (medical policy coverage data) for a thread."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    row = await doc_svc.set_thread_payer_mode(thread_id, company_id, body.payer_mode)
    if row is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    row_dict = dict(row)
    current_state = _json_object(row_dict.pop("current_state", {}))
    return ThreadListItem(
        **{
            **row_dict,
            "task_type": _infer_skill_from_state(current_state),
        }
    )


@public_router.get("/review-requests/{token}", response_model=PublicReviewRequestResponse)
async def get_public_review_request(token: str):
    """Get a public review-request payload by one-time token."""
    row = await doc_svc.get_public_review_request(token)
    if row is None:
        raise HTTPException(status_code=404, detail="Review request not found")
    return PublicReviewRequestResponse(**row)


@public_router.post(
    "/review-requests/{token}/submit",
    response_model=PublicReviewSubmitResponse,
)
async def submit_public_review_request(
    token: str,
    body: PublicReviewSubmitRequest,
):
    """Submit an anonymous review response via public token link."""
    try:
        result = await doc_svc.submit_public_review_request(
            token=token,
            feedback=body.feedback,
            rating=body.rating,
        )
    except ValueError as e:
        detail = str(e)
        if detail == "Review request not found":
            raise HTTPException(status_code=404, detail=detail)
        if detail == "Review response already submitted":
            raise HTTPException(status_code=409, detail=detail)
        raise HTTPException(status_code=400, detail=detail)

    return PublicReviewSubmitResponse(**result)


# ── Task Board endpoints ──














# ── Language Tutor Voice Sessions ──────────────────────────────────────────


@router.post("/threads/{thread_id}/tutor/start")
async def start_tutor_voice_session(
    thread_id: UUID,
    body: dict = Body(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Start a Gemini Live language tutor voice session linked to a matcha-work thread."""
    from app.core.services.auth import create_interview_ws_token

    language = body.get("language", "en")
    if language not in ("en", "es-mx", "fr"):
        raise HTTPException(status_code=400, detail="Language must be 'en', 'es-mx', or 'fr'")
    duration_minutes = body.get("duration_minutes", 5)
    if duration_minutes not in (0.33, 2, 5, 8):
        raise HTTPException(status_code=400, detail="Duration must be 0.33 (20s test), 2, 5, or 8 minutes")

    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        # Verify thread exists and belongs to user
        thread = await conn.fetchrow(
            "SELECT id, current_state FROM mw_threads WHERE id = $1 AND company_id IS NOT DISTINCT FROM $2",
            thread_id, company_id,
        )
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")

        # Create interview record (same as POST /tutor/sessions with mode=language_test)
        row = await conn.fetchrow(
            """
            INSERT INTO interviews (company_id, interviewer_name, interviewer_role, interview_type, status)
            VALUES (NULL, $1, $2, 'tutor_language', 'pending')
            RETURNING id
            """,
            current_user.email,
            language,
        )
        interview_id = row["id"]

        # Store interview_id in thread current_state
        raw_state = thread["current_state"]
        if isinstance(raw_state, str):
            current_state = json.loads(raw_state) if raw_state else {}
        elif isinstance(raw_state, dict):
            current_state = dict(raw_state)
        else:
            current_state = {}
        current_state["language_tutor"] = {
            "interview_id": str(interview_id),
            "language": language,
            "status": "active",
        }
        await conn.execute(
            "UPDATE mw_threads SET current_state = $1, updated_at = NOW() WHERE id = $2",
            json.dumps(current_state), thread_id,
        )

    duration_seconds = int(duration_minutes * 60)
    return {
        "interview_id": str(interview_id),
        "websocket_url": f"/api/ws/interview/{interview_id}",
        "ws_auth_token": create_interview_ws_token(interview_id),
        "max_session_duration_seconds": duration_seconds,
    }


@router.get("/threads/{thread_id}/tutor/status")
async def get_tutor_voice_status(
    thread_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Poll language tutor session status and analysis results.

    Runs analysis inline (no Celery) on first poll after session ends.
    """
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        thread = await conn.fetchrow(
            "SELECT id, current_state FROM mw_threads WHERE id = $1 AND company_id IS NOT DISTINCT FROM $2",
            thread_id, company_id,
        )
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")

        raw_state = thread["current_state"]
        if isinstance(raw_state, str):
            current_state = json.loads(raw_state) if raw_state else {}
        elif isinstance(raw_state, dict):
            current_state = dict(raw_state)
        else:
            current_state = {}
        tutor_state = current_state.get("language_tutor")
        if not tutor_state or not tutor_state.get("interview_id"):
            raise HTTPException(status_code=404, detail="No tutor session found for this thread")

        interview_id = tutor_state["interview_id"]
        interview = await conn.fetchrow(
            "SELECT status, tutor_analysis, transcript FROM interviews WHERE id = $1",
            UUID(interview_id),
        )
        if not interview:
            raise HTTPException(status_code=404, detail="Interview record not found")

        tutor_analysis = interview["tutor_analysis"]
        interview_status = interview["status"]

        # Run analysis inline if session ended but analysis hasn't run yet.
        # Atomically claim the analysis slot to prevent duplicate runs from concurrent polls.
        if interview_status in ("analyzing", "completed") and not tutor_analysis and interview["transcript"]:
            claimed = await conn.fetchval(
                "UPDATE interviews SET status = 'analyzing_inline' WHERE id = $1 AND status IN ('analyzing', 'completed') AND tutor_analysis IS NULL RETURNING id",
                UUID(interview_id),
            )
            if not claimed:
                # Another request is already running analysis
                return {"status": "analyzing", "tutor_analysis": None}
            try:
                from app.matcha.services.conversation_analyzer import ConversationAnalyzer
                settings = get_settings()
                analyzer = ConversationAnalyzer(
                    api_key=settings.gemini_api_key,
                    model=settings.analysis_model,
                )
                language = tutor_state.get("language", "en")
                tutor_analysis = await analyzer.analyze_tutor_language(
                    transcript=interview["transcript"],
                    language=language,
                )
                # Save analysis and mark completed
                await conn.execute(
                    "UPDATE interviews SET tutor_analysis = $1, status = 'completed' WHERE id = $2",
                    json.dumps(tutor_analysis), UUID(interview_id),
                )
                interview_status = "completed"
            except Exception as e:
                logger.error("Inline tutor analysis failed: %s", e)
                # Reset status so next poll can retry
                await conn.execute(
                    "UPDATE interviews SET status = 'analyzing' WHERE id = $1",
                    UUID(interview_id),
                )
                return {"status": "analyzing", "tutor_analysis": None}

        result = {
            "status": interview_status,
            "tutor_analysis": tutor_analysis if isinstance(tutor_analysis, dict) else (json.loads(tutor_analysis) if tutor_analysis else None),
        }

        # When analysis is complete, save summary as assistant message (idempotent)
        if interview_status == "completed" and tutor_analysis and not tutor_state.get("message_saved"):
            analysis = tutor_analysis if isinstance(tutor_analysis, dict) else json.loads(tutor_analysis)
            proficiency = analysis.get("overall_proficiency", {})
            level = proficiency.get("level", "N/A")
            level_desc = proficiency.get("level_description", "")
            summary_text = f"**Language Practice Complete** — CEFR Level: **{level}** ({level_desc})\n\n"
            strengths = proficiency.get("strengths", [])
            if strengths:
                summary_text += "**Strengths:** " + ", ".join(strengths) + "\n\n"
            areas = proficiency.get("areas_to_improve", [])
            if areas:
                summary_text += "**Areas to Improve:** " + ", ".join(areas) + "\n\n"
            grammar_data = analysis.get("grammar", {})
            errors = grammar_data.get("common_errors", [])
            if errors:
                summary_text += "**Grammar Notes:**\n"
                for err in errors[:5]:
                    if isinstance(err, dict):
                        summary_text += f"- {err.get('error', '')}: {err.get('correction', '')}\n"
                    else:
                        summary_text += f"- {err}\n"

            await doc_svc.add_message(thread_id, "assistant", summary_text.strip())

            # Mark message as saved so we don't duplicate
            current_state_updated = dict(current_state)
            current_state_updated["language_tutor"]["message_saved"] = True
            current_state_updated["language_tutor"]["status"] = "completed"
            await conn.execute(
                "UPDATE mw_threads SET current_state = $1, updated_at = NOW() WHERE id = $2",
                json.dumps(current_state_updated), thread_id,
            )

        return result


# ── Real-time utterance error checking ─────────────────────────────────


UTTERANCE_CHECK_PROMPT_EN = """You are a language tutor analyzing a student's English utterance for errors.

Utterance: "{utterance}"

Return a JSON array of errors found. Each error object has:
- "error": the incorrect word/phrase exactly as spoken
- "correction": the correct form
- "type": one of "grammar", "vocabulary", "pronunciation"
- "brief": a 5-word max explanation

If no errors, return an empty array [].
Only flag clear mistakes, not stylistic preferences. Be concise.
Return ONLY valid JSON, no markdown."""

UTTERANCE_CHECK_PROMPT_ES = """Eres un tutor de idiomas analizando una frase en español de un estudiante.

Frase: "{utterance}"

Devuelve un array JSON de errores encontrados. Cada objeto tiene:
- "error": la palabra/frase incorrecta exactamente como fue dicha
- "correction": la forma correcta
- "type": uno de "grammar", "vocabulary", "pronunciation"
- "brief": explicación de máximo 5 palabras

Si no hay errores, devuelve un array vacío [].
Solo marca errores claros, no preferencias de estilo. Sé conciso.
Devuelve SOLO JSON válido, sin markdown."""


UTTERANCE_CHECK_PROMPT_FR = """Tu es un tuteur de langues analysant une phrase en français d'un étudiant.

Phrase: "{utterance}"

Renvoie un tableau JSON des erreurs trouvées. Chaque objet contient:
- "error": le mot/la phrase incorrecte exactement comme prononcé
- "correction": la forme correcte
- "type": l'un de "grammar", "vocabulary", "pronunciation"
- "brief": explication de 5 mots maximum

S'il n'y a pas d'erreurs, renvoie un tableau vide [].
Ne signale que les erreurs claires, pas les préférences stylistiques. Sois concis.
Renvoie UNIQUEMENT du JSON valide, pas de markdown."""


@router.post("/threads/{thread_id}/tutor/check")
async def check_tutor_utterance(
    thread_id: UUID,
    body: dict = Body(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Real-time error check on a single user utterance during a voice session."""
    utterance = (body.get("utterance") or "").strip()
    language = body.get("language", "en")

    if not utterance or len(utterance) < 3:
        return {"errors": []}

    settings = get_settings()
    try:
        from google import genai
        client = genai.Client(api_key=settings.gemini_api_key)

        if language in ("es", "es-mx"):
            prompt = UTTERANCE_CHECK_PROMPT_ES.format(utterance=utterance)
        elif language == "fr":
            prompt = UTTERANCE_CHECK_PROMPT_FR.format(utterance=utterance)
        else:
            prompt = UTTERANCE_CHECK_PROMPT_EN.format(utterance=utterance)
        response = await client.aio.models.generate_content(model="gemini-3-flash-preview", contents=prompt)
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        errors = json.loads(text)
        return {"errors": errors if isinstance(errors, list) else []}
    except Exception as e:
        logger.warning("Utterance check failed: %s", e)
        return {"errors": []}


# ---------------------------------------------------------------------------
# Thread Collaborator endpoints
# ---------------------------------------------------------------------------

@router.get("/threads/{thread_id}/collaborators")
async def list_thread_collaborators(
    thread_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List collaborators on a thread with user info.

    Always includes the thread creator as a synthetic 'owner' row even if
    they don't have an explicit mw_thread_collaborators entry. Without this,
    the moment the first invitee is added the owner disappears from the
    collaborator list and their client-side `isOwner` flag flips to false.
    """
    company_id = await get_client_company_id(current_user)
    thread = await doc_svc.get_thread(thread_id, company_id, user_id=current_user.id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    owner_id = thread.get("created_by")

    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT tc.user_id, tc.role, tc.created_at,
                   u.email, u.avatar_url,
                   COALESCE(cl.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email) AS name
            FROM mw_thread_collaborators tc
            JOIN users u ON u.id = tc.user_id
            LEFT JOIN clients cl ON cl.user_id = tc.user_id
            LEFT JOIN employees e ON e.user_id = tc.user_id
            LEFT JOIN admins a ON a.user_id = tc.user_id
            WHERE tc.thread_id = $1
            ORDER BY tc.created_at
            """,
            thread_id,
        )

        result = [
            {
                "user_id": str(r["user_id"]),
                "name": r["name"],
                "email": r["email"],
                "role": r["role"],
                "avatar_url": r["avatar_url"],
                "added_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ]

        # Include the thread creator as a synthetic owner row if not already present
        if owner_id is not None and not any(c["user_id"] == str(owner_id) for c in result):
            owner_row = await conn.fetchrow(
                """
                SELECT u.id, u.email, u.avatar_url,
                       COALESCE(cl.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email) AS name
                FROM users u
                LEFT JOIN clients cl ON cl.user_id = u.id
                LEFT JOIN employees e ON e.user_id = u.id
                LEFT JOIN admins a ON a.user_id = u.id
                WHERE u.id = $1
                """,
                owner_id,
            )
            if owner_row:
                result.insert(0, {
                    "user_id": str(owner_row["id"]),
                    "name": owner_row["name"],
                    "email": owner_row["email"],
                    "role": "owner",
                    "avatar_url": owner_row["avatar_url"],
                    "added_at": None,
                })

    return result


@router.post("/threads/{thread_id}/collaborators")
async def add_thread_collaborator(
    thread_id: UUID,
    body: dict = Body(...),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Add a collaborator to a thread. Only the thread owner or admin can invite."""
    company_id = await get_client_company_id(current_user)
    thread = await doc_svc.get_thread(thread_id, company_id, user_id=current_user.id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    # Only the owner or an admin can add collaborators
    if current_user.role != "admin" and thread["created_by"] != current_user.id:
        raise HTTPException(status_code=403, detail="Only the thread owner can add collaborators")

    user_id = body.get("user_id")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    try:
        collab_user_id = UUID(user_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid user_id")

    if collab_user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot add yourself as a collaborator")

    async with get_connection() as conn:
        # Verify user exists and is active
        target_user = await conn.fetchrow(
            "SELECT id, email FROM users WHERE id = $1 AND is_active = true",
            collab_user_id,
        )
        if not target_user:
            raise HTTPException(status_code=404, detail="User not found")

        # Check if already a collaborator
        existing = await conn.fetchval(
            "SELECT id FROM mw_thread_collaborators WHERE thread_id = $1 AND user_id = $2",
            thread_id, collab_user_id,
        )
        if existing:
            raise HTTPException(status_code=400, detail="User is already a collaborator")

        await conn.execute(
            """INSERT INTO mw_thread_collaborators (thread_id, user_id, invited_by, role)
               VALUES ($1, $2, $3, 'collaborator')""",
            thread_id, collab_user_id, current_user.id,
        )

        # Send inbox notification
        try:
            inviter = await conn.fetchrow("SELECT email FROM users WHERE id = $1", current_user.id)
            inviter_client = await conn.fetchrow("SELECT name FROM clients WHERE user_id = $1", current_user.id)
            inviter_name = (inviter_client["name"] if inviter_client else None) or inviter["email"].split("@")[0]
            thread_title = thread.get("title") or "a thread"

            msg_content = f"**{inviter_name}** has invited you to collaborate on the thread **{thread_title}**."
            conversation = await conn.fetchrow(
                """INSERT INTO inbox_conversations (title, is_group, created_by, last_message_at, last_message_preview)
                   VALUES ($1, false, $2, NOW(), $3)
                   RETURNING id""",
                f"Thread Invite: {thread_title}", current_user.id, msg_content[:100],
            )
            conv_id = conversation["id"]
            await conn.execute(
                "INSERT INTO inbox_participants (conversation_id, user_id) VALUES ($1, $2)", conv_id, current_user.id,
            )
            await conn.execute(
                "INSERT INTO inbox_participants (conversation_id, user_id) VALUES ($1, $2)", conv_id, collab_user_id,
            )
            await conn.execute(
                """INSERT INTO inbox_messages (conversation_id, sender_id, content)
                   VALUES ($1, $2, $3)""",
                conv_id, current_user.id, msg_content,
            )
        except Exception as e:
            logger.warning("Failed to send thread collaborator inbox notification: %s", e)

        # Create MW notification
        try:
            from app.matcha.services import notification_service as notif_svc
            inviter_client = await conn.fetchrow("SELECT name FROM clients WHERE user_id = $1", current_user.id)
            inviter_name = (inviter_client["name"] if inviter_client else None) or "Someone"
            await notif_svc.create_notification(
                user_id=collab_user_id,
                company_id=company_id,
                type="thread_collaborator_added",
                title=f"{inviter_name} added you to a thread",
                body=f"You've been added as a collaborator on \"{thread.get('title', 'a thread')}\"",
                link="/work",
                metadata={"thread_id": str(thread_id), "invited_by": str(current_user.id)},
            )
        except Exception as e:
            logger.warning("Failed to create thread collaborator notification: %s", e)

    return {"added": True, "user_id": str(collab_user_id)}


@router.delete("/threads/{thread_id}/collaborators/{user_id}")
async def remove_thread_collaborator(
    thread_id: UUID,
    user_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Remove a collaborator from a thread. Owner, admin, or the collaborator themselves can do this."""
    company_id = await get_client_company_id(current_user)
    thread = await doc_svc.get_thread(thread_id, company_id, user_id=current_user.id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    # Allow removal if: admin, thread owner, or self-removal
    is_owner = thread["created_by"] == current_user.id
    is_self = user_id == current_user.id
    if current_user.role != "admin" and not is_owner and not is_self:
        raise HTTPException(status_code=403, detail="Only the thread owner can remove collaborators")

    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM mw_thread_collaborators WHERE thread_id = $1 AND user_id = $2",
            thread_id, user_id,
        )
        if result.endswith("0"):
            raise HTTPException(status_code=404, detail="Collaborator not found")

    return {"removed": True, "user_id": str(user_id)}


@router.get("/threads/{thread_id}/collaborators/search")
async def search_thread_collaborator_candidates(
    thread_id: UUID,
    q: str = Query(..., min_length=2, max_length=100),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Search users to invite as thread collaborators."""
    company_id = await get_client_company_id(current_user)
    thread = await doc_svc.get_thread(thread_id, company_id, user_id=current_user.id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    pattern = f"%{q}%"
    async with get_connection() as conn:
        # Search eligible invitees: same-company users + admins + accepted cross-tenant connections
        rows = await conn.fetch(
            """
            SELECT DISTINCT u.id AS user_id, u.email, u.avatar_url,
                   COALESCE(cl.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email) AS name
            FROM users u
            LEFT JOIN clients cl ON cl.user_id = u.id
            LEFT JOIN employees e ON e.user_id = u.id
            LEFT JOIN admins a ON a.user_id = u.id
            WHERE u.id != $1
              AND u.is_active = true
              AND (
                  COALESCE(cl.name, CONCAT(e.first_name, ' ', e.last_name), a.name, '') ILIKE $2
                  OR u.email ILIKE $2
              )
              AND (
                  (cl.company_id = $3)
                  OR (e.org_id = $3)
                  OR (a.user_id IS NOT NULL)
                  OR EXISTS (
                      SELECT 1 FROM user_connections uc
                      WHERE uc.status = 'accepted'
                        AND (
                          (uc.user_id = $1 AND uc.connected_user_id = u.id)
                          OR (uc.connected_user_id = $1 AND uc.user_id = u.id)
                        )
                  )
              )
              AND NOT EXISTS(
                  SELECT 1 FROM mw_thread_collaborators tc
                  WHERE tc.thread_id = $4 AND tc.user_id = u.id
              )
            ORDER BY u.email
            LIMIT 10
            """,
            current_user.id, pattern, company_id, thread_id,
        )
    return [
        {
            "user_id": str(r["user_id"]),
            "name": r["name"],
            "email": r["email"],
            "avatar_url": r["avatar_url"],
        }
        for r in rows
    ]
