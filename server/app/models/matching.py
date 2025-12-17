from datetime import datetime
from typing import Optional, Any
from uuid import UUID

from pydantic import BaseModel


class MatchResult(BaseModel):
    id: UUID
    company_id: UUID
    candidate_id: UUID
    match_score: float  # 0-100
    match_reasoning: Optional[str] = None
    culture_fit_breakdown: Optional[dict[str, Any]] = None
    created_at: datetime


class MatchResultResponse(BaseModel):
    id: UUID
    company_id: UUID
    candidate_id: UUID
    candidate_name: Optional[str] = None
    match_score: float
    match_reasoning: Optional[str] = None
    culture_fit_breakdown: Optional[dict[str, Any]] = None
    created_at: datetime


class MatchRequest(BaseModel):
    """Request to run matching for a company."""
    candidate_ids: Optional[list[UUID]] = None  # If None, match all candidates
