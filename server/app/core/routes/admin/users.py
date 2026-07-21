"""Admin users routes (J5 split)."""
import asyncio
import difflib
import json
import logging
import re
import secrets
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, AsyncGenerator
from uuid import UUID

import asyncpg
from fastapi import APIRouter, BackgroundTasks, Body, HTTPException, Depends, Query, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, EmailStr, Field

logger = logging.getLogger(__name__)

from app.database import get_connection
from app.core.dependencies import require_admin
from app.core.services.credential_crypto import decrypt_credential_fields
from app.core.services.scope_registry.codify import codified_sql
from app.core.feature_flags import merge_company_features
from app.core.services.email import get_email_service
from app.core.models.compliance import AutoCheckSettings, LocationCreate
from app.core.models.compliance_evals import EvalRunRequest, FindingResolveRequest
from app.core.compliance_registry import (
    TRIGGER_PROFILES,
    LABOR_CATEGORIES, HEALTHCARE_CATEGORIES, ONCOLOGY_CATEGORIES,
    MEDICAL_COMPLIANCE_CATEGORIES, SUPPLEMENTARY_CATEGORIES,
)
from app.core.services.compliance_service import (
    _resolve_industry,
    update_auto_check_settings,
    _jurisdiction_row_to_dict,
    run_compliance_check_background,
    run_compliance_check_stream,
    research_jurisdiction_repo_only,
    get_locations,
    get_location_requirements,
    create_location,
    admin_add_requirement_to_location,
)
from app.core.services.redis_cache import (
    get_redis_cache, cache_get, cache_set, cache_delete, cache_delete_pattern,
    admin_jurisdictions_list_key, admin_jurisdiction_detail_key,
    admin_jurisdiction_data_overview_key, admin_jurisdiction_policy_overview_key,
    admin_bookmarked_requirements_key,
)
from app.core.services.rate_limiter import get_rate_limiter
from app.core.services.auth import hash_password
from app.core.services.platform_settings import (
    get_visible_features, prime_visible_features_cache,
    get_matcha_work_model_mode, prime_matcha_work_model_mode_cache,
    get_jurisdiction_research_model_mode, prime_jurisdiction_research_model_mode_cache,
    get_er_similarity_weights, prime_er_similarity_weights_cache,
    get_tenant_codified_only, prime_tenant_codified_only_cache,
    DEFAULT_ER_SIMILARITY_WEIGHTS, EXPECTED_WEIGHT_KEYS,
)
from app.matcha.services import billing_service as mw_billing_service
from app.config import get_settings
from app.core.services.stripe_service import StripeService, StripeServiceError
from app.core.feature_flags import DEFAULT_COMPANY_FEATURES
from app.core.services.deal_pricing import DealInputs
from app.core.services.deal_full import FullDealInputs
from app.core.services.deal_broker import BrokerInputs
from app.core.services.deal_book import BookInputs


from app.core.services.scope_registry.jurisdiction_chain import (  # noqa: E402
    resolve_jurisdiction_chain as _resolve_jurisdiction_chain,
)

from app.core.models.admin import *  # noqa: F401,F403
from app.core.routes.admin._shared import *  # noqa: F401,F403

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api-usage", dependencies=[Depends(require_admin)])
async def get_api_usage():
    """Return current Gemini API usage stats for rate limiting monitoring."""
    limiter = get_rate_limiter()
    return await limiter.get_usage()


@router.get("/token-quotas", dependencies=[Depends(require_admin)])
async def list_token_quotas():
    """List all token quotas with user/company info."""
    async with get_connection() as conn:
        rows = await conn.fetch("""
            SELECT q.id, q.user_id, q.company_id, q.token_limit, q.window_hours, q.is_active, q.created_at,
                   u.email as user_email,
                   c.name as company_name
            FROM mw_token_quotas q
            LEFT JOIN users u ON q.user_id = u.id
            LEFT JOIN companies c ON q.company_id = c.id
            ORDER BY q.user_id NULLS LAST, q.created_at DESC
        """)
        return [dict(r) for r in rows]


@router.get("/token-usage", dependencies=[Depends(require_admin)])
async def list_token_usage():
    """Per-user token usage in the current window."""
    async with get_connection() as conn:
        rows = await conn.fetch("""
            SELECT u.id as user_id, u.email, c.name as company_name,
                   COALESCE(SUM(e.total_tokens), 0)::bigint as tokens_used,
                   COUNT(e.id)::int as call_count,
                   COALESCE(SUM(e.cost_dollars), 0)::numeric as cost_dollars,
                   MAX(e.created_at) as last_active
            FROM users u
            LEFT JOIN clients cl ON cl.user_id = u.id
            LEFT JOIN companies c ON c.id = cl.company_id
            LEFT JOIN mw_token_usage_events e ON e.user_id = u.id AND e.created_at > NOW() - interval '12 hours'
            WHERE u.is_active = true
            GROUP BY u.id, u.email, c.name
            HAVING COALESCE(SUM(e.total_tokens), 0) > 0
            ORDER BY tokens_used DESC
        """)
        return [dict(r) for r in rows]


@router.post("/token-quotas", dependencies=[Depends(require_admin)])
async def create_token_quota(body: dict):
    """Create a new token quota."""
    user_id = body.get("user_id")
    company_id = body.get("company_id")
    token_limit = body.get("token_limit", 100000)
    window_hours = body.get("window_hours", 12)

    async with get_connection() as conn:
        row = await conn.fetchrow("""
            INSERT INTO mw_token_quotas (user_id, company_id, token_limit, window_hours)
            VALUES ($1, $2, $3, $4)
            RETURNING *
        """, user_id, company_id, token_limit, window_hours)
        return dict(row)


@router.put("/token-quotas/{quota_id}", dependencies=[Depends(require_admin)])
async def update_token_quota(quota_id: str, body: dict):
    """Update an existing token quota."""
    from uuid import UUID
    async with get_connection() as conn:
        sets = []
        vals = []
        idx = 1
        for key in ("token_limit", "window_hours", "is_active"):
            if key in body:
                sets.append(f"{key} = ${idx}")
                vals.append(body[key])
                idx += 1
        if not sets:
            return {"detail": "No changes"}
        vals.append(UUID(quota_id))
        row = await conn.fetchrow(
            f"UPDATE mw_token_quotas SET {', '.join(sets)}, updated_at = NOW() WHERE id = ${idx} RETURNING *",
            *vals,
        )
        if not row:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Quota not found")
        return dict(row)


@router.delete("/token-quotas/{quota_id}", dependencies=[Depends(require_admin)])
async def delete_token_quota(quota_id: str):
    """Delete a token quota."""
    from uuid import UUID
    async with get_connection() as conn:
        await conn.execute("DELETE FROM mw_token_quotas WHERE id = $1", UUID(quota_id))
        return {"deleted": True}


@router.patch("/users/{user_id}/beta-flags")
async def patch_user_beta_flags(
    user_id: UUID,
    body: Dict[str, Any] = Body(...),
    current_user=Depends(require_admin),
):
    """Set matcha_work_beta_lite / matcha_work_beta_full flags on a user.

    These double as no-Stripe COMP GRANTS: the Werk plan resolver
    (entitlements_service) maps beta_full → Pro and beta_lite → Lite, so
    checking a box here grants the full paid tier without a subscription.
    """
    allowed = {"matcha_work_beta_lite", "matcha_work_beta_full"}
    patch = {k: v for k, v in body.items() if k in allowed and isinstance(v, bool)}
    if not patch:
        raise HTTPException(status_code=400, detail="No valid beta flag keys provided")
    # Audit: comp grants are money-equivalent — record actor + target + change.
    logger.warning(
        "COMP-GRANT beta-flags admin=%s target_user=%s patch=%s",
        getattr(current_user, "id", "?"), user_id, patch,
    )
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            UPDATE users
            SET beta_features = COALESCE(beta_features, '{}'::jsonb) || $1::jsonb
            WHERE id = $2
            RETURNING beta_features
            """,
            json.dumps(patch),
            user_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    # Comp grants change the resolved Werk plan — drop the 60s plan cache so
    # the grant (or revocation) takes effect on the user's next request.
    from app.matcha.services import entitlements_service
    entitlements_service.invalidate_plan_cache(user_id)

    return {"beta_features": dict(row["beta_features"])}


@router.post("/users/{user_id}/suspend", dependencies=[Depends(require_admin)])
async def admin_suspend_user(user_id: UUID, body: SuspendBody = Body(default=SuspendBody())):
    """Mark a user is_suspended. Login + bearer auth refuse them."""
    async with get_connection() as conn:
        result = await conn.execute(
            "UPDATE users SET is_suspended = TRUE WHERE id = $1",
            user_id,
        )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="User not found")
    logger.info("Admin suspended user %s reason=%s", user_id, body.reason or "—")
    return {"ok": True}


@router.post("/users/{user_id}/unsuspend", dependencies=[Depends(require_admin)])
async def admin_unsuspend_user(user_id: UUID):
    async with get_connection() as conn:
        result = await conn.execute(
            "UPDATE users SET is_suspended = FALSE WHERE id = $1",
            user_id,
        )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True}


@router.post("/users/{user_id}/password-reset", response_model=PasswordResetResponse, dependencies=[Depends(require_admin)])
async def admin_issue_password_reset(user_id: UUID):
    """Issue a 1-hour password-reset link for a user.

    The link is RETURNED to the admin (not emailed) so they can hand it off
    out-of-band when the customer's inbox is broken or they're on a call.
    Uses the same `password_reset_tokens` table as the user-facing forgot
    flow, so either path works to consume it.
    """
    settings = get_settings()
    async with get_connection() as conn:
        user = await conn.fetchrow("SELECT id FROM users WHERE id = $1", user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        token = secrets.token_urlsafe(48)
        await conn.execute(
            """INSERT INTO password_reset_tokens (user_id, token, expires_at)
               VALUES ($1, $2, NOW() + INTERVAL '1 hour')""",
            user_id, token,
        )
    base_url = settings.app_base_url.rstrip("/")
    return PasswordResetResponse(
        reset_url=f"{base_url}/reset-password?token={token}",
        expires_in_minutes=60,
    )


@router.delete("/users/{user_id}", dependencies=[Depends(require_admin)])
async def admin_soft_delete_user(user_id: UUID):
    """Soft-delete a user via is_active=false (used for individuals with no company)."""
    async with get_connection() as conn:
        result = await conn.execute(
            "UPDATE users SET is_active = FALSE WHERE id = $1",
            user_id,
        )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True}
