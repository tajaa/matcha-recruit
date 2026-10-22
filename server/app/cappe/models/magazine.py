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





# ── Open imagery (cappemag03) ───────────────────────────────────────────────
StockSource = Literal["openverse", "smithsonian", "met", "nasa"]


class CappeStockResult(BaseModel):
    """A picture an archive offers. `thumb` is our own signed thumbnail link
    (routes/public/stock.py); `imported` says it's already in the library."""
    source: StockSource
    source_id: str
    title: str = ""
    creator: str = ""
    license: str
    license_version: str = ""
    license_url: str = ""
    provider_label: str = ""
    landing_url: str = ""
    credit_line: str = ""
    width: Optional[int] = None
    height: Optional[int] = None
    thumb: str = ""
    imported: bool = False


class CappeStockSearch(BaseModel):
    source: StockSource
    query: str
    page: int
    results: list[CappeStockResult]
    has_more: bool


class CappeStockKey(BaseModel):
    source: StockSource
    source_id: str = Field(min_length=1, max_length=200)


class CappeStockImportRequest(BaseModel):
    items: list[CappeStockKey] = Field(min_length=1, max_length=24)
    post_id: Optional[UUID] = None


class CappeStockTopicRequest(BaseModel):
    topic: str = Field(max_length=40)
    count: int = Field(default=12, ge=1, le=24)
    post_id: Optional[UUID] = None


class CappeStockImport(BaseModel):
    id: UUID
    source: StockSource
    source_id: str
    status: Literal["pending", "working", "ready", "failed", "refused"]
    error: Optional[str] = None
    asset_id: Optional[UUID] = None
    asset: Optional[dict[str, Any]] = None
    created_at: datetime


class CappeStockImports(BaseModel):
    imports: list[CappeStockImport]
    remaining_today: Optional[int] = None


__all__ = [
    "MastheadStyle",
    "CappeMagazine",
    "CappeMagazineUpdate",
    "CappeStoryPreview",
    "CappeStoryLayoutInfo",
    "CappeStoryOptions",
    "StockSource",
    "CappeStockResult",
    "CappeStockSearch",
    "CappeStockKey",
    "CappeStockImportRequest",
    "CappeStockTopicRequest",
    "CappeStockImport",
    "CappeStockImports",
]
