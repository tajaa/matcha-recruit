"""Provisioning routes for external onboarding systems."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field

from ...core.models.auth import CurrentUser
from ...core.services.secret_crypto import decrypt_secret, encrypt_secret
from ...database import get_connection
from ..dependencies import get_client_company_id, require_admin_or_client
from ..services.google_workspace_service import GoogleWorkspaceService
from ..services.onboarding_orchestrator import (
    PROVIDER_GOOGLE_WORKSPACE,
    retry_google_workspace_onboarding,
    start_google_workspace_onboarding,
)

router = APIRouter()


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


class GoogleWorkspaceConnectionRequest(BaseModel):
    mode: str = Field(default="mock", pattern="^(mock|api_token)$")
    domain: Optional[str] = Field(default=None, max_length=255)
    admin_email: Optional[EmailStr] = None
    default_org_unit: Optional[str] = Field(default=None, max_length=255)
    default_groups: list[str] = Field(default_factory=list)
    access_token: Optional[str] = None
    test_connection: bool = True


class GoogleWorkspaceConnectionStatus(BaseModel):
    provider: str = PROVIDER_GOOGLE_WORKSPACE
    connected: bool
    status: str
    mode: Optional[str] = None
    domain: Optional[str] = None
    admin_email: Optional[str] = None
    default_org_unit: Optional[str] = None
    default_groups: list[str] = Field(default_factory=list)
    has_access_token: bool = False
    last_tested_at: Optional[datetime] = None
    last_error: Optional[str] = None
    updated_at: Optional[datetime] = None


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
        default_org_unit=config.get("default_org_unit"),
        default_groups=[str(item) for item in (config.get("default_groups") or []) if str(item).strip()],
        has_access_token=bool(secrets.get("access_token")),
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


@router.post("/google-workspace/connect", response_model=GoogleWorkspaceConnectionStatus)
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
                existing_access_token_plain = decrypt_secret(existing_secrets.get("access_token"))
            except ValueError:
                existing_access_token_unreadable = True

        default_groups = [str(item).strip() for item in request.default_groups if str(item).strip()]
        config = {
            "mode": request.mode,
            "domain": request.domain,
            "admin_email": str(request.admin_email) if request.admin_email else None,
            "default_org_unit": request.default_org_unit,
            "default_groups": default_groups,
        }

        requested_access_token = request.access_token.strip() if request.access_token else None
        access_token_plain = requested_access_token or existing_access_token_plain

        secrets_for_storage = dict(existing_secrets)
        secrets_for_test: dict = {}
        if request.mode == "mock":
            secrets_for_storage.pop("access_token", None)
        else:
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

        # Normalize older plaintext stored tokens into encrypted format on save.
        if request.mode == "api_token" and existing_access_token_plain and not requested_access_token:
            secrets_for_storage["access_token"] = encrypt_secret(existing_access_token_plain)

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


@router.post("/employees/{employee_id}/google-workspace", response_model=ProvisioningRunStatusResponse)
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


@router.get("/employees/{employee_id}/google-workspace", response_model=EmployeeProvisioningStatusResponse)
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
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Employee not found")

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
