"""Scope-aware links for messages, notifications, and payment flows."""

from __future__ import annotations

from uuid import UUID

from ...database import get_connection


def _append_suffix(base: str, suffix: str | None) -> str:
    if not suffix:
        return base
    if suffix.startswith("?"):
        return f"{base}{'&' if '?' in base else '?'}{suffix[1:]}"
    if suffix.startswith("/"):
        return f"{base}{suffix}"
    return f"{base}/{suffix}"


async def channel_app_path(conn, channel_id: UUID, *, suffix: str | None = None) -> str:
    """Resolve a channel to its owning product surface.

    Project discussions link back through the project, while Operations and
    community channels use their dedicated channel shells. Missing project
    metadata falls back to the channel scope rather than producing a broken
    link.
    """
    row = await conn.fetchrow(
        """
        SELECT COALESCE(ch.channel_scope, 'operations') AS channel_scope,
               p.id AS project_id
          FROM channels ch
          LEFT JOIN mw_projects p
            ON p.project_data->>'discussion_channel_id' = ch.id::text
         WHERE ch.id = $1
         LIMIT 1
        """,
        channel_id,
    )
    if not row:
        return _append_suffix(f"/ops/channels/{channel_id}", suffix)
    if row["channel_scope"] == "project_discussion" and row["project_id"]:
        return _append_suffix(f"/work/projects/{row['project_id']}?tab=chat", suffix)
    if row["channel_scope"] == "community":
        return _append_suffix(f"/werk/channels/{channel_id}", suffix)
    return _append_suffix(f"/ops/channels/{channel_id}", suffix)


async def resolve_channel_app_path(channel_id: UUID, *, suffix: str | None = None) -> str:
    """Resolve a channel link for callers that do not already hold a conn."""
    async with get_connection() as conn:
        return await channel_app_path(conn, channel_id, suffix=suffix)
