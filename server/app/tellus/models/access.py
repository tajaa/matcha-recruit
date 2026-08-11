"""Brand workspace access models shared by auth, team, and business routes."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


BrandRole = Literal["owner", "admin", "location_manager", "staff"]
BrandMembershipStatus = Literal["active", "suspended", "revoked"]
BrandCapability = Literal[
    "brand.update",
    "billing.manage",
    "team.manage",
    "stores.manage",
    "board.manage",
    "feedback.read",
    "feedback.manage",
    "comms.read",
    "comms.reply",
    "comms.assign",
    "comms.settings",
    "promos.manage",
    "scanners.manage",
    "rewards.manage",
    "redemptions.redeem",
]


class TellusBusinessStoreGrant(BaseModel):
    id: UUID
    name: str
    city: str | None = None
    state: str | None = None
    status: Literal["active", "archived"] = "active"


class TellusBusinessMembership(BaseModel):
    id: UUID
    brand_id: UUID
    brand_name: str
    brand_slug: str
    plan_status: str
    role: BrandRole
    status: BrandMembershipStatus
    all_stores: bool
    stores: list[TellusBusinessStoreGrant] = Field(default_factory=list)
    capabilities: set[BrandCapability] = Field(default_factory=set)


class TellusBrandInvite(BaseModel):
    id: UUID
    brand_id: UUID
    email: EmailStr
    role: Literal["admin", "location_manager", "staff"]
    all_stores: bool
    store_ids: list[UUID] = Field(default_factory=list)
    expires_at: datetime
    invited_by: UUID | None = None
    accepted_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime


class TellusBrandInviteCreate(BaseModel):
    email: EmailStr
    role: Literal["admin", "location_manager", "staff"]
    all_stores: bool = False
    store_ids: list[UUID] = Field(default_factory=list)


class TellusBrandMemberUpdate(BaseModel):
    role: Literal["admin", "location_manager", "staff"] | None = None
    status: Literal["active", "suspended", "revoked"] | None = None
    all_stores: bool | None = None
    store_ids: list[UUID] | None = None


class TellusOwnerTransfer(BaseModel):
    member_id: UUID
    password: str = Field(min_length=1, max_length=200)
