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

from .points_service import award_points


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


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def search_people(conn, viewer_id: UUID, query: str, limit: int) -> list[dict]:
    """Prefix-search discoverable consumers, excluding social exclusions."""
    prefix = _escape_like(query.strip().lower())
    return list(await conn.fetch(
        """SELECT a.id AS account_id, a.display_name, a.handle, a.avatar_url,
                  a.city, a.state, pb.level, pb.lifetime_points,
                  (SELECT COUNT(*) FROM tellus_friendships mutual
                     WHERE mutual.account_id = $1
                       AND mutual.friend_account_id IN (
                           SELECT f.friend_account_id FROM tellus_friendships f
                            WHERE f.account_id = a.id)) AS mutual_friend_count
             FROM tellus_accounts a
             LEFT JOIN tellus_points_balances pb ON pb.account_id = a.id
            WHERE a.account_type = 'consumer' AND a.status = 'active'
              AND a.discoverable AND a.profile_visibility <> 'private' AND a.id <> $1
              AND (a.handle LIKE $2 || '%' ESCAPE '\\'
                   OR lower(a.display_name) LIKE $2 || '%' ESCAPE '\\')
              AND NOT EXISTS (
                  SELECT 1 FROM tellus_account_blocks b
                   WHERE (b.blocker_account_id = $1 AND b.blocked_account_id = a.id)
                      OR (b.blocker_account_id = a.id AND b.blocked_account_id = $1))
              AND NOT EXISTS (
                  SELECT 1 FROM tellus_friendships f
                   WHERE f.account_id = $1 AND f.friend_account_id = a.id)
              AND NOT EXISTS (
                  SELECT 1 FROM tellus_friend_requests r
                   WHERE r.status = 'pending'
                     AND ((r.requester_account_id = $1 AND r.addressee_account_id = a.id)
                       OR (r.requester_account_id = a.id AND r.addressee_account_id = $1)))
            ORDER BY (a.handle = $2) DESC,
                     length(COALESCE(a.handle, a.display_name)), a.created_at
            LIMIT $3""",
        viewer_id, prefix, limit,
    ))


async def suggestions(conn, viewer_id: UUID, limit: int) -> list[UUID]:
    """Rank friends-of-friends, co-followers, co-board members, and city peers."""
    rows = await conn.fetch(
        """WITH candidates AS (
             SELECT f2.friend_account_id AS account_id, COUNT(*) * 3 AS weight
               FROM tellus_friendships f1
               JOIN tellus_friendships f2 ON f2.account_id = f1.friend_account_id
              WHERE f1.account_id = $1 AND f2.friend_account_id <> $1
              GROUP BY f2.friend_account_id
             UNION ALL
             SELECT bf2.consumer_account_id, COUNT(*) * 2
               FROM tellus_brand_follows bf1
               JOIN tellus_brand_follows bf2 ON bf2.brand_id = bf1.brand_id
              WHERE bf1.consumer_account_id = $1 AND bf2.consumer_account_id <> $1
              GROUP BY bf2.consumer_account_id
             HAVING COUNT(*) >= 2
             UNION ALL
             SELECT bm2.account_id, COUNT(*) * 2
               FROM tellus_board_memberships bm1
               JOIN tellus_board_memberships bm2 ON bm2.board_id = bm1.board_id
              WHERE bm1.account_id = $1 AND bm1.status = 'approved'
                AND bm2.status = 'approved' AND bm2.account_id <> $1
              GROUP BY bm2.account_id
             HAVING COUNT(*) >= 2
             UNION ALL
             SELECT a.id, 1
               FROM tellus_accounts viewer
               JOIN tellus_accounts a ON a.city IS NOT NULL
                  AND lower(a.city) = lower(viewer.city)
                  AND a.state IS NOT DISTINCT FROM viewer.state
              WHERE viewer.id = $1 AND a.id <> $1
           ), ranked AS (
             SELECT account_id, SUM(weight) AS weight
               FROM candidates GROUP BY account_id
           )
           SELECT r.account_id
             FROM ranked r JOIN tellus_accounts a ON a.id = r.account_id
            WHERE a.account_type = 'consumer' AND a.status = 'active'
              AND a.discoverable AND a.profile_visibility <> 'private'
              AND NOT EXISTS (
                  SELECT 1 FROM tellus_account_blocks b
                   WHERE (b.blocker_account_id = $1 AND b.blocked_account_id = a.id)
                      OR (b.blocker_account_id = a.id AND b.blocked_account_id = $1))
              AND NOT EXISTS (
                  SELECT 1 FROM tellus_friendships f
                   WHERE f.account_id = $1 AND f.friend_account_id = a.id)
              AND NOT EXISTS (
                  SELECT 1 FROM tellus_friend_requests fr
                   WHERE fr.status = 'pending'
                     AND ((fr.requester_account_id = $1 AND fr.addressee_account_id = a.id)
                       OR (fr.requester_account_id = a.id AND fr.addressee_account_id = $1)))
            ORDER BY r.weight DESC, a.created_at
            LIMIT $2""",
        viewer_id, limit,
    )
    return [row["account_id"] for row in rows]


async def filter_suggestion_ids(conn, viewer_id: UUID, candidate_ids: list[UUID]) -> list[UUID]:
    """Re-apply live social/privacy filters to cached suggestion ids.

    The ranking cache is intentionally short-lived, but blocks, requests, and
    privacy changes must take effect immediately rather than waiting for TTL.
    """
    if not candidate_ids:
        return []
    rows = await conn.fetch(
        """SELECT a.id
              FROM tellus_accounts a
             WHERE a.id = ANY($2::uuid[])
               AND a.account_type = 'consumer' AND a.status = 'active'
               AND a.discoverable AND a.profile_visibility <> 'private'
               AND NOT EXISTS (
                   SELECT 1 FROM tellus_account_blocks b
                    WHERE (b.blocker_account_id = $1 AND b.blocked_account_id = a.id)
                       OR (b.blocker_account_id = a.id AND b.blocked_account_id = $1))
               AND NOT EXISTS (
                   SELECT 1 FROM tellus_friendships f
                    WHERE f.account_id = $1 AND f.friend_account_id = a.id)
               AND NOT EXISTS (
                   SELECT 1 FROM tellus_friend_requests r
                    WHERE r.status = 'pending'
                      AND ((r.requester_account_id = $1 AND r.addressee_account_id = a.id)
                        OR (r.requester_account_id = a.id AND r.addressee_account_id = $1)))
             ORDER BY array_position($2::uuid[], a.id)""",
        viewer_id, candidate_ids,
    )
    return [row["id"] for row in rows]


async def friend_ids(conn, account_id: UUID) -> list[UUID]:
    rows = await conn.fetch(
        "SELECT friend_account_id FROM tellus_friendships WHERE account_id = $1",
        account_id,
    )
    return [row["friend_account_id"] for row in rows]


async def assert_not_blocked(conn, first: UUID, second: UUID) -> None:
    blocked = await conn.fetchval(
        """SELECT 1 FROM tellus_account_blocks
            WHERE (blocker_account_id = $1 AND blocked_account_id = $2)
               OR (blocker_account_id = $2 AND blocked_account_id = $1)""",
        first, second,
    )
    if blocked:
        from fastapi import HTTPException, status
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")


async def create_friendship(conn, first: UUID, second: UUID, source: str) -> None:
    """Create both mirror rows and award each account exactly once."""
    await assert_not_blocked(conn, first, second)
    await conn.execute(
        """INSERT INTO tellus_friendships (account_id, friend_account_id, source)
           VALUES ($1, $2, $3), ($2, $1, $3) ON CONFLICT DO NOTHING""",
        first, second, source,
    )
    reference_id = pair_key(first, second)
    for account_id in (first, second):
        await award_points(
            conn, account_id, "earn_engagement", event_key="friend_added",
            reference_type="friendship", reference_id=reference_id,
            description="Added a friend",
        )


async def remove_friendship(conn, first: UUID, second: UUID) -> None:
    await conn.execute(
        """DELETE FROM tellus_friendships
            WHERE (account_id = $1 AND friend_account_id = $2)
               OR (account_id = $2 AND friend_account_id = $1)""",
        first, second,
    )


async def block_account(conn, blocker: UUID, blocked: UUID) -> None:
    """Block an account and atomically remove social state in both directions."""
    async with conn.transaction():
        await conn.execute(
            """INSERT INTO tellus_account_blocks (blocker_account_id, blocked_account_id)
               VALUES ($1, $2) ON CONFLICT DO NOTHING""",
            blocker, blocked,
        )
        await remove_friendship(conn, blocker, blocked)
        await conn.execute(
            """UPDATE tellus_friend_requests SET status = 'cancelled', decided_at = NOW()
                WHERE status = 'pending'
                  AND ((requester_account_id = $1 AND addressee_account_id = $2)
                    OR (requester_account_id = $2 AND addressee_account_id = $1))""",
            blocker, blocked,
        )
