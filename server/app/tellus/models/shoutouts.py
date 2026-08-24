"""Pydantic shapes for the brand shoutout radar."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


ShoutoutPlatform = Literal["instagram", "tiktok", "youtube", "facebook", "x"]
ShoutoutStatus = Literal["pending", "approved", "rejected", "expired"]


class ShoutoutHandleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    platform: ShoutoutPlatform
    handle: str = Field(min_length=1, max_length=120)

    @field_validator("handle")
    @classmethod
    def normalize_handle(cls, value: str) -> str:
        normalized = value.strip().lstrip("@").lower()
        if not normalized:
            raise ValueError("handle must not be blank")
        return normalized


class ShoutoutConfigPut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    brand_terms: list[str] = Field(default_factory=list, max_length=20)
    exclude_terms: list[str] = Field(default_factory=list, max_length=20)
    default_store_id: UUID | None = None
    offer_title: str | None = Field(default=None, max_length=120)
    offer_terms: str | None = Field(default=None, max_length=2000)
    offer_expiry_days: int = Field(default=14, ge=1, le=365)
    min_confidence: int = Field(default=60, ge=0, le=100)
    lookback_days: int = Field(default=14, ge=1, le=90)
    require_app_install: bool = False
    handles: list[ShoutoutHandleIn] = Field(default_factory=list, max_length=20)

    @field_validator("brand_terms", "exclude_terms")
    @classmethod
    def normalize_terms(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))


class ShoutoutEnableIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool


class ShoutoutManualScanIn(ShoutoutHandleIn):
    """One-off public-post search target; it is never saved as a brand handle."""
    max_results: int = Field(default=10, ge=1, le=100)


class ShoutoutRejectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str | None = Field(default=None, max_length=1000)


class ShoutoutApproveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_request_id: UUID
    store_id: UUID | None = None
    title: str | None = Field(default=None, min_length=1, max_length=120)
    terms: str | None = Field(default=None, max_length=2000)
    expiry_days: int | None = Field(default=None, ge=1, le=365)


class ShoutoutTestPostIn(BaseModel):
    """Brand-entered fixture for exercising the radar review flow."""
    model_config = ConfigDict(extra="forbid")
    platform: ShoutoutPlatform
    post_url: str = Field(min_length=8, max_length=2_048)
    author_handle: str = Field(min_length=1, max_length=120)
    excerpt: str = Field(min_length=1, max_length=2_000)

    @field_validator("author_handle")
    @classmethod
    def normalize_author_handle(cls, value: str) -> str:
        return value.strip().lstrip("@").lower()


class ShoutoutTestPostOut(BaseModel):
    run_id: UUID
    mention_id: UUID | None = None
    created: bool


class ShoutoutMentionOut(BaseModel):
    id: UUID
    platform: ShoutoutPlatform
    post_url: str
    author_handle: str | None
    excerpt: str | None
    confidence: int
    matched_terms: list[str]
    corroborated: bool
    is_test: bool
    status: ShoutoutStatus
    seen_count: int
    first_seen_at: datetime
    last_seen_at: datetime
    decided_at: datetime | None = None
    like_count: int | None = None
    comment_count: int | None = None
    author_followers: int | None = None
    author_verified: bool | None = None
    posted_age: str | None = None
    image_url: str | None = None
    stats_source: Literal["search", "profile_api"] | None = None
    stats_status: Literal["ok", "not_found", "unsupported", "error"] | None = None
    stats_fetched_at: datetime | None = None


class ShoutoutStatsOut(BaseModel):
    like_count: int | None = None
    comment_count: int | None = None
    author_followers: int | None = None
    author_verified: bool | None = None
    posted_age: str | None = None
    image_url: str | None = None
    stats_source: Literal["search", "profile_api"] | None = None
    stats_status: Literal["ok", "not_found", "unsupported", "error"] | None = None
    stats_fetched_at: datetime | None = None


class ShoutoutConfigOut(BaseModel):
    is_enabled: bool
    brand_terms: list[str]
    exclude_terms: list[str]
    default_store_id: UUID | None
    offer_title: str | None
    offer_terms: str | None
    offer_expiry_days: int
    min_confidence: int
    lookback_days: int
    require_app_install: bool
    handles: list[ShoutoutHandleIn]
    platform_coverage: dict[str, Literal["good", "partial", "poor"]]
    last_scanned_at: datetime | None = None
    next_scan_after: datetime | None = None


class ShoutoutRunOut(BaseModel):
    id: UUID
    status: Literal["running", "completed", "failed"]
    trigger: Literal["scheduled", "admin", "manual", "test"]
    started_at: datetime
    finished_at: datetime | None = None
    gemini_calls: int
    grounding_uris: int
    grounding_resolved: int
    candidates_returned: int
    urls_rejected: int
    mentions_new: int
    mentions_duplicate: int
    error: str | None = None
    source_mismatch_rejected: int = 0
    invalid_candidates_rejected: int = 0
    below_confidence_rejected: int = 0


class ShoutoutScanResultOut(BaseModel):
    new: int
    duplicate: int
    source_mismatch_rejected: int
    invalid_candidates_rejected: int
    below_confidence_rejected: int
