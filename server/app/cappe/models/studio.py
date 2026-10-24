"""Reusable editorial collections in the creator's Studio library."""
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class StudioCollectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    doc: dict[str, Any]
    # Older clients omit this; new clients reuse it after a lost response.
    request_id: UUID | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value or any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in value):
            raise ValueError("Give the collection a name.")
        return value
