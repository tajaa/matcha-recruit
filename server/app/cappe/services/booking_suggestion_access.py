"""Existing-client capabilities for Cappe AI booking suggestions."""
import hashlib
import os
import re
import secrets
from datetime import datetime, timedelta
from typing import Any, Mapping
from uuid import UUID


SUGGESTION_LINK_TTL = timedelta(minutes=15)
SUGGESTION_SESSION_TTL = timedelta(minutes=30)
SUGGESTION_SESSION_COOKIE = "cappe_booking_suggestion"

_LINK_TTL = SUGGESTION_LINK_TTL
_SESSION_TTL = SUGGESTION_SESSION_TTL
_DNS_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def hash_access_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def make_access_token() -> str:
    return secrets.token_urlsafe(32)


async def find_existing_client(conn, *, site_id: UUID, email: str) -> dict[str, Any] | None:
    """Return a client identity only for an imported client, prior booker, or buyer."""
    email = email.strip().lower()
    row = await conn.fetchrow(
        """
        SELECT name FROM (
            SELECT name, 0 AS priority, created_at AS occurred_at, id AS source_id
            FROM cappe_clients
            WHERE site_id = $1 AND lower(email) = $2
            UNION ALL
            SELECT customer_name AS name, 1 AS priority, created_at AS occurred_at, id AS source_id
            FROM cappe_bookings
            WHERE site_id = $1 AND customer_email IS NOT NULL AND lower(customer_email) = $2
            UNION ALL
            SELECT customer_name AS name, 2 AS priority, created_at AS occurred_at, id AS source_id
            FROM cappe_orders
            WHERE site_id = $1 AND customer_email IS NOT NULL AND lower(customer_email) = $2
              AND status IN ('paid', 'fulfilled')
        ) existing
        ORDER BY priority, occurred_at DESC NULLS LAST, source_id
        LIMIT 1
        """,
        site_id,
        email,
    )
    return dict(row) if row else None


async def issue_suggestion_link(
    conn,
    *,
    site_id: UUID,
    email: str,
    now: datetime,
) -> tuple[str, str | None] | None:
    """Upsert one short-lived raw token for an eligible client."""
    email = email.strip().lower()
    client = await find_existing_client(conn, site_id=site_id, email=email)
    if client is None:
        return None

    await cleanup_expired_access_rows(conn, now=now)
    token = make_access_token()
    await conn.execute(
        """
        INSERT INTO cappe_booking_suggestion_links (site_id, client_email, token_hash, expires_at)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (site_id, client_email)
        DO UPDATE SET
            token_hash = EXCLUDED.token_hash,
            expires_at = EXCLUDED.expires_at,
            used_at = NULL,
            created_at = EXCLUDED.created_at
        """,
        site_id,
        email,
        hash_access_token(token),
        now + SUGGESTION_LINK_TTL,
    )
    return token, client.get("name")


async def redeem_suggestion_link(
    conn,
    *,
    token: str,
    site_id: UUID,
    now: datetime,
) -> tuple[UUID, str, str] | None:
    """Consume a single-use link and create a site-scoped browser session."""
    token_hash = hash_access_token(token)
    link = await conn.fetchrow(
        """
        SELECT id, site_id, client_email
        FROM cappe_booking_suggestion_links
        WHERE token_hash = $1
          AND site_id = $2
          AND used_at IS NULL AND expires_at > $3
        FOR UPDATE
        """,
        token_hash,
        site_id,
        now,
    )
    if link is None:
        return None

    await cleanup_expired_access_rows(conn, now=now)
    session_token = make_access_token()
    await conn.execute(
        "UPDATE cappe_booking_suggestion_links SET used_at = $2 WHERE id = $1",
        link["id"],
        now,
    )
    await conn.execute(
        """
        INSERT INTO cappe_booking_suggestion_sessions (site_id, client_email, token_hash, expires_at)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (site_id, client_email)
        DO UPDATE SET
            token_hash = EXCLUDED.token_hash,
            expires_at = EXCLUDED.expires_at,
            revoked_at = NULL,
            created_at = EXCLUDED.created_at
        """,
        link["site_id"],
        link["client_email"],
        hash_access_token(session_token),
        now + SUGGESTION_SESSION_TTL,
    )
    return link["site_id"], link["client_email"], session_token


async def cleanup_expired_access_rows(conn, *, now: datetime, limit: int = 100) -> None:
    """Bound opportunistic cleanup so expired capabilities do not accumulate."""
    await conn.execute(
        """
        WITH expired AS (
            SELECT id FROM cappe_booking_suggestion_links
            WHERE expires_at <= $1
            ORDER BY expires_at
            LIMIT $2
        )
        DELETE FROM cappe_booking_suggestion_links links
        USING expired
        WHERE links.id = expired.id
        """,
        now,
        limit,
    )
    await conn.execute(
        """
        WITH expired AS (
            SELECT id FROM cappe_booking_suggestion_sessions
            WHERE expires_at <= $1
            ORDER BY expires_at
            LIMIT $2
        )
        DELETE FROM cappe_booking_suggestion_sessions sessions
        USING expired
        WHERE sessions.id = expired.id
        """,
        now,
        limit,
    )


async def resolve_suggestion_session(
    conn,
    *,
    site_id: UUID,
    token: str | None,
    now: datetime,
) -> str | None:
    if not token:
        return None
    return await conn.fetchval(
        """
        SELECT client_email
        FROM cappe_booking_suggestion_sessions
        WHERE site_id = $1 AND token_hash = $2
          AND revoked_at IS NULL AND expires_at > $3
        """,
        site_id,
        hash_access_token(token),
        now,
    )


def canonical_suggestion_host(
    site: Mapping[str, Any],
    *,
    base_domain: str | None = None,
) -> str | None:
    """Build the only production host eligible for AI suggestions."""
    subdomain = str(site.get("subdomain") or "").strip().lower().rstrip(".")
    base = (base_domain or os.getenv("CAPPE_BASE_DOMAIN", "hey-matcha.com")).strip().lower().rstrip(".")
    if not subdomain or not base or not _DNS_LABEL_RE.fullmatch(subdomain):
        return None
    if any(not _DNS_LABEL_RE.fullmatch(part) for part in base.split(".")):
        return None
    return f"{subdomain}.{base}"


def canonical_suggestion_origin(
    site: Mapping[str, Any],
    *,
    base_domain: str | None = None,
) -> str | None:
    host = canonical_suggestion_host(site, base_domain=base_domain)
    return f"https://{host}" if host else None


__all__ = [
    "find_existing_client",
    "hash_access_token",
    "issue_suggestion_link",
    "make_access_token",
    "redeem_suggestion_link",
    "resolve_suggestion_session",
    "SUGGESTION_LINK_TTL",
    "SUGGESTION_SESSION_COOKIE",
    "SUGGESTION_SESSION_TTL",
    "canonical_suggestion_host",
    "canonical_suggestion_origin",
    "cleanup_expired_access_rows",
]
