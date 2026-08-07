import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class ContributorBase(BaseModel):
    name: str
    legal_name: str | None = None
    ipi_number: str | None = None
    pro_affiliation: str | None = None
    email: str | None = None
    notes: str | None = None


class ContributorCreate(ContributorBase):
    pass


class ContributorUpdate(BaseModel):
    name: str | None = None
    legal_name: str | None = None
    ipi_number: str | None = None
    pro_affiliation: str | None = None
    email: str | None = None
    notes: str | None = None

    @field_validator("name", mode="before")
    @classmethod
    def _not_explicit_null(cls, v, info):
        if v is None:
            raise ValueError(f"{info.field_name} cannot be null")
        return v


class ContributorRead(ContributorBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
