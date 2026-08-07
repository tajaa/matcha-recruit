import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.enums import CreditRole


class RecordingBase(BaseModel):
    title: str
    version: str | None = None
    explicit: bool | None = None
    language: str | None = None
    recording_year: int | None = None
    primary_artist_id: uuid.UUID


class RecordingCreate(RecordingBase):
    pass


class RecordingUpdate(BaseModel):
    title: str | None = None
    version: str | None = None
    explicit: bool | None = None
    language: str | None = None
    recording_year: int | None = None
    primary_artist_id: uuid.UUID | None = None


class RecordingRead(RecordingBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    isrc: str | None
    audio_file_id: uuid.UUID | None
    duration_seconds: Decimal | None
    sample_rate: int | None
    bit_depth: int | None
    channels: int | None
    audio_format: str | None
    created_at: datetime
    updated_at: datetime


class CreditIn(BaseModel):
    contributor_id: uuid.UUID
    role: CreditRole
    credited_as: str | None = None
    position: int


class CreditRead(CreditIn):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    recording_id: uuid.UUID


class MasterSplitIn(BaseModel):
    contributor_id: uuid.UUID
    role: CreditRole | None = None
    share_pct: Decimal


class MasterSplitRead(MasterSplitIn):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    recording_id: uuid.UUID


class WorkLinksIn(BaseModel):
    work_ids: list[uuid.UUID]
