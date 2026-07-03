"""Thread lifecycle: create/logo/handbook-upload, list/get, versions/revert/
finalize/save-draft, PDF export + proxy, archive/unarchive, review-requests
+ handbook-signatures + presentation, title/pin/node-mode/compliance-mode/
payer-mode, and the public review-request routes (own public_router).

This is the remainder of the original flat matcha_work.py after the rest
was extracted into sibling submodules during the package split
(2026-07-03) -- see matcha_work/CLAUDE.md for the module map. Feature-gate
(require_feature("matcha_work")) now lives solely on the __init__.py
aggregator router, not here (previously double-applied during the split's
transitional phase).
"""

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
from app.matcha.dependencies import require_admin_or_client, require_company_member, get_client_company_id
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



router = APIRouter()
public_router = APIRouter()



HANDBOOK_UPLOAD_EXTENSIONS = {".pdf", ".doc", ".docx"}
HANDBOOK_UPLOAD_MAX_BYTES = 10 * 1024 * 1024






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








# Kept in lockstep with ERDocumentParser.extract_text — every allowed type
# must be text-extractable so an attached file can actually feed the AI.
# (xlsx/xls excluded: no extractor; export to CSV instead.)
# Per-file cap on extracted text fed into the AI prompt. Keeps a single large
# PDF from blowing the context window; the user can ask follow-ups that target
# specific sections if a file is truncated.
















# ── Project (top-level) endpoints ──












# ── Recruiting clients (hiring clients a recruiter works for) ──




























# ── Discipline project endpoints ───────────────────────────────────













# ── Blog endpoints (project_type == 'blog') ──
























# ── Note (section) comment endpoints ──










# ── Project file attachment endpoints ──


# Blog post media — images + video embedded inline in section markdown.
# Higher cap accounts for short videos; keep in sync with desktop toolbar.








# ── Project Files: folders + move ──























# ── Project-scoped kanban tasks (collab projects) ──
























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






# ── Real-time utterance error checking ─────────────────────────────────









# ---------------------------------------------------------------------------
# Thread Collaborator endpoints
# ---------------------------------------------------------------------------







