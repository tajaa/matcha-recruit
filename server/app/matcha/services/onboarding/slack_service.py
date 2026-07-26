"""Slack provisioning client used by onboarding orchestration."""

from __future__ import annotations

from typing import Any, Optional
from uuid import uuid4

import httpx

from app.core.services.secret_crypto import decrypt_secret


class SlackProvisioningError(Exception):
    def __init__(self, code: str, message: str, *, needs_action: bool = False):
        super().__init__(message)
        self.code = code
        self.needs_action = needs_action


def _extract_response_error(response: httpx.Response) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, str):
                return error
    except Exception:
        pass
    return (response.text or "Unknown Slack API error").strip()


SLACK_NEEDS_ACTION_ERRORS = {
    "account_inactive",
    "feature_not_enabled",
    "invalid_auth",
    "invalid_team",
    "is_bot",
    "method_not_supported_for_team",
    "missing_scope",
    "no_permission",
    "not_allowed_token_type",
    "not_authed",
    "token_revoked",
}

SLACK_ALREADY_PRESENT_ERRORS = {
    "already_active",
    "already_in_team",
    "already_invited",
    "already_exists",
}

SLACK_ENTERPRISE_ONLY_ERRORS = {
    "not_allowed_token_type",
    "missing_scope",
    "feature_not_enabled",
    "method_not_supported_for_team",
}


def _needs_action_for_slack_error(error: str, status_code: int) -> bool:
    return error in SLACK_NEEDS_ACTION_ERRORS or status_code in {401, 403}


def _response_payload_dict(response: httpx.Response, operation: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except Exception:
        raise SlackProvisioningError(
            "api_response_invalid",
            f"Slack {operation} returned a non-JSON response: {_extract_response_error(response)}",
            needs_action=response.status_code in {401, 403},
        )

    if not isinstance(payload, dict):
        raise SlackProvisioningError(
            "api_response_invalid",
            f"Slack {operation} returned an invalid payload",
            needs_action=response.status_code in {401, 403},
        )

    return payload


class SlackService:
    BASE_URL = "https://slack.com/api"

    def __init__(self, *, timeout_seconds: float = 20.0):
        self.timeout_seconds = timeout_seconds

    async def test_connection(self, config: dict, secrets: dict) -> tuple[bool, Optional[str]]:
        mode = config.get("mode") or "api"
        if mode == "mock":
            return True, None

        try:
            access_token = self._resolve_access_token(secrets)
        except SlackProvisioningError as exc:
            return False, str(exc)

        headers = {"Authorization": f"Bearer {access_token}"}

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(f"{self.BASE_URL}/team.info", headers=headers)
            
        if response.status_code < 400:
            payload = response.json()
            if payload.get("ok"):
                return True, None
            else:
                return False, payload.get("error", "Unknown error")
        return False, _extract_response_error(response)

    async def provision_user(self, config: dict, secrets: dict, employee: dict) -> dict[str, Any]:
        mode = config.get("mode") or "api"
        if mode == "mock":
            return self._provision_user_mock(employee)

        access_token = self._resolve_access_token(secrets)

        return await self._provision_user_api_token(config, access_token, employee)

    def _resolve_access_token(self, secrets: dict) -> str:
        # Standard oauth tokens
        access_token = secrets.get("bot_access_token") or secrets.get("access_token")
        
        # We might have stored just client secret, wait. Actually OAuth callback stores `bot_access_token`?
        # Let's check how provisioning.py stores it
        
        if not access_token:
            raise SlackProvisioningError(
                "missing_access_token",
                "Slack access token is missing",
                needs_action=True,
            )
            
        # The token is encrypted
        decrypted = decrypt_secret(access_token)
        if not decrypted:
            raise SlackProvisioningError(
                "invalid_access_token",
                "Slack access token could not be decrypted",
                needs_action=True,
            )
            
        return decrypted

    def _provision_user_mock(self, employee: dict) -> dict[str, Any]:
        return {
            "mode": "mock",
            "external_user_id": f"mock-slack-{uuid4()}",
            "external_email": employee.get("email"),
            "status": "active",
            "warnings": [],
        }

    async def _provision_user_api_token(self, config: dict, access_token: str, employee: dict) -> dict[str, Any]:
        email = employee.get("email")
        if not email:
            raise SlackProvisioningError("missing_email", "Employee email is required for Slack provisioning")

        headers = {"Authorization": f"Bearer {access_token}"}
        first_name = str(employee.get("first_name") or "").strip()
        last_name = str(employee.get("last_name") or "").strip()
        full_name = " ".join(part for part in [first_name, last_name] if part)
        team_id = str(config.get("slack_team_id") or "").strip()

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            # Check if user already exists
            response = await client.get(
                f"{self.BASE_URL}/users.lookupByEmail", 
                headers=headers,
                params={"email": email}
            )
            payload = _response_payload_dict(response, "lookup by email")

            if payload.get("ok"):
                # User exists
                user = payload.get("user") if isinstance(payload.get("user"), dict) else {}
                user_id = user.get("id")
                if not user_id:
                    raise SlackProvisioningError(
                        "lookup_failed",
                        "Slack lookup by email returned a user without an id",
                    )
                return {
                    "mode": "api",
                    "external_user_id": user_id,
                    "external_email": email,
                    "status": "active",
                    "warnings": ["User already exists in Slack"],
                }

            error = str(payload.get("error") or "").strip()
            if error != "users_not_found":
                raise SlackProvisioningError(
                    "lookup_failed",
                    f"Slack lookup by email failed: {error or _extract_response_error(response)}",
                    needs_action=_needs_action_for_slack_error(error, response.status_code),
                )

            invite_payload: dict[str, str] = {"email": str(email)}
            if full_name:
                invite_payload["real_name"] = full_name
            if team_id:
                invite_payload["team_id"] = team_id

            invite_response = await client.post(
                f"{self.BASE_URL}/admin.users.invite",
                headers=headers,
                data=invite_payload,
            )
            invite_result = _response_payload_dict(invite_response, "invite")

            if invite_result.get("ok"):
                return {
                    "mode": "api_invite",
                    "external_user_id": None,
                    "external_email": email,
                    "status": "invited",
                    "warnings": [],
                }

            invite_error = str(invite_result.get("error") or "").strip()
            if invite_error in SLACK_ALREADY_PRESENT_ERRORS:
                status_value = "active" if invite_error in {"already_active", "already_in_team"} else "invited"
                return {
                    "mode": "api_invite",
                    "external_user_id": None,
                    "external_email": email,
                    "status": status_value,
                    "warnings": [f"Slack returned '{invite_error}' while inviting user."],
                }

            # Non-Enterprise workspaces can't use admin.users.invite — fall back to invite link
            invite_link = str(config.get("invite_link") or "").strip()
            if invite_error in SLACK_ENTERPRISE_ONLY_ERRORS and invite_link:
                return {
                    "mode": "invite_link",
                    "external_user_id": None,
                    "external_email": email,
                    "status": "invited_via_link",
                    "invite_link": invite_link,
                    "warnings": [
                        f"Workspace doesn't support admin.users.invite ({invite_error}). "
                        "Falling back to shared invite link."
                    ],
                }

            hint = (
                " Ensure your Slack app/token can call admin.users.invite "
                "(typically admin scopes on Enterprise Grid), or add a workspace invite link in Slack provisioning settings."
            )
            message = f"Slack invite failed: {invite_error or _extract_response_error(invite_response)}.{hint}"
            raise SlackProvisioningError(
                "invite_failed",
                message,
                needs_action=_needs_action_for_slack_error(invite_error, invite_response.status_code),
            )
