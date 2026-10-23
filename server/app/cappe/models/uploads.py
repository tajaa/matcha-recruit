"""Pydantic shapes — uploads, asset library, AI image generation."""
from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

class CappeAsset(BaseModel):
    """A row in the per-site image asset library (`cappe_assets`, migrations
    zzzzcappe23 + cappemag01) — a catalog entry over an S3 object that already
    exists; deleting the row never deletes the blob (see routes/uploads.py).

    `credit_line` is what a story prints under the picture; an AI image's is
    always "AI illustration". `variants` holds the responsive sizes a library
    upload is stored with (`{"webp": [{"w", "url"}], "share": {"w", "url"}}`)."""
    id: UUID
    kind: Literal["generated", "upload", "stock", "edit"]
    url: str
    prompt: Optional[str] = None
    aspect: Optional[str] = None
    image_size: Optional[str] = None
    created_at: datetime
    source: Optional[str] = None
    source_url: Optional[str] = None
    title: Optional[str] = None
    creator: Optional[str] = None
    creator_url: Optional[str] = None
    license: Optional[str] = None
    license_version: Optional[str] = None
    license_url: Optional[str] = None
    provider_label: Optional[str] = None
    credit_line: Optional[str] = None
    alt: Optional[str] = None
    caption: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    bytes: Optional[int] = None
    mime: Optional[str] = None
    variants: dict = Field(default_factory=dict)
    ai_generated: bool = False
    rights_attested_at: Optional[datetime] = None
    moderation: str = "unchecked"
    updated_at: Optional[datetime] = None
    # An edited picture (kind `edit`, cappemag10): the picture its pixels came
    # from, what was done (services/magazine/studio/recipe.py), and whether the
    # pixels differ from the source's (its credit then says "(adapted)").
    parent_asset_id: Optional[UUID] = None
    recipe: Optional[dict] = None
    adapted: bool = False


class CappeAssetPatch(BaseModel):
    """Owner edits to a library image. Alt text and caption on any image; the
    credit, title and creator only on the owner's own (non-AI) uploads — the
    route answers 422 for the rest."""
    alt: Optional[str] = Field(default=None, max_length=500)
    caption: Optional[str] = Field(default=None, max_length=1000)
    title: Optional[str] = Field(default=None, max_length=500)
    creator: Optional[str] = Field(default=None, max_length=300)
    credit_line: Optional[str] = Field(default=None, max_length=500)


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
    "CappeAssetPatch",
    "CappeUploadResponse",
    "CappeImageGenRequest",
]
