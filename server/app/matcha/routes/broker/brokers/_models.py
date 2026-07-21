"""Broker-portal request/response models (J7 split)."""
from __future__ import annotations

from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class BrokerClientSetupCreateRequest(BaseModel):
    company_name: str = Field(..., min_length=2, max_length=255)
    industry: Optional[str] = Field(default=None, max_length=100)
    company_size: Optional[str] = Field(default=None, max_length=50)
    headcount: Optional[int] = Field(default=None, ge=1, le=100_000)
    contact_name: Optional[str] = Field(default=None, max_length=255)
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = Field(default=None, max_length=50)
    notes: Optional[str] = Field(default=None, max_length=2000)
    locations: list[dict] = Field(default_factory=list)
    preconfigured_features: dict[str, bool] = Field(default_factory=dict)
    onboarding_template: dict = Field(default_factory=dict)
    link_permissions: dict = Field(default_factory=dict)
    invite_immediately: bool = False
    invite_expires_days: int = Field(default=14, ge=1, le=90)
class BrokerClientSetupUpdateRequest(BaseModel):
    company_name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    industry: Optional[str] = Field(default=None, max_length=100)
    company_size: Optional[str] = Field(default=None, max_length=50)
    headcount: Optional[int] = Field(default=None, ge=1, le=100_000)
    contact_name: Optional[str] = Field(default=None, max_length=255)
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = Field(default=None, max_length=50)
    notes: Optional[str] = Field(default=None, max_length=2000)
    locations: Optional[list[dict]] = None
    preconfigured_features: Optional[dict[str, bool]] = None
    onboarding_template: Optional[dict] = None
class BrokerBatchClientSetupRequest(BaseModel):
    clients: list[BrokerClientSetupCreateRequest] = Field(..., min_length=1, max_length=50)
class BrokerClientSetupInviteRequest(BaseModel):
    expires_days: int = Field(default=14, ge=1, le=90)
class LiteReferralTokenCreateRequest(BaseModel):
    label: Optional[str] = Field(default=None, max_length=255)
    expires_days: Optional[int] = Field(default=None, ge=1, le=3650)
    payer: str = Field(default="business", pattern="^(broker|business)$")
class LiteReferralTokenResponse(BaseModel):
    id: str
    broker_id: str
    token: str
    label: Optional[str]
    created_at: str
    expires_at: Optional[str]
    is_active: bool
    use_count: int
    last_used_at: Optional[str]
    referral_url: str
    payer: str
class ClientSeatInviteCreateRequest(BaseModel):
    company_name: str = Field(..., min_length=2, max_length=255)
    seat_count: int = Field(..., ge=1, le=100_000)
    tier: Literal["matcha_lite", "matcha_x"] = "matcha_lite"
    expires_days: Optional[int] = Field(default=None, ge=1, le=3650)
class BrokerMemberCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    role: Literal["admin", "member"] = "member"
    password: Optional[str] = Field(default=None, min_length=8, max_length=255)
class BrokerSetupStageRequest(BaseModel):
    onboarding_stage: Literal["submitted", "under_review", "configuring", "live"]
