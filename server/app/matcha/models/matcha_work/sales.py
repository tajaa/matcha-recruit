"""Bounded sales campaign bodies, shared by REST and Espresso tools."""

from typing import Literal
from uuid import UUID
from urllib.parse import urlsplit
import re
from pydantic import BaseModel, ConfigDict, Field, field_validator

Stage = Literal["lead", "qualified", "proposal", "negotiation", "closed"]


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


MAX_BATCH = 50
FOOTER_PLACEHOLDER = "[Your business name and postal address]"


class CampaignCreate(Body):
    request_id: UUID
    title: str = Field(min_length=1, max_length=100)
    target: str = Field(default="", max_length=2000)
    offer: str = Field(default="", max_length=4000)
    footer: str = Field(default="", max_length=1000)


class CampaignPatch(Body):
    title: str | None = Field(default=None, min_length=1, max_length=100)
    target: str | None = Field(default=None, max_length=2000)
    offer: str | None = Field(default=None, max_length=4000)
    # The opt-out line and postal address every commercial message carries.
    footer: str | None = Field(default=None, max_length=1000)


class Prospect(Body):
    email: str = Field(default="", max_length=254)
    name: str = Field(default="", max_length=200)
    company: str = Field(default="", max_length=200)
    website: str = Field(default="", max_length=2000)
    notes: str = Field(default="", max_length=4000)
    sources: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("email")
    @classmethod
    def mailbox(cls, value):
        if value and not re.fullmatch(
            r"[^\s@,;<>\r\n]+@[^\s@,;<>\r\n]+\.[^\s@,;<>\r\n]+", value
        ):
            raise ValueError("Use one complete email address per prospect.")
        return value.lower()

    @field_validator("website")
    @classmethod
    def site(cls, value):
        if value:
            public_url(value)
        return value

    @field_validator("sources")
    @classmethod
    def urls(cls, values):
        for value in values:
            public_url(value)
        return list(dict.fromkeys(values))


def public_url(value):
    parsed = urlsplit(value)
    if (
        len(value) > 2000
        or parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise ValueError("Sources and websites must be HTTP or HTTPS URLs.")


class ProspectImport(Body):
    prospects: list[Prospect] = Field(min_length=1, max_length=1000)


class ProspectPatch(Body):
    stage: Stage | None = None
    research: str | None = Field(default=None, max_length=6000)
    sources: list[str] | None = Field(default=None, max_length=10)
    subject: str | None = Field(default=None, max_length=300)
    body: str | None = Field(default=None, max_length=12000)
    email: str | None = Field(default=None, max_length=254)
    # Compare against the draft the person actually opened, not an intervening agent edit.
    review_token: str | None = Field(default=None, max_length=64)

    @field_validator("email")
    @classmethod
    def mailbox(cls, value):
        return Prospect.mailbox(value) if value is not None else value

    @field_validator("sources")
    @classmethod
    def urls(cls, values):
        return Prospect.urls(values) if values is not None else values

    @field_validator("subject")
    @classmethod
    def single_line(cls, value):
        if value is not None and ("\n" in value or "\r" in value):
            raise ValueError("Subject must be one line.")
        return value


class Template(Body):
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=12000)


class ApprovedDraft(Body):
    id: UUID
    review_token: str = Field(min_length=64, max_length=64)


class SendBatch(Body):
    request_id: UUID
    sender: str = Field(min_length=1, max_length=254)
    # Small enough that a person can read every message they approve.
    drafts: list[ApprovedDraft] = Field(min_length=1, max_length=MAX_BATCH)


class CampaignAction(Body):
    action: Literal["pause", "resume", "release_pending", "retry_failed"]


class ResolveUnknown(Body):
    """The person checked Gmail Sent for an unconfirmed message."""

    outcome: Literal["sent", "not_sent"]
