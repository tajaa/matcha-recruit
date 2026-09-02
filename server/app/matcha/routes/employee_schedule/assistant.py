"""The schedule editor's durable Huume session endpoint."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from ...dependencies import require_company_member
from app.core.feature_flags import get_company_features
from app.core.services.redis_cache import check_rate_limit
from ...models.scheduling.employee_schedule import ScheduleVoiceTranscript
from ...services._shared.uploads import read_wav_or_400
from ...services.scheduling import schedule_voice
from ...services.scheduling.schedule_chat_rules import parse_confirm_reply
from ...services.scheduling.schedule_assistant_session import (
    get_automatic_suggestion_status,
    get_or_create_schedule_assistant_session,
)
from ._shared import require_company_id


class ScheduleAssistantSessionRequest(BaseModel):
    location_id: UUID
    week_start: date


router = APIRouter()


async def _require_schedule_huume(company_id: UUID) -> None:
    features = await get_company_features(company_id)
    if not features.get("huume") or not features.get("matcha_work"):
        missing = "huume" if not features.get("huume") else "matcha_work"
        raise HTTPException(
            status_code=403,
            detail=f"The '{missing}' feature is not enabled for your company",
        )


@router.post("/assistant/sessions")
async def create_schedule_assistant_session(
    body: ScheduleAssistantSessionRequest,
    current_user=Depends(require_company_member),
) -> dict:
    company_id = await require_company_id(current_user)
    # The mount only gates `employee_schedule`; a Huume turn (turn_pipeline.py's
    # `_run_huume_dispatch`) also needs `huume` + `matcha_work`. Without this
    # check the panel opens fine and every turn then dies mid-stream with a
    # generic error — check before creating the (always-huume_mode=true)
    # session row so the caller gets one clear reason instead.
    await _require_schedule_huume(company_id)
    return await get_or_create_schedule_assistant_session(
        company_id=company_id,
        user_id=current_user.id,
        actor_role=current_user.role,
        location_id=body.location_id,
        week_start=body.week_start,
    )


@router.get("/assistant/suggestions")
async def automatic_schedule_suggestion_status(
    location_id: UUID,
    week_start: date,
    current_user=Depends(require_company_member),
) -> dict:
    company_id = await require_company_id(current_user)
    await _require_schedule_huume(company_id)
    return await get_automatic_suggestion_status(
        company_id=company_id,
        user_id=current_user.id,
        actor_role=current_user.role,
        location_id=location_id,
        week_start=week_start,
    )


@router.post("/assistant/voice-transcribe", response_model=ScheduleVoiceTranscript)
async def transcribe_schedule_voice(
    file: UploadFile = File(...),
    current_user=Depends(require_company_member),
) -> ScheduleVoiceTranscript:
    """Transcribe one push-to-talk Huume turn; audio is not persisted."""
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
    parsed = await schedule_voice.transcribe_schedule_request(audio, "audio/wav")
    transcript = parsed["transcript"]
    return ScheduleVoiceTranscript(
        available=parsed["available"],
        transcript=transcript,
        command=parse_confirm_reply(transcript or ""),
        model=parsed["model"],
    )
