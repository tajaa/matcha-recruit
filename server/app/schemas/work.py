import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.enums import WriterRole


class WorkBase(BaseModel):
    title: str
    iswc: str | None = None
    language: str | None = None
    notes: str | None = None


class WorkCreate(WorkBase):
    pass


class WorkUpdate(BaseModel):
    title: str | None = None
    iswc: str | None = None
    language: str | None = None
    notes: str | None = None

    @field_validator("title", mode="before")
    @classmethod
    def _not_explicit_null(cls, v, info):
        if v is None:
            raise ValueError(f"{info.field_name} cannot be null")
        return v


class WorkRead(WorkBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class WorkWriterIn(BaseModel):
    contributor_id: uuid.UUID
    role: WriterRole
    share_pct: Decimal
    publisher_name: str | None = None
    publisher_share_pct: Decimal | None = None


class WorkWriterRead(WorkWriterIn):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    work_id: uuid.UUID
