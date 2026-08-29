"""The AI-turn pipeline: TurnContext + the named stages send_message_stream
runs in order (quota gate -> attachments -> hard-stop gates -> huume dispatch
-> mode-context injection -> generation -> audit/persist), plus their
RAG-context, compliance-gap-detection, and thread-file-attachment helpers.

Moved from routes/matcha_work/messaging.py (refactor round 2, stage 5) — the
route handler itself (send_message_stream) stays there and calls into this
module by name.
"""
import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from uuid import UUID

from fastapi import HTTPException

from app.config import get_settings
from app.core.models.auth import CurrentUser
from app.core.services.rate_limiter import RateLimitExceeded
from app.core.services.storage import get_storage
from app.database import get_connection
from app.matcha.models.matcha_work.matcha_work import SendMessageRequest, SendMessageResponse
from app.matcha.services.matcha_work.ai_apply import (
    _apply_ai_updates_and_operations,
    _blog_mode_state_from_meta,
    _scope_slide_update,
)
# Pure/stateless (SSE formatting, row->response mapping, a byte cap) with zero
# routes-specific coupling. They used to live in routes/matcha_work/_shared.py,
# which made this a services->routes import at module scope; they now live in a
# services leaf and _shared.py re-exports them for the route submodules
# (recruiting.py, research_tasks.py, thread_uploads.py, threads.py) that use them.
from app.matcha.services.matcha_work.message_shapes import (
    THREAD_FILE_TEXT_CAP,
    _row_to_message,
    _sse_data,
)
from app.matcha.services.matcha_work import matcha_work_document as doc_svc
from app.matcha.services.billing import token_budget_service
from app.matcha.services.matcha_work.escalation_service import should_escalate, create_escalation
from app.core.feature_flags import get_company_features
from app.matcha.services.matcha_work.matcha_work_modes import THREAD_MODES, MODES_BY_KEY
from app.matcha.services.matcha_work.matcha_work_node import build_compliance_context, build_payer_staff_context, ComplianceContextResult
from app.matcha.services.matcha_work.matcha_work_ai import (
    _infer_skill_from_state,
    compact_conversation,
)
from app.matcha.services.matcha_work.work_permissions import (
    WorkAccess,
    resolve_work_access,
)
from app.matcha.services.huume.scope import (
    HuumeSurfaceContext,
    SCHEDULE_LOOKUP_TOPICS,
    SCHEDULE_TOOLS,
)
from app.matcha.services.scheduling.schedule_assistant_session import (
    ScheduleAssistantScope,
    resolve_schedule_assistant_scope,
)
from app.matcha.services.billing.model_pricing import calculate_call_cost

logger = logging.getLogger(__name__)

# Per-company Huume turn cap — shared with GET /matcha-work/usage/meter
# (routes/matcha_work/workspace.py) so the meter can never drift from the
# gate. History: 60 -> 120/hr, see the check_rate_limit call site below.
HUUME_TURN_LIMIT = 120
HUUME_TURN_WINDOW_SECONDS = 3600


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
        # Only the huume loop records this key today; skill-engine turns
        # carry no thinking_tokens and price exactly as before.
        thinking_tokens=final_usage.get("thinking_tokens"),
        cached_tokens=final_usage.get("cached_tokens"),
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
    from app.matcha.services.er.er_document_parser import ERDocumentParser
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

@dataclass
class TurnContext:
    """Mutable state threaded through the send_message_stream stages.

    The stages below are a mechanical decomposition of one very long handler —
    each reads the fields its predecessor set and writes its own. Nothing here
    is a new abstraction boundary; it exists so the SSE-emitting phases can be
    read (and later extended into a tool loop) independently.
    """
    # Request / thread identity
    thread_id: UUID
    body: SendMessageRequest
    current_user: CurrentUser
    thread: dict
    company_id: UUID
    work_access: WorkAccess | None = None
    # Resolved BEFORE the StreamingResponse starts (messaging.py) when the
    # thread is a schedule_assistant surface, so an authorization failure is
    # a real 403/404 the client can see, not swallowed into a generic
    # mid-stream error after headers are already sent. See _run_huume_dispatch.
    schedule_scope: "ScheduleAssistantScope | None" = None

    # Prompt inputs
    profile: dict | None = None
    ai_provider: object = None
    ctx: str = ""
    dyn_ctx: str = ""
    msg_dicts: list = field(default_factory=list)
    file_context_parts: list = field(default_factory=list)
    context_summary: str | None = None
    summary_at_count: int | None = None
    project_meta: dict | None = None

    # Attachments
    is_file_only: bool = False
    user_msg: dict | None = None

    # Mode context
    compliance_result: "ComplianceContextResult | None" = None
    stream_payer_prompt: str | None = None
    stream_payer_sources: list = field(default_factory=list)
    active_modes: list = field(default_factory=list)
    hr_pilot_mode_active: bool = False

    # Generation
    estimated_usage: dict | None = None
    ai_task: "asyncio.Task | None" = None
    ai_resp: object = None
    generate_started_at: float = 0.0
    # Single-fire guard for _schedule_cancel_finalizer. Running the finalizer
    # twice would record + deduct the same turn's usage twice (double-billing),
    # and there are now three call sites (two CancelledError handlers + the
    # generator-teardown finally). Flipped synchronously, on the single-
    # threaded event loop, before the task is created — so no interleaving can
    # observe it False twice.
    cancel_finalized: bool = False

    # Persistence results
    assistant_msg: dict | None = None
    current_state: dict | None = None
    current_version: int | None = None
    pdf_url: str | None = None
    final_usage: dict | None = None

    # Set by a stage that has already emitted its own terminal `complete`
    # event — the outer stream returns immediately without generating.
    terminated: bool = False

    # Set only when termination was the HR-Pilot hard-stop refusal
    # (classify_message returned verdict.hard_stop). Distinct from the other
    # `terminated` sites (file-only guard, Huume rate-limit/completion) so
    # callers can withhold model calls — e.g. autotitle — from a message the
    # hard stop deliberately kept out of the AI path.
    hard_stopped: bool = False


async def _run_quota_gate(company_id: UUID, current_user: CurrentUser) -> None:
    """Token-budget + per-user quota checks. Raises HTTPException BEFORE the
    StreamingResponse is constructed, so failures surface as a real status code
    (429 with structured detail) rather than an SSE error frame.

    Headroom contract: this gate is the ONLY tenant-side quota decision for
    a turn, and it runs at turn START only. `allowed` is `used < limit`, so
    a turn that starts at limit-1 runs to completion on overdraft —
    `token_budget_service.deduct_tokens` clamps the balance to zero rather
    than raising, and nothing re-checks mid-turn. Do not "fix" this into a
    mid-turn check: killing an agent turn partway strands half-executed
    tool writes with no user-visible result. The only thing allowed to stop
    a turn mid-flight is the platform-wide GeminiRateLimiter (see
    huume/agent.py's RateLimitExceeded handling), and even that force-
    finishes rather than discarding partial work once a call has run."""
    if current_user.role != "admin":
        await token_budget_service.check_token_budget(company_id)

    # Check token quota. Structured detail so the Werk client can tell a
    # free-taste exhaustion apart from a generic error and raise the paywall.
    quota = await doc_svc.check_token_quota(current_user.id, company_id)
    if not quota["allowed"]:
        from app.matcha.services.billing import entitlements_service

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


async def _prepare_attachments(tc: TurnContext) -> None:
    """Normalize + persist chat attachments onto the user message, extract
    thread-file text, and save the user message itself."""
    body = tc.body
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
    tc.is_file_only = bool(file_atts) and not (body.content or "").strip()

    # Save user message before streaming
    tc.user_msg = await doc_svc.add_message(tc.thread_id, "user", body.content, metadata=user_meta)

    # Once the attachments are persisted on the message itself, clear them from
    # thread state so they don't leak into the next send or get re-consumed by
    # the presentation skill.
    if attach_urls:
        try:
            await doc_svc.apply_update(tc.thread_id, {"images": []}, diff_summary="Consumed inline chat attachments")
        except Exception:
            logger.warning("Failed to clear thread images after attaching to message %s", tc.thread_id, exc_info=True)
        # apply_update persists to the DB but the in-memory `thread` dict we
        # fetched earlier still holds the old image URLs. Mirror the clear
        # locally so the complete event returns current_state.images == []
        # and the client doesn't re-render the attachments in the text box.
        if isinstance(tc.thread.get("current_state"), dict):
            tc.thread["current_state"]["images"] = []


def _attached_files_context(file_context_parts: list[str]) -> str:
    """The `=== ATTACHED FILES ===` block appended to the static company context.

    Second half of attachment handling: the text extracted by
    _build_thread_file_attachment_meta is read back off message metadata (so it
    survives follow-up turns) and rendered here."""
    if not file_context_parts:
        return ""
    joined = "\n\n".join(file_context_parts)
    return (
        "\n\n=== ATTACHED FILES ===\n"
        "The user attached the following file(s). Use their content only as "
        "the user's message directs — do not produce an unprompted full "
        "summary or analysis.\n\n" + joined + "\n"
    )


async def _run_hard_stop_gates(tc: TurnContext):
    """Deterministic pre-model gates that can end the turn outright.

    Two of them, both emitting their own terminal `complete` event and setting
    tc.terminated:
      1. file-only send → canned "what do you want?" reply, no model call.
      2. HR Pilot hard stop → refusal + routing to corporate HR.
    """
    thread_id = tc.thread_id
    thread = tc.thread
    body = tc.body
    company_id = tc.company_id
    current_user = tc.current_user
    user_msg = tc.user_msg

    # File-only send → ask for intent instead of auto-analyzing. The
    # file is already persisted with extracted text, so the user's next
    # message has full context. No model call (deterministic + free).
    if tc.is_file_only:
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
            task_type=_infer_skill_from_state(thread["current_state"], huume_mode=thread.get("huume_mode", False)),
            pdf_url=None,
            token_usage=None,
        )
        yield _sse_data({"type": "complete", "data": guard_response.model_dump(mode="json")})
        tc.terminated = True
        return
    # HR Pilot hard-stop gate — runs BEFORE any context building or
    # model call. Deterministic (hr_pilot_escalation.classify_message),
    # not a model judgment: a supervisor describing a harassment
    # complaint, an injury, a leave/medical situation, or a
    # termination must never get AI-drafted conversational guidance,
    # only "stop, call corporate HR". Re-checks the feature flag the
    # same way the generic mode loop in _inject_mode_contexts does — a
    # downgraded company must not keep gating either.
    if thread.get("hr_pilot_mode") and (body.content or "").strip():
        hr_pilot_active = True
        hr_pilot_features: dict = {}
        if MODES_BY_KEY["hr_pilot"].required_feature:
            hr_pilot_features = await get_company_features(company_id)
            hr_pilot_active = hr_pilot_features.get("hr_pilot", False)
        if hr_pilot_active:
            from app.matcha.services.pilots.hr_pilot_escalation import (
                classify_message,
                CORPORATE_HR_ESCALATION_NOTICE,
            )
            verdict = classify_message(body.content)
            if verdict.hard_stop:
                from app.matcha.services.pilots.hr_pilot_actions import should_stage_handoff
                _feats = hr_pilot_features if isinstance(hr_pilot_features, dict) else {}
                existing_action = (thread.get("current_state") or {}).get("hr_action")
                handoff_type = should_stage_handoff(existing_action, verdict.category, _feats)
                handoff_already_staged = (
                    isinstance(existing_action, dict)
                    and existing_action.get("type") in ("ir_report", "er_case")
                    and existing_action.get("status") == "proposed"
                )

                base_notice = verdict.notice or CORPORATE_HR_ESCALATION_NOTICE
                if handoff_type == "ir_report":
                    notice = base_notice + (
                        " If you'd like, I can log this as a formal incident report from your "
                        "description so it's on record — reply \"confirm\" to file it, or \"cancel\" to skip."
                    )
                elif handoff_type == "er_case":
                    notice = base_notice + (
                        " If you'd like, I can open a confidential HR case from your description so "
                        "it's formally on record — reply \"confirm\" to file it, or \"cancel\" to skip."
                    )
                elif handoff_already_staged:
                    notice = base_notice + (
                        " You already have a report staged from your earlier description — reply just "
                        "\"confirm\" to file it, or \"cancel\" to discard it."
                    )
                else:
                    notice = base_notice

                _msg_meta = {
                    "hr_pilot_escalation": {
                        "category": verdict.category,
                        "matched_terms": list(verdict.matched_terms),
                    }
                }
                if handoff_type:
                    _msg_meta["hr_pilot_handoff"] = {"type": handoff_type, "category": verdict.category}
                assistant_msg = await doc_svc.add_message(
                    thread_id, "assistant", notice, metadata=_msg_meta,
                )

                # Dedupe the admin email: notify only on the FIRST open
                # escalation for this thread+category (before inserting this one).
                _esc_title = f"HR Pilot escalation: {verdict.category or 'policy'}"
                _notify_admins = False
                try:
                    async with get_connection() as _dedupe_conn:
                        _prior = await _dedupe_conn.fetchval(
                            """SELECT COUNT(*) FROM mw_escalated_queries
                               WHERE company_id = $1 AND thread_id = $2
                                 AND ai_mode = 'hr_pilot_hard_stop' AND title = $3
                                 AND status IN ('open','in_review')""",
                            company_id, thread_id, _esc_title,
                        )
                    _notify_admins = (_prior or 0) == 0
                except Exception:
                    logger.warning("hr_pilot notify dedupe check failed for thread %s", thread_id)

                escalation_row = None
                try:
                    from app.matcha.services.matcha_work.escalation_service import create_hr_pilot_escalation
                    escalation_row = await create_hr_pilot_escalation(
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

                # Stage the warm hand-off — server-authored, carries the
                # supervisor's real narrative + the source marker the
                # executor requires. Only the server can mint these.
                stage_state = thread["current_state"]
                stage_version = thread["version"]
                if handoff_type:
                    try:
                        staged = {
                            "type": handoff_type,
                            "status": "proposed",
                            "source": "hard_stop_handoff",
                            "narrative": body.content,
                            "category": verdict.category,
                            "escalation_id": str(escalation_row["id"]) if escalation_row else None,
                            "thread_id": str(thread_id),
                        }
                        _sres = await doc_svc.apply_update(thread_id, {"hr_action": staged})
                        stage_state = _sres["current_state"]
                        stage_version = _sres["version"]
                    except Exception:
                        logger.warning("hr_pilot hand-off staging failed for thread %s", thread_id, exc_info=True)

                if _notify_admins:
                    try:
                        from app.matcha.services.matcha_work.escalation_service import send_hr_pilot_hard_stop_notifications
                        _track_background_task(asyncio.create_task(
                            send_hr_pilot_hard_stop_notifications(
                                company_id=company_id,
                                category=verdict.category,
                                thread_id=thread_id,
                                thread_title=thread.get("title"),
                            )
                        ))
                    except Exception:
                        logger.warning("hr_pilot admin notify failed for thread %s", thread_id)

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
                    current_state=stage_state,
                    version=stage_version,
                    task_type=_infer_skill_from_state(stage_state, huume_mode=tc.thread.get("huume_mode", False)),
                    pdf_url=None,
                    token_usage=None,
                )
                yield _sse_data({"type": "complete", "data": guard_response.model_dump(mode="json")})
                tc.terminated = True
                tc.hard_stopped = True
                return


async def _run_huume_dispatch(tc: TurnContext):
    """Huume's turn handler — replaces the rest of the pipeline entirely when
    the thread's `huume_mode` is on, the same way the file-only guard in
    `_run_hard_stop_gates` short-circuits: it emits its own terminal
    `complete` event and sets `tc.terminated = True`.

    Unlike every other thread mode (which only injects a context block —
    see `_inject_mode_contexts`), Huume runs a bounded multi-step Gemini
    tool-calling loop (`services/huume/agent.py`) in place of the normal
    single-shot skill engine for the WHOLE turn — hence `custom_dispatch`
    on its ThreadMode entry and its own dispatch stage here rather than a
    `build_context` callback.
    """
    thread = tc.thread
    thread_id = tc.thread_id
    company_id = tc.company_id
    current_user = tc.current_user

    if not thread.get("huume_mode"):
        return
    if not (tc.body.content or "").strip():
        return

    # The toggle route gates on required_feature, but the column stays true
    # if the flag is later revoked — re-check here, same as every other
    # mode's re-check in _inject_mode_contexts, so a downgraded company
    # falls through to the normal skill engine instead of keeping Huume.
    features = await get_company_features(company_id)
    is_schedule_thread = thread.get("surface") == "schedule_assistant"
    schedule_flag_off = is_schedule_thread and not features.get("employee_schedule")
    if not features.get("huume") or schedule_flag_off:
        if is_schedule_thread:
            # An employee is only admitted to this endpoint (messaging.py)
            # BECAUSE the thread is schedule_assistant. Falling through to
            # the generic skill engine below — the normal behavior for a
            # downgraded non-schedule company, see the comment above — would
            # hand that same employee the full workspace AI the surface
            # exists to deny them.
            #
            # Name the flag that's actually off — a 2026-08-26 incident
            # traced a real prod company to `huume` being disabled while
            # `employee_schedule` was on, and this message blamed scheduling
            # for three days because the two were OR'd into one string.
            message = (
                "Scheduling isn't enabled for this company right now."
                if schedule_flag_off
                else "Huume isn't enabled for this company."
            )
            yield _sse_data({"type": "error", "message": message})
            tc.terminated = True
        return

    from app.matcha.services.huume import agent as huume_agent, store as huume_store

    # Per-company turn cap — GeminiRateLimiter guards the platform's Gemini
    # quota, not a tenant's own usage. A Huume turn costs up to 8 model calls
    # plus whatever the pilot tools spend, and (unlike handbook_pilot_chat's
    # 40/hr) previously had no tenant limit at all. Raised 60->120/hr
    # 2026-07-31: real usage was hitting the cap in normal daily use, not a
    # runaway loop — the original 60/hr hit was `show_record` taking one id
    # per call (fixed by batching, see below), so this raise is headroom for
    # legitimate volume, not a re-opening of that old symptom.
    try:
        from app.core.services.redis_cache import check_rate_limit
        await check_rate_limit(str(company_id), "huume_turn", HUUME_TURN_LIMIT, HUUME_TURN_WINDOW_SECONDS)
    except HTTPException:
        yield _sse_data({"type": "error", "message": "Huume is being used a lot right now — try again in a bit."})
        tc.terminated = True
        return

    yield _sse_data({"type": "status", "message": "Huume is working…"})

    run_id = await huume_store.create_run(
        company_id=company_id, thread_id=thread_id, user_id=current_user.id, trigger="user_turn",
    )

    # `features` was already fetched above for the `huume` flag re-check —
    # reuse it (it's the identical merge `get_thread_features_and_integrations`
    # would otherwise re-fetch) and only pull the integrations half here, so
    # a Huume turn no longer queries `companies` for feature flags twice.
    integrations = await huume_store.get_thread_integrations(company_id)

    # Resolve against the thread's owning company. A shared thread may be
    # opened by a collaborator whose home company is different; that home
    # role must not grant target-company execution privileges.
    #
    # messaging.py already resolved (and re-validated) this scope before the
    # StreamingResponse started, specifically so an authorization failure is
    # a real 403/404 instead of a swallowed mid-stream error. Re-resolve here
    # only as a defense-in-depth backstop in case a future caller reaches
    # this dispatch without going through that route (e.g. a test harness) —
    # tc.schedule_scope is the source of truth when present.
    surface_context = None
    if thread.get("surface") == "schedule_assistant":
        schedule_scope = tc.schedule_scope or await resolve_schedule_assistant_scope(
            thread_id=thread_id,
            company_id=company_id,
            user_id=current_user.id,
            actor_role=current_user.role,
        )
        surface_context = HuumeSurfaceContext(
            surface="schedule_assistant",
            location_id=schedule_scope.location_id,
            week_start=schedule_scope.week_start,
            week_end=schedule_scope.week_end,
            allowed_tools=SCHEDULE_TOOLS,
            allowed_lookup_topics=SCHEDULE_LOOKUP_TOPICS,
        )
    else:
        async with get_connection() as conn:
            tc.work_access = await resolve_work_access(
                conn, user=current_user, company_id=company_id
            )

    current_state = thread.get("current_state") or {}
    final_result: dict | None = None
    run_failed = False
    try:
        async for frame in huume_agent.run_huume_turn(
            thread_id=thread_id, company_id=company_id, user_id=current_user.id,
            user_role=current_user.role, work_access=tc.work_access,
            history=tc.msg_dicts, current_state=current_state,
            company_name=(tc.profile or {}).get("name") or "",
            attachment_texts=tc.file_context_parts,
            features=features, integrations=integrations, run_id=run_id,
            surface_context=surface_context,
        ):
            if frame.get("type") == "huume_result":
                final_result = frame.get("data")
                continue
            if frame.get("type") == "step":
                step = frame.get("data") or {}
                try:
                    await huume_store.add_step(
                        run_id=run_id, seq=step.get("seq", 0), tool=step.get("tool", ""),
                        kind=step.get("kind", "write"), label=step.get("label", ""),
                        status=step.get("status", "error"),
                        args=step.get("args"), result=step.get("result"),
                    )
                except Exception:
                    logger.warning("huume add_step failed for run %s", run_id, exc_info=True)
            yield _sse_data(frame)
    except RateLimitExceeded:
        # agent.py only re-raises this before its first model call (see
        # _rate_limit_disposition) — any mid-loop hit force-finishes there
        # instead and reaches this generator as a normal huume_result frame.
        # A clean, specific message beats the generic crash text below.
        logger.warning("Huume turn refused: platform Gemini capacity limit (thread %s)", thread_id)
        run_failed = True
        yield _sse_data({"type": "error", "message": "AI capacity is maxed out right now — try again in a few minutes."})
    except Exception:
        logger.exception("Huume turn crashed for thread %s", thread_id)
        run_failed = True
        yield _sse_data({"type": "error", "message": "Huume hit a problem mid-turn."})

    if final_result is None:
        final_result = {
            "message": "Huume couldn't complete this turn — nothing was changed.",
            "steps": [], "token_usage": None, "state_updates": {}, "model_calls": 0,
        }

    state_updates = final_result.get("state_updates") or {}
    if state_updates:
        try:
            update_result = await doc_svc.apply_update(thread_id, state_updates, diff_summary="Huume turn")
            tc.current_state = update_result["current_state"]
            tc.current_version = update_result["version"]
        except Exception:
            logger.exception("Huume apply_update failed for thread %s", thread_id)
            tc.current_state = thread.get("current_state")
            tc.current_version = thread.get("version")
    else:
        tc.current_state = thread.get("current_state")
        tc.current_version = thread.get("version")

    # The loop may have written huume_plans (build/execute/cancel, via
    # `store.update_huume_plan`/`execute_plan_locked`) and/or huume_records
    # (show_record, via `store.update_huume_records`) mid-turn rather than
    # through state_updates/apply_update above — re-read so the `complete`
    # frame (and the plan card / record tabs it drives) reflects those
    # writes too.
    try:
        fresh = await doc_svc.get_thread(
            thread_id, company_id, user_id=current_user.id, allow_schedule_surface=True,
        )
        if fresh:
            tc.current_state = fresh.get("current_state")
            tc.current_version = fresh.get("version")
    except Exception:
        logger.warning("Huume post-turn state re-read failed for thread %s", thread_id, exc_info=True)

    assistant_metadata = {"huume_steps": final_result.get("steps") or [], "huume_run_id": str(run_id)}
    # Pilot-tool citation records (Legal/Handbook Pilot skills) — stored under
    # the same metadata keys HR Pilot uses, so MessageBubble's CitationSources
    # renders them with no client changes.
    if final_result.get("citations"):
        assistant_metadata["citations"] = final_result["citations"]
    if final_result.get("dropped_citations"):
        assistant_metadata["dropped_citations"] = final_result["dropped_citations"]
    assistant_msg = await doc_svc.add_message(
        thread_id, "assistant", final_result["message"],
        metadata=assistant_metadata,
    )
    tc.assistant_msg = assistant_msg

    try:
        turn_error = final_result.get("error")
        await huume_store.complete_run(
            run_id=run_id, status="failed" if (run_failed or turn_error) else "completed",
            model_calls=final_result.get("model_calls") or 0, token_usage=final_result.get("token_usage"),
            error=turn_error,
        )
    except Exception:
        logger.warning("huume complete_run failed for run %s", run_id, exc_info=True)

    try:
        from app.matcha.routes.work.thread_ws import thread_manager
        _track_background_task(asyncio.create_task(
            thread_manager.broadcast_new_message(
                str(thread_id),
                [_row_to_message(tc.user_msg).model_dump(mode="json"),
                 _row_to_message(assistant_msg).model_dump(mode="json")],
                exclude_user=current_user.id,
            )
        ))
    except Exception:
        logger.warning("Thread WS broadcast failed (huume) for thread %s", thread_id)

    tc.final_usage = await _record_turn_usage(
        thread_id=thread_id, company_id=company_id, user_id=current_user.id,
        user_role=current_user.role, final_usage=final_result.get("token_usage"),
        operation="huume_turn",
    )
    if tc.final_usage:
        yield _sse_data({"type": "usage", "data": {**tc.final_usage, "stage": "final"}})

    response = SendMessageResponse(
        user_message=_row_to_message(tc.user_msg),
        assistant_message=_row_to_message(assistant_msg),
        current_state=tc.current_state,
        version=tc.current_version,
        task_type=_infer_skill_from_state(tc.current_state, huume_mode=True),
        pdf_url=None,
        token_usage=tc.final_usage,
    )
    yield _sse_data({"type": "complete", "data": response.model_dump(mode="json")})
    tc.terminated = True


async def _inject_mode_contexts(tc: TurnContext):
    """Build every active thread mode's grounding context, emitting a status
    event per mode. Registry-driven loop first, then the two custom_dispatch
    modes (compliance, payer) that keep bespoke blocks.

    Accumulates into tc.dyn_ctx — NOT tc.ctx, which feeds the cacheable static
    prompt (H4: per-turn context in the static prompt broke the cache every
    turn). Each block is guarded: a context-builder failure (bad trigger data,
    DB hiccup) degrades to a status notice instead of killing the SSE stream.
    """
    thread = tc.thread
    company_id = tc.company_id
    body = tc.body

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
    tc.active_modes = _active_modes
    # HR Pilot mode active for this turn (column on + feature present).
    # Gates the model's HR-action vocabulary + server-side execution.
    tc.hr_pilot_mode_active = any(m.key == "hr_pilot" for m in _active_modes)
    for _mode in _active_modes:
        yield _sse_data({"type": "status", "message": _mode.status_loading})
        try:
            _mode_ctx = await _mode.build_context(company_id)
            if _mode_ctx:
                tc.dyn_ctx += "\n\n" + _mode_ctx
            else:
                yield _sse_data({"type": "status", "message": f"No {_mode.label.lower()} data on file yet — continuing without it..."})
        except Exception:
            logger.exception("%s context failed for company %s", _mode.label, company_id)
            yield _sse_data({"type": "status", "message": _mode.status_unavailable})

    if thread.get("compliance_mode"):
        yield _sse_data({"type": "status", "message": "Loading compliance data for your locations..."})
        try:
            tc.compliance_result = await build_compliance_context(company_id)
            compliance_ctx = tc.compliance_result.context_text
            # Counts come from the structured reasoning chains, not
            # substring-matching prose another module formats.
            _chains = tc.compliance_result.reasoning_chains or []
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
            tc.dyn_ctx += "\n\n" + compliance_ctx

            # RAG augmentation — only when the primary dump was
            # truncated or some location lacks jurisdiction data;
            # otherwise it re-retrieves what the full dump already
            # contains (extra embedding hop + vector scan per turn).
            if tc.compliance_result.truncated or tc.compliance_result.has_legacy_locations:
                yield _sse_data({"type": "status", "message": "Searching relevant regulations..."})
                rag_ctx = await _get_rag_context(body.content, company_id)
                if rag_ctx:
                    tc.dyn_ctx += "\n\n=== RELEVANT REGULATIONS (semantic search) ===\n" + rag_ctx
        except Exception:
            logger.exception("Compliance context failed for company %s", company_id)
            tc.compliance_result = None
            yield _sse_data({"type": "status", "message": "Compliance data unavailable — continuing without it..."})

    # Payer mode — build payer prompt inside stream for status events
    if thread.get("payer_mode"):
        yield _sse_data({"type": "status", "message": "Searching payer coverage data..."})
        try:
            import os as _os2
            from app.core.services.embedding_service import get_embedding_service as _ges2
            from app.core.services.payer_policy_rag import PayerPolicyRAGService as _PRAG2
            from app.config import get_settings as _gs2
            from app.matcha.services.matcha_work.matcha_work_ai import PAYER_MODE_SYSTEM_PROMPT as _PMSP
            from datetime import date as _d2

            _ak2 = _os2.getenv("GEMINI_API_KEY") or _gs2().gemini_api_key
            if _ak2 and body.content:
                _r2 = _PRAG2(_ges2(_ak2))
                async with get_connection() as _pc2:
                    _pctx, tc.stream_payer_sources = await _r2.get_context_for_query(
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
                cn2 = tc.profile.get("name", "your company")
                tc.stream_payer_prompt = _PMSP.format(
                    company_name=cn2,
                    today=_d2.today().isoformat(),
                    payer_context=_pctx or "No matching payer policy data found.",
                )
                if tc.stream_payer_sources:
                    yield _sse_data({"type": "status", "message": f"Found {len(tc.stream_payer_sources)} relevant payer policies"})
        except Exception as _pe:
            logger.warning("Stream payer context failed: %s", _pe)


def _schedule_cancel_finalizer(tc: TurnContext) -> None:
    # Client disconnected (stop button / tab close). The Gemini call
    # runs in a thread and cannot be interrupted — its cost is
    # already committed — so detach a finalizer that awaits it and
    # records + deducts the real usage. Without this, every "stop"
    # click was a fully-paid, entirely-unbilled turn.
    #
    # BILLING: this must fire at most once per turn — the finalizer deducts
    # tokens, so a second run double-charges the customer. All three call
    # sites go through this guard rather than scheduling directly.
    if tc.cancel_finalized or tc.ai_task is None:
        return
    tc.cancel_finalized = True
    _track_background_task(asyncio.create_task(_finalize_cancelled_turn(
        tc.ai_task,
        thread_id=tc.thread_id,
        company_id=tc.company_id,
        user_id=tc.current_user.id,
        user_role=tc.current_user.role,
        estimated_usage=tc.estimated_usage,
    )))


async def _generate_turn(tc: TurnContext):
    """Estimate usage, emit the estimate + "Generating response..." events, run
    the model call as a background task, and emit a keepalive every 15 s while
    it runs so proxies with short read-timeouts (e.g. nginx default 60 s) don't
    close the SSE connection. Sets tc.ai_resp."""
    thread = tc.thread
    body = tc.body
    company_id = tc.company_id
    current_user = tc.current_user
    ai_provider = tc.ai_provider

    tc.estimated_usage = await ai_provider.estimate_usage(
        tc.msg_dicts, thread["current_state"], company_context=tc.ctx,
        slide_index=body.slide_index, dynamic_context=tc.dyn_ctx,
        model_override=body.model,
        company_id=str(company_id), user_id=str(current_user.id),
    )
    yield _sse_data(
        {
            "type": "usage",
            "data": {
                **tc.estimated_usage,
                "stage": "estimate",
            },
        }
    )

    yield _sse_data({"type": "status", "message": "Generating response..."})
    import time as _time
    tc.generate_started_at = _time.monotonic()
    stream_blog_mode_state = _blog_mode_state_from_meta(tc.project_meta)
    tc.ai_task = asyncio.create_task(ai_provider.generate(
        tc.msg_dicts, thread["current_state"], company_context=tc.ctx,
        dynamic_context=tc.dyn_ctx,
        slide_index=body.slide_index, context_summary=tc.context_summary,
        payer_mode_prompt=tc.stream_payer_prompt,
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
        grounded_mode=bool(tc.active_modes),
        blog_mode_state=stream_blog_mode_state,
        thread_id=str(tc.thread_id),
        hr_pilot_mode=tc.hr_pilot_mode_active,
    ))

    try:
        while True:
            done, _ = await asyncio.wait({tc.ai_task}, timeout=15.0)
            if done:
                break
            yield _sse_data({"type": "keepalive"})
        tc.ai_resp = await tc.ai_task
    except asyncio.CancelledError:
        _schedule_cancel_finalizer(tc)
        raise
    except GeneratorExit:
        # The other half of the same disconnect: closing the tab tears the
        # generator down by throwing GeneratorExit at the keepalive `yield`,
        # which never reaches the CancelledError handler above. Left unhandled
        # the already-paid Gemini call is never billed and its task orphaned.
        #
        # BILLING: caught here rather than in a bare `finally` on purpose. A
        # `finally` also fires when OUR code raises, which would charge the
        # customer for our bug. Only the two disconnect signals bill.
        if tc.ai_task is not None and not tc.ai_task.done():
            _schedule_cancel_finalizer(tc)
        raise


async def _audit_and_persist(tc: TurnContext) -> None:
    """Everything after the model returns: HR-Pilot citation audit, state
    updates + operations, metadata assembly, message persistence, WS broadcast,
    low-confidence escalation, and the single billing call.

    Emits no SSE events. The AI cost is committed the moment the model call
    finishes — a disconnect during apply/persist/PDF-render must still bill the
    turn, not just a disconnect during generation.
    """
    thread_id = tc.thread_id
    thread = tc.thread
    body = tc.body
    company_id = tc.company_id
    current_user = tc.current_user
    ai_resp = tc.ai_resp
    user_msg = tc.user_msg

    try:
        import time as _time
        logger.info("[TIMING] AI generate took %.2fs for thread %s", _time.monotonic() - tc.generate_started_at, thread_id)
        _scope_slide_update(ai_resp, thread["current_state"], body.slide_index)

        current_version = thread["version"]
        (
            current_state,
            current_version,
            pdf_url,
            changed,
            assistant_reply_text,
            post_events,
        ) = await _apply_ai_updates_and_operations(
            thread_id=thread_id,
            company_id=company_id,
            ai_resp=ai_resp,
            current_state=thread["current_state"],
            current_version=current_version,
            user_message=body.content,
            current_user_id=current_user.id,
            project_id=thread.get("project_id"),
            project_meta=tc.project_meta,
            current_user_role=getattr(current_user, "role", None),
            thread_hr_pilot_mode=tc.hr_pilot_mode_active,
        )

        # HR Pilot citation gate. The corpus rendered into the prompt is
        # the only thing the model may cite; anything else it brackets is
        # invented and is stripped here, BEFORE the reply is persisted or
        # broadcast — so no supervisor ever sees a fabricated source, and
        # a stored message can't carry one either.
        #
        # This is the same corpus the prompt was built from (one cached
        # build — see get_hr_pilot_corpus), so a cache expiry between
        # prompt and gate can't reject every citation wholesale.
        hr_pilot_citations: list[dict] = []
        hr_pilot_dropped: list[str] = []
        if tc.hr_pilot_mode_active and assistant_reply_text:
            try:
                from app.matcha.services.pilots.hr_pilot_corpus import audit_citations
                from app.matcha.services.matcha_work.matcha_work_mode_contexts import (
                    get_hr_pilot_corpus,
                )
                _corpus = await get_hr_pilot_corpus(company_id)
                (
                    assistant_reply_text,
                    hr_pilot_citations,
                    hr_pilot_dropped,
                ) = audit_citations(assistant_reply_text, _corpus.get("index") or {})
                if hr_pilot_dropped:
                    logger.warning(
                        "hr_pilot: dropped %d uncorroborated citation(s) on thread %s: %s",
                        len(hr_pilot_dropped), thread_id, hr_pilot_dropped[:10],
                    )
            except Exception:
                # A failed audit must not swallow the turn — but it must
                # not pass unaudited citations off as audited either, so
                # the reply is emitted with no citation metadata at all.
                logger.exception("hr_pilot citation audit failed for thread %s", thread_id)
                hr_pilot_citations, hr_pilot_dropped = [], []

        # Build metadata from compliance reasoning chains + payer sources
        msg_metadata = _build_compliance_metadata(tc.compliance_result, ai_resp)
        if hr_pilot_citations or hr_pilot_dropped:
            if msg_metadata is None:
                msg_metadata = {}
            if hr_pilot_citations:
                msg_metadata["citations"] = hr_pilot_citations
            if hr_pilot_dropped:
                msg_metadata["dropped_citations"] = hr_pilot_dropped
        if ai_resp and getattr(ai_resp, "attachments", None):
            if msg_metadata is None:
                msg_metadata = {}
            msg_metadata["attachments"] = ai_resp.attachments
        if tc.stream_payer_sources:
            if msg_metadata is None:
                msg_metadata = {}
            msg_metadata["payer_sources"] = tc.stream_payer_sources

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
        if thread.get("node_mode") and thread.get("payer_mode") and tc.stream_payer_sources:
            try:
                payer_staff = await _get_payer_affected_staff(company_id, tc.stream_payer_sources)
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

        # Deferred events from the dispatcher that need the persisted
        # message id (HR Pilot compliance-block escalations — the message
        # id doesn't exist inside _apply_ai_updates_and_operations).
        for _evt in (post_events or []):
            if _evt.get("kind") == "hr_pilot_compliance_block":
                try:
                    from app.matcha.services.matcha_work.escalation_service import (
                        create_hr_pilot_compliance_escalation,
                    )
                    await create_hr_pilot_compliance_escalation(
                        company_id=company_id,
                        thread_id=thread_id,
                        user_message_id=user_msg["id"],
                        assistant_message_id=assistant_msg["id"],
                        user_query=_evt.get("user_query") or body.content,
                        notice=_evt.get("notice") or "",
                        blocks=_evt.get("blocks") or [],
                    )
                except Exception:
                    logger.warning("hr_pilot compliance escalation failed for thread %s", thread_id, exc_info=True)

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

        tc.assistant_msg = assistant_msg
        tc.current_state = current_state
        tc.current_version = current_version
        tc.pdf_url = pdf_url

        tc.final_usage = await _record_turn_usage(
            thread_id=thread_id,
            company_id=company_id,
            user_id=current_user.id,
            user_role=current_user.role,
            final_usage=ai_resp.token_usage or tc.estimated_usage,
            operation="send_message",
        )
    except asyncio.CancelledError:
        _schedule_cancel_finalizer(tc)
        raise
