import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TrackCreate(BaseModel):
    recording_id: uuid.UUID
    disc_number: int = 1
    position: int | None = None


class TrackUpdate(BaseModel):
    disc_number: int | None = None
    position: int | None = None
    title_override: str | None = None


class TrackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    release_id: uuid.UUID
    recording_id: uuid.UUID
    disc_number: int
    position: int
    title_override: str | None
    created_at: datetime
    updated_at: datetime


class TrackReorder(BaseModel):
    track_ids: list[uuid.UUID]
