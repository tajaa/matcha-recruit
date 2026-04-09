import asyncio

import pytest

from app.matcha.services.google_workspace_service import (
    GoogleWorkspaceProvisioningError,
    GoogleWorkspaceService,
)


def test_google_workspace_mock_provisioning():
    service = GoogleWorkspaceService()
    result = asyncio.run(
        service.provision_user(
            {"mode": "mock"},
            {},
            {"email": "jane@example.com", "first_name": "Jane", "last_name": "Doe"},
        )
    )

    assert result["mode"] == "mock"
    assert result["external_email"] == "jane@example.com"
    assert result["status"] == "active"
    assert result["external_user_id"].startswith("mock-")


def test_google_workspace_api_token_requires_token():
    service = GoogleWorkspaceService()
    with pytest.raises(GoogleWorkspaceProvisioningError, match="access token"):
        asyncio.run(
            service.provision_user(
                {"mode": "api_token"},
                {},
                {"email": "jane@example.com", "first_name": "Jane", "last_name": "Doe"},
            )
        )


def test_google_workspace_test_connection_missing_token():
    service = GoogleWorkspaceService()
    ok, error = asyncio.run(service.test_connection({"mode": "api_token"}, {}))

    assert ok is False
    assert error == "Google Workspace access token is missing"


def test_google_workspace_test_connection_missing_service_account_credentials():
    service = GoogleWorkspaceService()
    ok, error = asyncio.run(service.test_connection({"mode": "service_account"}, {}))

    assert ok is False
    assert error == "Google Workspace service account credentials are missing"


def test_google_workspace_service_account_requires_delegated_admin():
    service = GoogleWorkspaceService()
    credentials = {
        "client_email": "svc@example.iam.gserviceaccount.com",
        "private_key": "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----\n",
        "token_uri": "https://oauth2.googleapis.com/token",
    }

    with pytest.raises(GoogleWorkspaceProvisioningError, match="Delegated admin email is required"):
        asyncio.run(
            service.provision_user(
                {"mode": "service_account"},
                {"service_account_json": credentials},
                {"email": "jane@example.com", "first_name": "Jane", "last_name": "Doe"},
            )
        )


def test_google_workspace_api_token_sets_temporary_password(monkeypatch: pytest.MonkeyPatch):
    captured_payload = {}

    class _FakeResponse:
        def __init__(self, status_code: int, payload: dict):
            self.status_code = status_code
            self._payload = payload
            self.text = ""
            self.content = b"{}"

        def json(self):
            return self._payload

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url: str, headers=None, json=None):
            if url.endswith("/users"):
                captured_payload.update(json or {})
                return _FakeResponse(201, {"id": "google-user-1", "primaryEmail": "jane@example.com"})
            if "/groups/" in url and "/members" in url:
                return _FakeResponse(201, {})
            raise AssertionError(f"Unexpected POST URL {url}")

    monkeypatch.setattr("app.matcha.services.google_workspace_service.httpx.AsyncClient", _FakeAsyncClient)

    service = GoogleWorkspaceService()
    result = asyncio.run(
        service.provision_user(
            {"mode": "api_token", "default_groups": ["engineering@example.com"]},
            {"access_token": "token-123"},
            {"email": "jane@example.com", "first_name": "Jane", "last_name": "Doe"},
        )
    )

    assert isinstance(captured_payload.get("password"), str)
    assert len(captured_payload["password"]) >= 12
    assert captured_payload["changePasswordAtNextLogin"] is True
    assert result["external_email"] == "jane@example.com"


def test_google_workspace_api_token_falls_back_when_org_unit_invalid(monkeypatch: pytest.MonkeyPatch):
    payloads = []

    class _FakeResponse:
        def __init__(self, status_code: int, payload: dict):
            self.status_code = status_code
            self._payload = payload
            self.text = ""
            self.content = b"{}"

        def json(self):
            return self._payload

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url: str, headers=None, json=None):
            if not url.endswith("/users"):
                raise AssertionError(f"Unexpected POST URL {url}")
            payloads.append(dict(json or {}))
            if len(payloads) == 1:
                return _FakeResponse(400, {"error": {"message": "Invalid Input: INVALID_OU_ID"}})
            return _FakeResponse(201, {"id": "google-user-2", "primaryEmail": "jane@example.com"})

    monkeypatch.setattr("app.matcha.services.google_workspace_service.httpx.AsyncClient", _FakeAsyncClient)

    service = GoogleWorkspaceService()
    result = asyncio.run(
        service.provision_user(
            {"mode": "api_token", "default_org_unit": "/Employees"},
            {"access_token": "token-123"},
            {"email": "jane@example.com", "first_name": "Jane", "last_name": "Doe"},
        )
    )

    assert len(payloads) == 2
    assert payloads[0].get("orgUnitPath") == "/Employees"
    assert "orgUnitPath" not in payloads[1]
    assert "org_unit_fallback:/Employees:INVALID_OU_ID" in (result.get("warnings") or [])
