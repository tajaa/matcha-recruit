import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import WriterRole

ISWC_PATTERN = r"^T\d{10}$"
LANGUAGE_PATTERN = r"^[a-z]{2}$"


class WorkBase(BaseModel):
    title: str
    iswc: str | None = Field(default=None, pattern=ISWC_PATTERN)
    language: str | None = Field(default=None, pattern=LANGUAGE_PATTERN)
    notes: str | None = None


class WorkCreate(WorkBase):
    pass


class WorkUpdate(BaseModel):
    title: str | None = None
    iswc: str | None = Field(default=None, pattern=ISWC_PATTERN)
    language: str | None = Field(default=None, pattern=LANGUAGE_PATTERN)
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
    share_pct: Decimal = Field(ge=0, le=100)
    publisher_name: str | None = None
    publisher_share_pct: Decimal | None = Field(default=None, ge=0, le=100)


class WorkWriterRead(WorkWriterIn):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    work_id: uuid.UUID
