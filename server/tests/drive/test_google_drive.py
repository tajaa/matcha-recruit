"""Google Drive import: link parsing, one-time OAuth state, token refresh,
file fetch/export caps, and the import/callback routes. No network, no DB.

    cd server && ./venv/bin/python -m pytest tests/drive/test_google_drive.py -q
"""
import json
import time
from uuid import uuid4

import httpx
import pytest

from app.matcha.services.drive import google_drive_service as gd
from app.matcha.services.drive.google_drive_service import GoogleDriveError, GoogleDriveService
from app.matcha.services.matcha_work import oauth_state
from tests._helpers.routes import QueryConn

VALID_ID = "1AbCdEfGhIjKlMnOpQrStUv"


# ── Link parsing ────────────────────────────────────────────────────────


@pytest.mark.parametrize("url,expected", [
    (f"https://docs.google.com/document/d/{VALID_ID}/edit", VALID_ID),
    (f"https://docs.google.com/document/d/{VALID_ID}/edit?usp=sharing#heading=h.x", VALID_ID),
    (f"https://docs.google.com/spreadsheets/d/{VALID_ID}", VALID_ID),
    (f"https://drive.google.com/file/d/{VALID_ID}/view", VALID_ID),
    (f"https://drive.google.com/open?id={VALID_ID}", VALID_ID),
    (f"docs.google.com/document/d/{VALID_ID}/edit", VALID_ID),
    (f"https://drive.google.com/drive/folders/{VALID_ID}", None),
    (f"https://evil.example.com/document/d/{VALID_ID}/edit", None),
    (f"https://docs.google.com.evil.test/document/d/{VALID_ID}", None),
    (f"ftp://docs.google.com/document/d/{VALID_ID}", None),
    ("https://docs.google.com/document/d/short/edit", None),
    ("https://drive.google.com/open?id=../../etc", None),
    ("", None),
    ("not a url", None),
])
def test_parse_file_id(url, expected):
    assert gd.parse_file_id(url) == expected


def test_export_plan_and_extension():
    assert gd.export_plan("application/vnd.google-apps.document")[1] == ".docx"
    assert gd.export_plan("application/vnd.google-apps.presentation") == ("application/pdf", ".pdf")
    assert gd.export_plan("application/pdf") == (None, "")
    with pytest.raises(GoogleDriveError):
        gd.export_plan("application/vnd.google-apps.form")
    assert gd.ensure_extension("Write-up", ".docx") == "Write-up.docx"
    assert gd.ensure_extension("Write-up.DOCX", ".docx") == "Write-up.DOCX"
    assert gd.ensure_extension("  ", "") == "Untitled"


# ── One-time OAuth state ────────────────────────────────────────────────


class FakeRedis:
    def __init__(self):
        self.store = {}

    async def set(self, key, value, ex=None, nx=False):
        if nx and key in self.store:
            return False
        self.store[key] = value
        return True

    async def getdel(self, key):
        return self.store.pop(key, None)


@pytest.mark.asyncio
async def test_state_round_trip_is_single_use(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(oauth_state, "get_redis_cache", lambda: redis)
    user = uuid4()
    state = await oauth_state.issue_state("gdrive_oauth_state", user)
    assert await oauth_state.consume_state("gdrive_oauth_state", state) == user
    with pytest.raises(ValueError):
        await oauth_state.consume_state("gdrive_oauth_state", state)


@pytest.mark.asyncio
async def test_state_is_namespaced_by_prefix(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(oauth_state, "get_redis_cache", lambda: redis)
    state = await oauth_state.issue_state("gmail_oauth_state", uuid4())
    with pytest.raises(ValueError):
        await oauth_state.consume_state("gdrive_oauth_state", state)


@pytest.mark.asyncio
async def test_state_fails_closed(monkeypatch):
    monkeypatch.setattr(oauth_state, "get_redis_cache", lambda: None)
    with pytest.raises(oauth_state.OAuthStateUnavailable):
        await oauth_state.issue_state("p", uuid4())
    with pytest.raises(oauth_state.OAuthStateUnavailable):
        await oauth_state.consume_state("p", "a" * 43)
    with pytest.raises(ValueError):
        await oauth_state.consume_state("p", "bad state")


@pytest.mark.asyncio
async def test_state_accepts_bytes_from_redis(monkeypatch):
    user = uuid4()

    class BytesRedis(FakeRedis):
        async def getdel(self, key):
            return str(user).encode()
    monkeypatch.setattr(oauth_state, "get_redis_cache", lambda: BytesRedis())
    assert await oauth_state.consume_state("p", "a" * 43) == user


# ── Token handling ──────────────────────────────────────────────────────


CREDS = {"client_id": "cid", "client_secret": "csecret"}


@pytest.fixture
def plain_crypto(monkeypatch):
    monkeypatch.setattr(gd, "encrypt_secret", lambda v: f"enc:{v}")
    monkeypatch.setattr(gd, "decrypt_secret", lambda v: v.removeprefix("enc:"))
    monkeypatch.setattr(gd, "_client_credentials", lambda: CREDS)


def use_transport(monkeypatch, handler):
    real = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs.pop("timeout", None)
        return real(transport=httpx.MockTransport(handler), timeout=5.0)
    monkeypatch.setattr(gd.httpx, "AsyncClient", factory)


def stored_token(**overrides):
    base = {"access_token": "enc:old", "refresh_token": "enc:refresh", "expires_at": time.time() + 3600, "email": "gm@example.com"}
    base.update(overrides)
    return base


def conn_with(token, *, access_saved=True):
    return QueryConn(fetchval={
        "SELECT gdrive_token": json.dumps(token) if token else None,
        "gdrive_token || $1::jsonb": True if access_saved else None,
    })


@pytest.mark.asyncio
async def test_status_reports_connected_email(monkeypatch, plain_crypto):
    monkeypatch.setattr(gd, "get_connection", lambda *a, **k: conn_with(stored_token()))
    assert await GoogleDriveService(uuid4()).get_status() == {"connected": True, "email": "gm@example.com"}


@pytest.mark.asyncio
async def test_status_not_connected(monkeypatch, plain_crypto):
    monkeypatch.setattr(gd, "get_connection", lambda *a, **k: conn_with(None))
    assert (await GoogleDriveService(uuid4()).get_status())["connected"] is False


@pytest.mark.asyncio
async def test_undecryptable_token_reads_as_disconnected(monkeypatch, plain_crypto):
    def boom(v):
        raise ValueError("bad key")
    monkeypatch.setattr(gd, "decrypt_secret", boom)
    monkeypatch.setattr(gd, "get_connection", lambda *a, **k: conn_with(stored_token()))
    assert (await GoogleDriveService(uuid4()).get_status())["connected"] is False


@pytest.mark.asyncio
async def test_valid_access_token_is_reused(monkeypatch, plain_crypto):
    monkeypatch.setattr(gd, "get_connection", lambda *a, **k: conn_with(stored_token()))
    use_transport(monkeypatch, lambda req: pytest.fail("no network expected"))
    assert await GoogleDriveService(uuid4())._access_token() == "old"


@pytest.mark.asyncio
async def test_expired_token_refreshes_and_persists(monkeypatch, plain_crypto):
    conn = conn_with(stored_token(expires_at=time.time() - 10))
    monkeypatch.setattr(gd, "get_connection", lambda *a, **k: conn)

    def handler(req):
        assert req.url.path == "/token"
        assert b"grant_type=refresh_token" in req.content
        return httpx.Response(200, json={"access_token": "new", "expires_in": 3600})
    use_transport(monkeypatch, handler)
    assert await GoogleDriveService(uuid4())._access_token() == "new"
    # Only the access token and expiry are written, and only onto the same
    # connection: the refresh token and email are never rewritten from a copy.
    kind, sql, args = next(c for c in conn.calls if "gdrive_token || $1::jsonb" in c[1])
    patch = json.loads(args[0])
    assert set(patch) == {"access_token", "expires_at"} and patch["access_token"] == "enc:new"
    assert "gdrive_token->>'refresh_token' = $3" in sql and args[2] == "enc:refresh"


@pytest.mark.asyncio
async def test_a_refresh_that_loses_to_a_disconnect_does_not_undo_it(monkeypatch, plain_crypto):
    conn = conn_with(stored_token(expires_at=time.time() - 10), access_saved=False)
    monkeypatch.setattr(gd, "get_connection", lambda *a, **k: conn)
    use_transport(monkeypatch, lambda req: httpx.Response(200, json={"access_token": "new", "expires_in": 3600}))
    with pytest.raises(GoogleDriveError) as exc:
        await GoogleDriveService(uuid4())._access_token()
    assert exc.value.status == 409
    assert not any(sql.startswith("UPDATE users SET gdrive_token = $1") for sql in conn.sql_for("execute"))


@pytest.mark.asyncio
async def test_failed_refresh_asks_to_reconnect(monkeypatch, plain_crypto):
    conn = conn_with(stored_token(access_token=None))
    monkeypatch.setattr(gd, "get_connection", lambda *a, **k: conn)
    use_transport(monkeypatch, lambda req: httpx.Response(400, json={"error": "invalid_grant"}))
    service = GoogleDriveService(uuid4())
    with pytest.raises(GoogleDriveError) as exc:
        await service._access_token()
    assert exc.value.status == 409
    # A revoked grant is forgotten (unless replaced meanwhile), so status stops
    # saying connected and the dialog offers Connect again.
    kind, sql, args = next(c for c in conn.calls if "gdrive_token = NULL" in c[1])
    assert "gdrive_token->>'refresh_token' = $2" in sql and args[1] == "enc:refresh"


@pytest.mark.asyncio
async def test_google_being_down_during_refresh_keeps_the_connection(monkeypatch, plain_crypto):
    conn = conn_with(stored_token(access_token=None))
    monkeypatch.setattr(gd, "get_connection", lambda *a, **k: conn)
    use_transport(monkeypatch, lambda req: httpx.Response(503))
    with pytest.raises(GoogleDriveError) as exc:
        await GoogleDriveService(uuid4())._access_token()
    assert exc.value.status == 502
    assert not any("gdrive_token = NULL" in sql for sql in conn.sql_for("execute"))


@pytest.mark.asyncio
async def test_transport_errors_are_a_502_not_a_crash(monkeypatch, plain_crypto):
    monkeypatch.setattr(gd, "get_connection", lambda *a, **k: conn_with(stored_token(access_token=None)))

    def boom(req):
        raise httpx.ConnectError("down")
    use_transport(monkeypatch, boom)
    for call in (lambda s: s._access_token(), lambda s: s.exchange_code("c", "https://app.test/cb")):
        with pytest.raises(GoogleDriveError) as exc:
            await call(GoogleDriveService(uuid4()))
        assert exc.value.status == 502
    monkeypatch.setattr(gd, "get_connection", lambda *a, **k: conn_with(stored_token()))
    with pytest.raises(GoogleDriveError) as exc:
        await GoogleDriveService(uuid4()).fetch_file(VALID_ID)
    assert exc.value.status == 502


@pytest.mark.asyncio
async def test_not_connected_is_409(monkeypatch, plain_crypto):
    monkeypatch.setattr(gd, "get_connection", lambda *a, **k: conn_with(None))
    with pytest.raises(GoogleDriveError) as exc:
        await GoogleDriveService(uuid4())._access_token()
    assert exc.value.status == 409


@pytest.mark.asyncio
async def test_exchange_code_keeps_previous_refresh_token(monkeypatch, plain_crypto):
    conn = conn_with(stored_token())
    monkeypatch.setattr(gd, "get_connection", lambda *a, **k: conn)

    def handler(req):
        if req.url.path == "/token":
            return httpx.Response(200, json={"access_token": "fresh", "expires_in": 3600})
        return httpx.Response(200, json={"user": {"emailAddress": "gm@example.com"}})
    use_transport(monkeypatch, handler)
    await GoogleDriveService(uuid4()).exchange_code("code", "https://app.test/cb")
    saved = json.loads(conn.args_for("UPDATE users SET gdrive_token")[0])
    assert saved["refresh_token"] == "enc:refresh"
    assert saved["email"] == "gm@example.com"


@pytest.mark.asyncio
async def test_exchange_code_never_pairs_another_accounts_refresh_token(monkeypatch, plain_crypto):
    # Connected as gm@, now connecting other@ and Google sends no refresh token.
    monkeypatch.setattr(gd, "get_connection", lambda *a, **k: conn_with(stored_token()))

    def handler(req):
        if req.url.path == "/token":
            return httpx.Response(200, json={"access_token": "fresh", "expires_in": 3600})
        return httpx.Response(200, json={"user": {"emailAddress": "other@example.com"}})
    use_transport(monkeypatch, handler)
    with pytest.raises(GoogleDriveError) as exc:
        await GoogleDriveService(uuid4()).exchange_code("code", "https://app.test/cb")
    assert exc.value.status == 400


@pytest.mark.asyncio
async def test_exchange_code_without_any_refresh_token_refused(monkeypatch, plain_crypto):
    monkeypatch.setattr(gd, "get_connection", lambda *a, **k: conn_with(None))
    use_transport(monkeypatch, lambda req: httpx.Response(200, json={"access_token": "fresh"}) if req.url.path == "/token" else httpx.Response(500))
    with pytest.raises(GoogleDriveError):
        await GoogleDriveService(uuid4()).exchange_code("code", "https://app.test/cb")


@pytest.mark.asyncio
async def test_exchange_code_rejected(monkeypatch, plain_crypto):
    use_transport(monkeypatch, lambda req: httpx.Response(400, text="bad code"))
    with pytest.raises(GoogleDriveError) as exc:
        await GoogleDriveService(uuid4()).exchange_code("code", "https://app.test/cb")
    assert exc.value.status == 400


# ── Fetch ───────────────────────────────────────────────────────────────


@pytest.fixture
def connected(monkeypatch, plain_crypto):
    monkeypatch.setattr(gd, "get_connection", lambda *a, **k: conn_with(stored_token()))


@pytest.mark.asyncio
async def test_fetch_exports_google_doc_as_docx(monkeypatch, connected):
    seen = []

    def handler(req):
        seen.append(req.url.path)
        assert req.url.host == "www.googleapis.com"
        if req.url.path.endswith("/export"):
            assert req.url.params["mimeType"].endswith("wordprocessingml.document")
            return httpx.Response(200, content=b"PK\x03\x04docx")
        return httpx.Response(200, json={"id": VALID_ID, "name": "Write-up", "mimeType": "application/vnd.google-apps.document"})
    use_transport(monkeypatch, handler)
    got = await GoogleDriveService(uuid4()).fetch_file(VALID_ID)
    assert got.name == "Write-up.docx"
    assert got.data.startswith(b"PK")
    assert seen == [f"/drive/v3/files/{VALID_ID}", f"/drive/v3/files/{VALID_ID}/export"]


@pytest.mark.asyncio
async def test_fetch_missing_file_is_404(monkeypatch, connected):
    use_transport(monkeypatch, lambda req: httpx.Response(404))
    with pytest.raises(GoogleDriveError) as exc:
        await GoogleDriveService(uuid4()).fetch_file(VALID_ID)
    assert exc.value.status == 404


@pytest.mark.asyncio
async def test_fetch_refuses_declared_oversize_without_downloading(monkeypatch, connected):
    def handler(req):
        if req.url.params.get("alt") == "media":
            pytest.fail("must not download an oversize file")
        return httpx.Response(200, json={"id": VALID_ID, "name": "scan.pdf", "mimeType": "application/pdf", "size": str(30 * 1024 * 1024)})
    use_transport(monkeypatch, handler)
    with pytest.raises(GoogleDriveError) as exc:
        await GoogleDriveService(uuid4()).fetch_file(VALID_ID)
    assert exc.value.status == 413


@pytest.mark.asyncio
async def test_fetch_caps_bytes_while_streaming(monkeypatch, connected):
    monkeypatch.setattr(gd, "MAX_FILE_BYTES", 10)

    def handler(req):
        if req.url.params.get("alt") == "media":
            return httpx.Response(200, content=b"x" * 50)
        return httpx.Response(200, json={"id": VALID_ID, "name": "a.pdf", "mimeType": "application/pdf"})
    use_transport(monkeypatch, handler)
    with pytest.raises(GoogleDriveError) as exc:
        await GoogleDriveService(uuid4()).fetch_file(VALID_ID)
    assert exc.value.status == 413


@pytest.mark.asyncio
async def test_fetch_rejects_bad_id_and_google_error(monkeypatch, connected):
    with pytest.raises(GoogleDriveError):
        await GoogleDriveService(uuid4()).fetch_file("../x")
    use_transport(monkeypatch, lambda req: httpx.Response(500))
    with pytest.raises(GoogleDriveError) as exc:
        await GoogleDriveService(uuid4()).fetch_file(VALID_ID)
    assert exc.value.status == 502


@pytest.mark.asyncio
async def test_a_revoked_cached_token_refreshes_once_then_asks_to_reconnect(monkeypatch, plain_crypto):
    conn = conn_with(stored_token())
    monkeypatch.setattr(gd, "get_connection", lambda *a, **k: conn)
    seen = []
    mode = {"grant_gone": False}

    def handler(req):
        seen.append(req.url.path)
        if req.url.path == "/token":
            return httpx.Response(200, json={"access_token": "new", "expires_in": 3600})
        if req.headers["authorization"] == "Bearer old" or mode["grant_gone"]:
            return httpx.Response(401)
        if req.url.params.get("alt") == "media":
            return httpx.Response(200, content=b"%PDF-1.4")
        return httpx.Response(200, json={"id": VALID_ID, "name": "Lease agreement", "mimeType": "application/pdf"})
    use_transport(monkeypatch, handler)
    got = await GoogleDriveService(uuid4()).fetch_file(VALID_ID)
    assert seen.count("/token") == 1
    # A Drive upload with no extension takes one from its type (finding 8).
    assert got.name == "Lease agreement.pdf"

    mode["grant_gone"] = True
    with pytest.raises(GoogleDriveError) as exc:
        await GoogleDriveService(uuid4()).fetch_file(VALID_ID)
    assert exc.value.status == 409


@pytest.mark.parametrize("status,reason,expected", [
    (403, "rateLimitExceeded", 429),
    (429, "", 429),
    (403, "exportSizeLimitExceeded", 413),
    (403, "insufficientPermissions", 409),
    (403, "forbidden", 404),
    (404, "notFound", 404),
])
@pytest.mark.asyncio
async def test_drive_refusals_say_what_went_wrong(monkeypatch, connected, status, reason, expected):
    body = {"error": {"errors": [{"reason": reason}]}} if reason else {}
    use_transport(monkeypatch, lambda req: httpx.Response(status, json=body))
    with pytest.raises(GoogleDriveError) as exc:
        await GoogleDriveService(uuid4()).fetch_file(VALID_ID)
    assert exc.value.status == expected


@pytest.mark.asyncio
async def test_an_export_over_googles_limit_says_so(monkeypatch, connected):
    def handler(req):
        if req.url.path.endswith("/export"):
            return httpx.Response(403, json={"error": {"errors": [{"reason": "exportSizeLimitExceeded"}]}})
        return httpx.Response(200, json={"id": VALID_ID, "name": "Big", "mimeType": "application/vnd.google-apps.document"})
    use_transport(monkeypatch, handler)
    with pytest.raises(GoogleDriveError) as exc:
        await GoogleDriveService(uuid4()).fetch_file(VALID_ID)
    assert exc.value.status == 413 and "10 MB" in exc.value.detail


def test_download_extension():
    assert gd.download_extension("Lease agreement", "application/pdf") == ".pdf"
    assert gd.download_extension("scan.PDF", "application/pdf") == ""
    assert gd.download_extension("photo", "image/jpeg") == ".jpg"
    assert gd.download_extension("thing", "application/zip") == ""


@pytest.mark.asyncio
async def test_state_is_bound_to_the_browser_that_started_it(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(oauth_state, "get_redis_cache", lambda: redis)
    user = uuid4()
    mine = oauth_state.binding_hash("nonce-1")
    state = await oauth_state.issue_state("gdrive_oauth_state", user, binding=mine)
    assert await oauth_state.consume_state("gdrive_oauth_state", state, binding=mine) == user
    for wrong in (None, oauth_state.binding_hash("nonce-2")):
        state = await oauth_state.issue_state("gdrive_oauth_state", user, binding=mine)
        with pytest.raises(ValueError):
            await oauth_state.consume_state("gdrive_oauth_state", state, binding=wrong)
        # Consumed by the failed attempt: no second guess.
        with pytest.raises(ValueError):
            await oauth_state.consume_state("gdrive_oauth_state", state, binding=mine)


@pytest.mark.asyncio
async def test_disconnect_clears_column(monkeypatch, plain_crypto):
    conn = conn_with(None)
    monkeypatch.setattr(gd, "get_connection", lambda *a, **k: conn)
    await GoogleDriveService(uuid4()).disconnect()
    assert any("gdrive_token = NULL" in s for s in conn.sql_for("execute"))


def test_client_credentials_missing(monkeypatch):
    from app.matcha.services.matcha_work import gmail_service

    monkeypatch.setattr(gmail_service, "get_oauth_credentials", lambda: None)
    with pytest.raises(GoogleDriveError) as exc:
        gd._client_credentials()
    assert exc.value.status == 500
