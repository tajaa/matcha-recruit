"""IR Copilot orchestrator endpoints.

The Copilot is a per-incident chat-style assistant that proposes action
cards (run_analysis, set_field, request_info, escalate, close_incident)
the user can accept inline. Endpoints:

- GET    /{incident_id}/copilot           — transcript fetch
- POST   /{incident_id}/copilot/stream    — guidance round (SSE)
- POST   /{incident_id}/copilot/skip      — persist Skip on a card
- POST   /{incident_id}/copilot/close     — direct close (no card needed)
- POST   /{incident_id}/copilot/accept    — execute a card action (SSE)
"""
import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
from app.matcha.models.ir_incident import (
    IRCopilotAcceptRequest,
    IRCopilotCard,
    IRCopilotMessage,
    IRCopilotStreamRequest,
    IRCopilotTranscript,
)

# Helpers that still live in _legacy.py; will move to _shared.py in step 10.
from ._shared import (
    _get_incident_with_company_check,
    _safe_json_loads,
    _sse,
    log_audit,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ===========================================
# IR Copilot — orchestrator endpoints
# ===========================================


def _coerce_metadata_dict(value):
    """asyncpg returns JSONB as str when no codec is registered."""
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return None


def _serialize_message(row) -> IRCopilotMessage:
    return IRCopilotMessage(
        id=row["id"],
        role=row["role"],
        message_type=row.get("message_type", "text") if isinstance(row, dict) else row["message_type"],
        content=row["content"],
        metadata=_coerce_metadata_dict(row["metadata"]),
        created_by=row["created_by"],
        created_at=row["created_at"],
    )


def _extract_current_cards(messages: list) -> list[IRCopilotCard]:
    """Latest assistant card-set is everything between the last assistant text and now."""
    cards: list[dict] = []
    saw_assistant_text = False
    for m in messages:
        role = m["role"] if isinstance(m, dict) else m.role
        mtype = (m["message_type"] if isinstance(m, dict) else m.message_type) if hasattr(m, 'message_type') or isinstance(m, dict) else "text"
        if role == "assistant" and mtype == "text":
            saw_assistant_text = True
            cards = []  # reset — start fresh after each assistant text
            continue
        if saw_assistant_text and role == "assistant" and mtype == "card":
            md = _coerce_metadata_dict(m["metadata"] if isinstance(m, dict) else m.metadata) or {}
            card = md.get("card")
            if isinstance(card, dict):
                # Only include cards that haven't been accepted, superseded, or skipped.
                if not md.get("accepted") and not md.get("superseded") and not md.get("skipped"):
                    try:
                        cards.append(IRCopilotCard.model_validate(card))
                    except Exception:
                        continue
    return cards


def _extract_summary_and_open_questions(messages: list) -> tuple[Optional[str], list[str]]:
    summary: Optional[str] = None
    open_questions: list[str] = []
    for m in reversed(messages):
        role = m["role"] if isinstance(m, dict) else m.role
        mtype = m["message_type"] if isinstance(m, dict) else m.message_type
        if role == "assistant" and mtype == "text":
            summary = m["content"] if isinstance(m, dict) else m.content
            md = _coerce_metadata_dict(m["metadata"] if isinstance(m, dict) else m.metadata) or {}
            raw_q = md.get("open_questions") or []
            if isinstance(raw_q, list):
                open_questions = [str(q)[:280] for q in raw_q if isinstance(q, str)]
            break
    return summary, open_questions


@router.get("/{incident_id}/copilot", response_model=IRCopilotTranscript)
async def get_copilot_transcript(
    incident_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    """Return the full chat transcript + currently-active cards for an incident."""
    async with get_connection() as conn:
        await _get_incident_with_company_check(conn, incident_id, current_user, columns="id")
        rows = await conn.fetch(
            "SELECT id, role, message_type, content, metadata, created_by, created_at "
            "FROM ir_incident_ai_messages WHERE incident_id = $1 ORDER BY created_at",
            incident_id,
        )

    messages = [_serialize_message(r) for r in rows]
    cards = _extract_current_cards(messages)
    summary, open_questions = _extract_summary_and_open_questions(messages)
    return IRCopilotTranscript(
        incident_id=incident_id,
        messages=messages,
        current_cards=cards,
        summary=summary,
        open_questions=open_questions,
    )


@router.post("/{incident_id}/copilot/stream")
async def stream_copilot_round(
    incident_id: UUID,
    body: IRCopilotStreamRequest,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Run one guidance round. Empty body = cold start. SSE stream of:
      - {type:'status', stage:'thinking'}
      - {type:'summary', text:...}
      - {type:'card', card:...}  (one event per card)
      - {type:'open_question', text:...}
      - {type:'done'}
    Persists user message + assistant text + one row per card.
    """
    from app.matcha.services.ir_ai_orchestrator import (
        generate_guidance,
        load_incident_state,
        persist_assistant_round,
    )

    company_id = await get_client_company_id(current_user)

    async def event_stream():
        # Acquire connection inside generator so it lives for the full stream
        async with get_connection() as conn:
            incident, analyses, messages = await load_incident_state(
                conn, incident_id, company_id
            )
            if incident is None:
                yield _sse({"type": "error", "detail": "Incident not found"})
                return

            yield _sse({"type": "status", "stage": "thinking"})

            # Append the user's message FIRST so the orchestrator includes it.
            user_msg = (body.message or "").strip()
            if user_msg:
                from app.matcha.services.ir_ai_orchestrator import append_message
                user_row = await append_message(
                    conn,
                    incident_id=incident_id,
                    role="user",
                    message_type="text",
                    content=user_msg[:4000],
                    created_by=current_user.id,
                )
                messages.append(user_row)

            try:
                payload = await generate_guidance(
                    incident=incident,
                    analyses=analyses,
                    messages=messages,
                )
            except Exception as exc:
                logger.exception("IR Copilot round failed for incident %s", incident_id)
                yield _sse({"type": "error", "detail": "Failed to generate guidance"})
                return

            # Persist assistant text + cards
            await persist_assistant_round(
                conn,
                incident_id=incident_id,
                user_id=current_user.id,
                user_message=None,  # already inserted above
                guidance_payload=payload,
            )

            yield _sse({"type": "summary", "text": payload.get("summary") or ""})
            for q in payload.get("open_questions") or []:
                yield _sse({"type": "open_question", "text": q})
            for card in payload.get("cards") or []:
                yield _sse({"type": "card", "card": card})
            yield _sse({"type": "done", "model": payload.get("model")})

            await log_audit(
                conn,
                incident_id=str(incident_id),
                user_id=str(current_user.id),
                action="copilot_message",
                entity_type="incident",
                entity_id=str(incident_id),
                details={"cards": len(payload.get("cards") or []), "user_message_len": len(user_msg)},
                ip_address=request.client.host if request.client else None,
            )

    return StreamingResponse(event_stream(), media_type="text/event-stream")


_FIELD_WHITELIST = {
    "category": "incident_type",  # alias — DB col is incident_type
    "incident_type": "incident_type",
    "severity": "severity",
    "status": "status",
    "root_cause": "root_cause",
    "corrective_actions": "corrective_actions",
}

_FIELD_LABELS = {
    "incident_type": "Type",
    "severity": "Severity",
    "status": "Status",
    "root_cause": "Root cause",
    "corrective_actions": "Corrective actions",
}


_VALID_INCIDENT_TYPES = {"safety", "behavioral", "property", "near_miss", "other"}
_VALID_SEVERITIES = {"critical", "high", "medium", "low"}
_VALID_STATUSES = {"reported", "investigating", "action_required", "resolved", "closed"}


def _validate_field_value(field: str, value):
    if field == "incident_type" and value not in _VALID_INCIDENT_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid incident_type: {value}")
    if field == "severity" and value not in _VALID_SEVERITIES:
        raise HTTPException(status_code=400, detail=f"Invalid severity: {value}")
    if field == "status" and value not in _VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {value}")


@router.post("/{incident_id}/copilot/skip")
async def skip_copilot_card(
    incident_id: UUID,
    body: IRCopilotAcceptRequest,
    current_user=Depends(require_admin_or_client),
):
    """Persist a Skip on a copilot card so it doesn't re-surface on refresh
    or in the next round. Same body shape as /copilot/accept (message_id,
    card_id) — accept and skip are sibling actions on the same card row."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        await _get_incident_with_company_check(conn, incident_id, current_user, columns="id")

        row = await conn.fetchrow(
            """
            SELECT id, metadata
            FROM ir_incident_ai_messages
            WHERE id = $1 AND incident_id = $2 AND message_type = 'card'
            """,
            body.message_id, incident_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Card message not found")

        meta = _coerce_metadata_dict(row["metadata"]) or {}
        # Verify card_id matches what's stored — defense in depth.
        stored_card = meta.get("card") or {}
        if isinstance(stored_card, dict) and stored_card.get("id") != body.card_id:
            raise HTTPException(status_code=400, detail="Card id mismatch")

        meta["skipped"] = True
        meta["skipped_at"] = _utc_now_naive().isoformat()

        await conn.execute(
            "UPDATE ir_incident_ai_messages SET metadata = $1::jsonb WHERE id = $2",
            json.dumps(meta), body.message_id,
        )

        await log_audit(
            conn,
            incident_id=str(incident_id),
            user_id=str(current_user.id),
            action="copilot_skip",
            entity_type="incident",
            entity_id=str(incident_id),
            details={"card_id": body.card_id, "message_id": str(body.message_id)},
            ip_address=None,
        )

    _ = company_id  # company access already verified by _get_incident_with_company_check
    return {"ok": True}


async def _close_incident_via_copilot(
    conn,
    *,
    incident_id: UUID,
    source_card_id: Optional[UUID] = None,
) -> dict:
    """Close an incident and supersede any open card recommendations.

    Called from both the card-accept path (with source_card_id set) and the
    direct-button path (source_card_id None — supersede ALL open cards).
    Idempotent: returns ``already_closed=True`` and skips writes when the
    incident is already in 'closed' status.
    """
    prev_status = await conn.fetchval(
        "SELECT status FROM ir_incidents WHERE id = $1", incident_id,
    )
    if prev_status == "closed":
        return {"already_closed": True, "previous_value": prev_status, "new_value": "closed"}

    await conn.execute(
        "UPDATE ir_incidents SET status = 'closed', resolved_at = NOW(), "
        "updated_at = NOW() WHERE id = $1",
        incident_id,
    )
    if source_card_id is not None:
        await conn.execute(
            """
            UPDATE ir_incident_ai_messages
            SET metadata = jsonb_set(
                COALESCE(metadata, '{}'::jsonb),
                '{superseded}', 'true'::jsonb, true
            )
            WHERE incident_id = $1
              AND message_type = 'card'
              AND id != $2
              AND COALESCE((metadata->>'accepted')::boolean, FALSE) = FALSE
              AND COALESCE((metadata->>'superseded')::boolean, FALSE) = FALSE
            """,
            incident_id, source_card_id,
        )
    else:
        await conn.execute(
            """
            UPDATE ir_incident_ai_messages
            SET metadata = jsonb_set(
                COALESCE(metadata, '{}'::jsonb),
                '{superseded}', 'true'::jsonb, true
            )
            WHERE incident_id = $1
              AND message_type = 'card'
              AND COALESCE((metadata->>'accepted')::boolean, FALSE) = FALSE
              AND COALESCE((metadata->>'superseded')::boolean, FALSE) = FALSE
            """,
            incident_id,
        )

    return {
        "already_closed": False,
        "previous_value": prev_status,
        "new_value": "closed",
        "field": "status",
        "field_label": "Status",
    }


@router.post("/{incident_id}/copilot/close")
async def close_incident_via_copilot(
    incident_id: UUID,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Direct close — no card required. Used by the panel's Close button."""
    from app.matcha.services.ir_ai_orchestrator import append_message

    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        await _get_incident_with_company_check(
            conn, incident_id, current_user, columns="id"
        )
        result = await _close_incident_via_copilot(
            conn, incident_id=incident_id, source_card_id=None,
        )
        if result.get("already_closed"):
            _ = company_id
            return {"ok": True, "already_closed": True}

        await append_message(
            conn,
            incident_id=incident_id,
            role="system",
            message_type="event",
            content="Updated Status",
            metadata={
                "action": "close_incident",
                "card_id": None,
                "source": "direct_button",
                "field": "status",
                "field_label": "Status",
                "previous_value": result["previous_value"],
                "new_value": "closed",
                "note": "Closed directly from copilot. Other recommendations cleared.",
            },
            created_by=current_user.id,
        )
        await log_audit(
            conn,
            incident_id=str(incident_id),
            user_id=str(current_user.id),
            action="copilot_close_direct",
            entity_type="incident",
            entity_id=str(incident_id),
            details={"previous_status": result["previous_value"]},
            ip_address=request.client.host if request.client else None,
        )
    _ = company_id
    return {"ok": True, **result}


@router.post("/{incident_id}/copilot/accept")
async def accept_copilot_card(
    incident_id: UUID,
    body: IRCopilotAcceptRequest,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Execute a card action and stream stage progression to the client.

    SSE events:
      - {type:'status', stage:'starting'}
      - {type:'status', stage:'running_analysis', analysis_type:'policy_mapping'}
      - {type:'status', stage:'analysis_complete', analysis_type:...}
      - {type:'event', text:...}              event summary persisted
      - {type:'status', stage:'thinking'}     guidance round starting
      - {type:'summary', text:...}
      - {type:'card', card:...}                one event per card
      - {type:'open_question', text:...}
      - {type:'done'}
      - {type:'error', detail:...}
    """
    from app.matcha.services.ir_ai_orchestrator import (
        _canonical_analysis_type,
        append_message,
        generate_guidance,
        load_incident_state,
        persist_assistant_round,
    )

    company_id = await get_client_company_id(current_user)

    async def event_stream():
        async with get_connection() as conn:
            incident, analyses, messages = await load_incident_state(
                conn, incident_id, company_id
            )
            if incident is None:
                yield _sse({"type": "error", "detail": "Incident not found"})
                return

            card_row = await conn.fetchrow(
                "SELECT id, metadata FROM ir_incident_ai_messages "
                "WHERE id = $1 AND incident_id = $2 AND message_type = 'card'",
                body.message_id, incident_id,
            )
            if not card_row:
                yield _sse({"type": "error", "detail": "Card not found"})
                return

            md = _coerce_metadata_dict(card_row["metadata"]) or {}
            card = md.get("card") or {}
            if card.get("id") != body.card_id:
                yield _sse({"type": "error", "detail": "Card id mismatch"})
                return
            if md.get("accepted"):
                yield _sse({"type": "error", "detail": "Card already accepted"})
                return

            action = card.get("action") or {}
            action_type = action.get("type")
            event_summary = ""
            event_extra: dict = {}

            yield _sse({"type": "status", "stage": "starting", "action_type": action_type})

            try:
                if action_type == "set_field":
                    raw_field = (action.get("field_name") or "").strip()
                    new_value = action.get("field_value")
                    if raw_field not in _FIELD_WHITELIST:
                        yield _sse({"type": "error", "detail": "Field not editable via copilot"})
                        return
                    db_field = _FIELD_WHITELIST[raw_field]
                    try:
                        _validate_field_value(db_field, new_value)
                    except HTTPException as exc:
                        yield _sse({"type": "error", "detail": exc.detail})
                        return
                    prev = await conn.fetchval(
                        f"SELECT {db_field} FROM ir_incidents WHERE id = $1", incident_id,
                    )
                    await conn.execute(
                        f"UPDATE ir_incidents SET {db_field} = $1, updated_at = NOW() WHERE id = $2",
                        new_value, incident_id,
                    )
                    field_label = _FIELD_LABELS.get(db_field, db_field.replace("_", " ").title())
                    event_summary = f"Updated {field_label}"
                    event_extra = {
                        "field": db_field,
                        "field_label": field_label,
                        "previous_value": prev,
                        "new_value": new_value,
                    }

                elif action_type == "run_analysis":
                    analysis_type = _canonical_analysis_type(action.get("analysis_type"))
                    if analysis_type is None:
                        # Stale card from before the orchestrator filter landed.
                        # Surface as ephemeral SSE error — no DB event row, so the
                        # transcript stays clean instead of accumulating noise.
                        yield _sse({
                            "type": "error",
                            "detail": "Couldn't determine which analysis to run. Open the AI Analysis tab and pick one manually.",
                        })
                        return
                    if analysis_type == "policy_mapping":
                        yield _sse({
                            "type": "status",
                            "stage": "running_analysis",
                            "analysis_type": "policy_mapping",
                            "label": "Reading active handbook + policies, running policy mapping…",
                        })
                        try:
                            from .ai_analysis import _auto_map_policy_violations
                            await _auto_map_policy_violations(str(incident_id), str(incident["company_id"]))
                            yield _sse({
                                "type": "status",
                                "stage": "analysis_complete",
                                "analysis_type": "policy_mapping",
                            })
                            event_summary = "Policy mapping complete (uses active handbook + policies)."
                        except Exception as exc:
                            logger.exception("policy_mapping failed for incident %s", incident_id)
                            event_summary = f"Policy mapping failed: {exc}"
                    elif analysis_type == "root_cause":
                        yield _sse({
                            "type": "status",
                            "stage": "running_analysis",
                            "analysis_type": "root_cause",
                            "label": "Running root cause analysis…",
                        })
                        try:
                            from .ai_analysis import run_root_cause_inline
                            await run_root_cause_inline(
                                incident_id,
                                current_user,
                                ip_address=request.client.host if request.client else None,
                            )
                            yield _sse({
                                "type": "status",
                                "stage": "analysis_complete",
                                "analysis_type": "root_cause",
                            })
                            event_summary = "Root cause analysis complete. Open the AI Analysis tab to review."
                        except Exception as exc:
                            logger.exception("root_cause analysis failed for incident %s", incident_id)
                            event_summary = f"Root cause analysis failed: {exc}"
                    else:
                        event_summary = (
                            f"Open the AI Analysis tab and click Run on '{analysis_type.replace('_', ' ').title()}'."
                        )

                elif action_type == "escalate":
                    existing_er = await conn.fetchval(
                        "SELECT er_case_id FROM ir_incidents WHERE id = $1", incident_id,
                    )
                    if existing_er:
                        event_summary = f"Already linked to ER case {existing_er}"
                    else:
                        event_summary = "Marked for ER escalation — open ER Copilot to create the case."

                elif action_type == "close_incident":
                    close_result = await _close_incident_via_copilot(
                        conn,
                        incident_id=incident_id,
                        source_card_id=card_row["id"],
                    )
                    event_summary = "Updated Status"
                    event_extra = {
                        "field": "status",
                        "field_label": "Status",
                        "previous_value": close_result["previous_value"],
                        "new_value": "closed",
                        "note": "Other recommendations cleared.",
                    }

                elif action_type == "request_info":
                    event_summary = "Request acknowledged — answer in chat below."

                else:
                    yield _sse({"type": "error", "detail": f"Unknown action type: {action_type}"})
                    return

                # Mark the card accepted
                new_md = dict(md)
                new_md["accepted"] = True
                new_md["accepted_at"] = datetime.now(timezone.utc).isoformat()
                new_md["accepted_by"] = str(current_user.id)
                await conn.execute(
                    "UPDATE ir_incident_ai_messages SET metadata = $1::jsonb WHERE id = $2",
                    json.dumps(new_md), card_row["id"],
                )

                event_metadata = {"action": action_type, "card_id": body.card_id, **event_extra}
                await append_message(
                    conn,
                    incident_id=incident_id,
                    role="system",
                    message_type="event",
                    content=event_summary,
                    metadata=event_metadata,
                    created_by=current_user.id,
                )
                yield _sse({"type": "event", "text": event_summary, **event_extra, "action": action_type})

                await log_audit(
                    conn,
                    incident_id=str(incident_id),
                    user_id=str(current_user.id),
                    action="copilot_card_accepted",
                    entity_type="incident",
                    entity_id=str(incident_id),
                    details={"card_id": body.card_id, "action_type": action_type},
                    ip_address=request.client.host if request.client else None,
                )

                # Re-run guidance with fresh state
                yield _sse({"type": "status", "stage": "thinking"})
                incident, analyses, messages = await load_incident_state(
                    conn, incident_id, company_id
                )
                try:
                    payload = await generate_guidance(
                        incident=incident, analyses=analyses, messages=messages,
                    )
                except Exception:
                    logger.exception("Follow-up guidance failed after accept")
                    payload = {"summary": event_summary, "open_questions": [], "cards": []}

                await persist_assistant_round(
                    conn,
                    incident_id=incident_id,
                    user_id=current_user.id,
                    user_message=None,
                    guidance_payload=payload,
                )

                yield _sse({"type": "summary", "text": payload.get("summary") or ""})
                for q in payload.get("open_questions") or []:
                    yield _sse({"type": "open_question", "text": q})
                for new_card in payload.get("cards") or []:
                    yield _sse({"type": "card", "card": new_card})
                yield _sse({"type": "done", "model": payload.get("model")})
            except Exception:
                logger.exception("copilot accept failed for incident %s", incident_id)
                yield _sse({"type": "error", "detail": "Action failed — see server logs"})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
