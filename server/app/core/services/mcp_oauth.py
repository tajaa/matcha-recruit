"""OAuth 2.1 authorization server for the Matcha MCP connector.

Why this exists
---------------
Claude (claude.ai, Claude Desktop, Claude Code) and ChatGPT can reach Matcha as
a remote MCP "connector". The model then runs on the person's *own* Claude /
ChatGPT plan, and Matcha only exposes tools over that person's own data. That
is the one integration shape both vendors sanction for spending a user's plan
on a third-party product: Anthropic's consumer terms forbid using a Free/Pro/Max
login inside another product (Agent SDK included), and OpenAI steers programmatic
Codex use to API keys. So Matcha never asks for, stores, or proxies a Claude or
OpenAI credential. The OAuth here runs the other direction: it lets the
person's Claude/ChatGPT client authenticate *to Matcha* as that person.

Shape
-----
The MCP Python SDK (`mcp.server.auth`) implements the protocol handlers:
authorize / token / register / revoke, PKCE S256 verification, exact
redirect-URI matching, and client authentication. This module is the storage
and policy behind them, as an `OAuthAuthorizationServerProvider`:

- Clients register dynamically (RFC 7591). claude.ai, ChatGPT and Claude Code
  all support it; the registered redirect URIs are what the SDK matches against.
- `authorize()` does not decide anything. It packs the validated request into a
  signed, 10-minute handle and sends the browser to the SPA consent page
  (`/oauth/consent`), where the person is logged in as themselves and approves or
  denies. Only `approve_authorization()`—called by the consent API with the
  person's own session—mints a code.
- Codes are single-use, PKCE-bound, and bound to the RFC 8707 `resource`.
- Tokens are opaque random strings stored only as sha256. Access tokens last an
  hour; refresh tokens 30 days and rotate on every use. Presenting a refresh
  token that was already rotated away revokes the whole grant (`family_id`).
- Every token carries `resource = <origin>/api/mcp`; the MCP endpoint refuses a
  token minted for anything else (audience binding, MCP spec 2025-11-25).
- `load_access_token()` re-checks the person on every request: active, not
  suspended, company not deleted. A disconnect or password change revokes
  their grants outright (`revoke_user_grants`).

DCR client secrets are stored as issued because the SDK's client authenticator
compares them in constant time against the stored value. They only authenticate
a client that still needs a person's consent and a PKCE verifier to get
anything, so they are not bearer credentials for user data. Tokens, which are,
are never stored in the clear.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlencode, urlparse, urlunparse, parse_qsl

import asyncpg
from jose import JWTError, jwt
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    RefreshToken,
    RegistrationError,
    TokenError,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken

from app.database import get_connection

logger = logging.getLogger(__name__)

SCOPE_READ = "kanban:read"
SCOPE_WRITE = "kanban:write"
SUPPORTED_SCOPES = [SCOPE_READ, SCOPE_WRITE]

ACCESS_TOKEN_TTL = timedelta(hours=1)
REFRESH_TOKEN_TTL = timedelta(days=30)
AUTHORIZATION_CODE_TTL = timedelta(minutes=10)
CONSENT_REQUEST_TTL = timedelta(minutes=10)

_ACCESS_PREFIX = "mat_at_"
_REFRESH_PREFIX = "mat_rt_"
_CODE_PREFIX = "mat_ac_"
_CONSENT_TOKEN_TYPE = "mcp_oauth_consent"

# Redirect hosts that get a friendly name on the consent screen and in the
# "AI connectors" list. Anything else still works (DCR is open) — the consent
# screen shows its redirect host prominently so a person can tell who is asking.
_KNOWN_CLIENT_HOSTS = {
    "claude.ai": "claude",
    "claude.com": "claude",
    "chatgpt.com": "chatgpt",
    "chat.openai.com": "chatgpt",
}


# ── URLs ─────────────────────────────────────────────────────────────────────


def public_origin() -> str:
    """The public origin clients reach Matcha at, without a trailing slash.

    Read from the environment rather than `get_settings()` because the MCP app
    is assembled at import time, before the lifespan loads settings. Prod
    serves the SPA and `/api` on one origin, so `APP_BASE_URL` is right there;
    `MCP_PUBLIC_ORIGIN` overrides it for a tunnel during local connector tests.
    """
    origin = os.getenv("MCP_PUBLIC_ORIGIN") or os.getenv("APP_BASE_URL") or "http://localhost:5173"
    return origin.rstrip("/")


def app_origin() -> str:
    """Where the SPA consent page lives (the person's browser goes here).
    `MCP_APP_ORIGIN` overrides it for local runs where `APP_BASE_URL` names the
    backend rather than the Vite dev server."""
    origin = os.getenv("MCP_APP_ORIGIN") or os.getenv("APP_BASE_URL") or "http://localhost:5173"
    return origin.rstrip("/")


def mcp_resource_url() -> str:
    """Canonical RFC 8707 resource identifier of the MCP endpoint."""
    return f"{public_origin()}/api/mcp"


def issuer_url() -> str:
    return public_origin()


def oauth_endpoint(path: str) -> str:
    return f"{public_origin()}/api/oauth/{path.lstrip('/')}"


def authorization_server_metadata() -> dict[str, Any]:
    """RFC 8414 metadata. Built by hand (not the SDK's `build_metadata`) because
    the endpoints live under `/api/oauth/*` while the issuer is the bare origin,
    and because public clients (`none`) must be advertised."""
    return {
        "issuer": issuer_url(),
        "authorization_endpoint": oauth_endpoint("authorize"),
        "token_endpoint": oauth_endpoint("token"),
        "registration_endpoint": oauth_endpoint("register"),
        "revocation_endpoint": oauth_endpoint("revoke"),
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": [
            "client_secret_post", "client_secret_basic", "none",
        ],
        "revocation_endpoint_auth_methods_supported": [
            "client_secret_post", "client_secret_basic", "none",
        ],
        "scopes_supported": SUPPORTED_SCOPES,
        "authorization_response_iss_parameter_supported": True,
    }


def protected_resource_metadata() -> dict[str, Any]:
    """RFC 9728 metadata for the MCP endpoint."""
    return {
        "resource": mcp_resource_url(),
        "authorization_servers": [issuer_url()],
        "scopes_supported": SUPPORTED_SCOPES,
        "bearer_methods_supported": ["header"],
        "resource_name": "Matcha",
    }


def protected_resource_metadata_url() -> str:
    return f"{public_origin()}/.well-known/oauth-protected-resource/api/mcp"


# ── helpers ──────────────────────────────────────────────────────────────────


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _scopes(value: Optional[str]) -> list[str]:
    return [s for s in (value or "").split() if s]


def classify_client(redirect_uris: list[str], client_name: Optional[str] = None) -> str:
    """'claude' | 'chatgpt' | 'claude_code' | 'other', from where it redirects."""
    for uri in redirect_uris:
        host = (urlparse(uri).hostname or "").lower()
        if host in _KNOWN_CLIENT_HOSTS:
            return _KNOWN_CLIENT_HOSTS[host]
    name = (client_name or "").lower()
    if any((urlparse(u).hostname or "") in ("localhost", "127.0.0.1") for u in redirect_uris):
        if "claude" in name:
            return "claude_code"
    return "other"


def _redirect_uri_allowed(uri: str) -> bool:
    """https anywhere, or http only on loopback (native clients like Claude Code)."""
    parsed = urlparse(uri)
    if parsed.fragment:
        return False
    if parsed.scheme == "https" and parsed.hostname:
        return True
    return parsed.scheme == "http" and parsed.hostname in ("localhost", "127.0.0.1", "::1")


def _add_query(url: str, params: dict[str, str]) -> str:
    parsed = urlparse(url)
    query = parse_qsl(parsed.query, keep_blank_values=True)
    query.extend((k, v) for k, v in params.items() if v is not None)
    return urlunparse(parsed._replace(query=urlencode(query)))


def _jwt_secret() -> tuple[str, str]:
    from app.config import get_settings

    settings = get_settings()
    return settings.jwt_secret_key, settings.jwt_algorithm


# ── token models carrying our bookkeeping ────────────────────────────────────


class MatchaAuthorizationCode(AuthorizationCode):
    user_id: str


class MatchaRefreshToken(RefreshToken):
    family_id: str
    user_id: str


class MatchaAccessToken(AccessToken):
    family_id: str
    user_id: str


# ── consent handles ──────────────────────────────────────────────────────────


def issue_consent_handle(client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
    """Sign the already-validated authorize request so the consent page can
    carry it without server-side storage. It is not a credential: redeeming it
    also needs the person's own logged-in session."""
    secret, algorithm = _jwt_secret()
    now = _now()
    payload = {
        "type": _CONSENT_TOKEN_TYPE,
        "client_id": client.client_id,
        "redirect_uri": str(params.redirect_uri),
        "redirect_uri_provided_explicitly": params.redirect_uri_provided_explicitly,
        "scopes": params.scopes or [],
        "code_challenge": params.code_challenge,
        "state": params.state,
        "resource": params.resource or mcp_resource_url(),
        "iat": int(now.timestamp()),
        "exp": int((now + CONSENT_REQUEST_TTL).timestamp()),
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


def decode_consent_handle(handle: str) -> Optional[dict[str, Any]]:
    secret, algorithm = _jwt_secret()
    try:
        payload = jwt.decode(handle, secret, algorithms=[algorithm])
    except JWTError:
        return None
    if payload.get("type") != _CONSENT_TOKEN_TYPE:
        return None
    return payload


async def describe_consent(handle: str) -> Optional[dict[str, Any]]:
    """What the consent page shows: who is asking, where the code goes, what for."""
    request = decode_consent_handle(handle)
    if not request:
        return None
    client = await MatchaOAuthProvider().get_client(request["client_id"])
    if not client:
        return None
    redirect_host = urlparse(request["redirect_uri"]).hostname or ""
    return {
        "client_name": client.client_name or "An AI assistant",
        "client_kind": classify_client([str(u) for u in client.redirect_uris or []], client.client_name),
        "redirect_host": redirect_host,
        "scopes": request["scopes"],
        "resource": request["resource"],
    }


async def approve_authorization(handle: str, user_id: uuid.UUID) -> Optional[str]:
    """Mint a code for this person and return the client redirect URL."""
    request = decode_consent_handle(handle)
    if not request:
        return None
    code = _CODE_PREFIX + secrets.token_urlsafe(32)
    async with get_connection() as conn:
        exists = await conn.fetchval(
            "SELECT 1 FROM oauth_clients WHERE client_id = $1", request["client_id"]
        )
        if not exists:
            return None
        await conn.execute(
            """
            INSERT INTO oauth_authorization_codes
                (code_hash, client_id, user_id, redirect_uri,
                 redirect_uri_provided_explicitly, scope, code_challenge,
                 resource, expires_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
            _hash(code),
            request["client_id"],
            user_id,
            request["redirect_uri"],
            bool(request["redirect_uri_provided_explicitly"]),
            " ".join(request["scopes"]),
            request["code_challenge"],
            request["resource"],
            _now() + AUTHORIZATION_CODE_TTL,
        )
    logger.info("[mcp-oauth] code issued client=%s user=%s", request["client_id"], user_id)
    return _add_query(
        request["redirect_uri"],
        {"code": code, "state": request.get("state"), "iss": issuer_url()},
    )


def deny_authorization(handle: str) -> Optional[str]:
    request = decode_consent_handle(handle)
    if not request:
        return None
    return _add_query(
        request["redirect_uri"],
        {"error": "access_denied", "state": request.get("state"), "iss": issuer_url()},
    )


# ── grant management (the person's own "AI connectors" list) ─────────────────


async def list_user_grants(user_id: uuid.UUID) -> list[dict[str, Any]]:
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT c.client_id, c.client_name, c.redirect_uris,
                   MIN(t.created_at) AS connected_at,
                   MAX(t.last_used_at) AS last_used_at
              FROM oauth_tokens t
              JOIN oauth_clients c ON c.client_id = t.client_id
             WHERE t.user_id = $1
               AND t.revoked_at IS NULL
               AND t.expires_at > NOW()
             GROUP BY c.client_id, c.client_name, c.redirect_uris
             ORDER BY MIN(t.created_at) DESC
            """,
            user_id,
        )
    grants = []
    for row in rows:
        redirect_uris = row["redirect_uris"]
        if isinstance(redirect_uris, str):
            redirect_uris = json.loads(redirect_uris)
        grants.append({
            "client_id": row["client_id"],
            "client_name": row["client_name"],
            "kind": classify_client(redirect_uris or [], row["client_name"]),
            "connected_at": row["connected_at"].isoformat() if row["connected_at"] else None,
            "last_used_at": row["last_used_at"].isoformat() if row["last_used_at"] else None,
        })
    return grants


async def revoke_client_grants(user_id: uuid.UUID, client_id: str) -> int:
    async with get_connection() as conn:
        result = await conn.execute(
            """
            UPDATE oauth_tokens SET revoked_at = NOW()
             WHERE user_id = $1 AND client_id = $2 AND revoked_at IS NULL
            """,
            user_id, client_id,
        )
    return int((result or "UPDATE 0").split()[-1])


async def revoke_user_grants(conn, user_id: uuid.UUID) -> None:
    """Every connector grant this person holds. Called on password change and
    reset (not on logout: logging out of a browser tab should not unplug the
    person's Claude). Best-effort until the mcpconn01 migration is applied."""
    try:
        # Savepoint when the caller is already in a transaction, so a missing
        # table cannot abort the password change around it.
        async with conn.transaction():
            await conn.execute(
                "UPDATE oauth_tokens SET revoked_at = NOW() WHERE user_id = $1 AND revoked_at IS NULL",
                user_id,
            )
    except asyncpg.UndefinedTableError as exc:
        logger.warning("revoke_user_grants skipped: %s", type(exc).__name__)


# ── the provider the SDK drives ──────────────────────────────────────────────


def _client_from_row(row) -> OAuthClientInformationFull:
    redirect_uris = row["redirect_uris"]
    grant_types = row["grant_types"]
    metadata = row["metadata"]
    if isinstance(redirect_uris, str):
        redirect_uris = json.loads(redirect_uris)
    if isinstance(grant_types, str):
        grant_types = json.loads(grant_types)
    if isinstance(metadata, str):
        metadata = json.loads(metadata)
    return OAuthClientInformationFull(
        **(metadata or {}),
        client_id=row["client_id"],
        client_secret=row["client_secret"],
        client_id_issued_at=row["client_id_issued_at"],
        client_secret_expires_at=row["client_secret_expires_at"],
        client_name=row["client_name"],
        redirect_uris=redirect_uris,
        grant_types=grant_types,
        scope=row["scope"],
        token_endpoint_auth_method=row["token_endpoint_auth_method"],
    )


class MatchaOAuthProvider:
    """`OAuthAuthorizationServerProvider` over Postgres. Stateless; cheap to build."""

    async def get_client(self, client_id: str) -> Optional[OAuthClientInformationFull]:
        async with get_connection() as conn:
            row = await conn.fetchrow("SELECT * FROM oauth_clients WHERE client_id = $1", client_id)
        return _client_from_row(row) if row else None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        redirect_uris = [str(u) for u in client_info.redirect_uris or []]
        if not redirect_uris or not all(_redirect_uri_allowed(u) for u in redirect_uris):
            raise RegistrationError(
                error="invalid_redirect_uri",
                error_description="redirect_uris must be https, or http on localhost",
            )
        if len(redirect_uris) > 10:
            raise RegistrationError(
                error="invalid_client_metadata", error_description="too many redirect_uris"
            )
        name = (client_info.client_name or "").strip()[:120] or "Unnamed client"
        extra = client_info.model_dump(
            mode="json",
            exclude_none=True,
            include={"response_types", "application_type", "software_id", "software_version"},
        )
        async with get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO oauth_clients
                    (client_id, client_name, client_uri, logo_uri, redirect_uris,
                     grant_types, scope, token_endpoint_auth_method, client_secret,
                     client_id_issued_at, client_secret_expires_at, metadata)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7, $8, $9, $10, $11, $12::jsonb)
                """,
                client_info.client_id,
                name,
                str(client_info.client_uri) if client_info.client_uri else None,
                str(client_info.logo_uri) if client_info.logo_uri else None,
                json.dumps(redirect_uris),
                json.dumps(list(client_info.grant_types or ["authorization_code", "refresh_token"])),
                client_info.scope,
                client_info.token_endpoint_auth_method or "client_secret_post",
                client_info.client_secret,
                client_info.client_id_issued_at or int(time.time()),
                client_info.client_secret_expires_at,
                json.dumps(extra),
            )
        logger.info("[mcp-oauth] client registered id=%s name=%s", client_info.client_id, name)

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        # Tokens are only ever for our MCP endpoint. A client that names a
        # different resource is asking for something we do not issue.
        if params.resource and params.resource.rstrip("/") != mcp_resource_url():
            raise AuthorizeError(
                error="invalid_target",
                error_description="This server only issues tokens for its MCP endpoint",
            )
        scopes = params.scopes or list(SUPPORTED_SCOPES)
        unknown = set(scopes) - set(SUPPORTED_SCOPES)
        if unknown:
            raise AuthorizeError(error="invalid_scope", error_description="Unsupported scope")
        params = params.model_copy(update={"scopes": scopes, "resource": mcp_resource_url()})
        handle = issue_consent_handle(client, params)
        return f"{app_origin()}/oauth/consent?{urlencode({'request': handle})}"

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> Optional[MatchaAuthorizationCode]:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM oauth_authorization_codes
                 WHERE code_hash = $1 AND client_id = $2 AND used_at IS NULL
                """,
                _hash(authorization_code), client.client_id,
            )
        if not row:
            return None
        return MatchaAuthorizationCode(
            code=authorization_code,
            scopes=_scopes(row["scope"]),
            expires_at=row["expires_at"].timestamp(),
            client_id=row["client_id"],
            code_challenge=row["code_challenge"],
            redirect_uri=row["redirect_uri"],
            redirect_uri_provided_explicitly=row["redirect_uri_provided_explicitly"],
            resource=row["resource"],
            subject=str(row["user_id"]),
            user_id=str(row["user_id"]),
        )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: MatchaAuthorizationCode
    ) -> OAuthToken:
        async with get_connection() as conn:
            async with conn.transaction():
                # Single use: the conditional UPDATE is the lock. A second
                # exchange of the same code finds used_at set and gets nothing.
                claimed = await conn.fetchval(
                    """
                    UPDATE oauth_authorization_codes SET used_at = NOW()
                     WHERE code_hash = $1 AND client_id = $2 AND used_at IS NULL
                    RETURNING user_id
                    """,
                    _hash(authorization_code.code), client.client_id,
                )
                if claimed is None:
                    raise TokenError(error="invalid_grant", error_description="authorization code already used")
                return await _issue_pair(
                    conn,
                    client_id=client.client_id,
                    user_id=claimed,
                    scopes=authorization_code.scopes,
                    resource=authorization_code.resource or mcp_resource_url(),
                    family_id=uuid.uuid4(),
                )

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> Optional[MatchaRefreshToken]:
        if not refresh_token.startswith(_REFRESH_PREFIX):
            return None
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM oauth_tokens
                 WHERE token_hash = $1 AND kind = 'refresh' AND client_id = $2
                """,
                _hash(refresh_token), client.client_id,
            )
            if not row:
                return None
            if row["revoked_at"] is not None:
                # A rotated-away refresh token came back: someone holds a copy.
                # Kill the whole grant so neither copy works (OAuth 2.1 §4.3.1).
                await conn.execute(
                    "UPDATE oauth_tokens SET revoked_at = NOW() WHERE family_id = $1 AND revoked_at IS NULL",
                    row["family_id"],
                )
                logger.warning(
                    "[mcp-oauth] refresh token reuse; revoked family=%s client=%s",
                    row["family_id"], client.client_id,
                )
                return None
        return MatchaRefreshToken(
            token=refresh_token,
            client_id=row["client_id"],
            scopes=_scopes(row["scope"]),
            expires_at=int(row["expires_at"].timestamp()),
            resource=row["resource"],
            subject=str(row["user_id"]),
            family_id=str(row["family_id"]),
            user_id=str(row["user_id"]),
        )

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: MatchaRefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        async with get_connection() as conn:
            async with conn.transaction():
                rotated = await conn.fetchval(
                    """
                    UPDATE oauth_tokens SET revoked_at = NOW()
                     WHERE token_hash = $1 AND kind = 'refresh' AND revoked_at IS NULL
                    RETURNING id
                    """,
                    _hash(refresh_token.token),
                )
                if rotated is None:
                    raise TokenError(error="invalid_grant", error_description="refresh token no longer valid")
                # Old access tokens of this grant go too: one live pair per grant.
                await conn.execute(
                    """
                    UPDATE oauth_tokens SET revoked_at = NOW()
                     WHERE family_id = $1 AND kind = 'access' AND revoked_at IS NULL
                    """,
                    uuid.UUID(refresh_token.family_id),
                )
                return await _issue_pair(
                    conn,
                    client_id=client.client_id,
                    user_id=uuid.UUID(refresh_token.user_id),
                    scopes=scopes or refresh_token.scopes,
                    resource=refresh_token.resource or mcp_resource_url(),
                    family_id=uuid.UUID(refresh_token.family_id),
                )

    async def load_access_token(self, token: str) -> Optional[MatchaAccessToken]:
        if not token.startswith(_ACCESS_PREFIX):
            return None
        async with get_connection() as conn:
            row = await conn.fetchrow(
                """
                SELECT t.*, u.is_active, u.is_suspended,
                       (SELECT MIN(c.deleted_at)
                          FROM clients cl JOIN companies c ON c.id = cl.company_id
                         WHERE cl.user_id = u.id AND c.deleted_at IS NOT NULL) AS company_deleted_at
                  FROM oauth_tokens t
                  JOIN users u ON u.id = t.user_id
                 WHERE t.token_hash = $1 AND t.kind = 'access'
                """,
                _hash(token),
            )
            if (
                not row
                or row["revoked_at"] is not None
                or row["expires_at"] <= _now()
                or not row["is_active"]
                or row["is_suspended"]
                or row["company_deleted_at"] is not None
            ):
                return None
            await conn.execute(
                "UPDATE oauth_tokens SET last_used_at = NOW() WHERE id = $1", row["id"]
            )
        return MatchaAccessToken(
            token=token,
            client_id=row["client_id"],
            scopes=_scopes(row["scope"]),
            expires_at=int(row["expires_at"].timestamp()),
            resource=row["resource"],
            subject=str(row["user_id"]),
            family_id=str(row["family_id"]),
            user_id=str(row["user_id"]),
        )

    async def revoke_token(self, token: MatchaAccessToken | MatchaRefreshToken) -> None:
        async with get_connection() as conn:
            await conn.execute(
                "UPDATE oauth_tokens SET revoked_at = NOW() WHERE family_id = $1 AND revoked_at IS NULL",
                uuid.UUID(token.family_id),
            )

    async def exchange_identity_assertion(self, *args, **kwargs):  # pragma: no cover
        raise TokenError(error="unsupported_grant_type")


class MatchaTokenVerifier:
    """`TokenVerifier` for the MCP endpoint's bearer middleware."""

    def __init__(self, provider: Optional[MatchaOAuthProvider] = None):
        self._provider = provider or MatchaOAuthProvider()

    async def verify_token(self, token: str) -> Optional[AccessToken]:
        return await self._provider.load_access_token(token)


async def _issue_pair(
    conn,
    *,
    client_id: str,
    user_id: uuid.UUID,
    scopes: list[str],
    resource: str,
    family_id: uuid.UUID,
) -> OAuthToken:
    access = _ACCESS_PREFIX + secrets.token_urlsafe(32)
    refresh = _REFRESH_PREFIX + secrets.token_urlsafe(32)
    now = _now()
    scope = " ".join(scopes)
    await conn.executemany(
        """
        INSERT INTO oauth_tokens
            (token_hash, kind, family_id, client_id, user_id, scope, resource, expires_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        """,
        [
            (_hash(access), "access", family_id, client_id, user_id, scope, resource, now + ACCESS_TOKEN_TTL),
            (_hash(refresh), "refresh", family_id, client_id, user_id, scope, resource, now + REFRESH_TOKEN_TTL),
        ],
    )
    return OAuthToken(
        access_token=access,
        token_type="Bearer",
        expires_in=int(ACCESS_TOKEN_TTL.total_seconds()),
        scope=scope,
        refresh_token=refresh,
    )
