"""Response models for the broker Action Center (milestones + AI outreach).

The endpoints in routes/broker_portfolio.py return plain dicts (matching the
file's existing style); these models document the contract for the frontend and
are used as `response_model` for validation.
"""

from typing import Literal, Optional

from pydantic import BaseModel


class MilestoneItem(BaseModel):
    id: str
    company_id: str
    company_name: Optional[str] = None
    milestone_key: str
    milestone_family: str
    tier: Optional[int] = None
    title: str
    detail: Optional[str] = None
    current_value: Optional[float] = None
    benchmark_value: Optional[float] = None
    is_read: bool
    achieved_at: Optional[str] = None
    superseded_at: Optional[str] = None


class MilestonesSummary(BaseModel):
    total: int
    unread: int


class MilestonesResponse(BaseModel):
    summary: MilestonesSummary
    milestones: list[MilestoneItem]


class OutreachPrompt(BaseModel):
    title: str
    rationale: str
    suggested_action: str
    resource_link: Optional[str] = None
    tone: Literal["celebratory", "advisory", "urgent"]


class OutreachResponse(BaseModel):
    company_id: str
    company_name: Optional[str] = None
    cached: bool
    prompts: list[OutreachPrompt]
    generated_at: Optional[str] = None
    model: Optional[str] = None
