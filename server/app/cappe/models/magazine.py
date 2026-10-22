"""Pydantic shapes — a site's magazine (cappemag02) and story previews."""
from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

MastheadStyle = Literal["classic", "literary", "modern", "elegant", "display"]


class CappeMagazine(BaseModel):
    """A site's magazine. `live` is whether its pages render now: turned on
    AND the owner's plan includes magazines."""
    site_id: UUID
    enabled: bool = False
    name: str
    tagline: Optional[str] = None
    about: Optional[str] = None
    masthead_style: MastheadStyle = "classic"
    accent: Optional[str] = None
    topics: list[str] = Field(default_factory=list)
    front_at_root: bool = False
    nav_label: str = "Magazine"
    cover_post_id: Optional[UUID] = None
    follow_enabled: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    live: bool = False
    plan_includes_magazine: bool = False


class CappeMagazineUpdate(BaseModel):
    enabled: Optional[bool] = None
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    tagline: Optional[str] = Field(default=None, max_length=200)
    about: Optional[str] = Field(default=None, max_length=4000)
    masthead_style: Optional[MastheadStyle] = None
    accent: Optional[str] = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    topics: Optional[list[str]] = Field(default=None, max_length=5)
    front_at_root: Optional[bool] = None
    nav_label: Optional[str] = Field(default=None, min_length=1, max_length=40)
    cover_post_id: Optional[UUID] = None
    follow_enabled: Optional[bool] = None


class CappeStoryPreview(BaseModel):
    """An unsaved story to render as its page would look."""
    title: str = Field(default="", max_length=255)
    excerpt: Optional[str] = Field(default=None, max_length=600)
    kicker: Optional[str] = Field(default=None, max_length=60)
    topic: Optional[str] = Field(default=None, max_length=40)
    layout: Optional[str] = Field(default=None, max_length=20)
    byline: Optional[str] = Field(default=None, max_length=160)
    cover_asset_id: Optional[UUID] = None
    access: Literal["free", "paid"] = "free"
    content: dict[str, Any] = Field(default_factory=dict)


class CappeStoryLayoutInfo(BaseModel):
    key: str
    label: str
    content: dict[str, Any]


class CappeStoryOptions(BaseModel):
    """What the story editor offers: layouts with their starter blocks, topics."""
    layouts: list[CappeStoryLayoutInfo]
    topics: list[dict[str, str]]


__all__ = [
    "MastheadStyle",
    "CappeMagazine",
    "CappeMagazineUpdate",
    "CappeStoryPreview",
    "CappeStoryLayoutInfo",
    "CappeStoryOptions",
]
