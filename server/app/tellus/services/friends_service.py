"""Pure friends-domain helpers and shared constants.

Database access belongs here as the friends endpoints land, but these
predicates stay independent of asyncpg so the privacy and anti-spam matrix can
be tested without a database.
"""
import base64
import binascii
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID


HANDLE_RE = re.compile(r"^[a-z0-9_]{3,20}$")
RESERVED_HANDLES = frozenset(
    {
        "admin", "administrator", "api", "anonymous", "billing", "help", "me",
        "mod", "moderator", "null", "official", "root", "security", "staff",
        "support", "system", "team", "tellus", "tellus_team", "undefined", "www",
        "you",
    }
)
RESERVED_HANDLE_PREFIXES = ("tellus", "member")
PROFILE_SECTIONS = frozenset({"reviews", "followed_places", "boards"})
SCORE_SECTIONS = frozenset({"points", "badges"})
FRIEND_DECLINE_COOLDOWN = timedelta(days=30)


def normalize_handle(handle: str) -> str:
    """Return the canonical stored form; callers validate the result."""
    return handle.strip().lower()


def handle_rejection_reason(handle: str, *, taken: bool = False) -> Optional[str]:
    """Return the availability reason, or None when the handle is usable."""
    normalized = normalize_handle(handle)
    if not HANDLE_RE.fullmatch(normalized):
        return "format"
    if normalized in RESERVED_HANDLES or any(
        normalized.startswith(prefix) for prefix in RESERVED_HANDLE_PREFIXES
    ):
        return "reserved"
    if taken:
        return "taken"
    return None


def pair_key(first: UUID | str, second: UUID | str) -> str:
    """Stable, direction-independent ledger reference for an account pair."""
    return ":".join(sorted((str(first), str(second))))


def can_request(
    latest_status: Optional[str],
    decided_at: Optional[datetime],
    now: datetime,
) -> bool:
    """Whether a new request is allowed for the latest request state.

    A declined request blocks only 30 days, unlike the Regulars board's
    permanent declined/removed block: friend declines can be accidental and
    have no brand-moderation asymmetry. Pending and accepted states remain
    blocked; cancelled requests never block.
    """
    if latest_status is None or latest_status == "cancelled":
        return True
    if latest_status != "declined":
        return False
    if decided_at is None:
        return False
    if decided_at.tzinfo is None:
        decided_at = decided_at.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now >= decided_at + FRIEND_DECLINE_COOLDOWN


def visible_sections(
    *,
    is_self: bool,
    is_friend: bool,
    profile_visibility: str,
    leaderboard_opt_in: bool,
) -> frozenset[str]:
    """Apply the single profile-visibility truth table.

    Unknown visibility values fail closed. Scores/badges additionally require
    leaderboard opt-in, including on an otherwise visible profile.
    """
    if is_self or profile_visibility == "everyone" or (
        profile_visibility == "friends" and is_friend
    ):
        sections = set(PROFILE_SECTIONS)
    else:
        sections = set()
    if sections and leaderboard_opt_in:
        sections.update(SCORE_SECTIONS)
    return frozenset(sections)


def encode_cursor(happened_at: datetime, item_id: UUID | str) -> str:
    """Encode the feed keyset tuple as an opaque URL-safe cursor."""
    if happened_at.tzinfo is None:
        happened_at = happened_at.replace(tzinfo=timezone.utc)
    payload = {"happened_at": happened_at.isoformat(), "item_id": str(item_id)}
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> Optional[tuple[datetime, UUID]]:
    """Decode a cursor; malformed client input returns None, never raises."""
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        happened_at = datetime.fromisoformat(payload["happened_at"])
        if happened_at.tzinfo is None:
            happened_at = happened_at.replace(tzinfo=timezone.utc)
        return happened_at, UUID(str(payload["item_id"]))
    except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError, binascii.Error):
        return None


def display_name_for(display_name: Optional[str], handle: Optional[str], account_id: UUID | str) -> str:
    """Use the product's safe identity fallback; never derive identity from email."""
    return display_name or handle or f"Member-{str(account_id)[:4]}"
