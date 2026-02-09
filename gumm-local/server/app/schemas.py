from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class CafeCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    neighborhood: str | None = Field(default=None, max_length=255)
    accent_color: str = Field(default="#B15A38", pattern=r"^#[0-9A-Fa-f]{6}$")


class RewardProgramCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    visits_required: int = Field(ge=1, le=50)
    reward_description: str = Field(min_length=2, max_length=500)


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
