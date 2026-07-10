"""Request/response shapes for the compliance-eval admin API."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

EvalSuite = Literal["completeness", "authority", "tagging", "golden", "scope"]
FindingStatus = Literal["open", "confirmed", "dismissed", "fixed"]
Severity = Literal["critical", "warn", "info"]


class EvalRunRequest(BaseModel):
    suites: List[EvalSuite] = Field(
        default_factory=lambda: ["completeness", "tagging", "golden"]
    )
    jurisdiction_ids: Optional[List[UUID]] = None
    industries: Optional[List[str]] = None


class EvalRunResponse(BaseModel):
    run_id: UUID
    status: str
    dispatched_to: Literal["inline", "celery"]
    suites: List[str]


class EvalRunSummary(BaseModel):
    id: UUID
    suites: List[str]
    status: str
    trigger_source: str
    totals: Optional[Dict[str, Any]] = None
    error_text: Optional[str] = None
    started_at: datetime
    finished_at: Optional[datetime] = None


class EvalFinding(BaseModel):
    id: UUID
    suite: str
    finding_type: str
    severity: Severity
    jurisdiction_id: Optional[UUID] = None
    jurisdiction_label: Optional[str] = None
    requirement_id: Optional[UUID] = None
    requirement_key: Optional[str] = None
    category: Optional[str] = None
    industry: Optional[str] = None
    expected: Optional[Dict[str, Any]] = None
    observed: Optional[Dict[str, Any]] = None
    status: FindingStatus
    notes: Optional[str] = None
    created_at: datetime


class FindingResolveRequest(BaseModel):
    status: Literal["confirmed", "dismissed", "fixed"]
    notes: Optional[str] = None


class ScorecardCell(BaseModel):
    jurisdiction_id: UUID
    jurisdiction_label: str
    industry: Optional[str] = None
    composite: Optional[float] = None
    onboarding_ready: Optional[bool] = None
    status: Optional[str] = None
    subscores: Dict[str, Optional[float]] = Field(default_factory=dict)


class OnboardingReadiness(BaseModel):
    found: bool
    status: str
    industry: str
    ready: bool = False
    jurisdiction_id: Optional[UUID] = None
    composite: Optional[float] = None
    subscores: Dict[str, Optional[float]] = Field(default_factory=dict)
    blocking: List[str] = Field(default_factory=list)
    missing_keys: Dict[str, List[str]] = Field(default_factory=dict)
    focused_categories: List[str] = Field(default_factory=list)
    golden_fact_count: int = 0
    open_critical_findings: int = 0


class GoldenFactStatus(BaseModel):
    jurisdiction: str
    requirement_key: str
    category: str
    comparator: str
    severity: str
    effective_from: str
    effective_to: Optional[str] = None
    authority_url: str
    curated_by: str
    verified_by: Optional[str] = None
    state: Literal["active", "pending", "expired"]
