import uuid

from pydantic import BaseModel, Field, field_validator


class IsrcConfigRead(BaseModel):
    registrant_prefix: str
    year_digits: str
    next_designation: int


class IsrcConfigUpdate(BaseModel):
    registrant_prefix: str = Field(min_length=5, max_length=5, pattern=r"^[A-Z]{2}[A-Z0-9]{3}$")

    @field_validator("registrant_prefix", mode="before")
    @classmethod
    def _normalize(cls, v: str) -> str:
        if isinstance(v, str):
            return v.strip().upper()
        return v


class UpcAddIn(BaseModel):
    codes: list[str]


class UpcAddResult(BaseModel):
    added: int
    rejected: list[str]
    skipped: int


class UpcListItem(BaseModel):
    id: uuid.UUID
    code: str
    status: str
    release_id: uuid.UUID | None


class UpcListResponse(BaseModel):
    items: list[UpcListItem]
    available: int
    assigned: int


class AssignIsrcResult(BaseModel):
    isrc: str


class AssignUpcResult(BaseModel):
    upc: str
