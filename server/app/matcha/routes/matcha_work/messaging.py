"""The core AI-turn messaging surface: send_message_stream (SSE), plus its
RAG-context, compliance-gap-detection, and thread-file-attachment helpers.

The non-streaming POST /threads/{id}/messages handler was DELETED (2026-07-09):
no client called it (web + desktop both stream), and it had drifted from the
streaming handler — it bypassed the per-user token quota, built context from
the caller's company instead of the thread's, and crashed after billing on
payer-mode turns. See MATCHA_WORK_CHAT_AUDIT.md (C2/H1/H2/M5).

Extracted from the original flat matcha_work.py during the package split
(2026-07-03). See matcha_work/CLAUDE.md.
"""
import asyncio
import json
import logging
import os
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.config import get_settings
from app.core.models.auth import CurrentUser
from app.core.services.storage import get_storage
from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.matcha.models.matcha_work import SendMessageRequest, SendMessageResponse
from app.matcha.routes.matcha_work.ai_turn import (
    _apply_ai_updates_and_operations,
    _blog_mode_state_from_meta,
    _fetch_project_meta,
    _inject_recruiting_project_context,
    _inject_slide_context,
    _scope_slide_update,
)
from app.matcha.routes.matcha_work._shared import THREAD_FILE_TEXT_CAP, _row_to_message, _sse_data
from app.matcha.services import matcha_work_document as doc_svc
from app.matcha.services import token_budget_service
from app.matcha.services.escalation_service import should_escalate, create_escalation
from app.core.feature_flags import get_company_features
from app.matcha.services.matcha_work_modes import THREAD_MODES, MODES_BY_KEY
from app.matcha.services.matcha_work_node import build_compliance_context, build_payer_staff_context, ComplianceContextResult
from app.matcha.services.matcha_work_ai import (
    _build_company_context,
    _infer_skill_from_state,
    compact_conversation,
    get_ai_provider,
)
from app.matcha.services.model_pricing import calculate_call_cost

logger = logging.getLogger(__name__)
router = APIRouter()

async def _get_rag_context(content: str, company_id, max_tokens: int = 4000) -> str | None:
    """Fetch compliance RAG context for a user question. Returns None on failure."""
    try:
        from app.core.services.embedding_service import get_embedding_service
        from app.core.services.compliance_rag import ComplianceRAGService

        api_key = os.getenv("GEMINI_API_KEY") or get_settings().gemini_api_key
        if not api_key or not content:
            return None
        crag = ComplianceRAGService(get_embedding_service(api_key))
        async with get_connection() as conn:
            ctx, _ = await crag.get_context_for_question(
                query=content, conn=conn,
                company_id=company_id, max_tokens=max_tokens,
            )
        return ctx or None
    except Exception as e:
        logger.warning("RAG augmentation failed: %s", e)
        return None

# Strong refs to fire-and-forget tasks — the event loop only holds weak
# references, so an un-referenced task can be GC'd mid-flight.
_background_tasks: set = set()


def _track_background_task(task: "asyncio.Task") -> "asyncio.Task":
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


async def _record_turn_usage(
    *,
    thread_id: UUID,
    company_id: UUID,
    user_id: UUID,
    user_role: str,
    final_usage: dict | None,
    operation: str,
) -> dict | None:
    """THE single accounting path for a turn: cost → usage event → role-gated
    deduction. Both the happy path and the cancelled-turn finalizer call this —
    billing logic must not fork (the deleted non-streaming handler drifted from
    the streaming one on exactly this block, which is how turns went unbilled).
    Mutates and returns final_usage with cost_dollars set.
    """
    if not final_usage:
        return None
    cost = calculate_call_cost(
        model=str(final_usage.get("model") or "unknown"),
        prompt_tokens=final_usage.get("prompt_tokens"),
        completion_tokens=final_usage.get("completion_tokens"),
    )
    final_usage["cost_dollars"] = float(cost)
    try:
        await doc_svc.log_token_usage_event(
            company_id=company_id,
            user_id=user_id,
            thread_id=thread_id,
            token_usage=final_usage,
            operation=operation,
            cost_dollars=float(cost),
        )
    except Exception as e:
        logger.warning("Failed to log Matcha Work token usage for thread %s: %s", thread_id, e)
    if user_role != "admin":
        total_tokens = final_usage.get("total_tokens") or 0
        if total_tokens > 0:
            try:
                async with get_connection() as conn:
                    async with conn.transaction():
                        await token_budget_service.deduct_tokens(conn, company_id, total_tokens)
            except Exception as exc:
                logger.warning("Failed to deduct tokens for thread %s: %s", thread_id, exc)
    return final_usage


async def _finalize_cancelled_turn(
    ai_task: "asyncio.Task",
    *,
    thread_id: UUID,
    company_id: UUID,
    user_id: UUID,
    user_role: str,
    estimated_usage: dict | None,
) -> None:
    """Record + deduct usage for a turn whose SSE stream was cancelled.

    The Gemini call runs inside asyncio.to_thread — cancelling the task would
    not stop the underlying HTTP call, so the cost is committed either way.
    Awaiting it yields the REAL usage; fall back to the estimate if the call
    itself failed.
    """
    token_usage = None
    try:
        ai_resp = await ai_task
        token_usage = getattr(ai_resp, "token_usage", None)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.warning("Cancelled-turn AI task failed for thread %s", thread_id, exc_info=True)
    await _record_turn_usage(
        thread_id=thread_id,
        company_id=company_id,
        user_id=user_id,
        user_role=user_role,
        final_usage=token_usage or estimated_usage,
        operation="send_message_cancelled",
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
                try:
                    loc_ids.append(UUID(lid))
                except (ValueError, AttributeError, TypeError):
                    pass  # remote:<ST> pseudo-locations have no location row
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

async def _get_payer_affected_staff(
    company_id: UUID,
    payer_sources: list[dict],
) -> list[dict] | None:
    """Count staff at locations contracted with the payers Gemini actually cited.

    Mirrors _get_affected_employees for payer mode: deterministic counts from
    the roster, keyed off the cited payer_sources rather than model-emitted
    location labels.
    """
    from app.core.services.payer_policy_rag import contract_keys_for_display_names

    cited = sorted({s.get("payer_name") for s in payer_sources if s.get("payer_name")})
    if not cited:
        return None
    keys = contract_keys_for_display_names(cited)
    if not keys:
        return None
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT bl.name, bl.city, bl.state,
                   (SELECT jsonb_agg(p) FROM jsonb_array_elements_text(
                        bl.facility_attributes->'payer_contracts') p
                    WHERE p = ANY($2::text[])) AS matched_payers,
                   COUNT(e.id) AS staff
            FROM business_locations bl
            LEFT JOIN employees e
              ON e.work_location_id = bl.id AND e.termination_date IS NULL
            WHERE bl.company_id = $1 AND bl.is_active = true
              AND bl.facility_attributes->'payer_contracts' ?| $2::text[]
            GROUP BY bl.id, bl.name, bl.city, bl.state, bl.facility_attributes
            HAVING COUNT(e.id) > 0
            """,
            company_id, keys,
        )
    if not rows:
        return None
    from app.core.services.payer_policy_rag import normalize_payer_names
    out = []
    for r in rows:
        matched = r["matched_payers"]
        if isinstance(matched, str):
            try:
                matched = json.loads(matched)
            except (json.JSONDecodeError, TypeError):
                matched = []
        out.append({
            "location": f"{r['name'] or r['city']}, {r['state']}",
            "staff_count": r["staff"],
            "payers": normalize_payer_names(list(matched or [])),
        })
    return out


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
            "SELECT title, LEFT(content, 2000) AS content_head "
            "FROM policies WHERE company_id = $1 AND status = 'active'",
            company_id,
        )
        handbook_sections = await conn.fetch("""
            SELECT hs.title FROM handbook_sections hs
            JOIN handbook_versions hv ON hv.id = hs.handbook_version_id
            JOIN handbooks h ON h.id = hv.handbook_id
            WHERE h.company_id = $1 AND h.status = 'active'
              AND hv.version_number = h.active_version
        """, company_id)

    # Two haystacks with different precision requirements. Single-word
    # keywords ("safety", "wage", "leave") match TITLES ONLY — against 2KB of
    # body text they hit incidental prose in unrelated policies and suppress
    # real gaps. Multi-word phrases ("workplace safety", "paid sick") are
    # specific enough to search the content head too, which is what lets a
    # generically-titled policy whose body covers the category satisfy it.
    title_texts = {
        p["title"].lower() for p in policies if p["title"]
    } | {
        s["title"].lower() for s in handbook_sections if s["title"]
    }
    full_texts = title_texts | {
        f"{p['title']} {p['content_head'] or ''}".lower()
        for p in policies if p["title"]
    }

    gaps = []
    for cat in required_categories:
        keywords = _GAP_KEYWORDS.get(cat, [cat.replace("_", " ")])
        has_match = any(
            any(kw in text for text in (full_texts if " " in kw else title_texts))
            for kw in keywords
        )
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
    thresholds = compliance_result.threshold_status if compliance_result else None
    if not chains and not ai_steps and not thresholds:
        return None
    metadata: dict = {}
    if chains:
        metadata["compliance_reasoning"] = chains
    if thresholds:
        metadata["threshold_status"] = thresholds
    if ai_steps:
        metadata["ai_reasoning_steps"] = ai_steps
    if ai_resp and ai_resp.referenced_categories:
        metadata["referenced_categories"] = ai_resp.referenced_categories
    if ai_resp and ai_resp.referenced_locations:
        metadata["referenced_locations"] = ai_resp.referenced_locations
    return metadata

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

    # Fetch the project row ONCE per turn — the recruiting-context injector and
    # the blog-mode state builder both need it (was two identical queries).
    project_meta = await _fetch_project_meta(thread.get("project_id"))

    # Inject recruiting project context so AI generates posting sections in the right project
    ctx = await _inject_recruiting_project_context(ctx, thread, thread["current_state"], project_meta=project_meta)

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
                    from app.matcha.routes.work.thread_ws import thread_manager
                    _track_background_task(asyncio.create_task(
                        thread_manager.broadcast_new_message(
                            str(thread_id),
                            [_row_to_message(user_msg).model_dump(mode="json"),
                             _row_to_message(assistant_msg).model_dump(mode="json")],
                            exclude_user=current_user.id,
                        )
                    ))
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
            # HR Pilot hard-stop gate — runs BEFORE any context building or
            # model call. Deterministic (hr_pilot_escalation.classify_message),
            # not a model judgment: a supervisor describing a harassment
            # complaint, an injury, a leave/medical situation, or a
            # termination must never get AI-drafted conversational guidance,
            # only "stop, call corporate HR". Re-checks the feature flag the
            # same way the generic mode loop does below — a downgraded
            # company must not keep gating either.
            if thread.get("hr_pilot_mode") and (body.content or "").strip():
                hr_pilot_active = True
                if MODES_BY_KEY["hr_pilot"].required_feature:
                    hr_pilot_features = await get_company_features(company_id)
                    hr_pilot_active = hr_pilot_features.get("hr_pilot", False)
                if hr_pilot_active:
                    from app.matcha.services.hr_pilot_escalation import (
                        classify_message,
                        CORPORATE_HR_ESCALATION_NOTICE,
                    )
                    verdict = classify_message(body.content)
                    if verdict.hard_stop:
                        notice = verdict.notice or CORPORATE_HR_ESCALATION_NOTICE
                        assistant_msg = await doc_svc.add_message(
                            thread_id,
                            "assistant",
                            notice,
                            metadata={
                                "hr_pilot_escalation": {
                                    "category": verdict.category,
                                    "matched_terms": list(verdict.matched_terms),
                                }
                            },
                        )
                        try:
                            from app.matcha.services.escalation_service import create_hr_pilot_escalation
                            await create_hr_pilot_escalation(
                                company_id=company_id,
                                thread_id=thread_id,
                                user_message_id=user_msg["id"],
                                assistant_message_id=assistant_msg["id"],
                                category=verdict.category,
                                user_query=body.content,
                                notice=notice,
                                matched_terms=verdict.matched_terms,
                            )
                        except Exception:
                            logger.warning(
                                "hr_pilot escalation log failed for thread %s", thread_id, exc_info=True
                            )
                        try:
                            from app.matcha.routes.work.thread_ws import thread_manager
                            _track_background_task(asyncio.create_task(
                                thread_manager.broadcast_new_message(
                                    str(thread_id),
                                    [_row_to_message(user_msg).model_dump(mode="json"),
                                     _row_to_message(assistant_msg).model_dump(mode="json")],
                                    exclude_user=current_user.id,
                                )
                            ))
                        except Exception:
                            logger.warning("Thread WS broadcast failed (hr_pilot escalation) for thread %s", thread_id)
                        yield _sse_data({"type": "status", "message": "Routed to corporate HR."})
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
            # Build mode-specific context with status updates. Each block is
            # guarded: a context-builder failure (bad trigger data, DB hiccup)
            # degrades to a status notice instead of killing the SSE stream.
            # Mode/RAG blocks change per turn, so they accumulate in dyn_ctx —
            # NOT ctx, which feeds the cacheable static prompt (H4: putting
            # per-turn context in the static prompt broke the cache every turn).
            dyn_ctx = ""
            # Registry-driven modes (node, benefits, legal, risk, training, …).
            # Compliance and payer are custom_dispatch — their bespoke blocks
            # follow below (reasoning-chain statuses + RAG; prompt-swap path).
            #
            # The toggle route gates on required_feature, but the column stays
            # true if the flag is later revoked — so re-check here too, or a
            # downgraded company keeps getting the paid subsystem injected.
            _active_modes = [
                m for m in THREAD_MODES
                if not m.custom_dispatch and m.build_context is not None and thread.get(m.column)
            ]
            if any(m.required_feature for m in _active_modes):
                _features = await get_company_features(company_id)
                _active_modes = [
                    m for m in _active_modes
                    if not m.required_feature or _features.get(m.required_feature, False)
                ]
            for _mode in _active_modes:
                yield _sse_data({"type": "status", "message": _mode.status_loading})
                try:
                    _mode_ctx = await _mode.build_context(company_id)
                    if _mode_ctx:
                        dyn_ctx += "\n\n" + _mode_ctx
                    else:
                        yield _sse_data({"type": "status", "message": f"No {_mode.label.lower()} data on file yet — continuing without it..."})
                except Exception:
                    logger.exception("%s context failed for company %s", _mode.label, company_id)
                    yield _sse_data({"type": "status", "message": _mode.status_unavailable})

            if thread.get("compliance_mode"):
                yield _sse_data({"type": "status", "message": "Loading compliance data for your locations..."})
                try:
                    compliance_result = await build_compliance_context(company_id)
                    compliance_ctx = compliance_result.context_text
                    # Counts come from the structured reasoning chains, not
                    # substring-matching prose another module formats.
                    _chains = compliance_result.reasoning_chains or []
                    loc_count = len(_chains)
                    cat_count = sum(len(c.get("categories", [])) for c in _chains)
                    trigger_count = sum(
                        1
                        for c in _chains
                        for cat in c.get("categories", [])
                        for lvl in cat.get("all_levels", [])
                        if lvl.get("trigger_condition") is not None
                    )
                    if cat_count > 0:
                        parts = [f"{cat_count} regulatory categories across {loc_count} location{'s' if loc_count != 1 else ''}"]
                        if trigger_count > 0:
                            parts.append(f"{trigger_count} triggered requirement{'s' if trigger_count != 1 else ''}")
                        yield _sse_data({"type": "status", "message": f"Found {' with '.join(parts)} — building reasoning chains..."})
                    elif "legacy format" in compliance_ctx:
                        yield _sse_data({"type": "status", "message": "Loaded compliance data (legacy format) — cross-referencing..."})
                    else:
                        yield _sse_data({"type": "status", "message": "No compliance data found — will suggest running a check..."})
                    dyn_ctx += "\n\n" + compliance_ctx

                    # RAG augmentation — only when the primary dump was
                    # truncated or some location lacks jurisdiction data;
                    # otherwise it re-retrieves what the full dump already
                    # contains (extra embedding hop + vector scan per turn).
                    if compliance_result.truncated or compliance_result.has_legacy_locations:
                        yield _sse_data({"type": "status", "message": "Searching relevant regulations..."})
                        rag_ctx = await _get_rag_context(body.content, company_id)
                        if rag_ctx:
                            dyn_ctx += "\n\n=== RELEVANT REGULATIONS (semantic search) ===\n" + rag_ctx
                except Exception:
                    logger.exception("Compliance context failed for company %s", company_id)
                    compliance_result = None
                    yield _sse_data({"type": "status", "message": "Compliance data unavailable — continuing without it..."})

            # Payer mode — build payer prompt inside stream for status events
            stream_payer_prompt = None
            stream_payer_sources: list[dict] = []
            if thread.get("payer_mode"):
                yield _sse_data({"type": "status", "message": "Searching payer coverage data..."})
                try:
                    import os as _os2
                    from app.core.services.embedding_service import get_embedding_service as _ges2
                    from app.core.services.payer_policy_rag import PayerPolicyRAGService as _PRAG2
                    from app.config import get_settings as _gs2
                    from app.matcha.services.matcha_work_ai import PAYER_MODE_SYSTEM_PROMPT as _PMSP
                    from datetime import date as _d2

                    _ak2 = _os2.getenv("GEMINI_API_KEY") or _gs2().gemini_api_key
                    if _ak2 and body.content:
                        _r2 = _PRAG2(_ges2(_ak2))
                        async with get_connection() as _pc2:
                            _pctx, stream_payer_sources = await _r2.get_context_for_query(
                                query=body.content, conn=_pc2,
                                company_id=company_id, max_tokens=6000,
                            )
                        # Payer turns bypass the generic company context, so the
                        # roster grounding must ride the payer prompt itself.
                        if thread.get("node_mode"):
                            try:
                                _staff_ctx = await build_payer_staff_context(company_id)
                                if _staff_ctx:
                                    _pctx = ((_pctx + "\n\n") if _pctx else "") + _staff_ctx
                            except Exception:
                                logger.warning("Payer-staff context failed for company %s", company_id, exc_info=True)
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

            estimated_usage = await ai_provider.estimate_usage(
                msg_dicts, thread["current_state"], company_context=ctx,
                slide_index=body.slide_index, dynamic_context=dyn_ctx,
                model_override=body.model,
                company_id=str(company_id), user_id=str(current_user.id),
            )
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
            stream_project_meta = project_meta
            stream_blog_mode_state = _blog_mode_state_from_meta(stream_project_meta)
            _ai_task = asyncio.create_task(ai_provider.generate(
                msg_dicts, thread["current_state"], company_context=ctx,
                dynamic_context=dyn_ctx,
                slide_index=body.slide_index, context_summary=context_summary,
                payer_mode_prompt=stream_payer_prompt,
                model_override=body.model,
                company_id=str(company_id),
                user_id=str(current_user.id),
                compliance_mode=bool(thread.get("compliance_mode")),
                payer_mode=bool(thread.get("payer_mode")),
                node_mode=bool(thread.get("node_mode")),
                # Any registry mode with grounded context active → the model
                # should reason over injected records (bumps thinking level).
                # Uses the post-gate list: a mode whose feature was revoked
                # injected nothing, so it must not buy a thinking-level bump.
                grounded_mode=bool(_active_modes),
                blog_mode_state=stream_blog_mode_state,
                thread_id=str(thread_id),
            ))

            def _schedule_cancel_finalizer() -> None:
                # Client disconnected (stop button / tab close). The Gemini call
                # runs in a thread and cannot be interrupted — its cost is
                # already committed — so detach a finalizer that awaits it and
                # records + deducts the real usage. Without this, every "stop"
                # click was a fully-paid, entirely-unbilled turn.
                _track_background_task(asyncio.create_task(_finalize_cancelled_turn(
                    _ai_task,
                    thread_id=thread_id,
                    company_id=company_id,
                    user_id=current_user.id,
                    user_role=current_user.role,
                    estimated_usage=estimated_usage,
                )))

            try:
                while True:
                    done, _ = await asyncio.wait({_ai_task}, timeout=15.0)
                    if done:
                        break
                    yield _sse_data({"type": "keepalive"})
                ai_resp = await _ai_task
            except asyncio.CancelledError:
                _schedule_cancel_finalizer()
                raise
            # The AI cost is committed the moment the model call finishes —
            # a disconnect during apply/persist/PDF-render must still bill the
            # turn, not just a disconnect during generation.
            try:
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

                # Node × payer: staff counts at the locations contracted with the
                # payers this answer actually cited.
                if thread.get("node_mode") and thread.get("payer_mode") and stream_payer_sources:
                    try:
                        payer_staff = await _get_payer_affected_staff(company_id, stream_payer_sources)
                        if payer_staff:
                            if msg_metadata is None:
                                msg_metadata = {}
                            msg_metadata["payer_affected_staff"] = payer_staff
                    except Exception:
                        logger.warning("payer_affected_staff failed for thread %s", thread_id, exc_info=True)

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
                    from app.matcha.routes.work.thread_ws import thread_manager
                    user_msg_dict = _row_to_message(user_msg).model_dump(mode="json")
                    assistant_msg_dict = _row_to_message(assistant_msg).model_dump(mode="json")
                    _track_background_task(asyncio.create_task(
                        thread_manager.broadcast_new_message(
                            str(thread_id), [user_msg_dict, assistant_msg_dict], exclude_user=current_user.id
                        )
                    ))
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

                final_usage = await _record_turn_usage(
                    thread_id=thread_id,
                    company_id=company_id,
                    user_id=current_user.id,
                    user_role=current_user.role,
                    final_usage=ai_resp.token_usage or estimated_usage,
                    operation="send_message",
                )
            except asyncio.CancelledError:
                _schedule_cancel_finalizer()
                raise

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
            _track_background_task(asyncio.create_task(_maybe_compact(thread_id, ai_provider, summary_at_count)))
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
