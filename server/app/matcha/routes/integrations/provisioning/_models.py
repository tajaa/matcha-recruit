"""Provisioning request/response models (J7 split)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.matcha.services.onboarding_orchestrator import (
    PROVIDER_GOOGLE_WORKSPACE,
    PROVIDER_SLACK,
)
from app.matcha.services.hris_service import PROVIDER_HRIS


class GoogleWorkspaceConnectionRequest(BaseModel):
    mode: str = Field(default="mock", pattern="^(mock|api_token|service_account)$")
    domain: Optional[str] = Field(default=None, max_length=255)
    admin_email: Optional[EmailStr] = None
    delegated_admin_email: Optional[EmailStr] = None
    default_org_unit: Optional[str] = Field(default=None, max_length=255)
    default_groups: list[str] = Field(default_factory=list)
    auto_provision_on_employee_create: bool = True
    access_token: Optional[str] = None
    service_account_json: Optional[str] = None
    test_connection: bool = True
class GoogleWorkspaceConnectionStatus(BaseModel):
    provider: str = PROVIDER_GOOGLE_WORKSPACE
    connected: bool
    status: str
    mode: Optional[str] = None
    domain: Optional[str] = None
    admin_email: Optional[str] = None
    delegated_admin_email: Optional[str] = None
    default_org_unit: Optional[str] = None
    default_groups: list[str] = Field(default_factory=list)
    auto_provision_on_employee_create: bool = True
    has_access_token: bool = False
    has_service_account_credentials: bool = False
    last_tested_at: Optional[datetime] = None
    last_error: Optional[str] = None
    updated_at: Optional[datetime] = None
class SlackConnectionRequest(BaseModel):
    client_id: Optional[str] = Field(default=None, max_length=255)
    client_secret: Optional[str] = None
    workspace_url: Optional[str] = Field(default=None, max_length=255)
    admin_email: Optional[EmailStr] = None
    default_channels: list[str] = Field(default_factory=list)
    oauth_scopes: list[str] = Field(default_factory=lambda: list(DEFAULT_SLACK_SCOPES))
    invite_link: Optional[str] = Field(default=None, max_length=500)
    auto_invite_on_employee_create: bool = True
    sync_display_name: bool = True
class SlackConnectionStatus(BaseModel):
    provider: str = PROVIDER_SLACK
    connected: bool
    status: str
    client_id: Optional[str] = None
    has_client_secret: bool = False
    workspace_url: Optional[str] = None
    admin_email: Optional[str] = None
    default_channels: list[str] = Field(default_factory=list)
    oauth_scopes: list[str] = Field(default_factory=lambda: list(DEFAULT_SLACK_SCOPES))
    invite_link: Optional[str] = None
    auto_invite_on_employee_create: bool = True
    sync_display_name: bool = True
    has_bot_token: bool = False
    slack_team_id: Optional[str] = None
    slack_team_name: Optional[str] = None
    slack_team_domain: Optional[str] = None
    bot_user_id: Optional[str] = None
    oauth_redirect_uri: Optional[str] = None
    default_oauth_redirect_uri: Optional[str] = None
    last_tested_at: Optional[datetime] = None
    last_error: Optional[str] = None
    updated_at: Optional[datetime] = None
class SlackOAuthStartResponse(BaseModel):
    authorize_url: str
    state: str
    redirect_uri: Optional[str] = None
    default_redirect_uri: Optional[str] = None
class ProvisioningStepStatusResponse(BaseModel):
    step_id: UUID
    step_key: str
    status: str
    attempts: int
    last_error: Optional[str] = None
    last_response: dict = Field(default_factory=dict)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
class ProvisioningRunStatusResponse(BaseModel):
    run_id: UUID
    company_id: UUID
    employee_id: UUID
    provider: str
    status: str
    trigger_source: str
    triggered_by: Optional[UUID] = None
    retry_of_run_id: Optional[str] = None
    last_error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    steps: list[ProvisioningStepStatusResponse] = Field(default_factory=list)
class ExternalIdentityResponse(BaseModel):
    provider: str
    external_user_id: Optional[str] = None
    external_email: Optional[str] = None
    status: str
    raw_profile: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
class EmployeeProvisioningStatusResponse(BaseModel):
    connection: GoogleWorkspaceConnectionStatus
    external_identity: Optional[ExternalIdentityResponse] = None
    runs: list[ProvisioningRunStatusResponse] = Field(default_factory=list)
class SlackEmployeeProvisioningStatusResponse(BaseModel):
    connection: SlackConnectionStatus
    external_identity: Optional[ExternalIdentityResponse] = None
    runs: list[ProvisioningRunStatusResponse] = Field(default_factory=list)
class ProvisioningRunListItem(BaseModel):
    run_id: UUID
    company_id: UUID
    employee_id: UUID
    employee_name: Optional[str] = None
    employee_email: Optional[str] = None
    provider: str
    status: str
    trigger_source: str
    triggered_by: Optional[UUID] = None
    last_error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
class HRISConnectionRequest(BaseModel):
    # `finch_mock` / `gusto_mock` route to the real provider class serving its own
    # mock dataset (see hris_service.get_hris_service) — plain `mock` is the base
    # ADP-shaped mock. `finch` is rejected below (OAuth-only).
    mode: str = Field(default="mock", pattern="^(mock|adp|gusto|finch|gusto_mock|finch_mock)$")
    base_url: Optional[str] = Field(default=None, max_length=500)
    client_id: Optional[str] = Field(default=None, max_length=255)
    client_secret: Optional[str] = None
    gusto_company_id: Optional[str] = Field(default=None, max_length=255)
    auto_sync_on_schedule: bool = False
    sync_interval_hours: int = Field(default=24, ge=1, le=168)
    test_connection: bool = True
class HRISConnectionStatus(BaseModel):
    provider: str = PROVIDER_HRIS
    connected: bool
    status: str
    mode: Optional[str] = None
    base_url: Optional[str] = None
    gusto_company_id: Optional[str] = None
    has_client_secret: bool = False
    auto_sync_on_schedule: bool = False
    sync_interval_hours: int = 24
    last_tested_at: Optional[datetime] = None
    last_error: Optional[str] = None
    last_sync_at: Optional[datetime] = None
    total_synced_employees: int = 0
    updated_at: Optional[datetime] = None
class HRISSyncRunResponse(BaseModel):
    sync_run_id: UUID
    status: str
    total_records: int = 0
    created_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    error_count: int = 0
    errors: list[dict] = Field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
class FinchSandboxConnectRequest(BaseModel):
    # Finch sandbox provider id, e.g. "gusto", "bamboo_hr", "justworks".
    provider_id: str = Field(default="gusto", max_length=64)
    employee_size: int = Field(default=20, ge=1, le=100)
class BenefitCreateRequest(BaseModel):
    type: str = Field(..., description="Benefit type, e.g. '401k' — must be in /hris/benefits/meta")
    description: str = Field(..., min_length=1, max_length=255)
    frequency: str = Field("every_paycheck", description="Deduction frequency the provider supports")
