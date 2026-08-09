"""Pydantic request/response shapes for Tell-Us promo campaigns / reward cards."""
from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

CampaignStatus = Literal["active", "paused", "cancelled"]
EffectiveCardStatus = Literal["issued", "redeemed", "cancelled", "expired"]
ClaimUnavailableReason = Literal["ok", "cap_reached", "cancelled", "paused", "not_started", "ended"]


class CampaignCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    reward_text: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    max_claims: int = Field(ge=1, le=10000)
    card_expiry_days: int = Field(default=30, ge=1, le=365)
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None


class CampaignPatch(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=120)
    reward_text: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    ends_at: Optional[datetime] = None
    # Cancel is a one-way door with its own endpoint (invalidates cards) —
    # not reachable through this generic patch.
    status: Optional[Literal["active", "paused"]] = None


class CampaignStats(BaseModel):
    claimed: int
    redeemed: int
    outstanding: int
    expired: int
    cancelled: int


class CampaignOut(BaseModel):
    id: UUID
    title: str
    description: Optional[str]
    reward_text: str
    claim_token: str
    claim_url: str
    max_claims: int
    claim_count: int
    status: CampaignStatus
    card_expiry_days: int
    starts_at: Optional[datetime]
    ends_at: Optional[datetime]
    flyer_image_url: Optional[str]
    has_design: bool
    cancelled_at: Optional[datetime]
    created_at: datetime
    stats: Optional[CampaignStats] = None


class DesignPut(BaseModel):
    design_json: dict[str, Any]


class CancelOut(BaseModel):
    invalidated_count: int


class ScannerCreate(BaseModel):
    store_id: UUID
    label: Optional[str] = Field(default=None, max_length=80)


class ScannerOut(BaseModel):
    id: UUID
    store_id: UUID
    store_name: str
    label: Optional[str]
    token: str
    scanner_url: str
    is_active: bool
    created_at: datetime


class ClaimPreviewOut(BaseModel):
    brand_name: str
    brand_logo_url: Optional[str]
    title: str
    reward_text: str
    description: Optional[str]
    flyer_image_url: Optional[str]
    available: bool
    reason: ClaimUnavailableReason
    already_claimed: bool
    card_token: Optional[str] = None


class CardOut(BaseModel):
    id: UUID
    card_token: str
    card_url: str
    status: EffectiveCardStatus
    campaign_title: str
    reward_text: str
    brand_name: str
    brand_logo_url: Optional[str]
    issued_at: datetime
    expires_at: datetime
    redeemed_at: Optional[datetime]
    redeemed_store_name: Optional[str]


class ClaimOut(CardOut):
    created: bool


class RedeemIn(BaseModel):
    card_token: str = Field(min_length=1, max_length=512)


class RedeemOut(BaseModel):
    campaign_title: str
    reward_text: str
    redeemed_at: datetime
    store_name: Optional[str]


class ScanBootstrapOut(BaseModel):
    store_name: str
    brand_name: str
    brand_logo_url: Optional[str]
