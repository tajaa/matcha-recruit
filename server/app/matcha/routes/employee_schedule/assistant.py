"""The schedule editor's durable Huume session endpoint."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from ...dependencies import require_company_member
from app.core.services.redis_cache import check_rate_limit
from ...models.scheduling.employee_schedule import ScheduleVoiceTranscript
from ...services._shared.uploads import read_wav_or_400
from ...services.scheduling import schedule_voice
from ...services.scheduling.schedule_chat_rules import parse_confirm_reply
from ...services.scheduling.schedule_assistant_session import (
    get_or_create_schedule_assistant_session,
)
from ._shared import require_company_id


class ScheduleAssistantSessionRequest(BaseModel):
    location_id: UUID
    week_start: date


router = APIRouter()


@router.post("/assistant/sessions")
async def create_schedule_assistant_session(
    body: ScheduleAssistantSessionRequest,
    current_user=Depends(require_company_member),
) -> dict:
    company_id = await require_company_id(current_user)
    return await get_or_create_schedule_assistant_session(
        company_id=company_id,
        user_id=current_user.id,
        actor_role=current_user.role,
        location_id=body.location_id,
        week_start=body.week_start,
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
