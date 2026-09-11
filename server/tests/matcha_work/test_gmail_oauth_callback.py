"""Regression coverage for the system-browser Gmail OAuth callback."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core.services.secret_crypto import encrypt_secret
from app.matcha.routes import matcha_router
from app.matcha.routes.matcha_work import workspace
from app.matcha.services.matcha_work import gmail_service
from tests._helpers.routes import route_client


CALLBACK_PATH = "/api/matcha-work/agent/email/callback"


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


def test_oauth_state_round_trips_and_expires(monkeypatch):
    user_id = uuid4()
    monkeypatch.setattr(workspace.time, "time", lambda: 1_000)
    state = workspace._build_gmail_oauth_state(user_id)

    assert workspace._decode_gmail_oauth_state(state) == user_id

    monkeypatch.setattr(workspace.time, "time", lambda: 1_601)
    with pytest.raises(ValueError, match="Invalid or expired OAuth state"):
        workspace._decode_gmail_oauth_state(state)


def test_callback_rejects_legacy_user_id_only_state():
    legacy_state = encrypt_secret(str(uuid4()))
    assert legacy_state is not None

    with pytest.raises(ValueError, match="Invalid or expired OAuth state"):
        workspace._decode_gmail_oauth_state(legacy_state)


def test_callback_exchanges_code_and_stores_token_without_matcha_auth(monkeypatch):
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

    monkeypatch.setattr(
        workspace,
        "get_settings",
        lambda: SimpleNamespace(app_base_url="https://hey-matcha.com"),
    )
    monkeypatch.setattr(gmail_service, "get_oauth_credentials", lambda: credentials)
    monkeypatch.setattr(gmail_service, "GmailService", FakeGmailService)
    monkeypatch.setattr(workspace.httpx, "AsyncClient", FakeAsyncClient)

    state = workspace._build_gmail_oauth_state(user_id)
    with route_client(matcha_router, prefix="/api") as client:
        response = client.get(
            CALLBACK_PATH,
            params={"code": "authorization-code", "state": state},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Gmail connected" in response.text
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
