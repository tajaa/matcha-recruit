"""Provisioning routes for external onboarding systems."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime
from typing import Optional
from urllib.parse import urlencode
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field

from ...config import get_settings
from ...core.models.auth import CurrentUser
from ...core.services.secret_crypto import decrypt_secret, encrypt_secret
from ...database import get_connection
from ..dependencies import get_client_company_id, require_admin_or_client
from ..services.google_workspace_service import GoogleWorkspaceService
from ..services.onboarding_orchestrator import (
    PROVIDER_GOOGLE_WORKSPACE,
    PROVIDER_SLACK,
    retry_google_workspace_onboarding,
    start_google_workspace_onboarding,
    start_slack_onboarding,
)

router = APIRouter()

DEFAULT_SLACK_SCOPES = [
    "users:read",
    "users:read.email",
    "users:write",
    "channels:read",
    "conversations.invite",
]
SLACK_OAUTH_STATE_TTL_SECONDS = 900


def _json_object(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _coerce_bool(value, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _split_comma_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw_items = value.replace("\n", ",").split(",")
    elif isinstance(value, (list, tuple, set)):
        raw_items = list(value)
    else:
        raw_items = [value]

    result: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        normalized = str(item).strip()
        if not normalized:
            continue
        lowered = normalized.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        result.append(normalized)
    return result


def _normalize_slack_scopes(value) -> list[str]:
    scopes = _split_comma_list(value)
    return scopes or list(DEFAULT_SLACK_SCOPES)


def _normalize_slack_channels(value) -> list[str]:
    channels = _split_comma_list(value)
    normalized: list[str] = []
    for channel in channels:
        cleaned = channel.strip()
        if not cleaned:
            continue
        if not cleaned.startswith("#"):
            cleaned = f"#{cleaned}"
        normalized.append(cleaned.lower())
    # De-dupe preserving order
    deduped: list[str] = []
    seen: set[str] = set()
    for channel in normalized:
        if channel in seen:
            continue
        seen.add(channel)
        deduped.append(channel)
    return deduped


def _default_slack_oauth_redirect_uri() -> str:
    settings = get_settings()
    return f"{settings.app_base_url.rstrip('/')}/api/provisioning/slack/oauth/callback"


def _slack_oauth_redirect_uri() -> str:
    """Return Slack OAuth redirect URI, preferring explicit env override."""
    explicit = (os.getenv("SLACK_OAUTH_REDIRECT_URI") or "").strip()
    return explicit or _default_slack_oauth_redirect_uri()


def _build_slack_oauth_state(company_id: UUID) -> str:
    payload = f"{company_id}:{int(time.time())}:{secrets.token_urlsafe(12)}"
    secret = get_settings().jwt_secret_key.encode("utf-8")
    signature = hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    token = f"{payload}:{signature}"
    return base64.urlsafe_b64encode(token.encode("utf-8")).decode("utf-8").rstrip("=")


def _decode_slack_oauth_state(state: str) -> UUID:
    if not state:
        raise ValueError("Missing state")
    padded = state + "=" * (-len(state) % 4)
    try:
        decoded = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
    except Exception as exc:  # pragma: no cover - defensive parsing guard
        raise ValueError("Invalid state encoding") from exc

    parts = decoded.split(":")
    if len(parts) != 4:
        raise ValueError("Invalid state payload")

    company_raw, timestamp_raw, nonce, provided_signature = parts
    payload = f"{company_raw}:{timestamp_raw}:{nonce}"
    secret = get_settings().jwt_secret_key.encode("utf-8")
    expected_signature = hmac.new(
        secret, payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(provided_signature, expected_signature):
        raise ValueError("State signature mismatch")

    issued_at = int(timestamp_raw)
    if (int(time.time()) - issued_at) > SLACK_OAUTH_STATE_TTL_SECONDS:
        raise ValueError("State expired")

    return UUID(company_raw)


def _slack_callback_redirect(status_value: str, message: str) -> RedirectResponse:
    settings = get_settings()
    query = urlencode(
        {
            "slack_oauth": status_value,
            "slack_message": message,
        }
    )
    url = f"{settings.app_base_url.rstrip('/')}/app/matcha/slack-provisioning?{query}"
    return RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)


class GoogleWorkspaceConnectionRequest(BaseModel):
    mode: str = Field(default="mock", pattern="^(mock|api_token|service_account)$")
    domain: Optional[str] = Field(default=None, max_length=255)
    admin_email: Optional[EmailStr] = None
    delegated_admin_email: Optional[EmailStr] = None
    default_org_unit: Optional[str] = Field(default=None, max_length=255)
    default_groups: list[str] = Field(default_factory=list)
    auto_provision_on_employee_create: bool = True
    access_token: Optional[str] = None
    service_account_json: Optional[str] = None
    test_connection: bool = True


class GoogleWorkspaceConnectionStatus(BaseModel):
    provider: str = PROVIDER_GOOGLE_WORKSPACE
    connected: bool
    status: str
    mode: Optional[str] = None
    domain: Optional[str] = None
    admin_email: Optional[str] = None
    delegated_admin_email: Optional[str] = None
    default_org_unit: Optional[str] = None
    default_groups: list[str] = Field(default_factory=list)
    auto_provision_on_employee_create: bool = True
    has_access_token: bool = False
    has_service_account_credentials: bool = False
    last_tested_at: Optional[datetime] = None
    last_error: Optional[str] = None
    updated_at: Optional[datetime] = None


class SlackConnectionRequest(BaseModel):
    client_id: Optional[str] = Field(default=None, max_length=255)
    client_secret: Optional[str] = None
    workspace_url: Optional[str] = Field(default=None, max_length=255)
    admin_email: Optional[EmailStr] = None
    default_channels: list[str] = Field(default_factory=list)
    oauth_scopes: list[str] = Field(default_factory=lambda: list(DEFAULT_SLACK_SCOPES))
    auto_invite_on_employee_create: bool = True
    sync_display_name: bool = True


class SlackConnectionStatus(BaseModel):
    provider: str = PROVIDER_SLACK
    connected: bool
    status: str
    client_id: Optional[str] = None
    has_client_secret: bool = False
    workspace_url: Optional[str] = None
    admin_email: Optional[str] = None
    default_channels: list[str] = Field(default_factory=list)
    oauth_scopes: list[str] = Field(default_factory=lambda: list(DEFAULT_SLACK_SCOPES))
    auto_invite_on_employee_create: bool = True
    sync_display_name: bool = True
    has_bot_token: bool = False
    slack_team_id: Optional[str] = None
    slack_team_name: Optional[str] = None
    slack_team_domain: Optional[str] = None
    bot_user_id: Optional[str] = None
    oauth_redirect_uri: Optional[str] = None
    default_oauth_redirect_uri: Optional[str] = None
    last_tested_at: Optional[datetime] = None
    last_error: Optional[str] = None
    updated_at: Optional[datetime] = None


class SlackOAuthStartResponse(BaseModel):
    authorize_url: str
    state: str
    redirect_uri: Optional[str] = None
    default_redirect_uri: Optional[str] = None


class ProvisioningStepStatusResponse(BaseModel):
    step_id: UUID
    step_key: str
    status: str
    attempts: int
    last_error: Optional[str] = None
    last_response: dict = Field(default_factory=dict)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class ProvisioningRunStatusResponse(BaseModel):
    run_id: UUID
    company_id: UUID
    employee_id: UUID
    provider: str
    status: str
    trigger_source: str
    triggered_by: Optional[UUID] = None
    retry_of_run_id: Optional[str] = None
    last_error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    steps: list[ProvisioningStepStatusResponse] = Field(default_factory=list)


class ExternalIdentityResponse(BaseModel):
    provider: str
    external_user_id: Optional[str] = None
    external_email: Optional[str] = None
    status: str
    raw_profile: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class EmployeeProvisioningStatusResponse(BaseModel):
    connection: GoogleWorkspaceConnectionStatus
    external_identity: Optional[ExternalIdentityResponse] = None
    runs: list[ProvisioningRunStatusResponse] = Field(default_factory=list)


class SlackEmployeeProvisioningStatusResponse(BaseModel):
    connection: SlackConnectionStatus
    external_identity: Optional[ExternalIdentityResponse] = None
    runs: list[ProvisioningRunStatusResponse] = Field(default_factory=list)


class ProvisioningRunListItem(BaseModel):
    run_id: UUID
    company_id: UUID
    employee_id: UUID
    employee_name: Optional[str] = None
    employee_email: Optional[str] = None
    provider: str
    status: str
    trigger_source: str
    triggered_by: Optional[UUID] = None
    last_error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


def _connection_status_payload(row) -> GoogleWorkspaceConnectionStatus:
    if not row:
        return GoogleWorkspaceConnectionStatus(
            connected=False,
            status="disconnected",
            has_access_token=False,
        )

    config = _json_object(row["config"])
    secrets = _json_object(row["secrets"])
    status_value = row["status"] or "disconnected"
    return GoogleWorkspaceConnectionStatus(
        connected=status_value == "connected",
        status=status_value,
        mode=config.get("mode"),
        domain=config.get("domain"),
        admin_email=config.get("admin_email"),
        delegated_admin_email=config.get("delegated_admin_email"),
        default_org_unit=config.get("default_org_unit"),
        default_groups=[
            str(item)
            for item in (config.get("default_groups") or [])
            if str(item).strip()
        ],
        auto_provision_on_employee_create=_coerce_bool(
            config.get("auto_provision_on_employee_create"), True
        ),
        has_access_token=bool(secrets.get("access_token")),
        has_service_account_credentials=bool(secrets.get("service_account_json")),
        last_tested_at=row["last_tested_at"],
        last_error=row["last_error"],
        updated_at=row["updated_at"],
    )


def _slack_connection_status_payload(row) -> SlackConnectionStatus:
    resolved_redirect_uri = _slack_oauth_redirect_uri()
    default_redirect_uri = _default_slack_oauth_redirect_uri()
    if not row:
        return SlackConnectionStatus(
            connected=False,
            status="disconnected",
            oauth_scopes=list(DEFAULT_SLACK_SCOPES),
            has_client_secret=False,
            oauth_redirect_uri=resolved_redirect_uri,
            default_oauth_redirect_uri=default_redirect_uri,
        )

    config = _json_object(row["config"])
    secrets = _json_object(row["secrets"])
    status_value = row["status"] or "disconnected"
    return SlackConnectionStatus(
        connected=status_value == "connected",
        status=status_value,
        client_id=config.get("client_id"),
        has_client_secret=bool(secrets.get("client_secret")),
        workspace_url=config.get("workspace_url"),
        admin_email=config.get("admin_email"),
        default_channels=_normalize_slack_channels(config.get("default_channels")),
        oauth_scopes=_normalize_slack_scopes(config.get("oauth_scopes")),
        auto_invite_on_employee_create=_coerce_bool(
            config.get("auto_invite_on_employee_create"), True
        ),
        sync_display_name=_coerce_bool(config.get("sync_display_name"), True),
        has_bot_token=bool(secrets.get("bot_access_token")),
        slack_team_id=config.get("slack_team_id"),
        slack_team_name=config.get("slack_team_name"),
        slack_team_domain=config.get("slack_team_domain"),
        bot_user_id=config.get("bot_user_id"),
        oauth_redirect_uri=resolved_redirect_uri,
        default_oauth_redirect_uri=default_redirect_uri,
        last_tested_at=row["last_tested_at"],
        last_error=row["last_error"],
        updated_at=row["updated_at"],
    )


def _run_payload(run_row, step_rows: list) -> ProvisioningRunStatusResponse:
    metadata = _json_object(run_row["metadata"])
    step_models = [
        ProvisioningStepStatusResponse(
            step_id=step["id"],
            step_key=step["step_key"],
            status=step["status"],
            attempts=step["attempts"],
            last_error=step["last_error"],
            last_response=_json_object(step["last_response"]),
            started_at=step["started_at"],
            completed_at=step["completed_at"],
            created_at=step["created_at"],
            updated_at=step["updated_at"],
        )
        for step in step_rows
    ]
    return ProvisioningRunStatusResponse(
        run_id=run_row["id"],
        company_id=run_row["company_id"],
        employee_id=run_row["employee_id"],
        provider=run_row["provider"],
        status=run_row["status"],
        trigger_source=run_row["trigger_source"],
        triggered_by=run_row["triggered_by"],
        retry_of_run_id=metadata.get("retry_of_run_id"),
        last_error=run_row["last_error"],
        started_at=run_row["started_at"],
        completed_at=run_row["completed_at"],
        metadata=metadata,
        created_at=run_row["created_at"],
        updated_at=run_row["updated_at"],
        steps=step_models,
    )


@router.get("/google-workspace/status", response_model=GoogleWorkspaceConnectionStatus)
async def get_google_workspace_connection_status(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT *
            FROM integration_connections
            WHERE company_id = $1 AND provider = $2
            """,
            company_id,
            PROVIDER_GOOGLE_WORKSPACE,
        )
    return _connection_status_payload(row)


@router.post(
    "/google-workspace/connect", response_model=GoogleWorkspaceConnectionStatus
)
async def connect_google_workspace(
    request: GoogleWorkspaceConnectionRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    service = GoogleWorkspaceService()

    async with get_connection() as conn:
        existing = await conn.fetchrow(
            """
            SELECT config, secrets
            FROM integration_connections
            WHERE company_id = $1 AND provider = $2
            """,
            company_id,
            PROVIDER_GOOGLE_WORKSPACE,
        )
        existing_secrets = _json_object(existing["secrets"]) if existing else {}
        existing_access_token_plain: Optional[str] = None
        existing_access_token_unreadable = False
        if existing_secrets.get("access_token"):
            try:
                existing_access_token_plain = decrypt_secret(
                    existing_secrets.get("access_token")
                )
            except ValueError:
                existing_access_token_unreadable = True
        existing_service_account_json_plain: Optional[str] = None
        existing_service_account_json_unreadable = False
        if existing_secrets.get("service_account_json"):
            try:
                existing_service_account_json_plain = decrypt_secret(
                    existing_secrets.get("service_account_json")
                )
            except ValueError:
                existing_service_account_json_unreadable = True

        default_groups = [
            str(item).strip() for item in request.default_groups if str(item).strip()
        ]
        config = {
            "mode": request.mode,
            "domain": request.domain,
            "admin_email": str(request.admin_email) if request.admin_email else None,
            "delegated_admin_email": str(request.delegated_admin_email)
            if request.delegated_admin_email
            else None,
            "default_org_unit": request.default_org_unit,
            "default_groups": default_groups,
            "auto_provision_on_employee_create": bool(
                request.auto_provision_on_employee_create
            ),
        }

        requested_access_token = (
            request.access_token.strip() if request.access_token else None
        )
        requested_service_account_json = (
            request.service_account_json.strip()
            if request.service_account_json
            else None
        )
        access_token_plain = requested_access_token or existing_access_token_plain
        service_account_json_plain = (
            requested_service_account_json or existing_service_account_json_plain
        )

        secrets_for_storage = dict(existing_secrets)
        secrets_for_test: dict = {}
        if request.mode == "mock":
            secrets_for_storage.pop("access_token", None)
            secrets_for_storage.pop("service_account_json", None)
        elif request.mode == "api_token":
            if not access_token_plain:
                message = "access_token is required when mode is api_token"
                if existing_access_token_unreadable and not requested_access_token:
                    message = "Stored Google Workspace access token is unreadable. Provide a new access_token."
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=message,
                )
            secrets_for_test["access_token"] = access_token_plain
            secrets_for_storage["access_token"] = encrypt_secret(access_token_plain)
            secrets_for_storage.pop("service_account_json", None)
        elif request.mode == "service_account":
            if not service_account_json_plain:
                message = (
                    "service_account_json is required when mode is service_account"
                )
                if (
                    existing_service_account_json_unreadable
                    and not requested_service_account_json
                ):
                    message = "Stored service account credentials are unreadable. Provide new service_account_json."
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=message,
                )
            delegated_admin_email = config.get("delegated_admin_email") or config.get(
                "admin_email"
            )
            if not delegated_admin_email:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="delegated_admin_email is required when mode is service_account",
                )
            secrets_for_test["service_account_json"] = service_account_json_plain
            secrets_for_storage["service_account_json"] = encrypt_secret(
                service_account_json_plain
            )
            secrets_for_storage.pop("access_token", None)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported mode '{request.mode}'",
            )

        # Normalize older plaintext stored tokens into encrypted format on save.
        if (
            request.mode == "api_token"
            and existing_access_token_plain
            and not requested_access_token
        ):
            secrets_for_storage["access_token"] = encrypt_secret(
                existing_access_token_plain
            )
        if (
            request.mode == "service_account"
            and existing_service_account_json_plain
            and not requested_service_account_json
        ):
            secrets_for_storage["service_account_json"] = encrypt_secret(
                existing_service_account_json_plain
            )

        status_value = "connected" if request.mode == "mock" else "needs_action"
        last_error = None
        last_tested_at = None

        if request.test_connection:
            ok, error = await service.test_connection(config, secrets_for_test)
            last_tested_at = datetime.utcnow()
            if ok:
                status_value = "connected"
            else:
                status_value = "error"
                last_error = error or "Google Workspace connection test failed"

        row = await conn.fetchrow(
            """
            INSERT INTO integration_connections (
                company_id, provider, status, config, secrets, last_tested_at, last_error, created_by, updated_by
            )
            VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6, $7, $8, $8)
            ON CONFLICT (company_id, provider)
            DO UPDATE SET
                status = EXCLUDED.status,
                config = EXCLUDED.config,
                secrets = EXCLUDED.secrets,
                last_tested_at = EXCLUDED.last_tested_at,
                last_error = EXCLUDED.last_error,
                updated_by = EXCLUDED.updated_by,
                updated_at = NOW()
            RETURNING *
            """,
            company_id,
            PROVIDER_GOOGLE_WORKSPACE,
            status_value,
            json.dumps(config),
            json.dumps(secrets_for_storage),
            last_tested_at,
            last_error,
            current_user.id,
        )

    return _connection_status_payload(row)


@router.get("/slack/status", response_model=SlackConnectionStatus)
async def get_slack_connection_status(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT *
            FROM integration_connections
            WHERE company_id = $1 AND provider = $2
            """,
            company_id,
            PROVIDER_SLACK,
        )
    return _slack_connection_status_payload(row)


@router.post("/slack/connect", response_model=SlackConnectionStatus)
async def connect_slack(
    request: SlackConnectionRequest,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)

    requested_client_id = (request.client_id or "").strip() or None
    requested_client_secret = (request.client_secret or "").strip() or None
    workspace_url = (request.workspace_url or "").strip() or None
    admin_email = str(request.admin_email).strip() if request.admin_email else None
    default_channels = _normalize_slack_channels(request.default_channels)
    oauth_scopes = _normalize_slack_scopes(request.oauth_scopes)

    async with get_connection() as conn:
        existing = await conn.fetchrow(
            """
            SELECT status, config, secrets, last_tested_at, last_error
            FROM integration_connections
            WHERE company_id = $1 AND provider = $2
            """,
            company_id,
            PROVIDER_SLACK,
        )
        existing_config = _json_object(existing["config"]) if existing else {}
        existing_secrets = _json_object(existing["secrets"]) if existing else {}
        existing_client_secret_plain: Optional[str] = None
        existing_client_secret_unreadable = False
        if existing_secrets.get("client_secret"):
            try:
                existing_client_secret_plain = decrypt_secret(
                    existing_secrets.get("client_secret")
                )
            except ValueError:
                existing_client_secret_unreadable = True

        existing_client_id = str(existing_config.get("client_id") or "").strip() or None
        client_id = requested_client_id or existing_client_id

        secrets_for_storage = dict(existing_secrets)
        if requested_client_secret:
            secrets_for_storage["client_secret"] = encrypt_secret(
                requested_client_secret
            )
        elif existing_client_secret_plain:
            # Normalize already-stored values to the current encryption envelope.
            secrets_for_storage["client_secret"] = encrypt_secret(
                existing_client_secret_plain
            )
        elif existing_client_secret_unreadable:
            # Drop unreadable legacy values so UI accurately reports that secret must be re-entered.
            secrets_for_storage.pop("client_secret", None)

        has_bot_token = bool(existing_secrets.get("bot_access_token"))

        config = {
            "client_id": client_id,
            "workspace_url": workspace_url,
            "admin_email": admin_email,
            "default_channels": default_channels,
            "oauth_scopes": oauth_scopes,
            "auto_invite_on_employee_create": bool(
                request.auto_invite_on_employee_create
            ),
            "sync_display_name": bool(request.sync_display_name),
            "slack_team_id": existing_config.get("slack_team_id"),
            "slack_team_name": existing_config.get("slack_team_name"),
            "slack_team_domain": existing_config.get("slack_team_domain"),
            "bot_user_id": existing_config.get("bot_user_id"),
        }

        status_value = "connected" if has_bot_token else "needs_action"
        last_error = (
            None if has_bot_token else (existing["last_error"] if existing else None)
        )
        last_tested_at = existing["last_tested_at"] if existing else None

        row = await conn.fetchrow(
            """
            INSERT INTO integration_connections (
                company_id, provider, status, config, secrets, last_tested_at, last_error, created_by, updated_by
            )
            VALUES ($1, $2, $3, $4::jsonb, $5::jsonb, $6, $7, $8, $8)
            ON CONFLICT (company_id, provider)
            DO UPDATE SET
                status = EXCLUDED.status,
                config = EXCLUDED.config,
                secrets = EXCLUDED.secrets,
                last_tested_at = EXCLUDED.last_tested_at,
                last_error = EXCLUDED.last_error,
                updated_by = EXCLUDED.updated_by,
                updated_at = NOW()
            RETURNING *
            """,
            company_id,
            PROVIDER_SLACK,
            status_value,
            json.dumps(config),
            json.dumps(secrets_for_storage),
            last_tested_at,
            last_error,
            current_user.id,
        )

    return _slack_connection_status_payload(row)


@router.post("/slack/oauth/start", response_model=SlackOAuthStartResponse)
async def start_slack_oauth(
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT config, secrets
            FROM integration_connections
            WHERE company_id = $1 AND provider = $2
            """,
            company_id,
            PROVIDER_SLACK,
        )
        if not row:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Save Slack provisioning settings first, including client ID and client secret.",
            )
        config = _json_object(row["config"]) if row else {}
        secrets = _json_object(row["secrets"]) if row else {}
        client_id = (str(config.get("client_id") or "")).strip()
        if not client_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Slack client ID is missing. Save it in Slack provisioning settings.",
            )

        encrypted_client_secret = secrets.get("client_secret")
        if not encrypted_client_secret:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Slack client secret is missing. Save it in Slack provisioning settings.",
            )
        try:
            decrypted_client_secret = decrypt_secret(encrypted_client_secret)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Stored Slack client secret is unreadable. Re-save Slack client secret in provisioning settings.",
            )
        if not str(decrypted_client_secret).strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Slack client secret is empty. Save it in Slack provisioning settings.",
            )

        scopes = _normalize_slack_scopes(config.get("oauth_scopes"))

    state_value = _build_slack_oauth_state(company_id)
    oauth_redirect_uri = _slack_oauth_redirect_uri()
    authorize_params = {
        "client_id": client_id,
        "scope": ",".join(scopes),
        "state": state_value,
        "redirect_uri": oauth_redirect_uri,
    }

    query = urlencode(authorize_params)
    authorize_url = f"https://slack.com/oauth/v2/authorize?{query}"
    return SlackOAuthStartResponse(
        authorize_url=authorize_url,
        state=state_value,
        redirect_uri=oauth_redirect_uri,
        default_redirect_uri=_default_slack_oauth_redirect_uri(),
    )


@router.get("/slack/oauth/callback", include_in_schema=False)
async def slack_oauth_callback(
    code: Optional[str] = Query(default=None),
    state: Optional[str] = Query(default=None),
    error: Optional[str] = Query(default=None),
):
    if error:
        return _slack_callback_redirect("error", f"Slack OAuth was cancelled: {error}")

    if not code or not state:
        return _slack_callback_redirect(
            "error", "Slack OAuth callback is missing required parameters."
        )

    try:
        company_id = _decode_slack_oauth_state(state)
    except ValueError as exc:
        return _slack_callback_redirect(
            "error", f"Slack OAuth state validation failed: {exc}"
        )

    async with get_connection() as conn:
        existing = await conn.fetchrow(
            """
            SELECT config, secrets
            FROM integration_connections
            WHERE company_id = $1 AND provider = $2
            """,
            company_id,
            PROVIDER_SLACK,
        )

    if not existing:
        return _slack_callback_redirect(
            "error",
            "Slack provisioning settings are missing. Save client ID and client secret, then retry OAuth.",
        )

    existing_config = _json_object(existing["config"])
    existing_secrets = _json_object(existing["secrets"])
    client_id = str(existing_config.get("client_id") or "").strip()
    if not client_id:
        return _slack_callback_redirect(
            "error",
            "Slack client ID is missing. Save it in provisioning settings and retry OAuth.",
        )

    encrypted_client_secret = existing_secrets.get("client_secret")
    if not encrypted_client_secret:
        return _slack_callback_redirect(
            "error",
            "Slack client secret is missing. Save it in provisioning settings and retry OAuth.",
        )
    try:
        client_secret = decrypt_secret(encrypted_client_secret)
    except ValueError:
        return _slack_callback_redirect(
            "error",
            "Stored Slack client secret is unreadable. Re-save it in provisioning settings and retry OAuth.",
        )
    if not str(client_secret).strip():
        return _slack_callback_redirect(
            "error",
            "Slack client secret is empty. Save it in provisioning settings and retry OAuth.",
        )

    try:
        oauth_redirect_uri = _slack_oauth_redirect_uri()
        token_request_payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": oauth_redirect_uri,
        }

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                "https://slack.com/api/oauth.v2.access",
                data=token_request_payload,
            )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # pragma: no cover - network/Slack API variability
        return _slack_callback_redirect("error", f"Slack token exchange failed: {exc}")

    if not payload.get("ok"):
        return _slack_callback_redirect(
            "error",
            f"Slack OAuth failed: {payload.get('error') or 'unknown_error'}",
        )

    bot_access_token = payload.get("access_token")
    if not bot_access_token:
        return _slack_callback_redirect(
            "error", "Slack OAuth did not return a bot access token."
        )

    team = payload.get("team") or {}
    authed_user = payload.get("authed_user") or {}
    scope_value = payload.get("scope")

    async with get_connection() as conn:
        config = dict(existing_config)
        config.setdefault("oauth_scopes", list(DEFAULT_SLACK_SCOPES))
        if scope_value:
            config["oauth_scopes"] = _normalize_slack_scopes(scope_value)
        config.setdefault("auto_invite_on_employee_create", True)
        config.setdefault("sync_display_name", True)
        config["slack_team_id"] = team.get("id")
        config["slack_team_name"] = team.get("name")
        # Slack doesn't always include domain in OAuth response, so preserve existing.
        if team.get("domain"):
            config["slack_team_domain"] = team.get("domain")
        config["bot_user_id"] = payload.get("bot_user_id") or config.get("bot_user_id")
        config["workspace_url"] = config.get("workspace_url") or (
            f"https://{team.get('domain')}.slack.com"
            if team.get("domain")
            else config.get("workspace_url")
        )
        config["admin_email"] = config.get("admin_email") or authed_user.get("email")
        config["authed_user_id"] = authed_user.get("id")

        secrets_for_storage = dict(existing_secrets)
        secrets_for_storage["bot_access_token"] = encrypt_secret(bot_access_token)
        if payload.get("refresh_token"):
            secrets_for_storage["refresh_token"] = encrypt_secret(
                str(payload.get("refresh_token"))
            )

        await conn.execute(
            """
            INSERT INTO integration_connections (
                company_id, provider, status, config, secrets, last_tested_at, last_error, created_by, updated_by
            )
            VALUES ($1, $2, 'connected', $3::jsonb, $4::jsonb, NOW(), NULL, NULL, NULL)
            ON CONFLICT (company_id, provider)
            DO UPDATE SET
                status = 'connected',
                config = EXCLUDED.config,
                secrets = EXCLUDED.secrets,
                last_tested_at = NOW(),
                last_error = NULL,
                updated_by = NULL,
                updated_at = NOW()
            """,
            company_id,
            PROVIDER_SLACK,
            json.dumps(config),
            json.dumps(secrets_for_storage),
        )

    return _slack_callback_redirect(
        "success",
        f"Slack connected for {team.get('name') or 'workspace'}.",
    )


@router.post(
    "/employees/{employee_id}/google-workspace",
    response_model=ProvisioningRunStatusResponse,
)
async def provision_employee_google_workspace(
    employee_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)

    try:
        run_payload = await start_google_workspace_onboarding(
            company_id=company_id,
            employee_id=employee_id,
            triggered_by=current_user.id,
            trigger_source="manual",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    return ProvisioningRunStatusResponse.model_validate(run_payload)


@router.post("/runs/{run_id}/retry", response_model=ProvisioningRunStatusResponse)
async def retry_google_workspace_provisioning_run(
    run_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)
    try:
        run_payload = await retry_google_workspace_onboarding(
            company_id=company_id,
            run_id=run_id,
            triggered_by=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return ProvisioningRunStatusResponse.model_validate(run_payload)


@router.get(
    "/employees/{employee_id}/google-workspace",
    response_model=EmployeeProvisioningStatusResponse,
)
async def get_employee_google_workspace_provisioning_status(
    employee_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        employee_exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM employees WHERE id = $1 AND org_id = $2)",
            employee_id,
            company_id,
        )
        if not employee_exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found"
            )

        connection_row = await conn.fetchrow(
            """
            SELECT *
            FROM integration_connections
            WHERE company_id = $1 AND provider = $2
            """,
            company_id,
            PROVIDER_GOOGLE_WORKSPACE,
        )
        connection = _connection_status_payload(connection_row)

        identity_row = await conn.fetchrow(
            """
            SELECT *
            FROM external_identities
            WHERE company_id = $1
              AND employee_id = $2
              AND provider = $3
            """,
            company_id,
            employee_id,
            PROVIDER_GOOGLE_WORKSPACE,
        )
        external_identity = None
        if identity_row:
            external_identity = ExternalIdentityResponse(
                provider=identity_row["provider"],
                external_user_id=identity_row["external_user_id"],
                external_email=identity_row["external_email"],
                status=identity_row["status"],
                raw_profile=_json_object(identity_row["raw_profile"]),
                created_at=identity_row["created_at"],
                updated_at=identity_row["updated_at"],
            )

        run_rows = await conn.fetch(
            """
            SELECT *
            FROM onboarding_runs
            WHERE company_id = $1
              AND employee_id = $2
              AND provider = $3
            ORDER BY created_at DESC
            LIMIT 25
            """,
            company_id,
            employee_id,
            PROVIDER_GOOGLE_WORKSPACE,
        )

        run_ids = [row["id"] for row in run_rows]
        step_rows = []
        if run_ids:
            step_rows = await conn.fetch(
                """
                SELECT *
                FROM onboarding_steps
                WHERE run_id = ANY($1::uuid[])
                ORDER BY created_at ASC
                """,
                run_ids,
            )

        steps_by_run: dict[UUID, list] = {}
        for step in step_rows:
            steps_by_run.setdefault(step["run_id"], []).append(step)

        runs = [_run_payload(run, steps_by_run.get(run["id"], [])) for run in run_rows]

    return EmployeeProvisioningStatusResponse(
        connection=connection,
        external_identity=external_identity,
        runs=runs,
    )


@router.post(
    "/employees/{employee_id}/slack", response_model=ProvisioningRunStatusResponse
)
async def provision_employee_slack(
    employee_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)

    try:
        run_payload = await start_slack_onboarding(
            company_id=company_id,
            employee_id=employee_id,
            triggered_by=current_user.id,
            trigger_source="manual",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    return ProvisioningRunStatusResponse.model_validate(run_payload)


@router.get(
    "/employees/{employee_id}/slack",
    response_model=SlackEmployeeProvisioningStatusResponse,
)
async def get_employee_slack_provisioning_status(
    employee_id: UUID,
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        employee_exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM employees WHERE id = $1 AND org_id = $2)",
            employee_id,
            company_id,
        )
        if not employee_exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found"
            )

        connection_row = await conn.fetchrow(
            """
            SELECT *
            FROM integration_connections
            WHERE company_id = $1 AND provider = $2
            """,
            company_id,
            PROVIDER_SLACK,
        )
        connection = _slack_connection_status_payload(connection_row)

        identity_row = await conn.fetchrow(
            """
            SELECT *
            FROM external_identities
            WHERE company_id = $1
              AND employee_id = $2
              AND provider = $3
            """,
            company_id,
            employee_id,
            PROVIDER_SLACK,
        )
        external_identity = None
        if identity_row:
            external_identity = ExternalIdentityResponse(
                provider=identity_row["provider"],
                external_user_id=identity_row["external_user_id"],
                external_email=identity_row["external_email"],
                status=identity_row["status"],
                raw_profile=_json_object(identity_row["raw_profile"]),
                created_at=identity_row["created_at"],
                updated_at=identity_row["updated_at"],
            )

        run_rows = await conn.fetch(
            """
            SELECT *
            FROM onboarding_runs
            WHERE company_id = $1
              AND employee_id = $2
              AND provider = $3
            ORDER BY created_at DESC
            LIMIT 25
            """,
            company_id,
            employee_id,
            PROVIDER_SLACK,
        )

        run_ids = [row["id"] for row in run_rows]
        step_rows = []
        if run_ids:
            step_rows = await conn.fetch(
                """
                SELECT *
                FROM onboarding_steps
                WHERE run_id = ANY($1::uuid[])
                ORDER BY created_at ASC
                """,
                run_ids,
            )

        steps_by_run: dict[UUID, list] = {}
        for step in step_rows:
            steps_by_run.setdefault(step["run_id"], []).append(step)

        runs = [_run_payload(run, steps_by_run.get(run["id"], [])) for run in run_rows]

    return SlackEmployeeProvisioningStatusResponse(
        connection=connection,
        external_identity=external_identity,
        runs=runs,
    )


@router.get("/runs", response_model=list[ProvisioningRunListItem])
async def list_provisioning_runs(
    provider: Optional[str] = None,
    run_status: Optional[str] = Query(default=None, alias="status"),
    limit: int = Query(default=50, le=200),
    current_user: CurrentUser = Depends(require_admin_or_client),
):
    """Return recent provisioning runs for the company, optionally filtered by provider or status."""
    company_id = await get_client_company_id(current_user)

    async with get_connection() as conn:
        filters = ["r.company_id = $1"]
        params: list = [company_id]
        idx = 2

        if provider:
            filters.append(f"r.provider = ${idx}")
            params.append(provider)
            idx += 1

        if run_status:
            filters.append(f"r.status = ${idx}")
            params.append(run_status)
            idx += 1

        params.append(limit)
        where_clause = " AND ".join(filters)

        rows = await conn.fetch(
            f"""
            SELECT
                r.id,
                r.company_id,
                r.employee_id,
                r.provider,
                r.status,
                r.trigger_source,
                r.triggered_by,
                r.last_error,
                r.started_at,
                r.completed_at,
                r.created_at,
                r.updated_at,
                e.first_name || ' ' || e.last_name AS employee_name,
                e.email AS employee_email
            FROM onboarding_runs r
            LEFT JOIN employees e ON e.id = r.employee_id
            WHERE {where_clause}
            ORDER BY r.created_at DESC
            LIMIT ${idx}
            """,
            *params,
        )

        return [
            ProvisioningRunListItem(
                run_id=row["id"],
                company_id=row["company_id"],
                employee_id=row["employee_id"],
                employee_name=row["employee_name"],
                employee_email=row["employee_email"],
                provider=row["provider"],
                status=row["status"],
                trigger_source=row["trigger_source"],
                triggered_by=row["triggered_by"],
                last_error=row["last_error"],
                started_at=row["started_at"],
                completed_at=row["completed_at"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]
