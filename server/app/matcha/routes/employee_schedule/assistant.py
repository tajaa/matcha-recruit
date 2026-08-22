"""The schedule editor's durable Huume session endpoint."""

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...dependencies import require_company_member
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
