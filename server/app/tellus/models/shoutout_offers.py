"""Pydantic shapes for approved shoutout offers."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ShoutoutOfferOut(BaseModel):
    id: UUID
    mention_id: UUID
    campaign_id: UUID
    store_id: UUID | None
    store_name: str | None
    offer_token: str
    claim_url: str
    short_code: str
    reward_text: str
    status: Literal["sent", "claimed", "revoked"]
    claim_expires_at: datetime
    claimed_account_id: UUID | None = None
    claimed_at: datetime | None = None
    created_by: UUID | None = None
    created_at: datetime


class ShoutoutOfferPreviewOut(BaseModel):
    brand_name: str
    brand_logo_url: str | None
    store_name: str | None
    reward_text: str
    offer_terms: str | None
    short_code: str
    claim_expires_at: datetime
    available: bool
    already_claimed: bool = False
    card_token: str | None = None


class ShoutoutOfferClaimOut(BaseModel):
    offer_id: UUID
    card_token: str
    reward_text: str
    store_name: str | None
    claim_expires_at: datetime
    created: bool


class ShoutoutOfferRevokeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str | None = Field(default=None, max_length=1000)
