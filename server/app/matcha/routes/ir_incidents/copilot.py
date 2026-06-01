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
    OSHA_INJURY_TYPES,
    OSHA_INJURY_TYPE_LABELS,
    ROOT_CAUSE_INTERVIEW_STEPS,
    _get_incident_with_company_check,
    _safe_json_loads,
    _sse,
    _utc_now_naive,
    build_log_root_cause_query_card,
    build_osha_days_count_card,
    build_osha_days_type_query_card,
    build_osha_injury_type_query_card,
    build_osha_recordable_query_card,
    build_root_cause_text_card,
    compose_root_cause_text,
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

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


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

        # The OSHA reportable-event alert is non-skippable. The card itself
        # represents a regulatory disclosure obligation; users acknowledge
        # via the accept path with confirmation notes.
        stored_action = (stored_card.get("action") or {}) if isinstance(stored_card, dict) else {}
        if stored_action.get("type") == "osha_emergency_alert":
            raise HTTPException(
                status_code=400,
                detail="The OSHA reporting alert cannot be skipped. Acknowledge with confirmation notes instead.",
            )
        # Root-cause interview steps (text_input) are part of a chain the
        # user already opted into by clicking Yes on log_root_cause_query.
        # Skipping mid-chain leaves the JSONB partially populated; route
        # users back to answering or starting over.
        if (
            stored_action.get("type") == "text_input"
            and stored_action.get("target_field") in ROOT_CAUSE_INTERVIEW_STEPS
        ):
            raise HTTPException(
                status_code=400,
                detail="Finish the root cause interview or type 'no' on a fresh prompt instead.",
            )

        meta["skipped"] = True
        meta["skipped_at"] = _utc_now_naive().isoformat()

        await conn.execute(
            "UPDATE ir_incident_ai_messages SET metadata = $1::jsonb WHERE id = $2",
            json.dumps(meta), body.message_id,
        )

        # Honor the skip in the deterministic flow: record the gate so
        # resolve_next_step stops re-emitting the same card on later rounds.
        from app.matcha.services.ir_flow import gate_key_for_card
        gate = gate_key_for_card(stored_card.get("id") if isinstance(stored_card, dict) else None)
        if gate:
            await conn.execute(
                """
                UPDATE ir_incidents
                SET category_data = jsonb_set(
                    COALESCE(category_data, '{}'::jsonb),
                    '{flow_skipped}',
                    COALESCE(category_data->'flow_skipped', '[]'::jsonb) || to_jsonb($1::text),
                    true
                ),
                updated_at = NOW()
                WHERE id = $2
                  AND NOT (COALESCE(category_data->'flow_skipped', '[]'::jsonb) @> to_jsonb($1::text))
                """,
                gate, incident_id,
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


async def _emit_chain_card(conn, *, incident_id: UUID, card: dict, created_by=None) -> dict:
    """Append a single assistant card row to the transcript and return the inserted row.

    Used by the OSHA recordable chain to drop the next step's card after the
    user accepts the previous one (or after the close-time guard redirects).
    Shape matches what ``persist_assistant_round`` writes for AI-emitted cards.
    """
    from app.matcha.services.ir_ai_orchestrator import append_message

    return await append_message(
        conn,
        incident_id=incident_id,
        role="assistant",
        message_type="card",
        content=card.get("title") or "Recommendation",
        metadata={"card": card, "accepted": False},
        created_by=created_by,
    )


async def _should_emit_osha_recordable_chain(conn, incident_id) -> bool:
    """Pure check (no writes). True when the OSHA recordable chain hasn't
    run yet and the incident is OSHA-flagged via the emergency alert
    keyword scan or severity=critical.

    Used as the gate for the safety-net call sites that emit the
    recordable chain proactively when otherwise the AI fallback would
    suggest "close for documentation only" on a reportable injury.
    """
    row = await conn.fetchrow(
        "SELECT severity, osha_recordable, category_data "
        "FROM ir_incidents WHERE id = $1",
        incident_id,
    )
    if row is None or row["osha_recordable"] is not None:
        return False
    cd = _safe_json_loads(row["category_data"], {}) or {}
    flagged = (
        row["severity"] == "critical"
        or cd.get("osha_emergency_alert_active") in (True, "true")
        or "reported_to_osha_notes" in cd  # alert was acked, flag now false
    )
    if not flagged:
        return False
    if cd.get("osha_recordable_chain_started") is True:
        return False
    # Mirror the dedup at _close_incident_via_copilot:427-440 so a
    # repeat poll while a recordable_query card is already pending
    # doesn't stack identical cards in the transcript.
    existing = await conn.fetchval(
        """
        SELECT 1 FROM ir_incident_ai_messages
        WHERE incident_id = $1
          AND message_type = 'card'
          AND metadata->'card'->>'id' = 'osha_recordable_query'
          AND COALESCE((metadata->>'accepted')::boolean, FALSE) = FALSE
          AND COALESCE((metadata->>'superseded')::boolean, FALSE) = FALSE
          AND COALESCE((metadata->>'skipped')::boolean, FALSE) = FALSE
        LIMIT 1
        """,
        incident_id,
    )
    return existing is None


async def _emit_osha_recordable_chain(conn, *, incident_id, current_user):
    """Insert the osha_recordable_query card, stamp the chain-started
    flag on category_data, and return (card_dict, message_id_str).

    The caller must mark the triggering card accepted (if any) and skip
    the AI guidance round so the deterministic chain doesn't compete
    with an overlapping Gemini suggestion.
    """
    card = build_osha_recordable_query_card()
    inserted = await _emit_chain_card(
        conn,
        incident_id=incident_id,
        card=card,
        created_by=current_user.id if current_user else None,
    )
    await conn.execute(
        """
        UPDATE ir_incidents
        SET category_data = jsonb_set(
            COALESCE(category_data, '{}'::jsonb),
            '{osha_recordable_chain_started}',
            'true'::jsonb,
            true
        ),
            updated_at = NOW()
        WHERE id = $1
        """,
        incident_id,
    )
    return card, str(inserted["id"])


async def _close_incident_via_copilot(
    conn,
    *,
    incident_id: UUID,
    source_card_id: Optional[UUID] = None,
    current_user=None,
) -> dict:
    """Close an incident and supersede any open card recommendations.

    Called from both the card-accept path (with source_card_id set) and the
    direct-button path (source_card_id None — supersede ALL open cards).
    Idempotent: returns ``already_closed=True`` and skips writes when the
    incident is already in 'closed' status.

    Two pre-close guards run first:

    1. **OSHA emergency block** — if ``category_data.osha_emergency_alert_active``
       is true, the reportable-event alert hasn't been acknowledged. Return
       ``{blocked_by_emergency: True}``; callers should surface a 400 to the
       user. They can clear the block by accepting the ``osha_emergency_alert``
       card with confirmation notes.

    2. **OSHA recordable chain redirect** — if ``treatment_beyond_first_aid``
       is true AND ``osha_recordable`` is null, the OSHA 300 capture chain
       hasn't run. Emit the first chain card (``osha_recordable_query``) and
       return ``{redirected_to_osha_chain: True, redirect_card: <inserted row>}``
       without changing status. Callers should NOT mark close successful.

    Returns the normal close result dict when no guard trips.
    """
    row = await conn.fetchrow(
        """
        SELECT status, osha_recordable, category_data, root_cause,
               incident_type, severity
        FROM ir_incidents WHERE id = $1
        """,
        incident_id,
    )
    prev_status = row["status"] if row else None
    if prev_status == "closed":
        return {"already_closed": True, "previous_value": prev_status, "new_value": "closed"}

    category_data = _safe_json_loads(row["category_data"] if row else None, {}) or {}
    if category_data.get("osha_emergency_alert_active"):
        return {
            "blocked_by_emergency": True,
            "previous_value": prev_status,
            "new_value": prev_status,
        }

    # Pre-close root-cause prompt: for safety / near-miss / high-severity
    # incidents, require the user to either log a root cause or
    # explicitly decline before closing. Otherwise the wizard could let a
    # safety incident close with no investigation captured — which the
    # user reported as a regression. Skipped when:
    #   - root_cause is non-empty (already logged)
    #   - category_data.root_cause_declined is true (user said No)
    #   - category_data.root_cause_interview has any keys (mid-interview)
    incident_type_lower = (row["incident_type"] or "").strip().lower() if row else ""
    severity_lower = (row["severity"] or "").strip().lower() if row else ""
    rc_existing = (row["root_cause"] or "").strip() if row else ""
    rc_declined = category_data.get("root_cause_declined") in (True, "true")
    rc_interview = bool(category_data.get("root_cause_interview"))
    needs_root_cause_prompt = (
        not rc_existing
        and not rc_declined
        and not rc_interview
        and (
            incident_type_lower in {"safety", "near_miss"}
            or severity_lower in {"high", "critical"}
        )
    )
    if needs_root_cause_prompt:
        card = build_log_root_cause_query_card()
        # Idempotency: reuse a pending log_root_cause_query if one is
        # already in the transcript (e.g. double-click on Close).
        existing = await conn.fetchrow(
            """
            SELECT id FROM ir_incident_ai_messages
            WHERE incident_id = $1
              AND message_type = 'card'
              AND metadata->'card'->>'id' = $2
              AND COALESCE((metadata->>'accepted')::boolean, FALSE) = FALSE
              AND COALESCE((metadata->>'superseded')::boolean, FALSE) = FALSE
              AND COALESCE((metadata->>'skipped')::boolean, FALSE) = FALSE
            ORDER BY created_at DESC
            LIMIT 1
            """,
            incident_id, card["id"],
        )
        if existing:
            message_id = str(existing["id"])
        else:
            inserted = await _emit_chain_card(
                conn,
                incident_id=incident_id,
                card=card,
                created_by=current_user.id if current_user else None,
            )
            message_id = str(inserted["id"])
        return {
            "redirected_to_root_cause": True,
            "redirect_card": card,
            "redirect_message_id": message_id,
            "previous_value": prev_status,
            "new_value": prev_status,
        }

    treatment_flag = category_data.get("treatment_beyond_first_aid")
    if treatment_flag in (True, "true") and row["osha_recordable"] is None:
        card = build_osha_recordable_query_card()
        # Idempotency: if a prior close attempt already emitted the
        # recordable query and the user hasn't answered or skipped, reuse
        # that row instead of inserting a duplicate (a double-click on the
        # Close button would otherwise stack identical cards in the
        # transcript).
        existing = await conn.fetchrow(
            """
            SELECT id FROM ir_incident_ai_messages
            WHERE incident_id = $1
              AND message_type = 'card'
              AND metadata->'card'->>'id' = $2
              AND COALESCE((metadata->>'accepted')::boolean, FALSE) = FALSE
              AND COALESCE((metadata->>'superseded')::boolean, FALSE) = FALSE
              AND COALESCE((metadata->>'skipped')::boolean, FALSE) = FALSE
            ORDER BY created_at DESC
            LIMIT 1
            """,
            incident_id, card["id"],
        )
        if existing:
            message_id = str(existing["id"])
        else:
            inserted = await _emit_chain_card(
                conn,
                incident_id=incident_id,
                card=card,
                created_by=current_user.id if current_user else None,
            )
            message_id = str(inserted["id"])
        return {
            "redirected_to_osha_chain": True,
            "redirect_card": card,
            "redirect_message_id": message_id,
            "previous_value": prev_status,
            "new_value": prev_status,
        }

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
            current_user=current_user,
        )
        if result.get("already_closed"):
            _ = company_id
            return {"ok": True, "already_closed": True}
        if result.get("blocked_by_emergency"):
            _ = company_id
            raise HTTPException(
                status_code=400,
                detail=(
                    "OSHA reporting alert is unacknowledged. Open the alert "
                    "card in the Copilot, confirm reporting notes, then try "
                    "again."
                ),
            )
        if result.get("redirected_to_osha_chain"):
            _ = company_id
            return {
                "ok": True,
                "redirected_to_osha_chain": True,
                "redirect_card": result["redirect_card"],
                "redirect_message_id": result["redirect_message_id"],
            }
        if result.get("redirected_to_root_cause"):
            _ = company_id
            return {
                "ok": True,
                "redirected_to_root_cause": True,
                "redirect_card": result["redirect_card"],
                "redirect_message_id": result["redirect_message_id"],
            }

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


async def _handle_quick_reply(
    conn,
    *,
    incident_id: UUID,
    action: dict,
    body: IRCopilotAcceptRequest,
    current_user,
) -> dict:
    """Dispatch quick_reply card accepts by ``quick_reply_kind``.

    Returns a dict with optional ``error``, ``event_summary``, ``event_extra``,
    ``next_card`` (raw card dict to surface to the user), and
    ``next_message_id`` (the transcript row id of the inserted card).

    Three kinds handled:
      * ``osha_recordable_query`` — Yes/No → write ``osha_recordable``
      * ``osha_days_type_query`` — Days Away / Restriction / Neither → write
        ``osha_classification`` and dispatch the next card
      * ``osha_injury_type_query`` — 6-option picker → write injury type to
        ``osha_form_301_data->>'injury_type'``
    """
    kind = (action.get("quick_reply_kind") or "").strip()
    selected = (body.selected_value or "").strip().lower()
    if not selected:
        return {"error": "Pick an option to continue."}

    allowed_by_kind = {
        "treatment_query": {"yes", "no"},
        "osha_recordable_query": {"yes", "no"},
        "osha_days_type_query": {"days_away", "restricted_duty", "neither"},
        "osha_injury_type_query": OSHA_INJURY_TYPES,
        "log_root_cause_query": {"yes", "no"},
    }
    if kind not in allowed_by_kind:
        return {"error": f"Unknown quick_reply kind: {kind}"}
    if selected not in allowed_by_kind[kind]:
        return {"error": f"Invalid selection '{selected}' for {kind}"}

    if kind == "treatment_query":
        # Injury-assessment gate. Writes category_data.treatment_beyond_first_aid
        # (same JSONB key the set_field path uses). "Yes" → injury is generally
        # OSHA recordable, so chain straight into the recordable query.
        bool_value = selected == "yes"
        await conn.execute(
            """
            UPDATE ir_incidents
            SET category_data = jsonb_set(
                COALESCE(category_data, '{}'::jsonb),
                '{treatment_beyond_first_aid}',
                $1::jsonb,
                true
            ),
            updated_at = NOW()
            WHERE id = $2
            """,
            "true" if bool_value else "false",
            incident_id,
        )
        event_extra = {
            "field": "treatment_beyond_first_aid",
            "field_label": "Treatment beyond first aid",
            "previous_value": None,
            "new_value": bool_value,
        }
        if bool_value:
            next_card = build_osha_recordable_query_card()
            inserted = await _emit_chain_card(
                conn, incident_id=incident_id, card=next_card, created_by=current_user.id,
            )
            return {
                "event_summary": "Recorded: treatment beyond on-site first aid",
                "event_extra": event_extra,
                "next_card": next_card,
                "next_message_id": str(inserted["id"]),
            }
        return {
            "event_summary": "Recorded: on-site first aid only",
            "event_extra": event_extra,
        }

    if kind == "log_root_cause_query":
        # Skip-if-answered: a non-empty existing root_cause means the user
        # already filled this in (manual edit or prior interview round).
        existing = await conn.fetchval(
            "SELECT NULLIF(TRIM(root_cause), '') FROM ir_incidents WHERE id = $1",
            incident_id,
        )
        if existing:
            return {
                "event_summary": "Root cause already on file — skipping the interview.",
                "event_extra": {},
            }
        if selected == "yes":
            first = build_root_cause_text_card(step="hazard")
            inserted = await _emit_chain_card(
                conn, incident_id=incident_id, card=first, created_by=current_user.id,
            )
            return {
                "event_summary": "Starting root cause interview.",
                "event_extra": {},
                "next_card": first,
                "next_message_id": str(inserted["id"]),
            }
        # No: stamp category_data.root_cause_declined so the next guidance
        # round's safety-net rewrite skips re-prompting. Otherwise the AI
        # sees an empty root_cause and re-emits run_analysis root_cause,
        # which we'd just rewrite back to the same Yes/No card — an
        # infinite loop from the user's perspective.
        await conn.execute(
            """
            UPDATE ir_incidents
            SET category_data = jsonb_set(
                COALESCE(category_data, '{}'::jsonb),
                '{root_cause_declined}',
                'true'::jsonb,
                true
            ),
            updated_at = NOW()
            WHERE id = $1
            """,
            incident_id,
        )
        return {
            "event_summary": "Noted — no root cause logged.",
            "event_extra": {
                "field": "root_cause_declined",
                "field_label": "Root cause",
                "previous_value": None,
                "new_value": "declined",
            },
        }

    if kind == "osha_recordable_query":
        bool_value = selected == "yes"
        await conn.execute(
            "UPDATE ir_incidents SET osha_recordable = $1, updated_at = NOW() WHERE id = $2",
            bool_value, incident_id,
        )
        event_summary = (
            "Marked as OSHA recordable" if bool_value else "Marked as not OSHA recordable"
        )
        event_extra = {
            "field": "osha_recordable",
            "field_label": "OSHA recordable",
            "previous_value": None,
            "new_value": bool_value,
        }
        if bool_value:
            next_card = build_osha_days_type_query_card()
            inserted = await _emit_chain_card(
                conn, incident_id=incident_id, card=next_card, created_by=current_user.id,
            )
            return {
                "event_summary": event_summary,
                "event_extra": event_extra,
                "next_card": next_card,
                "next_message_id": str(inserted["id"]),
            }
        # Not recordable — OSHA capture is done. Hand back to the conversational
        # guidance round (root cause / clarifying questions / closure) instead of
        # jumping straight to a close button. Omitting next_card makes the accept
        # dispatcher run a normal generate_guidance round.
        return {
            "event_summary": event_summary,
            "event_extra": event_extra,
        }

    if kind == "osha_days_type_query":
        if selected == "days_away":
            next_card = build_osha_days_count_card(
                target_field="days_away_from_work",
                pending_classification="days_away",
            )
            inserted = await _emit_chain_card(
                conn, incident_id=incident_id, card=next_card, created_by=current_user.id,
            )
            return {
                "event_summary": "Captured: Days Away",
                "event_extra": {
                    "field": "osha_classification_pending",
                    "field_label": "OSHA case classification",
                    "previous_value": None,
                    "new_value": "days_away",
                },
                "next_card": next_card,
                "next_message_id": str(inserted["id"]),
            }
        if selected == "restricted_duty":
            next_card = build_osha_days_count_card(
                target_field="days_restricted_duty",
                pending_classification="restricted_duty",
            )
            inserted = await _emit_chain_card(
                conn, incident_id=incident_id, card=next_card, created_by=current_user.id,
            )
            return {
                "event_summary": "Captured: Job Restriction",
                "event_extra": {
                    "field": "osha_classification_pending",
                    "field_label": "OSHA case classification",
                    "previous_value": None,
                    "new_value": "restricted_duty",
                },
                "next_card": next_card,
                "next_message_id": str(inserted["id"]),
            }
        # Neither — straight to injury-type picker.
        await conn.execute(
            "UPDATE ir_incidents SET osha_classification = 'medical_treatment', "
            "updated_at = NOW() WHERE id = $1",
            incident_id,
        )
        next_card = build_osha_injury_type_query_card()
        inserted = await _emit_chain_card(
            conn, incident_id=incident_id, card=next_card, created_by=current_user.id,
        )
        return {
            "event_summary": "Captured: Medical treatment only",
            "event_extra": {
                "field": "osha_classification",
                "field_label": "OSHA case classification",
                "previous_value": None,
                "new_value": "medical_treatment",
            },
            "next_card": next_card,
            "next_message_id": str(inserted["id"]),
        }

    # osha_injury_type_query
    await conn.execute(
        """
        UPDATE ir_incidents
        SET osha_form_301_data = jsonb_set(
            COALESCE(osha_form_301_data, '{}'::jsonb),
            '{injury_type}',
            to_jsonb($1::text),
            true
        ),
        updated_at = NOW()
        WHERE id = $2
        """,
        selected, incident_id,
    )
    # OSHA recordable capture complete. Hand back to the conversational guidance
    # round so the copilot moves on to root cause / clarifying questions /
    # closure rather than dead-ending on a close button before those are done.
    # Omitting next_card makes the accept dispatcher run generate_guidance.
    return {
        "event_summary": f"Captured injury type: {OSHA_INJURY_TYPE_LABELS[selected]}",
        "event_extra": {
            "field": "osha_form_301_data.injury_type",
            "field_label": "OSHA injury type",
            "previous_value": None,
            "new_value": selected,
        },
    }


async def _handle_numeric_input(
    conn,
    *,
    incident_id: UUID,
    action: dict,
    body: IRCopilotAcceptRequest,
    current_user,
) -> dict:
    """Validate and persist a numeric_input card.

    Writes ``action.target_field`` (must be days_away_from_work or
    days_restricted_duty) and sets ``osha_classification`` to the carried
    ``pending_classification`` so the 300-log filter picks it up. Emits the
    injury-type picker as the next chain card.
    """
    target = (action.get("target_field") or "").strip()
    pending_classification = (action.get("pending_classification") or "").strip()
    allowed_targets = {"days_away_from_work", "days_restricted_duty"}
    if target not in allowed_targets:
        return {"error": f"Invalid target_field: {target}"}
    if pending_classification not in {"days_away", "restricted_duty"}:
        return {"error": f"Invalid pending_classification: {pending_classification}"}

    if body.numeric_value is None:
        return {"error": "Enter a number of days."}
    days = int(body.numeric_value)
    lo = int(action.get("input_min") or 1)
    hi = int(action.get("input_max") or 365)
    if days < lo or days > hi:
        return {"error": f"Days must be between {lo} and {hi}."}

    await conn.execute(
        f"UPDATE ir_incidents SET {target} = $1, osha_classification = $2, "
        "updated_at = NOW() WHERE id = $3",
        days, pending_classification, incident_id,
    )
    next_card = build_osha_injury_type_query_card()
    inserted = await _emit_chain_card(
        conn, incident_id=incident_id, card=next_card, created_by=current_user.id,
    )
    field_label = "Days away from work" if target == "days_away_from_work" else "Days on job restriction"
    return {
        "event_summary": f"Captured: {field_label} = {days}",
        "event_extra": {
            "field": target,
            "field_label": field_label,
            "previous_value": None,
            "new_value": days,
        },
        "next_card": next_card,
        "next_message_id": str(inserted["id"]),
    }


async def _handle_text_input(
    conn,
    *,
    incident_id: UUID,
    action: dict,
    body: IRCopilotAcceptRequest,
    current_user,
) -> dict:
    """Persist one root-cause interview answer and emit the next chain step.

    ``action.target_field`` carries the step name (hazard / why / prevention).
    Each answer lands in ``ir_incidents.category_data->'root_cause_interview'->>step``
    (JSONB). After the third step we compose all three into the existing
    ``root_cause`` TEXT column so the OSHA 301 printable form, broker readers,
    and the AI Analysis tab see a populated value.
    """
    step = (action.get("target_field") or "").strip()

    # Investigation findings — free-text documentation capture (not part of the
    # root-cause interview chain). Writes category_data.investigation_notes and
    # stamps investigation_documented so the deterministic flow advances.
    if step == "investigation_notes":
        raw = (body.text_value or "").strip()
        if not raw:
            return {"error": "Add your findings before saving (or Skip if there's nothing to add)."}
        notes = raw[:4000]
        await conn.execute(
            """
            UPDATE ir_incidents
            SET category_data = jsonb_set(
                jsonb_set(
                    COALESCE(category_data, '{}'::jsonb),
                    '{investigation_notes}',
                    to_jsonb($1::text),
                    true
                ),
                '{investigation_documented}',
                'true'::jsonb,
                true
            ),
            updated_at = NOW()
            WHERE id = $2
            """,
            notes, incident_id,
        )
        return {
            "event_summary": "Investigation findings documented",
            "event_extra": {
                "field": "investigation_notes",
                "field_label": "Investigation notes",
                "previous_value": None,
                "new_value": notes,
            },
        }

    if step not in ROOT_CAUSE_INTERVIEW_STEPS:
        return {"error": f"Invalid text_input target_field: {step}"}

    raw = body.text_value or ""
    answer = raw.strip()
    if not answer:
        return {"error": "Answer can't be empty. Type your response and Save."}
    if len(answer) > 4000:
        answer = answer[:4000]

    # Postgres jsonb_set does NOT auto-create intermediate object keys —
    # for a fresh incident with category_data='{}', writing the nested
    # path ['root_cause_interview', step] in one call silently returns
    # the original unchanged. Two-step: ensure the parent key exists as
    # an object, then write the leaf.
    await conn.execute(
        """
        UPDATE ir_incidents
        SET category_data = jsonb_set(
            jsonb_set(
                COALESCE(category_data, '{}'::jsonb),
                '{root_cause_interview}',
                COALESCE(category_data->'root_cause_interview', '{}'::jsonb),
                true
            ),
            ARRAY['root_cause_interview', $1],
            to_jsonb($2::text),
            true
        ),
        updated_at = NOW()
        WHERE id = $3
        """,
        step, answer, incident_id,
    )

    step_idx = ROOT_CAUSE_INTERVIEW_STEPS.index(step)
    event_summary = f"Captured root cause — {step}"
    event_extra = {
        "field": f"root_cause_interview.{step}",
        "field_label": f"Root cause · {step}",
        "previous_value": None,
        "new_value": answer,
    }

    if step_idx + 1 < len(ROOT_CAUSE_INTERVIEW_STEPS):
        next_step = ROOT_CAUSE_INTERVIEW_STEPS[step_idx + 1]
        next_card = build_root_cause_text_card(step=next_step)
        inserted = await _emit_chain_card(
            conn, incident_id=incident_id, card=next_card, created_by=current_user.id,
        )
        return {
            "event_summary": event_summary,
            "event_extra": event_extra,
            "next_card": next_card,
            "next_message_id": str(inserted["id"]),
        }

    # Final step — compose the combined text and write to root_cause column.
    # If the incident is OSHA-flagged (severity=critical or emergency-alert
    # markers in category_data) and the recordable chain hasn't started,
    # emit osha_recordable_query as next_card so the deterministic chain
    # takes over from here. Otherwise leave next_card unset so the
    # post-dispatch flow runs a normal AI guidance round.
    row = await conn.fetchrow(
        "SELECT category_data FROM ir_incidents WHERE id = $1",
        incident_id,
    )
    cd = _safe_json_loads(row["category_data"] if row else None, {}) or {}
    interview = cd.get("root_cause_interview") or {}
    combined = compose_root_cause_text(interview)
    await conn.execute(
        "UPDATE ir_incidents SET root_cause = $1, updated_at = NOW() WHERE id = $2",
        combined, incident_id,
    )
    event_extra = {
        "field": "root_cause",
        "field_label": "Root cause",
        "previous_value": None,
        "new_value": combined,
    }
    if await _should_emit_osha_recordable_chain(conn, incident_id):
        chain_card, chain_message_id = await _emit_osha_recordable_chain(
            conn, incident_id=incident_id, current_user=current_user,
        )
        return {
            "event_summary": "Root cause logged",
            "event_extra": event_extra,
            "next_card": chain_card,
            "next_message_id": chain_message_id,
        }
    return {
        "event_summary": "Root cause logged",
        "event_extra": event_extra,
    }


def _build_recommendations_corrective_card(recs) -> Optional[dict]:
    """Turn a RecommendationsAnalysis into a pre-filled corrective_actions card.

    The run_analysis:recommendations path generates corrective actions and
    caches them to ir_incident_analysis, but the content otherwise never
    reaches the copilot conversation — the user just saw a "review them" note
    with nothing to review. This surfaces the actual recommendations in the
    card's *visible* recommendation text (the frontend renders
    ``recommendation``/``rationale``, not ``field_value``) and pre-fills
    field_value so accepting writes them to ir_incidents.corrective_actions.
    Returns None when there's nothing to recommend.
    """
    items = getattr(recs, "recommendations", None) or []
    actions: list[str] = []
    for it in items:
        action = (getattr(it, "action", None) or "").strip()
        if action:
            prio = (getattr(it, "priority", None) or "").strip()
            actions.append(f"{action} ({prio} priority)" if prio else action)
    summary = (getattr(recs, "summary", None) or "").strip()
    if not actions and not summary:
        return None

    # Visible card text: the card body renders `recommendation` as a single
    # paragraph, so number the actions inline rather than as line breaks.
    numbered = "  ".join(f"({i}) {a}" for i, a in enumerate(actions, 1))
    shown = " ".join(p for p in (summary, numbered) if p).strip()[:900]

    # Saved value: newline-separated for clean storage / report rendering.
    saved_lines = ([summary] if summary else []) + [f"• {a}" for a in actions]
    field_value = "\n".join(saved_lines).strip()[:1800] or shown

    return {
        "id": "recommendations_corrective_actions",
        "title": "Recommended corrective actions",
        "recommendation": shown or "Apply the recommended corrective actions.",
        "rationale": "Accept to save these to the incident record, or skip to refine.",
        "priority": "medium",
        "blockers": [],
        "action": {
            "type": "set_field",
            "label": "Save corrective actions",
            "field_name": "corrective_actions",
            "field_value": field_value,
        },
    }


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
            # When the OSHA recordable chain dispatches its own next card,
            # the helpers populate these and the post-dispatch block streams
            # the card directly to the client instead of running an AI round.
            next_card: Optional[dict] = None
            next_message_id: Optional[str] = None

            yield _sse({"type": "status", "stage": "starting", "action_type": action_type})

            try:
                if action_type == "set_field":
                    raw_field = (action.get("field_name") or "").strip()
                    new_value = action.get("field_value")
                    # treatment_beyond_first_aid is stashed in category_data
                    # JSONB, not a real column. Handles the OSHA injury gate
                    # without an Alembic migration.
                    if raw_field == "treatment_beyond_first_aid":
                        normalized = str(new_value).strip().lower()
                        if normalized not in {"true", "false"}:
                            yield _sse({
                                "type": "error",
                                "detail": "treatment_beyond_first_aid must be true or false",
                            })
                            return
                        bool_value = normalized == "true"
                        await conn.execute(
                            """
                            UPDATE ir_incidents
                            SET category_data = jsonb_set(
                                COALESCE(category_data, '{}'::jsonb),
                                '{treatment_beyond_first_aid}',
                                $1::jsonb,
                                true
                            ),
                            updated_at = NOW()
                            WHERE id = $2
                            """,
                            "true" if bool_value else "false",
                            incident_id,
                        )
                        event_summary = (
                            "Recorded: treatment beyond on-site first aid"
                            if bool_value
                            else "Recorded: on-site first aid only"
                        )
                        event_extra = {
                            "field": "treatment_beyond_first_aid",
                            "field_label": "Treatment beyond first aid",
                            "previous_value": None,
                            "new_value": bool_value,
                        }
                    else:
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
                    elif analysis_type == "followup_questions":
                        yield _sse({
                            "type": "status",
                            "stage": "running_analysis",
                            "analysis_type": "followup_questions",
                            "label": "Working out what still needs to be investigated…",
                        })
                        try:
                            from .ai_analysis import run_followup_questions_inline
                            await run_followup_questions_inline(
                                incident_id,
                                current_user,
                                ip_address=request.client.host if request.client else None,
                            )
                            yield _sse({
                                "type": "status",
                                "stage": "analysis_complete",
                                "analysis_type": "followup_questions",
                            })
                            event_summary = "Investigation questions ready."
                        except Exception as exc:
                            logger.exception("followup_questions failed for incident %s", incident_id)
                            event_summary = f"Couldn't generate investigation questions: {exc}"
                    elif analysis_type == "recommendations":
                        yield _sse({
                            "type": "status",
                            "stage": "running_analysis",
                            "analysis_type": "recommendations",
                            "label": "Generating recommended corrective actions…",
                        })
                        try:
                            from .ai_analysis import run_recommendations_inline
                            recs = await run_recommendations_inline(
                                incident_id,
                                current_user,
                                ip_address=request.client.host if request.client else None,
                            )
                            yield _sse({
                                "type": "status",
                                "stage": "analysis_complete",
                                "analysis_type": "recommendations",
                            })
                            # Surface the generated recommendations IN the
                            # conversation as a pre-filled corrective_actions
                            # card. Without this they only land in the DB and the
                            # user sees an empty "review them" note (the bug).
                            rec_card = _build_recommendations_corrective_card(recs)
                            if rec_card is not None:
                                inserted = await _emit_chain_card(
                                    conn, incident_id=incident_id, card=rec_card,
                                    created_by=current_user.id,
                                )
                                next_card = rec_card
                                next_message_id = str(inserted["id"])
                                event_summary = "Generated recommended corrective actions."
                            else:
                                event_summary = "No corrective actions to recommend for this incident."
                        except Exception as exc:
                            logger.exception("recommendations analysis failed for incident %s", incident_id)
                            event_summary = f"Recommendations failed: {exc}"
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
                        current_user=current_user,
                    )
                    if close_result.get("blocked_by_emergency"):
                        yield _sse({
                            "type": "error",
                            "detail": (
                                "Acknowledge the OSHA reporting alert before "
                                "closing this incident."
                            ),
                        })
                        return
                    if close_result.get("redirected_to_osha_chain"):
                        # Mark THIS card accepted so the redirect chain card
                        # surfaces alone in the transcript. Stream the new
                        # card down to the client and skip the follow-up
                        # guidance round (chain is deterministic).
                        new_md = dict(md)
                        new_md["accepted"] = True
                        new_md["accepted_at"] = _utc_now_naive().isoformat()
                        new_md["accepted_by"] = str(current_user.id)
                        new_md["redirected_to_osha_chain"] = True
                        await conn.execute(
                            "UPDATE ir_incident_ai_messages SET metadata = $1::jsonb WHERE id = $2",
                            json.dumps(new_md), card_row["id"],
                        )
                        yield _sse({
                            "type": "card",
                            "card": close_result["redirect_card"],
                            "message_id": close_result["redirect_message_id"],
                        })
                        yield _sse({"type": "done", "model": "osha_chain"})
                        return
                    if close_result.get("redirected_to_root_cause"):
                        # Same pattern as the OSHA chain redirect — mark
                        # the close card accepted so the log_root_cause_query
                        # surfaces alone, stream the redirect card, and skip
                        # the AI guidance round (chain is deterministic).
                        new_md = dict(md)
                        new_md["accepted"] = True
                        new_md["accepted_at"] = _utc_now_naive().isoformat()
                        new_md["accepted_by"] = str(current_user.id)
                        new_md["redirected_to_root_cause"] = True
                        await conn.execute(
                            "UPDATE ir_incident_ai_messages SET metadata = $1::jsonb WHERE id = $2",
                            json.dumps(new_md), card_row["id"],
                        )
                        yield _sse({
                            "type": "card",
                            "card": close_result["redirect_card"],
                            "message_id": close_result["redirect_message_id"],
                        })
                        yield _sse({"type": "done", "model": "root_cause_chain"})
                        return
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

                elif action_type == "quick_reply":
                    chain_result = await _handle_quick_reply(
                        conn,
                        incident_id=incident_id,
                        action=action,
                        body=body,
                        current_user=current_user,
                    )
                    if chain_result.get("error"):
                        yield _sse({"type": "error", "detail": chain_result["error"]})
                        return
                    event_summary = chain_result.get("event_summary") or ""
                    event_extra = chain_result.get("event_extra") or {}
                    next_card = chain_result.get("next_card")
                    next_message_id = chain_result.get("next_message_id")

                elif action_type == "numeric_input":
                    chain_result = await _handle_numeric_input(
                        conn,
                        incident_id=incident_id,
                        action=action,
                        body=body,
                        current_user=current_user,
                    )
                    if chain_result.get("error"):
                        yield _sse({"type": "error", "detail": chain_result["error"]})
                        return
                    event_summary = chain_result.get("event_summary") or ""
                    event_extra = chain_result.get("event_extra") or {}
                    next_card = chain_result.get("next_card")
                    next_message_id = chain_result.get("next_message_id")

                elif action_type == "text_input":
                    chain_result = await _handle_text_input(
                        conn,
                        incident_id=incident_id,
                        action=action,
                        body=body,
                        current_user=current_user,
                    )
                    if chain_result.get("error"):
                        yield _sse({"type": "error", "detail": chain_result["error"]})
                        return
                    event_summary = chain_result.get("event_summary") or ""
                    event_extra = chain_result.get("event_extra") or {}
                    next_card = chain_result.get("next_card")
                    next_message_id = chain_result.get("next_message_id")

                elif action_type == "osha_emergency_alert":
                    if not body.notes or not body.notes.strip():
                        yield _sse({
                            "type": "error",
                            "detail": "Add confirmation notes before clearing this alert.",
                        })
                        return
                    notes_clean = body.notes.strip()[:2000]
                    await conn.execute(
                        """
                        UPDATE ir_incidents
                        SET category_data = jsonb_set(
                            jsonb_set(
                                COALESCE(category_data, '{}'::jsonb),
                                '{osha_emergency_alert_active}',
                                'false'::jsonb,
                                true
                            ),
                            '{reported_to_osha_notes}',
                            to_jsonb($1::text),
                            true
                        ),
                        updated_at = NOW()
                        WHERE id = $2
                        """,
                        notes_clean, incident_id,
                    )
                    event_summary = "OSHA reporting alert acknowledged"
                    event_extra = {
                        "field": "osha_emergency_alert_active",
                        "field_label": "OSHA alert",
                        "previous_value": True,
                        "new_value": False,
                        "notes": notes_clean,
                    }
                    # Safety net: kick off the OSHA recordable chain
                    # immediately after the alert is acked. Without this,
                    # a user who acks but never logs root cause (eye
                    # injuries often have an obvious cause) hits the
                    # same dormancy that fix 2A addresses for the
                    # root-cause path.
                    if await _should_emit_osha_recordable_chain(conn, incident_id):
                        chain_card, chain_message_id = await _emit_osha_recordable_chain(
                            conn, incident_id=incident_id, current_user=current_user,
                        )
                        next_card = chain_card
                        next_message_id = chain_message_id

                elif action_type == "request_documents":
                    # Document-capture step. The actual upload happens in the
                    # Documents tab; accepting this card marks the prompt
                    # satisfied (so the deterministic flow advances) and reports
                    # how many docs are now attached.
                    doc_count = await conn.fetchval(
                        "SELECT COUNT(*) FROM ir_incident_documents WHERE incident_id = $1",
                        incident_id,
                    ) or 0
                    await conn.execute(
                        """
                        UPDATE ir_incidents
                        SET category_data = jsonb_set(
                            COALESCE(category_data, '{}'::jsonb),
                            '{documents_prompted}',
                            'true'::jsonb,
                            true
                        ),
                        updated_at = NOW()
                        WHERE id = $1
                        """,
                        incident_id,
                    )
                    event_summary = (
                        f"{doc_count} document{'s' if doc_count != 1 else ''} attached"
                        if doc_count
                        else "No documents attached — marked reviewed"
                    )
                    event_extra = {
                        "field": "documents",
                        "field_label": "Documents",
                        "previous_value": None,
                        "new_value": int(doc_count),
                    }

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

                # OSHA recordable chain: when a quick_reply / numeric_input
                # step has emitted its own next card, stream that to the
                # client and stop. Skip the AI guidance round entirely —
                # the chain is deterministic and an extra Gemini call here
                # would risk overlaying an unrelated suggestion on top of
                # the chain step the user must answer next.
                if next_card is not None:
                    yield _sse({
                        "type": "card",
                        "card": next_card,
                        "message_id": next_message_id,
                    })
                    yield _sse({"type": "done", "model": "osha_chain"})
                    return

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

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )
