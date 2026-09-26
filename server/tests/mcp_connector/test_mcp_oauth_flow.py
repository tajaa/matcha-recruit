"""End-to-end OAuth for the MCP connector, through the MCP SDK's real handlers.

`MatchaOAuthProvider` is the storage/policy half; the protocol half (PKCE
verification, redirect matching, client authentication, error shapes) is the
SDK's. These tests drive the SDK endpoints over HTTP against an in-memory
stand-in for the three `oauth_*` tables, so a change on either side shows up
as a broken flow rather than a mocked-away call.
"""

from __future__ import annotations

import base64
import hashlib
import uuid
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from app.core.services import mcp_oauth

ORIGIN = "https://matcha.test"
APP = "https://app.matcha.test"
CLAUDE_REDIRECT = "https://claude.ai/api/mcp/auth_callback"
USER_ID = uuid.UUID("11111111-1111-4111-8111-111111111111")


class FakeOAuthDB:
    """Just enough of Postgres for the queries in `mcp_oauth`. Each branch
    matches one statement by its text; anything else fails loudly."""

    def __init__(self):
        self.clients: dict[str, dict] = {}
        self.codes: dict[str, dict] = {}
        self.tokens: list[dict] = []
        self.user = {"is_active": True, "is_suspended": False, "company_deleted_at": None}

    # context-manager + transaction shape of an asyncpg connection
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def transaction(self):
        return self

    @staticmethod
    def _now():
        return datetime.now(timezone.utc)

    async def fetchrow(self, sql, *args):
        if "FROM oauth_clients WHERE client_id" in sql:
            return self.clients.get(args[0])
        if "FROM oauth_authorization_codes" in sql:
            row = self.codes.get(args[0])
            if row and row["client_id"] == args[1] and row["used_at"] is None:
                return row
            return None
        if "kind = 'refresh' AND client_id" in sql:
            return next(
                (t for t in self.tokens if t["token_hash"] == args[0] and t["kind"] == "refresh" and t["client_id"] == args[1]),
                None,
            )
        if "t.kind = 'access'" in sql:
            row = next((t for t in self.tokens if t["token_hash"] == args[0] and t["kind"] == "access"), None)
            return {**row, **self.user} if row else None
        raise AssertionError(f"unexpected fetchrow: {sql[:120]}")

    async def fetchval(self, sql, *args):
        if "SELECT 1 FROM oauth_clients" in sql:
            return 1 if args[0] in self.clients else None
        if "UPDATE oauth_authorization_codes SET used_at" in sql:
            row = self.codes.get(args[0])
            if row and row["client_id"] == args[1] and row["used_at"] is None:
                row["used_at"] = self._now()
                return row["user_id"]
            return None
        if "UPDATE oauth_tokens SET revoked_at = NOW()" in sql and "token_hash = $1" in sql:
            for t in self.tokens:
                if t["token_hash"] == args[0] and t["kind"] == "refresh" and t["revoked_at"] is None:
                    t["revoked_at"] = self._now()
                    return t["id"]
            return None
        if "SELECT client_name FROM oauth_clients" in sql:
            client = self.clients.get(args[0])
            return client["client_name"] if client else None
        raise AssertionError(f"unexpected fetchval: {sql[:120]}")

    async def fetch(self, sql, *args):
        if "GROUP BY c.client_id" in sql:
            live = [t for t in self.tokens if t["user_id"] == args[0] and t["revoked_at"] is None]
            out = {}
            for t in live:
                c = self.clients[t["client_id"]]
                out.setdefault(t["client_id"], {
                    "client_id": c["client_id"], "client_name": c["client_name"],
                    "redirect_uris": c["redirect_uris"], "connected_at": t["created_at"],
                    "last_used_at": None,
                })
            return list(out.values())
        raise AssertionError(f"unexpected fetch: {sql[:120]}")

    async def execute(self, sql, *args):
        if "INSERT INTO oauth_clients" in sql:
            keys = ["client_id", "client_name", "client_uri", "logo_uri", "redirect_uris",
                    "grant_types", "scope", "token_endpoint_auth_method", "client_secret",
                    "client_id_issued_at", "client_secret_expires_at", "metadata"]
            self.clients[args[0]] = dict(zip(keys, args))
            return "INSERT 0 1"
        if "INSERT INTO oauth_authorization_codes" in sql:
            keys = ["code_hash", "client_id", "user_id", "redirect_uri",
                    "redirect_uri_provided_explicitly", "scope", "code_challenge",
                    "resource", "expires_at"]
            self.codes[args[0]] = {**dict(zip(keys, args)), "used_at": None}
            return "INSERT 0 1"
        if "UPDATE oauth_tokens SET revoked_at = NOW()" in sql:
            n = 0
            for t in self.tokens:
                if t["revoked_at"] is not None:
                    continue
                if "family_id = $1 AND kind = 'access'" in sql:
                    hit = t["family_id"] == args[0] and t["kind"] == "access"
                elif "family_id = $1" in sql:
                    hit = t["family_id"] == args[0]
                elif "user_id = $1 AND client_id = $2" in sql:
                    hit = t["user_id"] == args[0] and t["client_id"] == args[1]
                elif "user_id = $1" in sql:
                    hit = t["user_id"] == args[0]
                else:
                    raise AssertionError(f"unexpected revoke: {sql[:120]}")
                if hit:
                    t["revoked_at"] = self._now()
                    n += 1
            return f"UPDATE {n}"
        if "SET last_used_at" in sql:
            return "UPDATE 1"
        raise AssertionError(f"unexpected execute: {sql[:120]}")

    async def executemany(self, sql, rows):
        assert "INSERT INTO oauth_tokens" in sql
        for token_hash, kind, family_id, client_id, user_id, scope, resource, expires_at in rows:
            self.tokens.append({
                "id": uuid.uuid4(), "token_hash": token_hash, "kind": kind,
                "family_id": family_id, "client_id": client_id, "user_id": user_id,
                "scope": scope, "resource": resource, "expires_at": expires_at,
                "revoked_at": None, "created_at": self._now(),
            })


@pytest.fixture
def db(monkeypatch):
    fake = FakeOAuthDB()
    monkeypatch.setenv("MCP_PUBLIC_ORIGIN", ORIGIN)
    monkeypatch.setenv("MCP_APP_ORIGIN", APP)
    monkeypatch.setattr(mcp_oauth, "get_connection", lambda *a, **k: fake)
    monkeypatch.setattr(mcp_oauth, "_jwt_secret", lambda: ("test-secret-value-long-enough", "HS256"))
    return fake


@pytest.fixture
def client(db):
    from app.matcha.routes.mcp_connector import server

    with TestClient(Starlette(routes=server.connector_routes()), base_url=ORIGIN) as c:
        yield c


def _pkce():
    verifier = base64.urlsafe_b64encode(b"v" * 48).decode().rstrip("=")
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return verifier, challenge


def _register(client, redirect_uris=(CLAUDE_REDIRECT,), name="Claude"):
    return client.post("/api/oauth/register", json={
        "client_name": name,
        "redirect_uris": list(redirect_uris),
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "client_secret_post",
    })


def _authorize(client, reg, challenge, **extra):
    params = {
        "response_type": "code",
        "client_id": reg["client_id"],
        "redirect_uri": CLAUDE_REDIRECT,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": "st-1",
        "resource": f"{ORIGIN}/api/mcp",
        **extra,
    }
    return client.get("/api/oauth/authorize", params=params, follow_redirects=False)


async def _consent(resp):
    location = resp.headers["location"]
    assert location.startswith(f"{APP}/oauth/consent?request=")
    handle = parse_qs(urlparse(location).query)["request"][0]
    return handle


def _token(client, reg, **form):
    return client.post("/api/oauth/token", data={
        "client_id": reg["client_id"], "client_secret": reg["client_secret"], **form,
    })


async def _full_grant(client):
    reg = _register(client).json()
    verifier, challenge = _pkce()
    handle = await _consent(_authorize(client, reg, challenge))
    redirect = await mcp_oauth.approve_authorization(handle, USER_ID)
    code = parse_qs(urlparse(redirect).query)["code"][0]
    tokens = _token(
        client, reg, grant_type="authorization_code", code=code,
        redirect_uri=CLAUDE_REDIRECT, code_verifier=verifier, resource=f"{ORIGIN}/api/mcp",
    )
    assert tokens.status_code == 200, tokens.text
    return reg, tokens.json()


# ── discovery ────────────────────────────────────────────────────────────────


def test_metadata_documents_point_at_api_oauth(client):
    prm = client.get("/.well-known/oauth-protected-resource/api/mcp").json()
    assert prm["resource"] == f"{ORIGIN}/api/mcp"
    assert prm["authorization_servers"] == [ORIGIN]

    for path in ("/.well-known/oauth-authorization-server", "/.well-known/oauth-authorization-server/api/oauth"):
        meta = client.get(path).json()
        assert meta["issuer"] == ORIGIN
        assert meta["authorization_endpoint"] == f"{ORIGIN}/api/oauth/authorize"
        assert meta["token_endpoint"] == f"{ORIGIN}/api/oauth/token"
        assert meta["registration_endpoint"] == f"{ORIGIN}/api/oauth/register"
        assert meta["code_challenge_methods_supported"] == ["S256"]
        assert "none" in meta["token_endpoint_auth_methods_supported"]


def test_mcp_endpoint_challenges_with_resource_metadata(client):
    resp = client.post("/api/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert resp.status_code == 401
    challenge = resp.headers["www-authenticate"]
    assert f'resource_metadata="{ORIGIN}/.well-known/oauth-protected-resource/api/mcp"' in challenge


# ── registration ─────────────────────────────────────────────────────────────


def test_register_accepts_https_and_loopback(client, db):
    assert _register(client).status_code == 201
    assert _register(client, redirect_uris=("http://localhost:33418/callback",), name="Claude Code").status_code == 201
    assert len(db.clients) == 2


@pytest.mark.parametrize("uri", ["http://evil.test/cb", "https://ok.test/cb#frag"])
def test_register_rejects_unsafe_redirects(client, db, uri):
    resp = _register(client, redirect_uris=(uri,))
    assert resp.status_code == 400
    assert db.clients == {}


# ── authorize + consent ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_authorize_sends_the_browser_to_consent_not_a_code(client, db):
    reg = _register(client).json()
    _verifier, challenge = _pkce()
    resp = _authorize(client, reg, challenge)
    assert resp.status_code == 302
    handle = await _consent(resp)
    assert db.codes == {}  # nothing minted until the person approves

    described = await mcp_oauth.describe_consent(handle)
    assert described["client_name"] == "Claude"
    assert described["client_kind"] == "claude"
    assert described["redirect_host"] == "claude.ai"
    assert set(described["scopes"]) == {"kanban:read", "kanban:write"}


def test_authorize_refuses_a_foreign_resource(client):
    reg = _register(client).json()
    _verifier, challenge = _pkce()
    resp = _authorize(client, reg, challenge, resource="https://other.test/mcp")
    assert resp.status_code == 302
    assert "error=invalid_target" in resp.headers["location"]
    assert resp.headers["location"].startswith(CLAUDE_REDIRECT)


def test_authorize_refuses_an_unregistered_redirect(client):
    reg = _register(client).json()
    _verifier, challenge = _pkce()
    resp = _authorize(client, reg, challenge, redirect_uri="https://attacker.test/cb")
    # Never redirect to an unregistered URI: the SDK answers in place.
    assert resp.status_code == 400
    assert "location" not in resp.headers


@pytest.mark.asyncio
async def test_deny_redirects_with_access_denied(client):
    reg = _register(client).json()
    _verifier, challenge = _pkce()
    handle = await _consent(_authorize(client, reg, challenge))
    url = mcp_oauth.deny_authorization(handle)
    q = parse_qs(urlparse(url).query)
    assert q["error"] == ["access_denied"] and q["state"] == ["st-1"] and q["iss"] == [ORIGIN]


@pytest.mark.asyncio
async def test_tampered_consent_handle_is_rejected(client):
    reg = _register(client).json()
    _verifier, challenge = _pkce()
    handle = await _consent(_authorize(client, reg, challenge))
    assert await mcp_oauth.approve_authorization(handle[:-4] + "AAAA", USER_ID) is None
    assert await mcp_oauth.describe_consent("not-a-jwt") is None


# ── token exchange ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_code_exchange_issues_audience_bound_tokens(client, db):
    _reg, tokens = await _full_grant(client)
    assert tokens["access_token"].startswith("mat_at_")
    assert tokens["refresh_token"].startswith("mat_rt_")
    # Stored only as hashes, bound to the MCP endpoint.
    assert all(t["token_hash"] != tokens["access_token"] for t in db.tokens)
    assert {t["resource"] for t in db.tokens} == {f"{ORIGIN}/api/mcp"}

    access = await mcp_oauth.MatchaTokenVerifier().verify_token(tokens["access_token"])
    assert access.subject == str(USER_ID)
    assert access.resource == f"{ORIGIN}/api/mcp"


@pytest.mark.asyncio
async def test_wrong_pkce_verifier_and_code_reuse_fail(client):
    reg = _register(client).json()
    verifier, challenge = _pkce()
    handle = await _consent(_authorize(client, reg, challenge))
    code = parse_qs(urlparse(await mcp_oauth.approve_authorization(handle, USER_ID)).query)["code"][0]

    bad = _token(client, reg, grant_type="authorization_code", code=code,
                 redirect_uri=CLAUDE_REDIRECT, code_verifier="x" * 50)
    assert bad.status_code == 400 and bad.json()["error"] == "invalid_grant"

    ok = _token(client, reg, grant_type="authorization_code", code=code,
                redirect_uri=CLAUDE_REDIRECT, code_verifier=verifier)
    assert ok.status_code == 200
    again = _token(client, reg, grant_type="authorization_code", code=code,
                   redirect_uri=CLAUDE_REDIRECT, code_verifier=verifier)
    assert again.status_code == 400 and again.json()["error"] == "invalid_grant"


@pytest.mark.asyncio
async def test_refresh_rotates_and_reuse_revokes_the_grant(client):
    reg, first = await _full_grant(client)
    rotated = _token(client, reg, grant_type="refresh_token", refresh_token=first["refresh_token"])
    assert rotated.status_code == 200, rotated.text
    second = rotated.json()
    assert second["refresh_token"] != first["refresh_token"]

    verifier = mcp_oauth.MatchaTokenVerifier()
    assert await verifier.verify_token(first["access_token"]) is None  # old access retired
    assert await verifier.verify_token(second["access_token"]) is not None

    # Replaying the spent refresh token kills the whole grant.
    replay = _token(client, reg, grant_type="refresh_token", refresh_token=first["refresh_token"])
    assert replay.status_code == 400
    assert await verifier.verify_token(second["access_token"]) is None


# ── access-token checks + grants ─────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [
    {"is_active": False}, {"is_suspended": True}, {"company_deleted_at": datetime.now(timezone.utc)},
])
async def test_access_token_stops_working_when_the_account_does(client, db, change):
    _reg, tokens = await _full_grant(client)
    db.user.update(change)
    assert await mcp_oauth.MatchaTokenVerifier().verify_token(tokens["access_token"]) is None


@pytest.mark.asyncio
async def test_unknown_or_foreign_tokens_are_ignored(db):
    verifier = mcp_oauth.MatchaTokenVerifier()
    assert await verifier.verify_token("eyJhbGciOi.app.jwt") is None  # an app JWT is not accepted here
    assert await verifier.verify_token("mat_at_nope") is None


@pytest.mark.asyncio
async def test_grants_list_and_disconnect(client, db):
    reg, tokens = await _full_grant(client)
    grants = await mcp_oauth.list_user_grants(USER_ID)
    assert [(g["client_id"], g["kind"]) for g in grants] == [(reg["client_id"], "claude")]

    assert await mcp_oauth.revoke_client_grants(USER_ID, reg["client_id"]) == 2
    assert await mcp_oauth.list_user_grants(USER_ID) == []
    assert await mcp_oauth.MatchaTokenVerifier().verify_token(tokens["access_token"]) is None


@pytest.mark.asyncio
async def test_password_change_revocation_covers_every_client(client, db):
    await _full_grant(client)
    await _full_grant(client)
    await mcp_oauth.revoke_user_grants(db, USER_ID)
    assert all(t["revoked_at"] is not None for t in db.tokens)


@pytest.mark.asyncio
async def test_revoke_user_grants_tolerates_missing_table():
    import asyncpg

    class NoTable:
        def transaction(self):
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def execute(self, *_a):
            raise asyncpg.UndefinedTableError("relation \"oauth_tokens\" does not exist")

    await mcp_oauth.revoke_user_grants(NoTable(), USER_ID)  # must not raise


def test_classify_client():
    assert mcp_oauth.classify_client(["https://chatgpt.com/connector_platform_oauth_redirect"]) == "chatgpt"
    assert mcp_oauth.classify_client(["https://claude.ai/api/mcp/auth_callback"]) == "claude"
    assert mcp_oauth.classify_client(["http://localhost:4312/callback"], "Claude Code (matcha)") == "claude_code"
    assert mcp_oauth.classify_client(["http://127.0.0.1:5555/callback"], "Codex") == "codex"
    assert mcp_oauth.classify_client(["https://cursor.test/cb"], "Cursor") == "other"


def test_public_origin_prefers_mcp_override(monkeypatch):
    monkeypatch.setenv("APP_BASE_URL", "https://hey-matcha.com/")
    monkeypatch.delenv("MCP_PUBLIC_ORIGIN", raising=False)
    monkeypatch.delenv("MCP_APP_ORIGIN", raising=False)
    assert mcp_oauth.mcp_resource_url() == "https://hey-matcha.com/api/mcp"
    assert mcp_oauth.app_origin() == "https://hey-matcha.com"
    monkeypatch.setenv("MCP_PUBLIC_ORIGIN", "https://tunnel.test")
    assert mcp_oauth.issuer_url() == "https://tunnel.test"


def test_register_and_token_are_rate_limited_per_ip(client, monkeypatch):
    import app.core.services.redis_cache as redis_cache
    from fastapi import HTTPException

    seen = []

    async def limited(ip, action, limit, window):
        seen.append((action, limit, window))
        raise HTTPException(status_code=429, headers={"Retry-After": str(window)})

    monkeypatch.setattr(redis_cache, "check_rate_limit", limited)
    resp = _register(client)
    assert resp.status_code == 429 and resp.json()["error"] == "slow_down"
    assert resp.headers["retry-after"] == "3600"
    assert client.post("/api/oauth/token", data={}).status_code == 429
    assert seen == [("mcp_oauth_register", 20, 3600), ("mcp_oauth_token", 60, 60)]
    # Discovery and the authorize redirect are not throttled here.
    assert client.get("/.well-known/oauth-authorization-server").status_code == 200
