from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class RankingRequest(BaseModel):
    candidate_ids: Optional[list[UUID]] = None


class RankedCandidateResponse(BaseModel):
    id: UUID
    company_id: UUID
    candidate_id: UUID
    candidate_name: Optional[str]
    overall_rank_score: float
    screening_score: Optional[float]
    conversation_score: Optional[float]
    culture_alignment_score: Optional[float]
    has_interview_data: bool
    signal_breakdown: Optional[dict]
    interview_ids: Optional[list]
    created_at: datetime
