import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.oceanlab.models.enums import ArtistRole, ReleaseStatus, ReleaseType


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
    # Optional on create ONLY so label settings can supply it (see
    # services/defaults.apply_release_defaults). The column is NOT NULL and
    # the route 422s when neither the payload nor the defaults provide one.
    primary_artist_id: uuid.UUID | None = None
    # Same reason: omitted means "use the label default", whereas
    # ReleaseBase's "WW" would mask the setting entirely.
    territories: str | None = None


class ReleaseUpdate(BaseModel):
    title: str | None = None
    release_type: ReleaseType | None = None
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

    @field_validator(
        "title",
        "release_type",
        "territories",
        "label_name",
        "primary_artist_id",
        mode="before",
    )
    @classmethod
    def _not_explicit_null(cls, v, info):
        if v is None:
            raise ValueError(f"{info.field_name} cannot be null")
        return v


class ReleaseRead(ReleaseBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: ReleaseStatus
    upc: str | None
    artwork_file_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class ReleaseArtistIn(BaseModel):
    artist_id: uuid.UUID
    role: ArtistRole
    position: int


class ReleaseArtistRead(ReleaseArtistIn):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    release_id: uuid.UUID


class ReleaseArtistsIn(BaseModel):
    """Replace-all payload for a release's artist credits.

    The DB unique is (release_id, artist_id, role), so the same artist may
    appear once as primary and once as featured — dedupe on the pair, not on
    artist_id alone, or a legitimate credit becomes unexpressible.
    """

    artists: list[ReleaseArtistIn]

    @model_validator(mode="after")
    def _no_duplicate_artist_role(self):
        pairs = [(a.artist_id, a.role) for a in self.artists]
        if len(set(pairs)) != len(pairs):
            raise ValueError("artists must not repeat the same (artist_id, role) pair")
        return self
