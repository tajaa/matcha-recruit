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
