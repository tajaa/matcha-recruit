"""Request model for D&O attestations."""

from typing import Optional
from pydantic import BaseModel, Field


class DoAttestation(BaseModel):
    item_key: str = Field(..., max_length=60)
    status: str = Field(..., pattern="^(in_place|partial|gap|unknown)$")
    note: Optional[str] = Field(None, max_length=2000)
