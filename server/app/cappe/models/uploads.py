"""Pydantic shapes — uploads, asset library, AI image generation."""
from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

class CappeAsset(BaseModel):
    """A row in the per-site image asset library (`cappe_assets`, migration
    zzzzcappe23) — a catalog entry over an S3 object that already exists;
    deleting the row never deletes the blob (see routes/assets.py)."""
    id: UUID
    kind: Literal["generated", "upload"]
    url: str
    prompt: Optional[str] = None
    aspect: Optional[str] = None
    image_size: Optional[str] = None
    created_at: datetime


class CappeAssetList(BaseModel):
    assets: list[CappeAsset] = Field(default_factory=list)


class CappeUploadResponse(BaseModel):
    url: str


class CappeImageGenRequest(BaseModel):
    """AI image generation for a site (see routes/uploads.py). prompt is length-
    capped (abuse guard); aspect_ratio/image_size are normalized against
    image_gen's whitelists server-side, so an unknown value degrades to the
    default rather than a 422 — resolution is a quality knob, not worth
    failing a generation over.

    style/mood are optional wizard direction (a chip label like "Cinematic",
    free text, or omitted for "you decide") — `image_prompting.build_image_prompt`
    expands them into a fuller prompt before it reaches Gemini. `prompt` itself
    stays the user's own words unmodified; it's what's stored on the asset
    catalog row, so a user reviewing their library sees what THEY asked for."""
    prompt: str = Field(min_length=1, max_length=1000)
    aspect_ratio: str = Field(default="16:9", max_length=8)
    image_size: Optional[str] = Field(default=None, max_length=8)
    style: Optional[str] = Field(default=None, max_length=120)
    mood: Optional[str] = Field(default=None, max_length=120)


__all__ = [
    "CappeAsset",
    "CappeAssetList",
    "CappeUploadResponse",
    "CappeImageGenRequest",
]
