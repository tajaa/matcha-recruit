import uuid
from datetime import datetime

from pydantic import AliasPath, BaseModel, ConfigDict, Field, field_validator


class TrackCreate(BaseModel):
    recording_id: uuid.UUID
    disc_number: int = Field(default=1, ge=1)
    position: int | None = Field(default=None, ge=1)


class TrackUpdate(BaseModel):
    disc_number: int | None = Field(default=None, ge=1)
    position: int | None = Field(default=None, ge=1)
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


class TrackReadWithRecording(TrackRead):
    recording_title: str = Field(validation_alias=AliasPath("recording", "title"))
    recording_isrc: str | None = Field(default=None, validation_alias=AliasPath("recording", "isrc"))


class TrackReorder(BaseModel):
    disc_number: int = 1
    track_ids: list[uuid.UUID]

    @field_validator("track_ids")
    @classmethod
    def _no_duplicates(cls, v: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(set(v)) != len(v):
            raise ValueError("track_ids must not contain duplicates")
        return v
