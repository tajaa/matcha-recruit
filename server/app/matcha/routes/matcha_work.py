"""Matcha Work — chat-driven AI workspace for HR document elements."""

import json
import logging
import re
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from ...core.models.auth import CurrentUser
from ..dependencies import require_admin_or_client, get_client_company_id
from ..models.matcha_work import (
    CreateThreadRequest,
    CreateThreadResponse,
    DocumentVersionResponse,
    ElementListItem,
    FinalizeResponse,
    MWMessageOut,
    ReviewDocument,
    RevertRequest,
    SaveDraftResponse,
    SendMessageRequest,
    SendMessageResponse,
    PinThreadRequest,
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
)
from ..services import matcha_work_document as doc_svc
from ..services.matcha_work_ai import get_ai_provider

logger = logging.getLogger(__name__)

router = APIRouter()
public_router = APIRouter()

VALID_OFFER_LETTER_FIELDS = set(OfferLetterDocument.model_fields.keys())
VALID_REVIEW_FIELDS = set(ReviewDocument.model_fields.keys())
UNSUPPORTED_SKILL_REPLY = "I can't do that. I can help with offer letters and anonymized reviews."

OFFER_INTENT_PATTERNS: tuple[tuple[str, int], ...] = (
    (r"\boffer letter\b", 4),
    (r"\bjob offer\b", 4),
    (r"\bemployment offer\b", 4),
    (r"\boffer\b", 1),
    (r"\bsalary\b", 1),
    (r"\bcompensation\b", 1),
    (r"\bbenefits?\b", 1),
    (r"\bstart date\b", 1),
    (r"\bcandidate\b", 1),
)

REVIEW_INTENT_PATTERNS: tuple[tuple[str, int], ...] = (
    (r"\bperformance review\b", 4),
    (r"\banonym(?:ous|ized)\s+review\b", 4),
    (r"\breview\b", 1),
    (r"\bfeedback\b", 1),
    (r"\bstrengths?\b", 1),
    (r"\bgrowth areas?\b", 1),
    (r"\brating\b", 1),
    (r"\bevaluation\b", 1),
)


def _normalize_task_type(task_type: Optional[str]) -> str:
    return "review" if task_type == "review" else "offer_letter"


def _is_offer_letter_task(task_type: Optional[str]) -> bool:
    return _normalize_task_type(task_type) == "offer_letter"


def _validate_updates(task_type: Optional[str], updates: dict) -> dict:
    """Filter AI updates to known fields for the thread task type."""
    valid_fields = VALID_OFFER_LETTER_FIELDS if _is_offer_letter_task(task_type) else VALID_REVIEW_FIELDS
    return {k: v for k, v in updates.items() if k in valid_fields}


def _intent_score(text: str, patterns: tuple[tuple[str, int], ...]) -> int:
    score = 0
    for pattern, weight in patterns:
        if re.search(pattern, text):
            score += weight
    return score


def _detect_requested_task_type(content: str) -> Optional[str]:
    text = content.lower().strip()
    if not text:
        return None
    offer_score = _intent_score(text, OFFER_INTENT_PATTERNS)
    review_score = _intent_score(text, REVIEW_INTENT_PATTERNS)
    if offer_score == 0 and review_score == 0:
        return None
    if offer_score > review_score:
        return "offer_letter"
    if review_score > offer_score:
        return "review"
    if re.search(r"\boffer letter\b|\bjob offer\b|\bemployment offer\b", text):
        return "offer_letter"
    if re.search(r"\bperformance review\b|\banonym(?:ous|ized)\s+review\b", text):
        return "review"
    return None


def _thread_has_existing_work(thread: dict, prior_message_count: int = 0) -> bool:
    return bool(thread.get("current_state")) or int(thread.get("version", 0)) > 0 or prior_message_count > 0


async def _resolve_task_type_for_message(
    thread: dict,
    company_id: UUID,
    content: str,
    prior_message_count: int = 0,
) -> tuple[Optional[str], dict, Optional[str]]:
    current_task_type = _normalize_task_type(thread.get("task_type"))
    requested_task_type = _detect_requested_task_type(content)
    has_existing_work = _thread_has_existing_work(thread, prior_message_count=prior_message_count)

    if requested_task_type is None:
        if has_existing_work:
            return current_task_type, thread, None
        return None, thread, UNSUPPORTED_SKILL_REPLY

    if requested_task_type != current_task_type:
        if has_existing_work:
            return None, thread, UNSUPPORTED_SKILL_REPLY
        switched = await doc_svc.set_thread_task_type(thread["id"], company_id, requested_task_type)
        if switched is not None:
            thread = switched
        current_task_type = requested_task_type

    return current_task_type, thread, None


def _row_to_message(row: dict) -> MWMessageOut:
    return MWMessageOut(
        id=row["id"],
        thread_id=row["thread_id"],
        role=row["role"],
        content=row["content"],
        version_created=row.get("version_created"),
        created_at=row["created_at"],
    )


def _sse_data(payload: dict) -> str:
    return f"data: {json.dumps(payload, default=str)}\n\n"


@router.post("/threads", response_model=CreateThreadResponse, status_code=201)
async def create_thread(
    body: CreateThreadRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Create a new chat thread (optionally with an initial message)."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=400, detail="No company associated with this account")

    task_type = _normalize_task_type(body.task_type)
    default_title = "Untitled Review" if task_type == "review" else "Untitled Chat"
    title = body.title or default_title
    thread = await doc_svc.create_thread(company_id, current_user.id, title, task_type=task_type)
    thread_id = thread["id"]

    assistant_reply = None
    pdf_url = None

    if body.initial_message:
        # Save user message
        await doc_svc.add_message(thread_id, "user", body.initial_message)
        resolved_task_type, thread, unsupported_reply = await _resolve_task_type_for_message(
            thread,
            company_id,
            body.initial_message,
            prior_message_count=0,
        )

        if unsupported_reply:
            await doc_svc.add_message(thread_id, "assistant", unsupported_reply)
            assistant_reply = unsupported_reply
        else:
            # Call AI
            ai_provider = get_ai_provider()
            messages = [{"role": "user", "content": body.initial_message}]
            estimated_usage = ai_provider.estimate_usage(
                messages, thread["current_state"], task_type=resolved_task_type
            )
            ai_resp = await ai_provider.generate(
                messages, thread["current_state"], task_type=resolved_task_type
            )
            final_usage = ai_resp.token_usage or estimated_usage

            new_version = thread["version"]
            applied_update = False
            if ai_resp.structured_update:
                safe_updates = _validate_updates(resolved_task_type, ai_resp.structured_update)
                if safe_updates:
                    result = await doc_svc.apply_update(thread_id, safe_updates)
                    new_version = result["version"]
                    thread["current_state"] = result["current_state"]
                    applied_update = True

            await doc_svc.add_message(
                thread_id,
                "assistant",
                ai_resp.assistant_reply,
                version_created=new_version if applied_update else None,
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
            thread["task_type"] = resolved_task_type
            assistant_reply = ai_resp.assistant_reply

            # Offer-letter threads render draft PDFs; review threads remain chat-only.
            if _is_offer_letter_task(resolved_task_type) and thread["current_state"]:
                pdf_url = await doc_svc.generate_pdf(
                    thread["current_state"], thread_id, new_version, is_draft=True
                )

    return CreateThreadResponse(
        id=thread_id,
        title=thread["title"],
        task_type=thread["task_type"],
        status=thread["status"],
        current_state=thread["current_state"],
        version=thread["version"],
        is_pinned=thread.get("is_pinned", False),
        created_at=thread["created_at"],
        assistant_reply=assistant_reply,
        pdf_url=pdf_url,
    )


@router.get("/threads", response_model=list[ThreadListItem])
async def list_threads(
    status: Optional[str] = Query(None, pattern="^(active|finalized|archived)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """List threads for the current company."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return []

    threads = await doc_svc.list_threads(company_id, status=status, limit=limit, offset=offset)
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
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    thread = await doc_svc.get_thread(thread_id, company_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    messages = await doc_svc.get_thread_messages(thread_id)

    return ThreadDetailResponse(
        id=thread["id"],
        title=thread["title"],
        task_type=thread["task_type"],
        status=thread["status"],
        current_state=thread["current_state"],
        version=thread["version"],
        is_pinned=thread.get("is_pinned", False),
        linked_offer_letter_id=thread.get("linked_offer_letter_id"),
        created_at=thread["created_at"],
        updated_at=thread["updated_at"],
        messages=[_row_to_message(m) for m in messages],
    )


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

    thread = await doc_svc.get_thread(thread_id, company_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    if thread["status"] == "finalized":
        raise HTTPException(status_code=400, detail="Cannot send messages to a finalized thread")

    if thread["status"] == "archived":
        raise HTTPException(status_code=400, detail="Cannot send messages to an archived thread")

    # Save user message
    user_msg = await doc_svc.add_message(thread_id, "user", body.content)

    # Fetch message history for context (sliding window handled by AI provider)
    messages = await doc_svc.get_thread_messages(thread_id)
    msg_dicts = [{"role": m["role"], "content": m["content"]} for m in messages]
    prior_message_count = max(0, len(messages) - 1)
    resolved_task_type, thread, unsupported_reply = await _resolve_task_type_for_message(
        thread,
        company_id,
        body.content,
        prior_message_count=prior_message_count,
    )

    if unsupported_reply:
        assistant_msg = await doc_svc.add_message(
            thread_id,
            "assistant",
            unsupported_reply,
            version_created=None,
        )
        return SendMessageResponse(
            user_message=_row_to_message(user_msg),
            assistant_message=_row_to_message(assistant_msg),
            current_state=thread["current_state"],
            version=thread["version"],
            pdf_url=None,
            token_usage=None,
        )

    # Call AI
    ai_provider = get_ai_provider()
    estimated_usage = ai_provider.estimate_usage(
        msg_dicts, thread["current_state"], task_type=resolved_task_type
    )
    ai_resp = await ai_provider.generate(
        msg_dicts, thread["current_state"], task_type=resolved_task_type
    )
    final_usage = ai_resp.token_usage or estimated_usage

    current_version = thread["version"]
    current_state = thread["current_state"]
    pdf_url = None
    applied_update = False

    # Apply updates if AI returned any
    if ai_resp.structured_update:
        safe_updates = _validate_updates(resolved_task_type, ai_resp.structured_update)
        if safe_updates:
            result = await doc_svc.apply_update(thread_id, safe_updates)
            current_version = result["version"]
            current_state = result["current_state"]
            applied_update = True

            if _is_offer_letter_task(resolved_task_type):
                # Generate PDF for offer-letter mode.
                pdf_url = await doc_svc.generate_pdf(
                    current_state, thread_id, current_version, is_draft=True
                )

    # Save assistant message
    assistant_msg = await doc_svc.add_message(
        thread_id,
        "assistant",
        ai_resp.assistant_reply,
        version_created=current_version if applied_update else None,
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

    return SendMessageResponse(
        user_message=_row_to_message(user_msg),
        assistant_message=_row_to_message(assistant_msg),
        current_state=current_state,
        version=current_version,
        pdf_url=pdf_url,
        token_usage=final_usage,
    )


@router.post("/threads/{thread_id}/messages/stream")
async def send_message_stream(
    thread_id: UUID,
    body: SendMessageRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Send message with SSE progress + token usage events."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    thread = await doc_svc.get_thread(thread_id, company_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    if thread["status"] == "finalized":
        raise HTTPException(status_code=400, detail="Cannot send messages to a finalized thread")

    if thread["status"] == "archived":
        raise HTTPException(status_code=400, detail="Cannot send messages to an archived thread")

    # Save user message before streaming
    user_msg = await doc_svc.add_message(thread_id, "user", body.content)

    # Fetch message history for context (sliding window handled by AI provider)
    messages = await doc_svc.get_thread_messages(thread_id)
    msg_dicts = [{"role": m["role"], "content": m["content"]} for m in messages]
    prior_message_count = max(0, len(messages) - 1)
    resolved_task_type, thread, unsupported_reply = await _resolve_task_type_for_message(
        thread,
        company_id,
        body.content,
        prior_message_count=prior_message_count,
    )

    if unsupported_reply:
        assistant_msg = await doc_svc.add_message(
            thread_id,
            "assistant",
            unsupported_reply,
            version_created=None,
        )
        unsupported_response = SendMessageResponse(
            user_message=_row_to_message(user_msg),
            assistant_message=_row_to_message(assistant_msg),
            current_state=thread["current_state"],
            version=thread["version"],
            pdf_url=None,
            token_usage=None,
        )

        async def unsupported_stream():
            yield _sse_data({"type": "complete", "data": unsupported_response.model_dump(mode="json")})
            yield "data: [DONE]\n\n"

        return StreamingResponse(unsupported_stream(), media_type="text/event-stream")

    ai_provider = get_ai_provider()
    estimated_usage = ai_provider.estimate_usage(
        msg_dicts, thread["current_state"], task_type=resolved_task_type
    )

    async def event_stream():
        try:
            yield _sse_data(
                {
                    "type": "usage",
                    "data": {
                        **estimated_usage,
                        "stage": "estimate",
                    },
                }
            )

            ai_resp = await ai_provider.generate(
                msg_dicts, thread["current_state"], task_type=resolved_task_type
            )

            current_version = thread["version"]
            current_state = thread["current_state"]
            pdf_url = None
            applied_update = False

            # Apply updates if AI returned any
            if ai_resp.structured_update:
                safe_updates = _validate_updates(resolved_task_type, ai_resp.structured_update)
                if safe_updates:
                    result = await doc_svc.apply_update(thread_id, safe_updates)
                    current_version = result["version"]
                    current_state = result["current_state"]
                    applied_update = True

                    if _is_offer_letter_task(resolved_task_type):
                        # Generate PDF for offer-letter mode.
                        pdf_url = await doc_svc.generate_pdf(
                            current_state, thread_id, current_version, is_draft=True
                        )

            # Save assistant message
            assistant_msg = await doc_svc.add_message(
                thread_id,
                "assistant",
                ai_resp.assistant_reply,
                version_created=current_version if applied_update else None,
            )

            final_usage = ai_resp.token_usage or estimated_usage
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
                pdf_url=pdf_url,
                token_usage=final_usage,
            )

            yield _sse_data({"type": "complete", "data": response.model_dump(mode="json")})
        except Exception as e:
            logger.error("Matcha Work stream failed for thread %s: %s", thread_id, e, exc_info=True)
            yield _sse_data(
                {
                    "type": "error",
                    "message": "Failed to process message. Please try again.",
                }
            )
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/usage/summary", response_model=UsageSummaryResponse)
async def get_usage_summary(
    period_days: int = Query(30, ge=1, le=365),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Get Matcha Work token usage totals for the current user, grouped by model."""
    company_id = await get_client_company_id(current_user)
    if company_id is None:
        return UsageSummaryResponse(
            period_days=period_days,
            generated_at=datetime.now(timezone.utc),
            totals={
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "operation_count": 0,
                "estimated_operations": 0,
            },
            by_model=[],
        )

    summary = await doc_svc.get_token_usage_summary(company_id, current_user.id, period_days)
    return UsageSummaryResponse(**summary)


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
    if _is_offer_letter_task(thread["task_type"]):
        pdf_url = await doc_svc.generate_pdf(new_state, thread_id, new_version, is_draft=True)

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
    if not _is_offer_letter_task(thread["task_type"]):
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
    if not _is_offer_letter_task(thread["task_type"]):
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
    pdf_url = await doc_svc.generate_pdf(state, thread_id, target_version, is_draft=is_draft)

    if pdf_url is None:
        raise HTTPException(status_code=503, detail="PDF generation unavailable")

    return {"pdf_url": pdf_url, "version": target_version}


@router.delete("/threads/{thread_id}", status_code=204)
async def archive_thread(
    thread_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Archive (soft-delete) a thread."""
    from ...database import get_connection

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


@router.patch("/threads/{thread_id}", response_model=ThreadListItem)
async def update_thread_title(
    thread_id: UUID,
    body: UpdateTitleRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Update thread title."""
    from ...database import get_connection

    company_id = await get_client_company_id(current_user)
    if company_id is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            UPDATE mw_threads
            SET title=$1, updated_at=NOW()
            WHERE id=$2 AND company_id=$3
            RETURNING id, title, task_type, status, version, is_pinned, created_at, updated_at
            """,
            body.title,
            thread_id,
            company_id,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    await doc_svc.sync_element_record(thread_id)

    return ThreadListItem(**dict(row))


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
