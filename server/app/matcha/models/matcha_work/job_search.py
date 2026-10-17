"""Bounded job-search bodies for the Espresso Job search REST API."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

UserState = Literal["new", "saved", "applied", "dismissed"]
RemotePreference = Literal["any", "remote_only", "onsite_only"]


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def _clean_list(values: list[str], limit: int) -> list[str]:
    out, seen = [], set()
    for value in values:
        text = " ".join(str(value).split())[:limit]
        if text and text.casefold() not in seen:
            seen.add(text.casefold())
            out.append(text)
    return out


class JobWeights(Body):
    """How much each part counts in the ranking, 0..1 each (renormalized)."""

    base: float = Field(default=0.45, ge=0, le=1)
    bonus: float = Field(default=0.2, ge=0, le=1)
    equity: float = Field(default=0.2, ge=0, le=1)
    fit: float = Field(default=0.15, ge=0, le=1)

    @field_validator("fit")
    @classmethod
    def something_counts(cls, value, info):
        others = sum(float(info.data.get(k) or 0) for k in ("base", "bonus", "equity"))
        if others + value <= 0:
            raise ValueError("At least one weight must be above zero.")
        return value


class JobCriteria(Body):
    titles: list[str] = Field(default_factory=list, max_length=8)
    locations: list[str] = Field(default_factory=list, max_length=6)
    remote: RemotePreference = "any"
    base_floor: int | None = Field(default=None, ge=0, le=10_000_000)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    seniority: str = Field(default="", max_length=60)
    industries: list[str] = Field(default_factory=list, max_length=8)
    exclude_companies: list[str] = Field(default_factory=list, max_length=30)
    deal_breakers: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("titles", "locations", "industries")
    @classmethod
    def short_items(cls, values):
        return _clean_list(values, 80)

    @field_validator("exclude_companies")
    @classmethod
    def companies(cls, values):
        return _clean_list(values, 120)

    @field_validator("deal_breakers")
    @classmethod
    def breakers(cls, values):
        return _clean_list(values, 160)

    @field_validator("currency")
    @classmethod
    def code(cls, value):
        value = value.upper()
        if not value.isalpha():
            raise ValueError("Use a three-letter currency code, like USD.")
        return value


class JobSearchCreate(Body):
    request_id: UUID
    title: str = Field(default="", max_length=120)
    ask: str = Field(min_length=3, max_length=4000)
    criteria: JobCriteria = Field(default_factory=JobCriteria)
    weights: JobWeights | None = None
    use_resume: bool = False
    # The `jobs` disclosure version the person just agreed to, when they had not yet.
    consent_version: str | None = Field(default=None, max_length=40)


class LeadPatch(Body):
    user_state: UserState | None = None
    notes: str | None = Field(default=None, max_length=4000)


class EmailDraftRequest(Body):
    # Only the draft already in Gmail: never make one. A job's Edit draft asks
    # this way, so a draft that was sent or deleted in Gmail isn't quietly made
    # again; making a new one is its own click.
    existing_only: bool = False
