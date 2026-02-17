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
