"""Shared provisioning helpers (J7 split)."""
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

logger = logging.getLogger(__name__)


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
