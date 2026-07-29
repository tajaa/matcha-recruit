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
import json
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.database import get_connection
from app.matcha.dependencies import require_admin_or_client, get_client_company_id
# Safe at module level: ir_flow's own imports of this package are function-local.
from app.matcha.services.ir import ir_flow
from app.matcha.models.ir.copilot import IRCopilotAcceptRequest, IRCopilotStreamRequest, IRCopilotTranscript

# Helpers that still live in _legacy.py; will move to _shared.py in step 10.
from ._shared import ROOT_CAUSE_INTERVIEW_STEPS, _get_incident_with_company_check, _safe_json_loads, _sse, _utc_now_naive, parse_witnesses, build_assign_training_card, log_audit

logger = logging.getLogger(__name__)

router = APIRouter()


# The card/chain state machine moved to services/ir/ir_copilot_flow.py in
# refactor round 2 stage 5.
#
# NOTE these are `from … import` BY NAME, so each one is bound into this
# module's namespace at import time. `monkeypatch.setattr(ir_copilot_flow, "X",
# fake)` does NOT reach the routes below — they hold their own reference. To
# patch a name for a route in this file, patch it HERE (`setattr(copilot, "X")`).
# See ir_incidents/CLAUDE.md for the full three-target rule; an earlier version
# of this comment claimed the opposite and was wrong.
from app.matcha.services.ir.ir_copilot_flow import (  # noqa: F401
    _ACTION_PRIORITY_RE,
    _FIELD_LABELS,
    _FIELD_WHITELIST,
    _PROTECTED_CHAIN_CARD_IDS,
    _PROTECTED_CHAIN_CARD_ID_PREFIXES,
    _VALID_INCIDENT_TYPES,
    _VALID_SEVERITIES,
    _VALID_STATUSES,
    _build_recommendations_corrective_card,
    _close_incident_via_copilot,
    _coerce_metadata_dict,
    _emit_chain_card,
    _emit_osha_description_review,
    _emit_osha_recordable_chain,
    _extract_current_cards,
    _extract_summary_and_open_questions,
    _handle_numeric_input,
    _handle_quick_reply,
    _handle_text_input,
    _has_pending_protected_card,
    _parse_action_bullets,
    _seed_structured_corrective_actions,
    _serialize_message,
    _should_emit_osha_recordable_chain,
    _validate_field_value,
    ensure_case_chain,
    resume_copilot_after_info_request,
)


# ===========================================
# IR Copilot — orchestrator endpoints
# ===========================================


@router.get("/{incident_id}/copilot", response_model=IRCopilotTranscript)
async def get_copilot_transcript(
    incident_id: UUID,
    current_user=Depends(require_admin_or_client),
):
    """Return the full chat transcript + currently-active cards for an incident."""
    async with get_connection() as conn:
        incident = await _get_incident_with_company_check(
            conn, incident_id, current_user,
            columns=(
                "id, title, description, status, incident_type, severity, "
                "root_cause, corrective_actions, osha_recordable, category_data, "
                "witnesses, reported_at, resolved_at"
            ),
        )
        rows = await conn.fetch(
            "SELECT id, role, message_type, content, metadata, created_by, created_at "
            "FROM ir_incident_ai_messages WHERE incident_id = $1 ORDER BY created_at, id",
            incident_id,
        )
        # Single round trip for the evidence-tracker counts — cheaper than one
        # query per table, and this endpoint is polled every 15s per open tab.
        evidence_counts = await conn.fetchrow(
            """
            SELECT
                (SELECT COUNT(*) FROM ir_incident_documents WHERE incident_id = $1) AS document_count,
                (SELECT COUNT(*) FROM ir_corrective_actions WHERE incident_id = $1) AS corrective_action_count,
                (SELECT COUNT(*) FROM ir_investigation_interviews
                    WHERE incident_id = $1 AND status = 'completed') AS completed_interview_count
            """,
            incident_id,
        )

    messages = [_serialize_message(r) for r in rows]
    cards = _extract_current_cards(messages)
    summary, open_questions = _extract_summary_and_open_questions(messages)
    incident_dict = dict(incident) if incident else {}
    witness_count = len(parse_witnesses(incident_dict.get("witnesses"))) + (
        evidence_counts["completed_interview_count"] if evidence_counts else 0
    )
    return IRCopilotTranscript(
        incident_id=incident_id,
        messages=messages,
        current_cards=cards,
        summary=summary,
        open_questions=open_questions,
        progress=ir_flow.close_progress(incident_dict),
        evidence=ir_flow.copilot_evidence(
            incident_dict,
            document_count=(evidence_counts["document_count"] if evidence_counts else 0),
            witness_count=witness_count,
            corrective_action_count=(evidence_counts["corrective_action_count"] if evidence_counts else 0),
        ),
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
    from app.matcha.services.ir.ir_ai_orchestrator import (
        generate_guidance,
        load_incident_state,
        persist_assistant_round,
    )

    company_id = await get_client_company_id(current_user)

    async def event_stream():
        # Load state + append the user turn on a SHORT-LIVED connection, then
        # RELEASE it before the (up-to-60s) Gemini call so a slow model round
        # doesn't pin an asyncpg pool slot for its whole duration. Re-acquire a
        # fresh connection only for the persist/audit writes afterward.
        async with get_connection() as conn:
            incident, analyses, messages = await load_incident_state(
                conn, incident_id, company_id
            )
            if incident is None:
                yield _sse({"type": "error", "detail": "Incident not found"})
                return

            # Append the user's message FIRST so the orchestrator includes it.
            user_msg = (body.message or "").strip()
            if user_msg:
                from app.matcha.services.ir.ir_ai_orchestrator import append_message
                user_row = await append_message(
                    conn,
                    incident_id=incident_id,
                    role="user",
                    message_type="text",
                    content=user_msg[:4000],
                    created_by=current_user.id,
                )
                messages.append(user_row)

        yield _sse({"type": "status", "stage": "thinking"})

        try:
            payload = await generate_guidance(
                incident=incident,
                analyses=analyses,
                messages=messages,
            )
        except Exception:
            logger.exception("IR Copilot round failed for incident %s", incident_id)
            yield _sse({"type": "error", "detail": "Failed to generate guidance"})
            return

        # Persist assistant text + cards + audit on a fresh short-lived connection.
        async with get_connection() as conn:
            await persist_assistant_round(
                conn,
                incident_id=incident_id,
                user_id=current_user.id,
                user_message=None,  # already inserted above
                guidance_payload=payload,
            )

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

        yield _sse({"type": "summary", "text": payload.get("summary") or ""})
        for q in payload.get("open_questions") or []:
            yield _sse({"type": "open_question", "text": q})
        for card in payload.get("cards") or []:
            yield _sse({"type": "card", "card": card})
        yield _sse({"type": "done", "model": payload.get("model")})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )


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
        from app.matcha.services.ir.ir_flow import gate_key_for_card
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


@router.post("/{incident_id}/copilot/close")
async def close_incident_via_copilot(
    incident_id: UUID,
    request: Request,
    current_user=Depends(require_admin_or_client),
):
    """Direct close — no card required. Used by the panel's Close button."""
    from app.matcha.services.ir.ir_ai_orchestrator import append_message

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
    from app.matcha.services.ir.ir_ai_orchestrator import (
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

            # Claim the card atomically before running any side effects. The
            # previous `if md.get("accepted"):` was a plain read with no lock,
            # so two concurrent accepts (double-click, client retry on a slow
            # SSE stream) both passed the guard and both ran the action body —
            # duplicate training assignment, duplicate corrective actions,
            # duplicate transcript events. This conditional UPDATE claims the
            # card the same way info_requests.py's resend/revoke do: whichever
            # request's UPDATE actually flips accepted false->true wins, the
            # other sees zero rows and reports "already accepted". This also
            # replaces the later "mark the card accepted" write — accepted_at/
            # accepted_by are stamped here, not after the action runs.
            accepted_at = datetime.now(timezone.utc)
            claimed = await conn.fetchrow(
                """
                UPDATE ir_incident_ai_messages
                SET metadata = jsonb_set(
                    jsonb_set(
                        jsonb_set(COALESCE(metadata, '{}'::jsonb), '{accepted}', 'true', true),
                        '{accepted_at}', to_jsonb($3::text), true
                    ),
                    '{accepted_by}', to_jsonb($4::text), true
                )
                WHERE id = $1 AND incident_id = $2 AND message_type = 'card'
                  AND COALESCE(metadata->>'accepted', 'false')::boolean = false
                RETURNING id
                """,
                body.message_id, incident_id, accepted_at.isoformat(), str(current_user.id),
            )
            if claimed is None:
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

                        # Bridge: accepting the AI recommendations card also
                        # materializes each action as a tracked CAPA row so it
                        # gets an owner, due date, and the deadline worker's
                        # follow-through — not just a note in the text column.
                        if (
                            db_field == "corrective_actions"
                            and card.get("id") == "recommendations_corrective_actions"
                        ):
                            try:
                                seeded = await _seed_structured_corrective_actions(
                                    conn, incident_id, company_id, current_user.id, new_value,
                                )
                                if seeded:
                                    event_extra["structured_actions_created"] = seeded
                            except Exception as exc:  # never block the text write
                                logger.warning(
                                    "Failed to seed structured corrective actions: %s", exc
                                )

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

                            # Best-effort: if a recommended training topic
                            # confidently matched an existing requirement and
                            # the incident has involved employees, emit a
                            # second (additional, non-blocking) transcript
                            # card suggesting the assignment. Doesn't touch
                            # next_card — this turn's response still carries
                            # the corrective-actions card; the training card
                            # surfaces on the next transcript fetch.
                            try:
                                involved_ids = incident.get("involved_employee_ids") or []
                                if involved_ids:
                                    mapping_row = await conn.fetchrow(
                                        "SELECT analysis_data FROM ir_incident_analysis "
                                        "WHERE incident_id = $1 AND analysis_type = 'training_mapping' "
                                        "ORDER BY generated_at DESC LIMIT 1",
                                        incident_id,
                                    )
                                    mapping_data = _safe_json_loads(mapping_row["analysis_data"], {}) if mapping_row else {}
                                    matches = (mapping_data or {}).get("matches") or []
                                    if matches:
                                        best = max(matches, key=lambda m: m.get("confidence", 0))
                                        training_card = build_assign_training_card(
                                            requirement_id=best["requirement_id"],
                                            requirement_title=best["title"],
                                            trainee_count=len(involved_ids),
                                            reasoning=best.get("reasoning"),
                                        )
                                        await _emit_chain_card(
                                            conn, incident_id=incident_id, card=training_card,
                                            created_by=current_user.id,
                                        )
                            except Exception:
                                logger.exception(
                                    "Failed to emit assign_training card for incident %s", incident_id,
                                )
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

                elif action_type == "assign_training":
                    from app.core.feature_flags import get_company_features
                    from app.matcha.services.training.training_assignment import assign_training

                    features = await get_company_features(company_id, conn=conn)
                    if not features.get("training"):
                        yield _sse({"type": "error", "detail": "Training feature is not enabled for this company"})
                        return

                    requirement_id = action.get("requirement_id")
                    if not requirement_id:
                        yield _sse({"type": "error", "detail": "Card has no requirement_id"})
                        return
                    requirement = await conn.fetchrow(
                        "SELECT id, title, training_type, frequency_months "
                        "FROM training_requirements WHERE id = $1 AND company_id = $2 AND is_active = true",
                        str(requirement_id), str(company_id),
                    )
                    if not requirement:
                        yield _sse({"type": "error", "detail": "Training requirement not found"})
                        return
                    employee_ids = action.get("employee_ids") or incident.get("involved_employee_ids") or []
                    if not employee_ids:
                        event_summary = "No involved employees to assign training to."
                    else:
                        outcome = await assign_training(
                            conn,
                            company_id,
                            dict(requirement),
                            employee_ids,
                            source_type="incident",
                            source_ref=incident_id,
                            source_note="Assigned via IR Copilot",
                            assigned_by=current_user.id,
                        )
                        event_summary = (
                            f"Assigned “{requirement['title']}” to {outcome.assigned} employee(s)."
                            if outcome.assigned
                            else "Training already assigned to the involved employee(s)."
                        )
                        event_extra = {
                            "field": "training",
                            "field_label": "Training",
                            "previous_value": None,
                            "new_value": outcome.assigned,
                        }

                else:
                    yield _sse({"type": "error", "detail": f"Unknown action type: {action_type}"})
                    return

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
            except Exception:
                logger.exception("copilot accept failed for incident %s", incident_id)
                yield _sse({"type": "error", "detail": "Action failed — see server logs"})
                return

        # Follow-up guidance round — OUTSIDE the action's connection scope so the
        # (up-to-60s) Gemini call doesn't pin a pool slot: reload state on a
        # short-lived connection, release it for the model call, then re-acquire
        # to persist the round.
        try:
            yield _sse({"type": "status", "stage": "thinking"})
            async with get_connection() as conn:
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

            async with get_connection() as conn:
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
            logger.exception("copilot accept follow-up failed for incident %s", incident_id)
            yield _sse({"type": "error", "detail": "Action failed — see server logs"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
    )
