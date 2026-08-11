"""Pydantic shapes — Cappe creator marketplace (profiles, socials, portfolio, rates)."""
import re
from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

SocialPlatform = Literal["instagram", "tiktok", "youtube", "x", "twitch", "facebook", "linkedin", "other"]
DeliverableType = Literal["post", "reel", "story", "video", "short", "stream", "ugc", "blog", "other"]

_HANDLE_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,29}$")

# Directory facet vocab — the only niches the UI offers (free-text rejected).
CREATOR_NICHES = [
    "fitness", "beauty", "fashion", "food", "travel", "tech", "gaming",
    "music", "art", "parenting", "finance", "health", "sports", "comedy",
    "education", "lifestyle", "outdoors", "pets", "diy", "other",
]


class CreatorProfileCreate(BaseModel):
    handle: str = Field(min_length=3, max_length=30)
    display_name: str = Field(min_length=1, max_length=120)

    @field_validator("handle")
    @classmethod
    def _handle_shape(cls, v: str) -> str:
        v = v.strip().lower().lstrip("@")
        if not _HANDLE_RE.match(v):
            raise ValueError("Handle must be 3-30 chars: a-z, 0-9, - or _, starting with a letter or digit")
        return v


class CreatorProfileUpdate(BaseModel):
    display_name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    avatar_url: Optional[str] = None
    cover_url: Optional[str] = None
    bio: Optional[str] = Field(default=None, max_length=2000)
    location: Optional[str] = Field(default=None, max_length=120)
    niches: Optional[list[str]] = Field(default=None, max_length=6)
    languages: Optional[list[str]] = Field(default=None, max_length=6)
    open_to_offers: Optional[bool] = None

    @field_validator("niches")
    @classmethod
    def _known_niches(cls, v):
        if v is None:
            return v
        bad = [n for n in v if n not in CREATOR_NICHES]
        if bad:
            raise ValueError(f"Unknown niches: {', '.join(bad)}")
        return v


class CreatorSocialUpsert(BaseModel):
    platform: SocialPlatform
    handle: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=8, max_length=500)   # https://… enforced below
    follower_count: Optional[int] = Field(default=None, ge=0, le=2_000_000_000)
    engagement_rate: Optional[float] = Field(default=None, ge=0, le=100)
    sort_order: int = 0

    @field_validator("url")
    @classmethod
    def _https(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith("https://"):
            raise ValueError("Social URL must start with https://")
        return v


class CreatorSocial(BaseModel):
    id: UUID
    platform: str
    handle: str
    url: str
    follower_count: Optional[int] = None
    engagement_rate: Optional[float] = None
    audit_status: str
    verified_follower_count: Optional[int] = None
    audited_at: Optional[datetime] = None
    sort_order: int


class CreatorPortfolioUpsert(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    media_url: Optional[str] = None
    media_type: Optional[Literal["image", "video"]] = None
    external_url: Optional[str] = Field(default=None, max_length=500)
    brand_name: Optional[str] = Field(default=None, max_length=120)
    metrics: dict[str, Any] = Field(default_factory=dict)
    sort_order: int = 0


class CreatorPortfolioItem(CreatorPortfolioUpsert):
    id: UUID
    created_at: datetime


class CreatorRateUpsert(BaseModel):
    deliverable_type: DeliverableType
    platform: SocialPlatform
    price_cents: int = Field(ge=0, le=100_000_000)
    negotiable: bool = True
    notes: Optional[str] = Field(default=None, max_length=500)
    sort_order: int = 0


class CreatorRate(CreatorRateUpsert):
    id: UUID


class CreatorProfileMe(BaseModel):
    """Own-profile response (any status)."""
    id: UUID
    handle: str
    display_name: str
    avatar_url: Optional[str] = None
    cover_url: Optional[str] = None
    bio: Optional[str] = None
    location: Optional[str] = None
    niches: list[str]
    languages: list[str]
    open_to_offers: bool
    status: str
    review_note: Optional[str] = None
    submitted_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    reach_verified: bool
    reach_audited_at: Optional[datetime] = None
    socials: list[CreatorSocial]
    portfolio: list[CreatorPortfolioItem]
    rates: list[CreatorRate]


class PublicCreatorCard(BaseModel):
    """Directory row."""
    handle: str
    display_name: str
    avatar_url: Optional[str] = None
    cover_url: Optional[str] = None
    bio: Optional[str] = None
    location: Optional[str] = None
    niches: list[str]
    reach_verified: bool
    max_followers: int
    max_engagement_rate: Optional[float] = None
    min_rate_cents: Optional[int] = None
    platforms: list[str]


class PublicCreatorProfile(BaseModel):
    """Full public profile page payload."""
    id: UUID                      # needed by the brand offer composer
    handle: str
    display_name: str
    avatar_url: Optional[str] = None
    cover_url: Optional[str] = None
    bio: Optional[str] = None
    location: Optional[str] = None
    niches: list[str]
    languages: list[str]
    open_to_offers: bool
    reach_verified: bool
    reach_audited_at: Optional[datetime] = None
    socials: list[CreatorSocial]          # flagged socials excluded server-side
    portfolio: list[CreatorPortfolioItem]
    rates: list[CreatorRate]


class PublicCreatorPage(BaseModel):
    creators: list[PublicCreatorCard]
    total: int
