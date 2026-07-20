"""Broker tokens routes (J7 split)."""
from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field

from app.config import get_settings
from app.core.feature_flags import default_company_features_json, merge_company_features
from app.core.models.auth import CurrentUser
from app.core.services.email import get_email_service
from app.database import get_connection
from app.matcha.dependencies import require_broker

from app.matcha.routes.broker.brokers._models import *  # noqa: F401,F403
from app.matcha.routes.broker.brokers._shared import *  # noqa: F401,F403

router = APIRouter()


@router.post("/lite-referral-tokens", response_model=LiteReferralTokenResponse)
async def create_lite_referral_token(
    request: LiteReferralTokenCreateRequest,
    current_user: CurrentUser = Depends(require_broker),
):
    async with get_connection() as conn:
        membership = await _get_broker_membership(conn, user_id=current_user.id)
        _assert_can_manage_clients(membership)
        broker_id = membership["broker_id"]

        token = secrets.token_urlsafe(32)
        expires_at = None
        if request.expires_days:
            expires_at = datetime.utcnow() + timedelta(days=request.expires_days)

        row = await conn.fetchrow(
            """
            INSERT INTO broker_lite_referral_tokens
                (broker_id, token, label, created_by, expires_at, payer)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING *
            """,
            broker_id,
            token,
            request.label,
            current_user.id,
            expires_at,
            request.payer,
        )
        base_url = get_settings().app_base_url
        return _fmt_token_row(dict(row), base_url)
@router.get("/lite-referral-tokens")
async def list_lite_referral_tokens(current_user: CurrentUser = Depends(require_broker)):
    async with get_connection() as conn:
        membership = await _get_broker_membership(conn, user_id=current_user.id)
        _assert_can_manage_clients(membership)
        broker_id = membership["broker_id"]

        rows = await conn.fetch(
            """
            SELECT * FROM broker_lite_referral_tokens
            WHERE broker_id = $1 AND is_active = true
              AND intended_company_name IS NULL
            ORDER BY created_at DESC
            """,
            broker_id,
        )
        base_url = get_settings().app_base_url
        tokens = [_fmt_token_row(dict(r), base_url) for r in rows]
        return {"tokens": tokens, "total": len(tokens)}
@router.delete("/lite-referral-tokens/{token_id}")
async def deactivate_lite_referral_token(
    token_id: str,
    current_user: CurrentUser = Depends(require_broker),
):
    async with get_connection() as conn:
        membership = await _get_broker_membership(conn, user_id=current_user.id)
        _assert_can_manage_clients(membership)
        broker_id = membership["broker_id"]

        row = await conn.fetchrow(
            """
            UPDATE broker_lite_referral_tokens
            SET is_active = false
            WHERE id = $1 AND broker_id = $2
            RETURNING id
            """,
            UUID(token_id),
            broker_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Token not found")
        return {"status": "deactivated"}
