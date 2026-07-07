"""Risk Pilot request models (Pydantic v2)."""

from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    domain: Optional[str] = Field(None, max_length=30)
    goal: Optional[str] = Field(None, max_length=2000)


class SessionUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=300)
    goal: Optional[str] = Field(None, max_length=2000)
    status: Optional[Literal["active", "closed"]] = None


class DatasetPatch(BaseModel):
    """Confirm/adjust a dataset before (re)analysis. `mapping` overrides column→
    role; `column_kinds` marks a series as already-returns; `extraction` lets the
    user correct document-extracted figures before they drive metrics."""
    mapping: Optional[dict[str, str]] = None
    column_kinds: Optional[dict[str, Literal["level", "returns"]]] = None
    periods_per_year: Optional[int] = Field(None, ge=1, le=100000)
    risk_free: Optional[float] = Field(None, ge=-1, le=1)
    kind: Optional[str] = Field(None, max_length=30)
    extraction: Optional[dict] = None


class ComparisonCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    dataset_ids: list[UUID] = Field(..., min_length=2, max_length=8)
    spec: Optional[dict] = None


class ChatIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000)


class ReportIn(BaseModel):
    scope: Literal["session", "comparison"] = "session"
    comparison_id: Optional[UUID] = None
