"""HR incident review and editable write-up suggestion payloads."""

from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PolicyViolationReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # A human classification, never inferred from the model's triage matches.
    classification: Literal["policy_violation"]
    employee_id: UUID
    action_type: Literal["verbal_warning", "written_warning", "final_warning", "suspension", "pip", "other"]
    infraction_type: Literal["attendance", "performance", "conduct", "safety", "policy_violation"]
    occurrence_dates: list[date] = Field(..., min_length=1, max_length=30)


class SuggestionAccept(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggestion_id: UUID
    letter: str = Field(..., min_length=1, max_length=20_000)


class SuggestionDismiss(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggestion_id: UUID
    reason: str = Field(..., min_length=10, max_length=2000)
