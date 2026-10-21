"""The shapes a network provider speaks in — the rest of the package never
sees a Graph API payload."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


class ProviderError(RuntimeError):
    """A network call failed. `retryable` decides whether the publisher tries
    the target again later (rate limits, outages) or fails it now (a rejected
    image, a revoked token)."""

    def __init__(self, message: str, *, retryable: bool = False, code: Optional[int] = None):
        super().__init__(message)
        self.retryable = retryable
        self.code = code


@dataclass(frozen=True)
class ConnectionDraft:
    """An account the OAuth round-trip found, before it is stored."""
    platform: str
    external_id: str
    access_token: str
    handle: Optional[str] = None
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    token_expires_at: Optional[datetime] = None
    scopes: tuple[str, ...] = ()
    followers_count: Optional[int] = None


@dataclass(frozen=True)
class PublishResult:
    external_post_id: str
    permalink: Optional[str] = None


@dataclass(frozen=True)
class InboundEvent:
    """A comment or message a webhook delivered. `recipient_external_id` is
    the connected account it landed on — the key an inbox row is found by."""
    platform: str
    recipient_external_id: str
    kind: str                       # comment | message
    external_id: str
    text: str
    parent_external_id: Optional[str] = None
    author_external_id: Optional[str] = None
    author_name: Optional[str] = None
    received_at: Optional[datetime] = None
    raw: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """JSON-safe, for the Celery hop between the webhook and the worker."""
        return {
            "platform": self.platform,
            "recipient_external_id": self.recipient_external_id,
            "kind": self.kind,
            "external_id": self.external_id,
            "text": self.text,
            "parent_external_id": self.parent_external_id,
            "author_external_id": self.author_external_id,
            "author_name": self.author_name,
            "received_at": self.received_at.isoformat() if self.received_at else None,
            "raw": self.raw,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InboundEvent":
        received = data.get("received_at")
        return cls(
            platform=str(data["platform"]),
            recipient_external_id=str(data["recipient_external_id"]),
            kind=str(data["kind"]),
            external_id=str(data["external_id"]),
            text=str(data.get("text") or ""),
            parent_external_id=data.get("parent_external_id"),
            author_external_id=data.get("author_external_id"),
            author_name=data.get("author_name"),
            received_at=datetime.fromisoformat(received) if received else None,
            raw=dict(data.get("raw") or {}),
        )


__all__ = ["ProviderError", "ConnectionDraft", "PublishResult", "InboundEvent"]
