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

import logging
import os
import re
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse

from app.core.models.auth import CurrentUser
from app.matcha.services.matcha_work.ai_apply import _apply_ai_updates_and_operations
from app.matcha.routes.matcha_work._shared import (
    _build_thread_detail_response,
    _json_object,
    _row_to_message,
)
from app.core.feature_flags import get_company_features
from app.core.services.storage import get_storage
from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.matcha.models.matcha_work.matcha_work import (
    CreateThreadRequest,
    CreateThreadResponse,
    DocumentVersionResponse,
    ElementListItem,
    FinalizeResponse,
    RevertRequest,
    SaveDraftResponse,
    SendMessageResponse,
    PinThreadRequest,
    ThreadModeRequest,
    NodeModeRequest,
    ComplianceModeRequest,
    PayerModeRequest,
    ThreadDetailResponse,
    ThreadListItem,
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
)
from app.matcha.services.matcha_work import matcha_work_document as doc_svc
from app.matcha.services.matcha_work.matcha_work_modes import MODE_COLUMNS_SQL, MODES_BY_KEY, THREAD_MODES
from app.matcha.services.matcha_work.matcha_work_handbook_upload import (
    HANDBOOK_UPLOAD_EXTENSIONS,
    HANDBOOK_UPLOAD_MAX_BYTES,
    _thread_accepts_handbook_upload,
    run_handbook_upload,
)
from app.matcha.services._shared.uploads import read_upload_capped
from app.matcha.services.matcha_work.matcha_work_ai import get_ai_provider, _infer_skill_from_state, _build_company_context
from app.core.services.handbook_service import HandbookService

logger = logging.getLogger(__name__)



router = APIRouter()
public_router = APIRouter()

























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
            _post_events,  # HR Pilot mode can't be on for a just-created thread — always empty
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
        # Registry-driven so a new mode can't be silently dropped here.
        **{m.column: thread.get(m.column, False) for m in THREAD_MODES},
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
    stream with quarterly progress events for the happy-path analysis. The audit
    itself lives in services/matcha_work/matcha_work_handbook_upload.py.
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

    # Extension first, then a CAPPED read. `content=await file.read()` as a call
    # argument materialized the entire body before run_handbook_upload got to
    # check the extension whitelist or the synced-locations gate, so a 500MB zip
    # was pulled fully into the process and then 400'd. The service re-checks
    # both (it is the contract, and huume calls it too) — this is the bound.
    extension = os.path.splitext((file.filename or "").strip())[1].lower()
    if extension not in HANDBOOK_UPLOAD_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Only PDF, DOCX, and DOC handbooks are supported")

    stream = await run_handbook_upload(
        thread_id=thread_id,
        company_id=company_id,
        thread=thread,
        raw_filename=file.filename,
        content=await read_upload_capped(file, HANDBOOK_UPLOAD_MAX_BYTES),
        content_type=file.content_type,
    )
    if stream is None:
        # Blocked or rejected — state + messages already written by the service.
        return await _build_thread_detail_response(thread_id, company_id)
    return StreamingResponse(stream, media_type="text/event-stream")


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
    background_tasks: BackgroundTasks,
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
            # This endpoint exists to ask employees to sign, so it notifies —
            # after the response, like the /handbooks distribute route.
            background_tasks=background_tasks,
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
            f"""
            UPDATE mw_threads
            SET title=$1, updated_at=NOW()
            WHERE id=$2 AND company_id=$3
            RETURNING id, title, status, version, is_pinned, {MODE_COLUMNS_SQL}, created_at, updated_at, current_state
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


@router.post("/threads/{thread_id}/modes/{mode_key}", response_model=ThreadListItem)
async def set_thread_mode(
    thread_id: UUID,
    mode_key: str,
    body: ThreadModeRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Enable or disable any registered grounding mode for a thread.

    mode_key is validated against matcha_work_modes.THREAD_MODES. The
    per-mode endpoints below (/node-mode, /compliance-mode, /payer-mode)
    are legacy aliases kept for older clients (Werk desktop)."""
    mode = MODES_BY_KEY.get(mode_key)
    if mode is None:
        raise HTTPException(status_code=404, detail="Unknown thread mode")
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    # A mode injects records from its subsystem into every AI turn, so the
    # company must actually own that subsystem's feature. Enforced here rather
    # than via require_feature(), which is a static per-route dependency and
    # can't read the flag name off a path param. Admins bypass, as they do there.
    if mode.required_feature and current_user.role != "admin":
        features = await get_company_features(company_id)
        if not features.get(mode.required_feature, False):
            raise HTTPException(
                status_code=403,
                detail=f"The '{mode.required_feature}' feature is not enabled for your company",
            )

    row = await doc_svc.set_thread_mode(thread_id, company_id, mode_key, body.enabled)
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







