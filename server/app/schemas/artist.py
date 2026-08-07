import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

COUNTRY_PATTERN = r"^[A-Z]{2}$"


class ArtistBase(BaseModel):
    name: str
    sort_name: str | None = None
    country: str | None = Field(default=None, pattern=COUNTRY_PATTERN)
    spotify_id: str | None = None
    apple_music_id: str | None = None
    notes: str | None = None


class ArtistCreate(ArtistBase):
    pass


class ArtistUpdate(BaseModel):
    name: str | None = None
    sort_name: str | None = None
    country: str | None = Field(default=None, pattern=COUNTRY_PATTERN)
    spotify_id: str | None = None
    apple_music_id: str | None = None
    notes: str | None = None


class ArtistRead(ArtistBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
