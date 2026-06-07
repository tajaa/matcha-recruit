"""Request/response models for the fractional HR admin tooling.

Internal master-admin vertical: Matcha delivers HR fractionally to client
companies (which may or may not be existing tenants). Operated by admins;
no client-facing login.
"""

from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field

# Service areas a fractional HR engagement might cover. Stored as free text so
# the list can grow without a migration; these seed the UI dropdowns.
SERVICE_CATEGORIES = [
    "policy",
    "handbook",
    "audit",
    "org_design",
    "team_direction",
    "coaching",
    "strategy",
    "hiring",
    "compliance",
    "other",
]

BillingModel = Literal["monthly_retainer", "hours_block", "project_fixed", "hourly"]
ClientStatus = Literal["prospect", "active", "paused", "offboarded"]
RetainerPeriod = Literal["weekly", "monthly", "quarterly"]
AssignmentRole = Literal["lead", "consultant", "jr"]
ScopeStatus = Literal["planned", "active", "on_hold", "done"]
TaskStatus = Literal["todo", "in_progress", "blocked", "review", "done"]
Priority = Literal["low", "medium", "high"]


class ClientCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    company_id: Optional[str] = None
    status: ClientStatus = "prospect"
    billing_model: BillingModel = "monthly_retainer"
    retainer_hours: Optional[float] = Field(default=None, ge=0, le=10_000)
    retainer_period: RetainerPeriod = "monthly"
    rollover_unused: bool = False
    billing_rate: Optional[float] = Field(default=None, ge=0, le=100_000)
    project_fee: Optional[float] = Field(default=None, ge=0, le=10_000_000)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    industry: Optional[str] = Field(default=None, max_length=100)
    headcount: Optional[int] = Field(default=None, ge=0, le=1_000_000)
    jurisdictions: list[str] = Field(default_factory=list)
    contact_name: Optional[str] = Field(default=None, max_length=255)
    contact_email: Optional[str] = Field(default=None, max_length=320)
    contact_phone: Optional[str] = Field(default=None, max_length=50)
    lead_pro_id: Optional[str] = None
    start_date: Optional[date] = None
    notes: Optional[str] = Field(default=None, max_length=5000)


class ClientUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    company_id: Optional[str] = None
    status: Optional[ClientStatus] = None
    billing_model: Optional[BillingModel] = None
    retainer_hours: Optional[float] = Field(default=None, ge=0, le=10_000)
    retainer_period: Optional[RetainerPeriod] = None
    rollover_unused: Optional[bool] = None
    billing_rate: Optional[float] = Field(default=None, ge=0, le=100_000)
    project_fee: Optional[float] = Field(default=None, ge=0, le=10_000_000)
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    industry: Optional[str] = Field(default=None, max_length=100)
    headcount: Optional[int] = Field(default=None, ge=0, le=1_000_000)
    jurisdictions: Optional[list[str]] = None
    contact_name: Optional[str] = Field(default=None, max_length=255)
    contact_email: Optional[str] = Field(default=None, max_length=320)
    contact_phone: Optional[str] = Field(default=None, max_length=50)
    lead_pro_id: Optional[str] = None
    start_date: Optional[date] = None
    notes: Optional[str] = Field(default=None, max_length=5000)


class AssignmentCreateRequest(BaseModel):
    pro_user_id: str
    role: AssignmentRole = "consultant"


class ScopeItemCreateRequest(BaseModel):
    service_category: str = Field(default="other", max_length=40)
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=5000)
    status: ScopeStatus = "planned"
    priority: Priority = "medium"


class ScopeItemUpdateRequest(BaseModel):
    service_category: Optional[str] = Field(default=None, max_length=40)
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=5000)
    status: Optional[ScopeStatus] = None
    priority: Optional[Priority] = None


class TaskCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=5000)
    service_category: str = Field(default="other", max_length=40)
    scope_item_id: Optional[str] = None
    status: TaskStatus = "todo"
    priority: Priority = "medium"
    assignee_pro_id: Optional[str] = None
    due_date: Optional[date] = None
    estimated_hours: Optional[float] = Field(default=None, ge=0, le=10_000)
    billable: bool = True


class TaskUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=5000)
    service_category: Optional[str] = Field(default=None, max_length=40)
    scope_item_id: Optional[str] = None
    status: Optional[TaskStatus] = None
    priority: Optional[Priority] = None
    assignee_pro_id: Optional[str] = None
    due_date: Optional[date] = None
    estimated_hours: Optional[float] = Field(default=None, ge=0, le=10_000)
    billable: Optional[bool] = None


class TimeEntryCreateRequest(BaseModel):
    hours: float = Field(..., gt=0, le=10_000)
    task_id: Optional[str] = None
    entry_date: Optional[date] = None
    note: Optional[str] = Field(default=None, max_length=2000)
    billable: bool = True
    service_category: Optional[str] = Field(default=None, max_length=40)
    pro_id: Optional[str] = None  # defaults to the acting admin
