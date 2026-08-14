"""Pydantic shapes for the Matcha Ops admin control plane."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class MatchaOpsFeaturePatch(BaseModel):
    features: dict[str, bool] = Field(min_length=1)


class OpsCompanySummary(BaseModel):
    company_id: UUID
    company_name: str
    status: str
    signup_source: Optional[str] = None
    is_personal: bool = False
    matcha_ops_enabled: bool
    enabled_ops_features: list[str]
    channel_count: int = 0
    operations_channel_count: int = 0
    open_events: int = 0
    low_stock_items: int = 0
    open_orders: int = 0
    upcoming_shifts: int = 0
    pending_schedule_requests: int = 0
    needs_attention: bool = False


class OpsCompanyDetail(OpsCompanySummary):
    stored_features: dict[str, bool]
    effective_features: dict[str, bool]
    dependency_violations: dict[str, list[str]]
    feature_provenance: dict[str, object] = Field(default_factory=dict)
    created_at: Optional[datetime] = None


class OpsOverview(BaseModel):
    companies_enabled: int
    companies_with_attention: int
    operations_channels: int
    open_events: int
    low_stock_items: int
    open_orders: int
    upcoming_shifts: int
    pending_schedule_requests: int
