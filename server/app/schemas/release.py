import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import ReleaseStatus, ReleaseType


class ReleaseBase(BaseModel):
    title: str
    release_type: ReleaseType
    release_date: date | None = None
    original_release_date: date | None = None
    label_name: str | None = None
    c_line: str | None = None
    p_line: str | None = None
    genre: str | None = None
    subgenre: str | None = None
    territories: str = "WW"
    primary_artist_id: uuid.UUID
    catalog_number: str | None = None
    notes: str | None = None


class ReleaseCreate(ReleaseBase):
    pass


class ReleaseUpdate(BaseModel):
    title: str | None = None
    release_type: ReleaseType | None = None
    status: ReleaseStatus | None = None
    release_date: date | None = None
    original_release_date: date | None = None
    label_name: str | None = None
    c_line: str | None = None
    p_line: str | None = None
    genre: str | None = None
    subgenre: str | None = None
    territories: str | None = None
    primary_artist_id: uuid.UUID | None = None
    catalog_number: str | None = None
    notes: str | None = None


class ReleaseRead(ReleaseBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: ReleaseStatus
    upc: str | None
    artwork_file_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
