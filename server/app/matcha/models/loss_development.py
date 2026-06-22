"""Loss-run triangulation request models."""

from datetime import date
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class LossRunPeriod(BaseModel):
    """One policy-period row within a single loss-run valuation."""

    policy_period_label: str = Field(..., min_length=1, max_length=40)
    policy_period_start: Optional[date] = None
    claim_count: int = Field(default=0, ge=0)
    open_count: int = Field(default=0, ge=0)
    paid: float = Field(default=0, ge=0)
    reserved: float = Field(default=0, ge=0)


class LossRunValuationCommit(BaseModel):
    """A loss run valued as of one date → one row per policy period it covers."""

    valuation_date: date
    line: Literal["wc", "gl", "auto"] = "wc"
    source: Optional[str] = Field(None, max_length=60)
    periods: List[LossRunPeriod] = Field(..., min_length=1)
