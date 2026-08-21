"""Schedule-editor assistant endpoints.

The editor uses the same proposal builders as channel and thread scheduling,
but its Apply button creates drafts by default and never relies on a chat
message as an implicit confirmation.
"""

from __future__ import annotations

import json
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.core.services.redis_cache import check_rate_limit
from app.core.feature_flags import get_company_features
from app.database import get_connection
from ...dependencies import require_admin_or_client
from ...models.scheduling.employee_schedule import (
    ScheduleChatApply,
    ScheduleChatMessage,
    ScheduleVoiceTranscript,
)
from ...services._shared.uploads import read_wav_or_400
from ...services.scheduling import schedule_chat, schedule_voice
from ...services.scheduling.schedule_chat_rules import (
    parse_confirm_reply,
    resolve_clarify_answer,
    snapped_to_option,
)
from ._shared import require_company_id

router = APIRouter()


def _decode(value):
    return json.loads(value) if isinstance(value, str) else value


def _response(row, build: schedule_chat.ProposalBuild) -> dict:
    proposal = _decode(row["proposal"])
    return {
        "proposal_id": str(build.proposal_id),
        "kind": build.kind,
        "message": proposal.get("clarify_question") or proposal.get("ack") or build.pill_text,
        "proposal": proposal,
        "pill_text": build.pill_text,
    }


@router.post("/chat/voice-transcribe", response_model=ScheduleVoiceTranscript)
async def transcribe_schedule_voice(
    file: UploadFile = File(...),
    current_user=Depends(require_admin_or_client),
) -> ScheduleVoiceTranscript:
    """Transcribe one push-to-talk turn; scheduling still runs through /chat."""
    company_id = await require_company_id(current_user)
    user_key = f"user:{current_user.id}"
    await check_rate_limit(user_key, "schedule_voice_parse_burst", 5, 60)
    await check_rate_limit(user_key, "schedule_voice_parse", 30, 3600)
    await check_rate_limit(str(company_id), "schedule_voice_parse_co", 120, 3600)

    audio = await read_wav_or_400(file, max_bytes=schedule_voice.MAX_AUDIO_BYTES)
    try:
        schedule_voice.validate_schedule_wav(audio)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    parsed = await schedule_voice.transcribe_schedule_request(
        audio,
        "audio/wav",
    )
    transcript = parsed["transcript"]
    return ScheduleVoiceTranscript(
        available=parsed["available"],
        transcript=transcript,
        command=parse_confirm_reply(transcript or ""),
        model=parsed["model"],
    )


async def _load_proposal(conn, company_id: UUID, proposal_id: UUID):
    row = await conn.fetchrow(
        """SELECT id, company_id, channel_id, proposal, parse, status
           FROM schedule_chat_proposals WHERE id=$1 AND company_id=$2""",
        proposal_id, company_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Schedule proposal not found")
    return row


@router.post("/chat")
async def schedule_chat_turn(
    body: ScheduleChatMessage,
    current_user=Depends(require_admin_or_client),
) -> dict:
    company_id = await require_company_id(current_user)
    await check_rate_limit(str(company_id), "editor_schedule_chat", 30, 3600)

    stored_proposal = None
    stored_parse = None
    if body.existing_proposal_id:
        async with get_connection() as conn:
            existing = await _load_proposal(conn, company_id, body.existing_proposal_id)
            if existing["status"] != "clarifying":
                raise HTTPException(status_code=409, detail="That clarification is no longer active")
            stored_proposal = _decode(existing["proposal"])
            stored_parse = _decode(existing["parse"])

    today = date.today()
    original_content = body.message
    parsed = None
    clarify_history: list[dict] = []

    if stored_proposal and stored_parse:
        options = stored_proposal.get("clarify_options") or []
        snapped = resolve_clarify_answer(body.message, options)
        location_question = (
            stored_proposal.get("clarify_question")
            == schedule_chat.LOCATION_CLARIFY_QUESTION
        )
        location_answer = location_question and snapped_to_option(snapped, options)

        if location_answer:
            parsed = dict(stored_parse)
            parsed["location_hint"] = snapped
        else:
            original_content = schedule_chat.compose_clarify_followup(
                stored_proposal, snapped,
            )
            parsed = await schedule_chat.parse_schedule_request(
                original_content, today, week_start=body.week_start,
            )
            if parsed is None and location_question:
                parsed = dict(stored_parse)
            if parsed is not None and location_question and not (
                parsed.get("location_hint") or ""
            ).strip():
                parsed["location_hint"] = snapped

        clarify_history = list(stored_proposal.get("clarify_history") or []) + [{
            "q": stored_proposal.get("clarify_question"),
            "a": body.message,
        }]
        original_content = stored_proposal.get("original_content") or body.message
    else:
        parsed = await schedule_chat.parse_schedule_request(
            original_content, today, week_start=body.week_start,
        )

    if parsed is None:
        if stored_proposal:
            return {
                "proposal_id": body.existing_proposal_id,
                "kind": "clarify",
                "message": "I couldn't understand that — could you restate the days, hours, or people?",
                "proposal": None,
            }
        return {
            "proposal_id": None, "kind": "unactionable",
            "message": "Ask about coverage, shifts, edits, week templates, or applying a saved week.",
            "proposal": None,
        }

    async with get_connection() as conn:
        if body.location_id and not parsed.get("location_hint"):
            parsed["location_hint"] = await conn.fetchval(
                """SELECT name FROM business_locations
                   WHERE id=$1 AND company_id=$2 AND is_active IS NOT FALSE""",
                body.location_id, company_id,
            )

        common = dict(
            company_id=company_id, channel_id=None, source_message_id=None,
            created_by=current_user.id, parsed=parsed, today=today,
            original_content=original_content, surface="editor",
            clarify_history=clarify_history,
            existing_proposal_id=body.existing_proposal_id,
        )
        original_kind = stored_proposal.get("kind") if stored_proposal else parsed.get("action")
        if original_kind == "template":
            build = await schedule_chat.build_template_proposal(conn, **common)
        elif original_kind == "apply_template":
            build = await schedule_chat.build_apply_template_proposal(
                conn, **common, week_start=body.week_start,
            )
        elif original_kind == "edit":
            statuses = ("draft", "published") if body.edit_published else ("draft",)
            build = await schedule_chat.build_edit_proposal(
                conn, **common, shift_statuses=statuses, editor_location_id=body.location_id,
            )
        else:
            build = await schedule_chat.build_proposal(
                conn, **common, week_start=body.week_start,
            )
        row = await _load_proposal(conn, company_id, build.proposal_id)
        return _response(row, build)


@router.post("/chat/{proposal_id}/apply")
async def schedule_chat_apply(
    proposal_id: UUID,
    body: ScheduleChatApply,
    current_user=Depends(require_admin_or_client),
) -> dict:
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        row = await _load_proposal(conn, company_id, proposal_id)
        if row["status"] != "proposed":
            raise HTTPException(status_code=409, detail="That proposal is no longer available")
        proposal = _decode(row["proposal"])
        features = await get_company_features(company_id, conn=conn)
        proposal_row = {**dict(row), "proposal": proposal}
        week_template_id = None
        try:
            if proposal.get("kind") == "template":
                text = await schedule_chat.execute_template_proposal(
                    conn, proposal_row=proposal_row, confirmed_by=current_user.id, features=features,
                )
                week_template_id = await conn.fetchval(
                    "SELECT proposal->>'created_week_template_id' FROM schedule_chat_proposals WHERE id=$1",
                    proposal_id,
                )
            elif proposal.get("kind") == "apply_template":
                text = await schedule_chat.execute_apply_template_proposal(
                    conn, proposal_row=proposal_row, confirmed_by=current_user.id, features=features,
                )
            elif proposal.get("kind") == "edit":
                text = await schedule_chat.execute_edit_proposal(
                    conn, proposal_row=proposal_row, confirmed_by=current_user.id,
                    features=features, edit_published=body.edit_published,
                )
            else:
                text = await schedule_chat.execute_proposal(
                    conn, proposal_row=proposal_row, confirmed_by=current_user.id,
                    features=features, create_status="draft" if body.as_draft else "published",
                )
        except schedule_chat.ProposalExecutionClaimError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        shift_ids = await conn.fetchval(
            "SELECT created_shift_ids FROM schedule_chat_proposals WHERE id=$1",
            proposal_id,
        )
    return {
        "ok": True, "text": text, "shift_ids": [str(i) for i in (shift_ids or [])],
        "week_template_id": week_template_id,
    }


@router.post("/chat/{proposal_id}/discard")
async def schedule_chat_discard(
    proposal_id: UUID,
    current_user=Depends(require_admin_or_client),
) -> dict:
    company_id = await require_company_id(current_user)
    async with get_connection() as conn:
        result = await conn.execute(
            """UPDATE schedule_chat_proposals SET status='cancelled', updated_at=NOW()
               WHERE id=$1 AND company_id=$2 AND status IN ('proposed','clarifying')""",
            proposal_id, company_id,
        )
    if result == "UPDATE 0":
        raise HTTPException(status_code=409, detail="That proposal is no longer active")
    return {"ok": True}
