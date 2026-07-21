"""Provisioning runs provisioning routes (J7 split)."""
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
