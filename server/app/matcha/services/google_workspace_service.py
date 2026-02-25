"""Google Workspace provisioning client used by onboarding orchestration."""

from __future__ import annotations

import json
import secrets
import string
import time
from typing import Any, Optional
from uuid import uuid4

import httpx
from jose import jwt


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
    SERVICE_ACCOUNT_TOKEN_AUDIENCE = "https://oauth2.googleapis.com/token"
    SERVICE_ACCOUNT_SCOPES = [
        "https://www.googleapis.com/auth/admin.directory.user",
        "https://www.googleapis.com/auth/admin.directory.group.member",
    ]

    def __init__(self, *, timeout_seconds: float = 20.0):
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _generate_initial_password(length: int = 20) -> str:
        """Generate a strong temporary password for newly provisioned users."""
        if length < 12:
            length = 12
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
        required = [
            secrets.choice(string.ascii_lowercase),
            secrets.choice(string.ascii_uppercase),
            secrets.choice(string.digits),
            secrets.choice("!@#$%^&*()-_=+"),
        ]
        remaining = [secrets.choice(alphabet) for _ in range(length - len(required))]
        chars = required + remaining
        secrets.SystemRandom().shuffle(chars)
        return "".join(chars)

    async def test_connection(self, config: dict, secrets: dict) -> tuple[bool, Optional[str]]:
        mode = (config or {}).get("mode") or "mock"
        if mode == "mock":
            return True, None

        try:
            access_token = await self._resolve_access_token(mode, config, secrets)
        except GoogleWorkspaceProvisioningError as exc:
            return False, str(exc)

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

        access_token = await self._resolve_access_token(mode, config, secrets)

        return await self._provision_user_api_token(config, access_token, employee)

    async def _resolve_access_token(self, mode: str, config: dict, secrets: dict) -> str:
        if mode == "api_token":
            access_token = (secrets or {}).get("access_token")
            if not access_token:
                raise GoogleWorkspaceProvisioningError(
                    "missing_access_token",
                    "Google Workspace access token is missing",
                    needs_action=True,
                )
            return str(access_token)

        if mode == "service_account":
            return await self._access_token_from_service_account(config, secrets)

        raise GoogleWorkspaceProvisioningError(
            "unsupported_mode",
            f"Unsupported Google Workspace mode '{mode}'",
            needs_action=True,
        )

    def _provision_user_mock(self, employee: dict) -> dict[str, Any]:
        return {
            "mode": "mock",
            "external_user_id": f"mock-{uuid4()}",
            "external_email": employee.get("email"),
            "status": "active",
            "groups_added": [],
            "warnings": [],
        }

    async def _access_token_from_service_account(self, config: dict, secrets: dict) -> str:
        raw_credentials = (secrets or {}).get("service_account_json")
        if not raw_credentials:
            raise GoogleWorkspaceProvisioningError(
                "missing_service_account_credentials",
                "Google Workspace service account credentials are missing",
                needs_action=True,
            )

        if isinstance(raw_credentials, dict):
            credentials = dict(raw_credentials)
        else:
            try:
                credentials = json.loads(str(raw_credentials))
            except json.JSONDecodeError:
                raise GoogleWorkspaceProvisioningError(
                    "invalid_service_account_credentials",
                    "Google Workspace service account credentials must be valid JSON",
                    needs_action=True,
                )

        client_email = str(credentials.get("client_email") or "").strip()
        private_key = str(credentials.get("private_key") or "").strip()
        token_uri = str(
            credentials.get("token_uri")
            or self.SERVICE_ACCOUNT_TOKEN_AUDIENCE
        ).strip()
        delegated_admin_email = str(
            (config or {}).get("delegated_admin_email")
            or (config or {}).get("admin_email")
            or ""
        ).strip()

        if not client_email or not private_key:
            raise GoogleWorkspaceProvisioningError(
                "invalid_service_account_credentials",
                "Service account credentials must include client_email and private_key",
                needs_action=True,
            )
        if not delegated_admin_email:
            raise GoogleWorkspaceProvisioningError(
                "missing_delegated_admin_email",
                "Delegated admin email is required for service account mode",
                needs_action=True,
            )

        now = int(time.time())
        assertion_payload = {
            "iss": client_email,
            "sub": delegated_admin_email,
            "scope": " ".join(self.SERVICE_ACCOUNT_SCOPES),
            "aud": token_uri,
            "iat": now,
            "exp": now + 3600,
        }
        headers = {}
        key_id = str(credentials.get("private_key_id") or "").strip()
        if key_id:
            headers["kid"] = key_id

        try:
            assertion = jwt.encode(
                assertion_payload,
                private_key,
                algorithm="RS256",
                headers=headers or None,
            )
        except Exception as exc:  # pragma: no cover - defensive conversion
            raise GoogleWorkspaceProvisioningError(
                "service_account_signing_failed",
                f"Failed to sign service account assertion: {exc}",
                needs_action=True,
            )

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                token_uri,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": assertion,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        if response.status_code >= 400:
            error_msg = _extract_response_error(response)
            if "invalid_grant" in error_msg or "Invalid email" in error_msg:
                error_msg = (
                    f"{error_msg}. Hint: Ensure the Service Account has Domain-Wide Delegation enabled "
                    f"in the Google Admin Console and that '{delegated_admin_email}' is a valid admin user."
                )
            
            raise GoogleWorkspaceProvisioningError(
                "service_account_token_exchange_failed",
                error_msg,
                needs_action=response.status_code in (400, 401, 403),
            )

        payload = response.json() if response.content else {}
        access_token = payload.get("access_token") if isinstance(payload, dict) else None
        if not access_token:
            raise GoogleWorkspaceProvisioningError(
                "service_account_token_missing",
                "Google OAuth token response did not include access_token",
                needs_action=True,
            )
        return str(access_token)

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
            "password": self._generate_initial_password(),
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
