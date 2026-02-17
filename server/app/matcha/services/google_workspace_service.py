"""Google Workspace provisioning client used by onboarding orchestration."""

from __future__ import annotations

from typing import Any, Optional
from uuid import uuid4

import httpx


class GoogleWorkspaceProvisioningError(Exception):
    def __init__(self, code: str, message: str, *, needs_action: bool = False):
        super().__init__(message)
        self.code = code
        self.needs_action = needs_action


def _extract_response_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                message = error.get("message")
                if isinstance(message, str) and message.strip():
                    return message.strip()
            message = payload.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()
    except Exception:
        pass
    return (response.text or "Unknown Google API error").strip()


class GoogleWorkspaceService:
    BASE_URL = "https://admin.googleapis.com/admin/directory/v1"

    def __init__(self, *, timeout_seconds: float = 20.0):
        self.timeout_seconds = timeout_seconds

    async def test_connection(self, config: dict, secrets: dict) -> tuple[bool, Optional[str]]:
        mode = (config or {}).get("mode") or "mock"
        if mode == "mock":
            return True, None

        if mode != "api_token":
            return False, f"Unsupported Google Workspace mode '{mode}'"

        access_token = (secrets or {}).get("access_token")
        if not access_token:
            return False, "Google Workspace access token is missing"

        headers = {"Authorization": f"Bearer {access_token}"}
        params = {"customer": "my_customer", "maxResults": 1}

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(f"{self.BASE_URL}/users", headers=headers, params=params)
        if response.status_code < 400:
            return True, None
        return False, _extract_response_error(response)

    async def provision_user(self, config: dict, secrets: dict, employee: dict) -> dict[str, Any]:
        mode = (config or {}).get("mode") or "mock"
        if mode == "mock":
            return self._provision_user_mock(employee)

        if mode != "api_token":
            raise GoogleWorkspaceProvisioningError(
                "unsupported_mode",
                f"Unsupported Google Workspace mode '{mode}'",
                needs_action=True,
            )

        access_token = (secrets or {}).get("access_token")
        if not access_token:
            raise GoogleWorkspaceProvisioningError(
                "missing_access_token",
                "Google Workspace access token is missing",
                needs_action=True,
            )

        return await self._provision_user_api_token(config, access_token, employee)

    def _provision_user_mock(self, employee: dict) -> dict[str, Any]:
        return {
            "mode": "mock",
            "external_user_id": f"mock-{uuid4()}",
            "external_email": employee.get("email"),
            "status": "active",
            "groups_added": [],
            "warnings": [],
        }

    async def _provision_user_api_token(self, config: dict, access_token: str, employee: dict) -> dict[str, Any]:
        primary_email = str(employee.get("email") or "").strip()
        first_name = str(employee.get("first_name") or "").strip() or "Unknown"
        last_name = str(employee.get("last_name") or "").strip() or "User"

        if not primary_email:
            raise GoogleWorkspaceProvisioningError(
                "invalid_employee_email",
                "Employee email is required for Google Workspace provisioning",
                needs_action=True,
            )

        org_unit = (config or {}).get("default_org_unit")
        groups = (config or {}).get("default_groups") or []

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        user_payload: dict[str, Any] = {
            "primaryEmail": primary_email,
            "name": {
                "givenName": first_name,
                "familyName": last_name,
            },
            "changePasswordAtNextLogin": True,
        }
        if org_unit:
            user_payload["orgUnitPath"] = org_unit

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            create_resp = await client.post(f"{self.BASE_URL}/users", headers=headers, json=user_payload)

            if create_resp.status_code in (200, 201):
                user_json = create_resp.json()
            elif create_resp.status_code == 409:
                # User already exists: treat as idempotent success.
                fetch_resp = await client.get(f"{self.BASE_URL}/users/{primary_email}", headers=headers)
                if fetch_resp.status_code >= 400:
                    raise GoogleWorkspaceProvisioningError(
                        "google_user_conflict_fetch_failed",
                        _extract_response_error(fetch_resp),
                    )
                user_json = fetch_resp.json()
            elif create_resp.status_code in (401, 403):
                raise GoogleWorkspaceProvisioningError(
                    "google_auth_failed",
                    _extract_response_error(create_resp),
                    needs_action=True,
                )
            else:
                raise GoogleWorkspaceProvisioningError(
                    "google_user_create_failed",
                    _extract_response_error(create_resp),
                )

            groups_added: list[str] = []
            warnings: list[str] = []
            for group in groups:
                group_key = str(group).strip()
                if not group_key:
                    continue
                member_resp = await client.post(
                    f"{self.BASE_URL}/groups/{group_key}/members",
                    headers=headers,
                    json={"email": primary_email, "role": "MEMBER"},
                )
                if member_resp.status_code in (200, 201, 409):
                    groups_added.append(group_key)
                else:
                    warnings.append(f"group:{group_key}:{_extract_response_error(member_resp)}")

        return {
            "mode": "api_token",
            "external_user_id": user_json.get("id"),
            "external_email": user_json.get("primaryEmail", primary_email),
            "status": "active",
            "groups_added": groups_added,
            "warnings": warnings,
            "raw_user": user_json,
        }
