"""Bounded immutable display data. Neither tool arguments nor transcripts are accepted."""
from __future__ import annotations

import hashlib
import json
import unicodedata
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

Outcome = Literal["observed", "drafted", "confirmed", "dry_run", "held", "handoff", "declined", "failed", "unknown", "partial", "cancelled"]
State = Literal["collecting", "waiting", "queued", "rendering", "ready", "failed", "skipped", "expired", "deleted"]


def clip(value: object, limit: int = 160) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    cut = max(0, limit - 1)
    while cut and (unicodedata.combining(text[cut]) or text[cut] in "\ufe0f\u200d" or text[cut - 1] == "\u200d"):
        cut -= 1
    return text[:cut] + "…"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Fact(Strict):
    label: str = Field(max_length=80)
    value: str = Field(max_length=300)


class Event(Strict):
    schema_version: Literal[1] = 1
    title: str = Field(min_length=1, max_length=160)
    outcome: Outcome = "observed"
    kind: Literal["request", "phase_completed", "action_resolved", "question_opened", "question_resolved", "result", "warning"]
    occurred_at: datetime
    facts: list[Fact] = Field(default_factory=list, max_length=6)

    @model_validator(mode="after")
    def bounded(self):
        if self.occurred_at.tzinfo is None:
            raise ValueError("timezone required")
        if len(self.model_dump_json().encode()) > 16_384:
            raise ValueError("event exceeds byte budget")
        return self


class Asset(Strict):
    key: str = Field(pattern=r"^espresso-recaps/[a-f0-9-]+/[a-f0-9-]+/[a-f0-9-]+/(source|renders)/[a-f0-9-]+/[a-f0-9-]+/[a-z0-9.]+$")
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    bytes: int = Field(gt=0, le=128 * 1024 * 1024)
    mime: Literal["application/zip", "image/png", "image/webp", "video/mp4"]


class Scene(Strict):
    event: Event
    seconds: int = Field(ge=2, le=20)
    asset: Asset | None = None


class Manifest(Strict):
    schema_version: Literal[1] = 1
    template_version: Literal["espresso-recap.v1"] = "espresso-recap.v1"
    scenes: list[Scene] = Field(min_length=1, max_length=12)
    transcript: list[Event] = Field(default_factory=list, max_length=256)

    @model_validator(mode="after")
    def budget(self):
        if sum(s.seconds for s in self.scenes) > 120 or len(self.model_dump_json().encode()) > 1_048_576:
            raise ValueError("manifest exceeds budget")
        return self

    def digest(self) -> str:
        raw = json.dumps(self.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode()).hexdigest()


class Preferences(Strict):
    enabled: bool = Field(strict=True)
    email_enabled: bool = Field(strict=True)


class Retry(Strict):
    request_id: UUID


class Statuses(Strict):
    ids: list[UUID] = Field(max_length=50)


class Cursor(Strict):
    at: AwareDatetime
    id: UUID
