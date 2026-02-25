"""Matcha Work — chat-driven, AI-powered offer letter generation."""

import json
import logging
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
    FinalizeResponse,
    MWMessageOut,
    RevertRequest,
    SaveDraftResponse,
    SendMessageRequest,
    SendMessageResponse,
    ThreadDetailResponse,
    ThreadListItem,
    OfferLetterDocument,
    UsageSummaryResponse,
    UpdateTitleRequest,
)
from ..services import matcha_work_document as doc_svc
from ..services.matcha_work_ai import get_ai_provider

logger = logging.getLogger(__name__)

router = APIRouter()

VALID_DOCUMENT_FIELDS = set(OfferLetterDocument.model_fields.keys())


def _validate_updates(updates: dict) -> dict:
    """Filter AI updates to only known OfferLetterDocument fields."""
    return {k: v for k, v in updates.items() if k in VALID_DOCUMENT_FIELDS}


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

    title = body.title or "Untitled Offer Letter"
    thread = await doc_svc.create_thread(company_id, current_user.id, title)
    thread_id = thread["id"]

    assistant_reply = None
    pdf_url = None

    if body.initial_message:
        # Save user message
        await doc_svc.add_message(thread_id, "user", body.initial_message)

        # Call AI
        ai_provider = get_ai_provider()
        messages = [{"role": "user", "content": body.initial_message}]
        estimated_usage = ai_provider.estimate_usage(messages, thread["current_state"])
        ai_resp = await ai_provider.generate(messages, thread["current_state"])
        final_usage = ai_resp.token_usage or estimated_usage

        new_version = thread["version"]
        if ai_resp.structured_update:
            safe_updates = _validate_updates(ai_resp.structured_update)
            if safe_updates:
                result = await doc_svc.apply_update(thread_id, safe_updates)
                new_version = result["version"]
                thread["current_state"] = result["current_state"]

        await doc_svc.add_message(
            thread_id, "assistant", ai_resp.assistant_reply, version_created=new_version
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
        assistant_reply = ai_resp.assistant_reply

        # Generate PDF if there are document fields
        if thread["current_state"]:
            pdf_url = await doc_svc.generate_pdf(
                thread["current_state"], thread_id, new_version, is_draft=True
            )

    return CreateThreadResponse(
        id=thread_id,
        title=thread["title"],
        status=thread["status"],
        current_state=thread["current_state"],
        version=thread["version"],
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

    # Call AI
    ai_provider = get_ai_provider()
    estimated_usage = ai_provider.estimate_usage(msg_dicts, thread["current_state"])
    ai_resp = await ai_provider.generate(msg_dicts, thread["current_state"])
    final_usage = ai_resp.token_usage or estimated_usage

    current_version = thread["version"]
    current_state = thread["current_state"]
    pdf_url = None

    # Apply updates if AI returned any
    if ai_resp.structured_update:
        safe_updates = _validate_updates(ai_resp.structured_update)
        if safe_updates:
            result = await doc_svc.apply_update(thread_id, safe_updates)
            current_version = result["version"]
            current_state = result["current_state"]

            # Generate PDF
            pdf_url = await doc_svc.generate_pdf(
                current_state, thread_id, current_version, is_draft=True
            )

    # Save assistant message
    assistant_msg = await doc_svc.add_message(
        thread_id,
        "assistant",
        ai_resp.assistant_reply,
        version_created=current_version if ai_resp.structured_update else None,
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

    ai_provider = get_ai_provider()
    estimated_usage = ai_provider.estimate_usage(msg_dicts, thread["current_state"])

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

            ai_resp = await ai_provider.generate(msg_dicts, thread["current_state"])

            current_version = thread["version"]
            current_state = thread["current_state"]
            pdf_url = None

            # Apply updates if AI returned any
            if ai_resp.structured_update:
                safe_updates = _validate_updates(ai_resp.structured_update)
                if safe_updates:
                    result = await doc_svc.apply_update(thread_id, safe_updates)
                    current_version = result["version"]
                    current_state = result["current_state"]

                    # Generate PDF
                    pdf_url = await doc_svc.generate_pdf(
                        current_state, thread_id, current_version, is_draft=True
                    )

            # Save assistant message
            assistant_msg = await doc_svc.add_message(
                thread_id,
                "assistant",
                ai_resp.assistant_reply,
                version_created=current_version if ai_resp.structured_update else None,
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
            RETURNING id, title, task_type, status, version, created_at, updated_at
            """,
            body.title,
            thread_id,
            company_id,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="Thread not found")

    return ThreadListItem(**dict(row))
