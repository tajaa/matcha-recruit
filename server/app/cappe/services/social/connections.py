"""Stored connected accounts (`cappe_social_connections`).

Tokens are Fernet-encrypted at rest with `core.services.secret_crypto` and
only ever decrypted here, for the call that needs them. Nothing in this
module returns a token in a row the HTTP layer could serialize.
"""
from __future__ import annotations

import json
from typing import Any, Optional
from uuid import UUID

from app.core.services.secret_crypto import decrypt_secret, encrypt_secret

from ..common import loads
from .providers.base import ConnectionDraft

# Everything a response may carry — no `access_token_enc`.
PUBLIC_COLUMNS = (
    "id, site_id, account_id, platform, external_id, handle, display_name, avatar_url, "
    "status, last_error, followers_count, metrics, metrics_at, token_expires_at, connected_at, updated_at, "
    "inbox_enabled"
)


def _public(row) -> dict:
    # asyncpg hands JSONB back as text (no codec is registered).
    d = dict(row)
    d["metrics"] = loads(d.get("metrics"))
    return d


def inbox_default(drafts: list[ConnectionDraft]) -> bool:
    """Whether accounts new to the site start with their inbox on. Connect
    brings in every Page the person manages (an agency's, a friend's band's),
    and an inbox that's on is answered as this store. One Page is the store's;
    several, and the owner turns on the ones that are."""
    return sum(1 for d in drafts if d.platform == "facebook") <= 1


async def save_drafts(conn, *, site_id: UUID, account_id: UUID, drafts: list[ConnectionDraft]) -> list[dict]:
    """Insert or refresh one row per draft. Re-connecting an account the site
    already has replaces its token and clears any error, and keeps the
    owner's inbox choice."""
    rows: list[dict] = []
    inbox = inbox_default(drafts)
    for draft in drafts:
        row = await conn.fetchrow(
            f"""INSERT INTO cappe_social_connections
                    (site_id, account_id, platform, external_id, handle, display_name, avatar_url,
                     access_token_enc, token_expires_at, scopes, followers_count, inbox_enabled)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                ON CONFLICT (site_id, platform, external_id) DO UPDATE SET
                    handle = EXCLUDED.handle, display_name = EXCLUDED.display_name,
                    avatar_url = EXCLUDED.avatar_url, access_token_enc = EXCLUDED.access_token_enc,
                    token_expires_at = EXCLUDED.token_expires_at, scopes = EXCLUDED.scopes,
                    followers_count = COALESCE(EXCLUDED.followers_count, cappe_social_connections.followers_count),
                    status = 'connected', last_error = NULL, updated_at = NOW()
                RETURNING {PUBLIC_COLUMNS}""",
            site_id, account_id, draft.platform, draft.external_id, draft.handle, draft.display_name,
            draft.avatar_url, encrypt_secret(draft.access_token), draft.token_expires_at,
            list(draft.scopes), draft.followers_count, inbox,
        )
        rows.append(_public(row))
    return rows


async def set_inbox_enabled(conn, site_id: UUID, connection_id: UUID, enabled: bool) -> Optional[dict]:
    row = await conn.fetchrow(
        f"""UPDATE cappe_social_connections SET inbox_enabled = $3, updated_at = NOW()
            WHERE id = $1 AND site_id = $2 RETURNING {PUBLIC_COLUMNS}""",
        connection_id, site_id, enabled,
    )
    return _public(row) if row else None


async def list_connections(conn, site_id: UUID) -> list[dict]:
    rows = await conn.fetch(
        f"SELECT {PUBLIC_COLUMNS} FROM cappe_social_connections WHERE site_id = $1 "
        "ORDER BY platform, connected_at",
        site_id,
    )
    return [_public(r) for r in rows]


async def get_connection(conn, site_id: UUID, connection_id: UUID) -> Optional[dict]:
    row = await conn.fetchrow(
        f"SELECT {PUBLIC_COLUMNS} FROM cappe_social_connections WHERE id = $1 AND site_id = $2",
        connection_id, site_id,
    )
    return _public(row) if row else None


async def delete_connection(conn, site_id: UUID, connection_id: UUID) -> bool:
    row = await conn.fetchrow(
        "DELETE FROM cappe_social_connections WHERE id = $1 AND site_id = $2 RETURNING id",
        connection_id, site_id,
    )
    return row is not None


async def credentials(conn, connection_id: UUID) -> Optional[dict[str, Any]]:
    """`{platform, external_id, token, status, site_id}` for one connection —
    for a call that is about to be made, never for a response."""
    row = await conn.fetchrow(
        "SELECT id, site_id, platform, external_id, access_token_enc, status "
        "FROM cappe_social_connections WHERE id = $1",
        connection_id,
    )
    if row is None:
        return None
    return {
        "id": row["id"], "site_id": row["site_id"], "platform": row["platform"],
        "external_id": row["external_id"], "status": row["status"],
        "token": decrypt_secret(row["access_token_enc"]) or "",
    }


async def by_external_id(conn, platform: str, external_id: str) -> list[dict]:
    """The connections a webhook event for `external_id` is delivered to: one
    Page may be connected on more than one site. Only live ones with their
    inbox on — a connection whose token Meta refused (often a former Page
    admin's, on their own account) gets nobody's comments or DMs, and one the
    owner switched off isn't answered as the store. First-connected first:
    the inbound worker lets only that one answer."""
    rows = await conn.fetch(
        "SELECT id, site_id, platform, external_id, handle, status "
        "FROM cappe_social_connections WHERE platform = $1 AND external_id = $2 "
        "AND status = 'connected' AND inbox_enabled ORDER BY connected_at, id",
        platform, external_id,
    )
    return [dict(r) for r in rows]


async def mark_status(conn, connection_id: UUID, status: str, error: Optional[str] = None) -> None:
    await conn.execute(
        "UPDATE cappe_social_connections SET status = $2, last_error = $3, updated_at = NOW() WHERE id = $1",
        connection_id, status, (error or "")[:500] or None,
    )


async def record_metrics(conn, connection_id: UUID, metrics: dict[str, Any]) -> None:
    followers = metrics.get("followers_count")
    await conn.execute(
        "UPDATE cappe_social_connections SET metrics = $2::jsonb, metrics_at = NOW(), "
        "followers_count = COALESCE($3, followers_count), updated_at = NOW() WHERE id = $1",
        connection_id, json.dumps(metrics), followers if isinstance(followers, int) else None,
    )


__all__ = [
    "PUBLIC_COLUMNS", "inbox_default", "save_drafts", "set_inbox_enabled", "list_connections", "get_connection",
    "delete_connection",
    "credentials", "by_external_id", "mark_status", "record_metrics",
]
