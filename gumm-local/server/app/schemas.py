from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class BusinessRegister(BaseModel):
    business_name: str = Field(min_length=2, max_length=255)
    owner_name: str = Field(min_length=2, max_length=255)
    owner_email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    initial_cafe_name: str = Field(default="Main Cafe", min_length=2, max_length=255)
    initial_neighborhood: str | None = Field(default=None, max_length=255)
    initial_accent_color: str = Field(default="#B15A38", pattern=r"^#[0-9A-Fa-f]{6}$")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class TeamMemberCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: Literal["admin", "staff"]


class BusinessSettingsUpdate(BaseModel):
    business_name: str | None = Field(default=None, min_length=2, max_length=255)
    timezone: str | None = Field(default=None, min_length=2, max_length=100)
    currency: str | None = Field(default=None, min_length=3, max_length=10)
    sender_name: str | None = Field(default=None, max_length=255)
    sender_email: EmailStr | None = None
    loyalty_message: str | None = Field(default=None, max_length=1200)
    vip_label: str | None = Field(default=None, min_length=2, max_length=120)


class BusinessMediaUpdate(BaseModel):
    caption: str | None = Field(default=None, max_length=500)
    sort_order: int | None = Field(default=None, ge=0, le=999)


class CafeCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    neighborhood: str | None = Field(default=None, max_length=255)
    accent_color: str = Field(default="#B15A38", pattern=r"^#[0-9A-Fa-f]{6}$")


class CafeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    neighborhood: str | None = Field(default=None, max_length=255)
    accent_color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")


class RewardProgramCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    visits_required: int = Field(ge=1, le=50)
    reward_description: str = Field(min_length=2, max_length=500)


class RewardProgramUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    visits_required: int | None = Field(default=None, ge=1, le=50)
    reward_description: str | None = Field(default=None, min_length=2, max_length=500)
    active: bool | None = None


class LocalCreate(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    email: EmailStr | None = None
    favorite_order: str | None = Field(default=None, max_length=300)
    notes: str | None = Field(default=None, max_length=500)
    is_vip: bool = False


class LocalUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    email: EmailStr | None = None
    favorite_order: str | None = Field(default=None, max_length=300)
    notes: str | None = Field(default=None, max_length=500)
    is_vip: bool | None = None


class VisitCreate(BaseModel):
    program_id: UUID | None = None
    order_total: Decimal | None = Field(default=None, ge=0)
    visit_note: str | None = Field(default=None, max_length=500)


class RedemptionCreate(BaseModel):
    program_id: UUID
    redemption_note: str | None = Field(default=None, max_length=500)


class EmailCampaignCreate(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    subject: str = Field(min_length=2, max_length=255)
    body: str = Field(min_length=2, max_length=5000)
    target_segment: Literal["all", "vip", "regular", "reward_ready"] = "all"
    send_now: bool = True


class CafeOut(BaseModel):
    id: UUID
    name: str
    neighborhood: str | None
    accent_color: str
    created_at: datetime


class ProgramOut(BaseModel):
    id: UUID
    cafe_id: UUID
    name: str
    visits_required: int
    reward_description: str
    active: bool
    created_at: datetime
