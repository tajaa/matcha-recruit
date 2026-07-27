"""Pydantic shapes — style presets (reusable saved looks: theme subset or
section _design)."""
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

class CappeStylePresetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    kind: Literal["theme", "section"]
    data: dict[str, Any] = Field(default_factory=dict)


class CappeStylePreset(BaseModel):
    id: UUID
    name: str
    kind: Literal["theme", "section"]
    data: dict[str, Any]
    created_at: datetime


__all__ = [
    "CappeStylePresetCreate",
    "CappeStylePreset",
]
