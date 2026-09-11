"""Regression coverage for the system-browser Gmail OAuth callback."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.matcha.routes import matcha_router
from app.matcha.routes.matcha_work import workspace
from app.matcha.services.matcha_work import gmail_service
from tests._helpers.routes import route_client


CALLBACK_PATH = "/api/matcha-work/agent/email/callback"


class FakeRedis:
    def __init__(self, *, set_error=None, getdel_error=None, reject_sets=False):
        self.values = {}
        self.set_calls = []
        self.set_error = set_error
        self.getdel_error = getdel_error
        self.reject_sets = reject_sets

    async def set(self, key, value, **kwargs):
        self.set_calls.append((key, value, kwargs))
        if self.set_error:
            raise self.set_error
        if self.reject_sets:
            return False
        if kwargs.get("nx") and key in self.values:
            return False
        self.values[key] = value
        return True

    async def getdel(self, key):
        if self.getdel_error:
            raise self.getdel_error
        return self.values.pop(key, None)


@pytest.fixture(autouse=True)
def oauth_settings(monkeypatch):
    monkeypatch.setattr(
        workspace,
        "get_settings",
        lambda: SimpleNamespace(
            app_base_url="https://hey-matcha.com",
        ),
    )


def test_callback_is_public_but_connect_remains_authenticated():
    with route_client(matcha_router, prefix="/api") as client:
        callback_response = client.get(
            CALLBACK_PATH,
            params={"code": "unused", "state": "invalid"},
        )
        connect_response = client.post("/api/matcha-work/agent/email/connect")

    assert callback_response.status_code == 400
    assert callback_response.json() == {"detail": "Invalid or expired OAuth state"}
    assert connect_response.status_code in {401, 403}
    assert connect_response.json() == {"detail": "Not authenticated"}


@pytest.mark.asyncio
async def test_oauth_state_is_opaque_stored_for_30_minutes_and_single_use(monkeypatch):
    redis = FakeRedis()
    user_id = uuid4()
    monkeypatch.setattr(workspace, "get_redis_cache", lambda: redis)

    state = await workspace._issue_gmail_oauth_state(user_id)

    assert len(state) == 43
    assert str(user_id) not in state
    assert redis.set_calls == [
        (
            f"gmail_oauth_state:{state}",
            str(user_id),
            {"ex": 30 * 60, "nx": True},
        )
    ]
    assert await workspace._consume_gmail_oauth_state(state) == user_id
    with pytest.raises(ValueError, match="Invalid or expired OAuth state"):
        await workspace._consume_gmail_oauth_state(state)


def test_callback_rejects_forgeable_plaintext_json_state(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(workspace, "get_redis_cache", lambda: redis)
    forged_state = (
        '{"user_id":"00000000-0000-0000-0000-000000000001",'
        '"issued_at":9999999999,"nonce":"x"}'
    )

    with route_client(matcha_router, prefix="/api") as client:
        response = client.get(
            CALLBACK_PATH,
            params={"code": "attacker-code", "state": forged_state},
        )

    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid or expired OAuth state"}
    assert redis.values == {}


@pytest.mark.asyncio
async def test_oauth_state_fails_closed_without_redis(monkeypatch):
    monkeypatch.setattr(workspace, "get_redis_cache", lambda: None)

    with pytest.raises(workspace._GmailOAuthStateStoreUnavailable):
        await workspace._issue_gmail_oauth_state(uuid4())
    with pytest.raises(workspace._GmailOAuthStateStoreUnavailable):
        await workspace._consume_gmail_oauth_state("a" * 43)


@pytest.mark.asyncio
async def test_oauth_state_store_errors_and_collisions_fail_closed(monkeypatch):
    monkeypatch.setattr(
        workspace,
        "get_redis_cache",
        lambda: FakeRedis(set_error=ConnectionError("set failed")),
    )
    with pytest.raises(workspace._GmailOAuthStateStoreUnavailable):
        await workspace._issue_gmail_oauth_state(uuid4())

    monkeypatch.setattr(
        workspace,
        "get_redis_cache",
        lambda: FakeRedis(reject_sets=True),
    )
    with pytest.raises(workspace._GmailOAuthStateStoreUnavailable):
        await workspace._issue_gmail_oauth_state(uuid4())

    monkeypatch.setattr(
        workspace,
        "get_redis_cache",
        lambda: FakeRedis(getdel_error=ConnectionError("getdel failed")),
    )
    with pytest.raises(workspace._GmailOAuthStateStoreUnavailable):
        await workspace._consume_gmail_oauth_state("a" * 43)


@pytest.mark.asyncio
async def test_oauth_state_rejects_corrupt_user_binding(monkeypatch):
    redis = FakeRedis()
    state = workspace.secrets.token_urlsafe(32)
    redis.values[workspace._gmail_oauth_state_key(state)] = "not-a-user-id"
    monkeypatch.setattr(workspace, "get_redis_cache", lambda: redis)

    with pytest.raises(ValueError, match="Invalid or expired OAuth state"):
        await workspace._consume_gmail_oauth_state(state)

    assert redis.values == {}


def test_callback_returns_503_when_state_store_is_unavailable(monkeypatch):
    monkeypatch.setattr(workspace, "get_redis_cache", lambda: None)

    with route_client(matcha_router, prefix="/api") as client:
        response = client.get(
            CALLBACK_PATH,
            params={"code": "unused", "state": "a" * 43},
        )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Gmail connection is temporarily unavailable. Please try again."
    }


@pytest.mark.asyncio
async def test_connect_returns_503_when_state_store_is_unavailable(monkeypatch):
    monkeypatch.setattr(workspace, "get_redis_cache", lambda: None)
    monkeypatch.setattr(
        gmail_service,
        "get_oauth_credentials",
        lambda: {"client_id": "client-id", "client_secret": "client-secret"},
    )

    with pytest.raises(workspace.HTTPException) as exc_info:
        await workspace.agent_email_connect(SimpleNamespace(id=uuid4()))

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == (
        "Gmail connection is temporarily unavailable. Please try again."
    )


def test_google_cancel_returns_friendly_html_without_requiring_code(monkeypatch):
    redis = FakeRedis()
    user_id = uuid4()
    monkeypatch.setattr(workspace, "get_redis_cache", lambda: redis)
    state = workspace.secrets.token_urlsafe(32)
    redis.values[workspace._gmail_oauth_state_key(state)] = str(user_id)

    with route_client(matcha_router, prefix="/api") as client:
        response = client.get(
            CALLBACK_PATH,
            params={"error": "access_denied", "state": state},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Gmail connection canceled" in response.text
    assert redis.values == {}


def test_missing_code_returns_friendly_html_instead_of_422(monkeypatch):
    redis = FakeRedis()
    user_id = uuid4()
    monkeypatch.setattr(workspace, "get_redis_cache", lambda: redis)
    state = workspace.secrets.token_urlsafe(32)
    redis.values[workspace._gmail_oauth_state_key(state)] = str(user_id)

    with route_client(matcha_router, prefix="/api") as client:
        response = client.get(CALLBACK_PATH, params={"state": state})

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("text/html")
    assert "Google could not complete" in response.text
    assert redis.values == {}


def test_callback_exchanges_code_and_stores_token_without_matcha_auth(monkeypatch):
    redis = FakeRedis()
    user_id = uuid4()
    credentials = {
        "client_id": "client-id.apps.googleusercontent.com",
        "client_secret": "client-secret",
    }
    exchange_calls = []
    saved = {}

    class FakeResponse:
        status_code = 200
        text = "ok"

        @staticmethod
        def json():
            return {
                "access_token": "access-token",
                "refresh_token": "refresh-token",
            }

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

        async def post(self, url, **kwargs):
            exchange_calls.append((url, kwargs))
            return FakeResponse()

    class FakeGmailService:
        def __init__(self, token_user_id):
            saved["user_id"] = token_user_id

        async def save_token(self, token):
            saved["token"] = token

    monkeypatch.setattr(workspace, "get_redis_cache", lambda: redis)
    monkeypatch.setattr(gmail_service, "get_oauth_credentials", lambda: credentials)
    monkeypatch.setattr(gmail_service, "GmailService", FakeGmailService)
    monkeypatch.setattr(workspace.httpx, "AsyncClient", FakeAsyncClient)

    state = workspace.secrets.token_urlsafe(32)
    redis.values[workspace._gmail_oauth_state_key(state)] = str(user_id)
    with route_client(matcha_router, prefix="/api") as client:
        response = client.get(
            CALLBACK_PATH,
            params={"code": "authorization-code", "state": state},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Gmail connected" in response.text
    assert redis.values == {}
    assert exchange_calls == [
        (
            "https://oauth2.googleapis.com/token",
            {
                "data": {
                    "code": "authorization-code",
                    "client_id": credentials["client_id"],
                    "client_secret": credentials["client_secret"],
                    "redirect_uri": (
                        "https://hey-matcha.com/api/matcha-work/agent/email/callback"
                    ),
                    "grant_type": "authorization_code",
                },
                "timeout": 15.0,
            },
        )
    ]
    assert saved == {
        "user_id": user_id,
        "token": {
            "token": "access-token",
            "refresh_token": "refresh-token",
            "client_id": credentials["client_id"],
            "client_secret": credentials["client_secret"],
            "scopes": gmail_service.GMAIL_SCOPES,
        },
    }
