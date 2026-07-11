"""Request models for Total Cost of Risk inputs."""

from typing import Optional

from pydantic import BaseModel, Field


class TcorInput(BaseModel):
    line: str = Field(..., max_length=40)          # 'wc'|'gl'|'auto'|'property'|...
    annual_premium: Optional[float] = None
    fees: Optional[float] = None
    risk_mitigation_spend: Optional[float] = None
    current_retention: Optional[float] = None
    policy_year: Optional[int] = None
