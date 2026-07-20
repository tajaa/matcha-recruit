"""Google Workspace provisioning routes (J7 split)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from datetime import datetime
from typing import Optional
from urllib.parse import urlencode
from uuid import UUID

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field

from app.config import get_settings
from app.core.models.auth import CurrentUser
from app.core.dependencies import require_admin
from app.core.services.secret_crypto import decrypt_secret, encrypt_secret
from app.database import get_connection
from app.matcha.dependencies import (
    get_client_company_id,
    require_admin_or_client,
    require_any_feature,
    require_feature,
    require_feature,
)
from app.matcha.services.google_workspace_service import GoogleWorkspaceService
from app.matcha.services.onboarding_orchestrator import (
    PROVIDER_GOOGLE_WORKSPACE,
    PROVIDER_SLACK,
    retry_google_workspace_onboarding,
    start_google_workspace_onboarding,
    start_slack_onboarding,
)
from app.matcha.services.hris_service import PROVIDER_HRIS, HRISProvisioningError

# Several handlers below already call logger.error(...) on their failure paths
# (Gusto company fetch; Finch Connect-session / sandbox / token exchange) but
# the module never defined one — so those lines raised NameError at request
# time, replacing a logged upstream error with a 500. Same class of bug as the
# IR NameErrors that test_review_fixes.py locks down.
from app.matcha.routes.integrations.provisioning._models import *  # noqa: F401,F403
from app.matcha.routes.integrations.provisioning._shared import (  # noqa: F401
    _json_object, _coerce_bool, _split_comma_list, _run_payload,
)

logger = logging.getLogger(__name__)
router = APIRouter()


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
