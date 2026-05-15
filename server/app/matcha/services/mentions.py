"""@-mention parsing and resolution for channel messages.

Mentions are lightweight: parsed from the message content on send (server-side),
resolved against the channel's member list, and used to enqueue email
notifications for any mentioned user who is currently offline. We do NOT
persist mention rows — they can always be re-derived from the message content.

The handle convention (v1) is the email local-part:
    "aaron@hey-matcha.com" -> handle "aaron"

Comparison is case-insensitive. Handles that don't resolve to a current channel
member are silently dropped — we don't email outsiders or leak channel
membership.
"""

from __future__ import annotations

import re
from typing import Iterable
from uuid import UUID

# Regex matches @handle where handle is 2-32 chars from [A-Za-z0-9._-].
# The lookbehind prevents matching email addresses ("foo@bar" -> no match for
# "@bar" because it's preceded by a non-whitespace char).
_MENTION_RE = re.compile(r"(?:(?<=^)|(?<=\s))@([A-Za-z0-9._-]{2,32})\b")


def parse_mentions(content: str) -> set[str]:
    """Extract distinct lowercase mention handles from message content."""
    if not content:
        return set()
    return {m.group(1).lower() for m in _MENTION_RE.finditer(content)}


async def resolve_mentions(
    conn,
    channel_id: UUID,
    handles: Iterable[str],
    exclude_user_id: UUID,
) -> list[dict]:
    """Resolve mention handles to (user_id, email, name) for channel members.

    Returns rows with keys: id, email, name. Excludes the sender (`exclude_user_id`)
    and members marked removed_for_inactivity. Returns empty list if no matches.
    """
    handle_set = {h.lower() for h in handles if h}
    if not handle_set:
        return []

    rows = await conn.fetch(
        """
        SELECT u.id,
               u.email,
               COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email) AS name,
               LOWER(SPLIT_PART(u.email, '@', 1)) AS handle
        FROM channel_members cm
        JOIN users u ON u.id = cm.user_id
        LEFT JOIN clients c ON c.user_id = u.id
        LEFT JOIN employees e ON e.user_id = u.id
        LEFT JOIN admins a ON a.user_id = u.id
        WHERE cm.channel_id = $1
          AND cm.removed_for_inactivity IS NOT TRUE
          AND u.id != $2
          AND LOWER(SPLIT_PART(u.email, '@', 1)) = ANY($3::text[])
        """,
        channel_id,
        exclude_user_id,
        list(handle_set),
    )
    return [dict(r) for r in rows]
