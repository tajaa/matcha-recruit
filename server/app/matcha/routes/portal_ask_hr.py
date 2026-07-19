"""Employee "Ask HR" — portal Q&A over the company's own handbook + policies.

Mounted at `/v1/portal/ask-hr`, gated `require_feature("ask_hr")`, every endpoint
scoped to the calling employee via `require_employee_record`.

Two things this router is responsible for that the service layer is not:

1. **The hard stop runs here, before any model call.** A harassment / safety /
   leave / termination question is never sent to Gemini at all — it is refused,
   filed into the shared escalation queue, and the company's admins are notified
   content-free. Putting the gate in the service would leave a future caller
   able to reach the model around it.

2. **Ownership.** Session ids come from the client, so every read and write
   re-derives the employee from the token and filters on BOTH `employee_id` and
   `org_id` — one employee must never reach another's Ask HR history, and a
   session must never outlive its tenant.
"""

import asyncio
import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.core.services.redis_cache import check_rate_limit
from app.database import get_connection
from app.matcha.dependencies import require_employee_record
from app.matcha.models.ask_hr import (
    AskHrChatIn,
    AskHrMessageResponse,
    AskHrSessionCreate,
    AskHrSessionResponse,
)
from app.matcha.services import ask_hr as svc

logger = logging.getLogger(__name__)

router = APIRouter()

# Per-employee, per-hour. Each turn is one Gemini call over a large corpus; this
# is a comfort ceiling for a genuine user and a hard stop for a script.
_RATE_LIMIT = 20
_RATE_WINDOW = 3600

_MAX_HISTORY = 40


async def _load_session(conn, session_id: UUID, employee: dict) -> dict:
    row = await conn.fetchrow(
        """SELECT id, title, created_at, updated_at
           FROM ask_hr_sessions
           WHERE id = $1 AND employee_id = $2 AND org_id = $3""",
        session_id, employee["id"], employee["org_id"],
    )
    if not row:
        # 404 rather than 403 — an employee probing ids should not be able to
        # learn that a session exists but belongs to someone else.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return dict(row)


async def _load_messages(conn, session_id: UUID) -> list[dict]:
    """The most recent `_MAX_HISTORY` messages, oldest-first.

    Ordering DESC and reversing is load-bearing: `ORDER BY created_at LIMIT n`
    keeps the OLDEST n, so past the cap the employee's UI would freeze on their
    first 40 messages and the prompt would ground on the start of a conversation
    while ignoring the part being had right now."""
    rows = await conn.fetch(
        """SELECT id, role, content, metadata, created_at
           FROM ask_hr_messages WHERE session_id = $1
           ORDER BY created_at DESC LIMIT $2""",
        session_id, _MAX_HISTORY,
    )
    out = []
    for r in reversed(rows):
        d = dict(r)
        if isinstance(d.get("metadata"), str):
            try:
                d["metadata"] = json.loads(d["metadata"])
            except (json.JSONDecodeError, TypeError):
                d["metadata"] = None
        out.append(d)
    return out


@router.post("/sessions", response_model=AskHrSessionResponse)
async def create_session(body: AskHrSessionCreate, employee=Depends(require_employee_record)):
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """INSERT INTO ask_hr_sessions (org_id, employee_id, title)
               VALUES ($1, $2, $3)
               RETURNING id, title, created_at, updated_at""",
            employee["org_id"], employee["id"], body.title,
        )
    return AskHrSessionResponse(**dict(row))


@router.get("/sessions", response_model=list[AskHrSessionResponse])
async def list_sessions(employee=Depends(require_employee_record)):
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT id, title, created_at, updated_at
               FROM ask_hr_sessions
               WHERE employee_id = $1 AND org_id = $2
               ORDER BY updated_at DESC LIMIT 50""",
            employee["id"], employee["org_id"],
        )
    return [AskHrSessionResponse(**dict(r)) for r in rows]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: UUID, employee=Depends(require_employee_record)):
    """Let an employee clear their own history.

    Messages cascade. Any escalation already filed does NOT — `ask_hr_session_id`
    is ON DELETE SET NULL by design: HR was told a person raised something, and
    deleting the conversation must not retract that."""
    async with get_connection() as conn:
        await _load_session(conn, session_id, employee)
        await conn.execute("DELETE FROM ask_hr_sessions WHERE id = $1", session_id)


@router.get("/sessions/{session_id}/messages", response_model=list[AskHrMessageResponse])
async def list_messages(session_id: UUID, employee=Depends(require_employee_record)):
    async with get_connection() as conn:
        await _load_session(conn, session_id, employee)
        rows = await _load_messages(conn, session_id)
    return [AskHrMessageResponse(**r) for r in rows]


@router.post("/sessions/{session_id}/chat")
async def chat(session_id: UUID, body: AskHrChatIn, employee=Depends(require_employee_record)):
    company_id = employee["org_id"]

    # Pre-work in one connection; release before the long Gemini call.
    async with get_connection() as conn:
        await _load_session(conn, session_id, employee)
        await check_rate_limit(str(employee["id"]), "ask_hr_chat", _RATE_LIMIT, _RATE_WINDOW)
        history = await _load_messages(conn, session_id)
        await conn.execute(
            """INSERT INTO ask_hr_messages (session_id, role, content)
               VALUES ($1, 'user', $2)""",
            session_id, body.message,
        )
        job_title = await conn.fetchval(
            "SELECT job_title FROM employees WHERE id = $1", employee["id"]
        )

    # ---- Hard stop. Before the model, always. --------------------------------
    verdict = svc.should_refuse(body.message)
    if verdict.hard_stop:
        # Everything that MATTERS about a refusal (the record, the escalation,
        # the admin email) is committed HERE, in the request body — not inside
        # the SSE generator. A generator only runs while the client is reading
        # it, so an employee who closes the tab after sending would otherwise
        # get a refusal that promised "I've let your HR team know" while the
        # escalation was never filed. It is all fast and Gemini-free, so there
        # is nothing to gain by deferring it.
        payload = await _handle_hard_stop(verdict, session_id, company_id, body.message)
        return StreamingResponse(
            _replay(payload), media_type="text/event-stream",
            headers={"X-Accel-Buffering": "no"},
        )

    # ---- Grounded answer -----------------------------------------------------
    from app.matcha.services.matcha_work_mode_contexts import get_hr_pilot_corpus
    corpus = await get_hr_pilot_corpus(company_id)
    subject = {**employee, "job_title": job_title}

    async def _persist(payload: dict) -> None:
        async with get_connection() as c2:
            async with c2.transaction():
                await c2.execute(
                    """INSERT INTO ask_hr_messages (session_id, role, content, metadata)
                       VALUES ($1, 'assistant', $2, $3::jsonb)""",
                    session_id, payload.get("assistant_text") or "",
                    json.dumps({
                        "citations": payload.get("citations") or [],
                        "dropped_citations": payload.get("dropped_citations") or [],
                        "open_questions": payload.get("open_questions") or [],
                        "cannot_answer": bool(payload.get("cannot_answer")),
                    }),
                )
                await _touch_session(c2, session_id, body.message)

    async def event_stream():
        payload = None
        try:
            async for ev in svc.run_ask_hr_turn(subject, history, corpus, body.message):
                if ev.get("type") == "result":
                    payload = ev.get("data")
                yield f"data: {json.dumps(ev, default=str)}\n\n"
        except Exception:
            logger.exception("ask_hr: chat stream error for session %s", session_id)
            yield f"data: {json.dumps({'type': 'error', 'message': 'Something went wrong.'})}\n\n"
        # Persist after streaming, shielded — the Gemini tokens are already
        # spent, so a disconnect here must not lose the completed turn.
        if payload:
            try:
                await asyncio.shield(_persist(payload))
            except Exception:
                logger.exception("ask_hr: failed to persist turn for session %s", session_id)
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"}
    )


async def _touch_session(conn, session_id: UUID, first_message: str) -> None:
    """Bump updated_at, and title the session from its first question so the
    employee's list is navigable without storing anything extra."""
    await conn.execute(
        """UPDATE ask_hr_sessions
           SET updated_at = NOW(),
               title = COALESCE(title, LEFT($2, 200))
           WHERE id = $1""",
        session_id, first_message,
    )


async def _handle_hard_stop(verdict, session_id: UUID, company_id, question: str) -> dict:
    """Persist the refusal, file the escalation, notify admins. Returns the
    result payload for the caller to replay over SSE.

    The escalation is filed automatically rather than offered as a choice. These
    four categories are the ones where an employer that knows and does nothing is
    itself the exposure — a consent prompt would let the most serious reports go
    unfiled at exactly the moment a person is least likely to press the button.
    The employee is told plainly that HR was notified (see ask_hr._REFUSAL) so it
    is disclosed, not silent."""
    text = svc.refusal_message(verdict)
    assistant_id = None
    try:
        async with get_connection() as conn:
            async with conn.transaction():
                assistant_id = await conn.fetchval(
                    """INSERT INTO ask_hr_messages (session_id, role, content, metadata)
                       VALUES ($1, 'assistant', $2, $3::jsonb) RETURNING id""",
                    session_id, text,
                    json.dumps({"hard_stop_category": verdict.category}),
                )
                await _touch_session(conn, session_id, question)
    except Exception:
        logger.exception("ask_hr: failed to persist refusal for session %s", session_id)

    # Filing the escalation is the whole point of the refusal — log loudly if it
    # fails, because the employee has already been told HR was notified.
    try:
        from app.matcha.services.escalation_service import (
            create_ask_hr_escalation,
            send_hr_pilot_hard_stop_notifications,
        )
        # First-occurrence only, per session+category — mirrors the supervisor
        # path's dedupe (messaging.py). An upset employee rephrasing the same
        # disclosure four times is one situation, not four; without this it is
        # four queue rows and four emails, which buries the queue and trains
        # admins to ignore it.
        async with get_connection() as conn:
            already_open = await conn.fetchval(
                """SELECT 1 FROM mw_escalated_queries
                   WHERE ask_hr_session_id = $1 AND ai_mode = 'ask_hr_hard_stop'
                     AND title = $2 AND status = 'open'
                   LIMIT 1""",
                session_id, f"Employee Ask HR escalation: {verdict.category or 'policy'}",
            )
        if not already_open:
            await create_ask_hr_escalation(
                company_id=company_id,
                session_id=session_id,
                assistant_message_id=assistant_id,
                category=verdict.category,
                user_query=question,
                notice=verdict.notice or "",
                matched_terms=verdict.matched_terms,
            )
            await send_hr_pilot_hard_stop_notifications(
                company_id=company_id, category=verdict.category, origin="employee",
            )
    except Exception:
        logger.exception(
            "ask_hr: HARD-STOP ESCALATION FAILED for company %s session %s — the "
            "employee was told HR was notified", company_id, session_id,
        )

    return {
        "assistant_text": text,
        "hard_stop": True,
        "hard_stop_category": verdict.category,
        "citations": [],
    }


async def _replay(payload: dict):
    """Stream an already-committed result. Nothing here has side effects, so a
    client that never reads it loses only the display."""
    yield "data: " + json.dumps({
        "type": "status", "message": "Routing this to your HR team…",
    }) + "\n\n"
    yield "data: " + json.dumps({"type": "result", "data": payload}) + "\n\n"
    yield "data: [DONE]\n\n"
