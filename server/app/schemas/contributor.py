import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


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


class ContributorRead(ContributorBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
