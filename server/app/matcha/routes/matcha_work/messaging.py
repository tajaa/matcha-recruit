"""The core AI-turn messaging surface: send_message_stream (SSE route).

The pipeline it orchestrates (TurnContext + the named stages) moved to
services/matcha_work/turn_pipeline.py (refactor round 2, stage 5) — this
file just wires the HTTP layer to it.

The non-streaming POST /threads/{id}/messages handler was DELETED (2026-07-09):
no client called it (web + desktop both stream), and it had drifted from the
streaming handler — it bypassed the per-user token quota, built context from
the caller's company instead of the thread's, and crashed after billing on
payer-mode turns. See MATCHA_WORK_CHAT_AUDIT.md (C2/H1/H2/M5).
"""
import asyncio
import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.core.models.auth import CurrentUser
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.matcha.models.matcha_work.matcha_work import SendMessageRequest, SendMessageResponse
from app.matcha.routes.matcha_work._shared import _row_to_message, _sse_data
from app.matcha.services.matcha_work import matcha_work_document as doc_svc
from app.matcha.services.matcha_work.ai_apply import (
    _fetch_project_meta,
    _inject_recruiting_project_context,
    _inject_slide_context,
)
from app.matcha.services.matcha_work.matcha_work_ai import _build_company_context, _infer_skill_from_state, get_ai_provider
from app.matcha.services.matcha_work.turn_pipeline import (
    TurnContext,
    _attached_files_context,
    _audit_and_persist,
    _generate_turn,
    _inject_mode_contexts,
    _maybe_compact,
    _prepare_attachments,
    _run_hard_stop_gates,
    _run_huume_dispatch,
    _run_quota_gate,
    _track_background_task,
)

logger = logging.getLogger(__name__)
router = APIRouter()


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

    await _run_quota_gate(company_id, current_user)

    tc = TurnContext(
        thread_id=thread_id,
        body=body,
        current_user=current_user,
        thread=thread,
        company_id=company_id,
    )

    await _prepare_attachments(tc)

    # Fetch message history + company profile + context summary in parallel
    messages, profile, (context_summary, summary_at_count) = await asyncio.gather(
        doc_svc.get_thread_messages(thread_id, limit=20),
        doc_svc.get_company_profile_for_ai(company_id),
        doc_svc.get_context_summary(thread_id),
    )
    tc.profile = profile
    tc.context_summary = context_summary
    tc.summary_at_count = summary_at_count
    # Whether this turn is the thread's first exchange — the one auto-title
    # dispatch point. `messages` is the pre-turn history (fetched above,
    # before this turn's own messages are persisted), so an empty list here
    # means the user's message about to be sent is the first one.
    is_first_exchange = not messages
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
    tc.msg_dicts = msg_dicts
    tc.file_context_parts = file_context_parts

    # Inject selected slide content into the AI-facing message (not saved to DB)
    _inject_slide_context(msg_dicts, thread["current_state"], body.slide_index)

    # Pre-fetch any image attachment bytes concurrently off the event loop so
    # the prompt builder (which runs in a thread pool) doesn't block on I/O.
    from app.matcha.services.matcha_work.matcha_work_ai import fetch_image_parts_for_messages
    await fetch_image_parts_for_messages(msg_dicts)

    tc.ai_provider = get_ai_provider()
    ctx = _build_company_context(profile)

    # Inject project file attachments metadata
    if thread.get("project_id"):
        from app.matcha.services.matcha_work import project_file_service
        pfiles = await project_file_service.list_project_files(thread["project_id"])
        if pfiles:
            listing = "\n".join(f"- {f['filename']} ({f['content_type']}, {f['file_size']:,} bytes)" for f in pfiles)
            ctx += f"\n\n=== PROJECT ATTACHMENTS ===\nThe user has attached these files to the project. Reference them when relevant:\n{listing}\n"

    # Inject the text of files the user attached to chat messages. These are
    # reference material — the system-prompt note tells the model not to
    # volunteer a full analysis unless the user's message asks for it.
    ctx += _attached_files_context(file_context_parts)

    # Fetch the project row ONCE per turn — the recruiting-context injector and
    # the blog-mode state builder both need it (was two identical queries).
    tc.project_meta = await _fetch_project_meta(thread.get("project_id"))

    # Inject recruiting project context so AI generates posting sections in the right project
    tc.ctx = await _inject_recruiting_project_context(ctx, thread, thread["current_state"], project_meta=tc.project_meta)

    # Node/compliance context is built inside event_stream() so we can yield status events

    def _dispatch_autotitle() -> None:
        # Fire-and-forget; the service re-checks the title itself, so this is
        # harmless even if called from more than one exit path in practice
        # (only one ever runs per request). Never dispatched on a hard-stop
        # refusal — the HR-Pilot hard stop's whole point is "no model call"
        # on that content, and a titler summarizing it into mw_threads.title
        # would leak it into the company-wide Chats list.
        if is_first_exchange and thread["title"].startswith("New Chat"):
            from app.matcha.services.matcha_work import thread_title_service
            _track_background_task(
                asyncio.create_task(thread_title_service.maybe_autotitle_thread(thread_id))
            )

    async def event_stream():
        try:
            async for _evt in _run_hard_stop_gates(tc):
                yield _evt
            if tc.terminated:
                if not tc.hard_stopped:
                    _dispatch_autotitle()
                return

            async for _evt in _run_huume_dispatch(tc):
                yield _evt
            if tc.terminated:
                _dispatch_autotitle()
                return

            # Build mode-specific context with status updates.
            async for _evt in _inject_mode_contexts(tc):
                yield _evt

            async for _evt in _generate_turn(tc):
                yield _evt

            await _audit_and_persist(tc)

            if tc.final_usage:
                yield _sse_data(
                    {
                        "type": "usage",
                        "data": {
                            **tc.final_usage,
                            "stage": "final",
                        },
                    }
                )

            response = SendMessageResponse(
                user_message=_row_to_message(tc.user_msg),
                assistant_message=_row_to_message(tc.assistant_msg),
                current_state=tc.current_state,
                version=tc.current_version,
                task_type=_infer_skill_from_state(tc.current_state, huume_mode=tc.thread.get("huume_mode", False)),
                pdf_url=tc.pdf_url,
                token_usage=tc.final_usage,
            )

            yield _sse_data({"type": "complete", "data": response.model_dump(mode="json")})

            # Trigger compaction in the background if needed
            _track_background_task(asyncio.create_task(_maybe_compact(thread_id, tc.ai_provider, tc.summary_at_count)))
            _dispatch_autotitle()
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
