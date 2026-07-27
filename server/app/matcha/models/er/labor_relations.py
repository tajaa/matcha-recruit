"""Pydantic request/response models for the Labor Relations package.

Covers CBAs, the clause library, and the grievance workflow (Phase 1).
Enum-constrained fields use ``Literal`` and mirror the CHECK constraints in
migration ``labor01``. Routers serialize asyncpg rows to JSON-friendly dicts
(via ``_shared._serialize``), so response shapes here stay light — they exist
mainly for request validation + OpenAPI.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

# ── Shared enum literals (kept in sync with labor01 CHECK constraints) ───────

CBAStatus = Literal["draft", "active", "expired", "superseded", "in_negotiation"]
ClauseCategory = Literal[
    "wages", "hours", "seniority", "grievance_procedure", "discipline", "just_cause",
    "overtime", "benefits", "union_security", "management_rights", "health_safety",
    "layoff_recall", "holidays_leave", "other",
]
GrievanceType = Literal[
    "discipline", "discharge", "contract_interpretation", "pay_wages", "seniority",
    "overtime", "working_conditions", "health_safety", "management_rights",
    "past_practice", "other",
]
GrievanceStatus = Literal[
    "draft", "filed", "in_progress", "advanced", "resolved", "withdrawn",
    "denied", "arbitration", "settled",
]
GrievanceResolution = Literal[
    "granted", "denied", "partially_granted", "withdrawn", "settled",
    "arbitrated_win", "arbitrated_loss",
]
StepOutcome = Literal["granted", "denied", "partially_granted", "advanced"]
DayBasis = Literal["calendar", "working"]


# ── CBA ──────────────────────────────────────────────────────────────────────

class GrievanceStepConfigItem(BaseModel):
    """One step in a CBA's contractual grievance procedure."""
    step: int = Field(..., ge=1, le=20)
    name: str = Field(..., min_length=1, max_length=100)
    file_within_days: int = Field(..., ge=0, le=365)
    respond_within_days: int = Field(..., ge=0, le=365)
    day_basis: DayBasis = "calendar"


class CBACreateRequest(BaseModel):
    union_name: str = Field(..., min_length=1, max_length=255)
    union_local: Optional[str] = Field(None, max_length=100)
    bargaining_unit_desc: Optional[str] = None
    effective_date: Optional[date] = None
    expiration_date: Optional[date] = None
    status: CBAStatus = "active"
    renewal_alert_days: int = Field(90, ge=0, le=730)
    grievance_step_config: Optional[list[GrievanceStepConfigItem]] = None


class CBAUpdateRequest(BaseModel):
    union_name: Optional[str] = Field(None, min_length=1, max_length=255)
    union_local: Optional[str] = Field(None, max_length=100)
    bargaining_unit_desc: Optional[str] = None
    effective_date: Optional[date] = None
    expiration_date: Optional[date] = None
    status: Optional[CBAStatus] = None
    renewal_alert_days: Optional[int] = Field(None, ge=0, le=730)
    grievance_step_config: Optional[list[GrievanceStepConfigItem]] = None
    # HR confirms the (AI-seeded) grievance procedure before the deadline engine
    # is allowed to enforce off it.
    grievance_steps_confirmed: Optional[bool] = None


# ── Clauses ─────────────────────────────────────────────────────────────────

class ClauseCreateRequest(BaseModel):
    article_number: Optional[str] = Field(None, max_length=50)
    title: Optional[str] = Field(None, max_length=300)
    clause_text: str = Field(..., min_length=1)
    category: Optional[ClauseCategory] = None
    sort_order: int = 0


class ClauseUpdateRequest(BaseModel):
    article_number: Optional[str] = Field(None, max_length=50)
    title: Optional[str] = Field(None, max_length=300)
    clause_text: Optional[str] = Field(None, min_length=1)
    category: Optional[ClauseCategory] = None
    sort_order: Optional[int] = None
    # Confirming an AI-extracted clause flips source→manual (HR-owned).
    confirm: bool = False


# ── Grievances ──────────────────────────────────────────────────────────────

class GrievanceCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    cba_id: Optional[UUID] = None
    grievant_employee_id: Optional[UUID] = None
    is_class_grievance: bool = False
    steward_employee_id: Optional[UUID] = None
    steward_name_external: Optional[str] = Field(None, max_length=255)
    grievance_type: Optional[GrievanceType] = None
    incident_date: Optional[date] = None
    assigned_to: Optional[UUID] = None
    linked_discipline_id: Optional[UUID] = None
    linked_er_case_id: Optional[UUID] = None
    violated_clause_ids: Optional[list[UUID]] = None


class GrievanceUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    cba_id: Optional[UUID] = None
    grievant_employee_id: Optional[UUID] = None
    is_class_grievance: Optional[bool] = None
    steward_employee_id: Optional[UUID] = None
    steward_name_external: Optional[str] = Field(None, max_length=255)
    grievance_type: Optional[GrievanceType] = None
    incident_date: Optional[date] = None
    assigned_to: Optional[UUID] = None


class StepRespondRequest(BaseModel):
    management_response: Optional[str] = None
    union_position: Optional[str] = None
    outcome: StepOutcome
    response_date: Optional[date] = None


class AdvanceRequest(BaseModel):
    note: Optional[str] = None


class ResolveRequest(BaseModel):
    resolution: GrievanceResolution
    resolution_summary: Optional[str] = None


class WithdrawRequest(BaseModel):
    reason: Optional[str] = None


class AttachClausesRequest(BaseModel):
    clause_ids: list[UUID] = Field(..., min_length=0)


class GrievanceDocumentRequest(BaseModel):
    """Attach an already-uploaded document reference to a grievance."""
    storage_path: str = Field(..., min_length=1)
    filename: str = Field(..., min_length=1, max_length=255)
    content_type: Optional[str] = None
    note: Optional[str] = None
