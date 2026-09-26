"""Short-lived first-party grants for Espresso's bundled Codex process.

Only Matcha credentials pass through this service. Vendor login stays inside
Codex. Each run receives a separate, revocable family with no refresh token.
The token grants the user's research permissions, not access to only one card.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import timedelta

from app.core.services import mcp_oauth
from app.database import get_connection

CLIENT_ID = "espresso-local-codex"
TOKEN_TTL = timedelta(minutes=30)


async def issue_token(user_id: uuid.UUID) -> dict:
    token = "mat_at_" + secrets.token_urlsafe(32)
    grant_id = uuid.uuid4()
    expires_at = mcp_oauth._now() + TOKEN_TTL
    resource = mcp_oauth.mcp_resource_url()
    async with get_connection() as conn:
        async with conn.transaction():
            # One fixed client, even when two devices issue their first grant
            # concurrently. It has no OAuth redirect, secret, or refresh grant.
            await conn.execute(
                """INSERT INTO oauth_clients
                     (client_id, client_name, redirect_uris, grant_types, scope,
                      token_endpoint_auth_method, client_id_issued_at)
                   VALUES ($1, 'Espresso local Codex', '[]'::jsonb, '[]'::jsonb,
                           $2, 'none', EXTRACT(EPOCH FROM NOW())::bigint)
                   ON CONFLICT (client_id) DO NOTHING""",
                CLIENT_ID, " ".join(mcp_oauth.SUPPORTED_SCOPES),
            )
            await conn.execute(
                """INSERT INTO oauth_tokens
                     (token_hash, kind, family_id, client_id, user_id, scope, resource, expires_at)
                   VALUES ($1, 'access', $2, $3, $4, $5, $6, $7)""",
                mcp_oauth._hash(token), grant_id, CLIENT_ID, user_id,
                " ".join(mcp_oauth.SUPPORTED_SCOPES), resource, expires_at,
            )
    return {
        "access_token": token, "token_type": "Bearer", "expires_at": expires_at,
        "resource": resource, "client_id": CLIENT_ID, "grant_id": grant_id,
    }


async def revoke_token(user_id: uuid.UUID, grant_id: uuid.UUID) -> None:
    """Idempotent, caller-scoped cleanup; never revokes another active run."""
    async with get_connection() as conn:
        await conn.execute(
            """UPDATE oauth_tokens SET revoked_at = NOW()
               WHERE user_id = $1 AND family_id = $2 AND client_id = $3
                 AND revoked_at IS NULL""",
            user_id, grant_id, CLIENT_ID,
        )
