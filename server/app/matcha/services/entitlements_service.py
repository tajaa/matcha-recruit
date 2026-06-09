"""Werk plan entitlements — the single source of truth for Free/Lite/Pro/Business.

Resolves a user's plan from role + company + mw_subscriptions + beta flags and
maps it to a feature/quota set. Consumed by:
  - GET /matcha-work/entitlements (the Werk client's plan read)
  - model selection (matcha_work_ai._get_model)
  - per-user rolling token quota defaults (matcha_work_document.check_token_quota)
  - feature gates (project create, broadcasts, paid channels, email AI, journals)

Plans:
  free      — non-AI collaboration (channels/DMs/people) + basic journals + AI taste
  lite      — $9/mo `matcha_work_lite`: solo projects, full journals, email AI, flash
  pro       — $20/mo `matcha_work_personal` (grandfathered): pro model, collab
              projects + kanban, Go Live, paid-channel creation, big quota
  business  — role=client on a non-personal company with the `matcha_work`
              feature: pro-level + business modes; billed via company contract
              and token packs, never via personal SKUs.

Admin beta flags map onto plans (matcha_work_beta_full → pro-equivalent,
matcha_work_beta_lite → lite-equivalent) so existing beta users keep exactly
their current capability with no data migration.
"""

from __future__ import annotations

import json
import time
from typing import Any, Optional
from uuid import UUID

from fastapi import HTTPException

from ...database import get_connection

PLAN_FREE = "free"
PLAN_LITE = "lite"
PLAN_PRO = "pro"
PLAN_BUSINESS = "business"

# Personal SKUs. PRO_PACK_ID is the pre-existing $20 "Plus" pack — kept verbatim
# so current subscribers grandfather into Pro automatically.
LITE_PACK_ID = "matcha_work_lite"
PRO_PACK_ID = "matcha_work_personal"
# Business metered token pack ($40/5M) — orthogonal to the personal ladder.
TOKEN_PACK_ID = "matcha_work_pro"

LITE_AMOUNT_CENTS = 900
PRO_AMOUNT_CENTS = 2000

# Per-user rolling-window quota defaults by plan: (token_limit, window_hours).
# Explicit mw_token_quotas rows always override these (admin grants).
PLAN_QUOTAS: dict[str, tuple[int, int]] = {
    PLAN_FREE: (25_000, 12),
    PLAN_LITE: (100_000, 12),
    PLAN_PRO: (500_000, 12),
    PLAN_BUSINESS: (500_000, 12),
}

# Plan ordering for ">= lite" style checks.
_PLAN_RANK = {PLAN_FREE: 0, PLAN_LITE: 1, PLAN_PRO: 2, PLAN_BUSINESS: 2}

# Journal kinds gated to lite+ (basic note/todo/journal stay free).
PREMIUM_JOURNAL_KINDS = {"novel", "screenplay", "blog"}
# Project types gated to pro+ (lite gets the solo types).
SOLO_PROJECT_TYPES = {"general", "presentation", "blog"}
COLLAB_PROJECT_TYPES = {"collab", "recruiting"}

# Small in-process plan cache — the resolver sits on hot paths (every AI send /
# model selection). 60s staleness after a checkout is acceptable: the client
# refetches entitlements on scene-active anyway.
_PLAN_CACHE_TTL_SECONDS = 60.0
_plan_cache: dict[str, tuple[float, str]] = {}


def invalidate_plan_cache(user_id: UUID | str | None = None) -> None:
    """Drop cached plan(s) — call after subscription changes."""
    if user_id is None:
        _plan_cache.clear()
    else:
        _plan_cache.pop(str(user_id), None)


def _parse_jsonb(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (ValueError, TypeError):
            return {}
    return {}


def plan_at_least(plan: str, minimum: str) -> bool:
    return _PLAN_RANK.get(plan, 0) >= _PLAN_RANK.get(minimum, 0)


async def resolve_plan_for_user(user_id: UUID | str) -> str:
    """Resolve the user's plan. Cached for 60s per user."""
    key = str(user_id)
    cached = _plan_cache.get(key)
    now = time.monotonic()
    if cached and now - cached[0] < _PLAN_CACHE_TTL_SECONDS:
        return cached[1]

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT u.role,
                   COALESCE(u.beta_features, '{}'::jsonb) AS beta_features,
                   c.id AS company_id,
                   COALESCE(c.is_personal, false) AS is_personal,
                   COALESCE(c.enabled_features, '{}'::jsonb) AS enabled_features,
                   sub.pack_id AS sub_pack_id
            FROM users u
            LEFT JOIN clients cl ON cl.user_id = u.id
            LEFT JOIN companies c ON c.id = cl.company_id
            LEFT JOIN LATERAL (
                SELECT s.pack_id
                FROM mw_subscriptions s
                WHERE s.company_id = c.id
                  AND (
                    s.status IN ('active', 'past_due')
                    -- Canceled subs stay entitled until the paid period ends
                    -- (DELETE /billing/subscription flips status immediately).
                    OR (s.status = 'canceled'
                        AND s.current_period_end IS NOT NULL
                        AND s.current_period_end > NOW())
                  )
                  AND s.pack_id IN ($2, $3)
                ORDER BY s.created_at DESC
                LIMIT 1
            ) sub ON TRUE
            WHERE u.id = $1
            LIMIT 1
            """,
            UUID(key),
            PRO_PACK_ID,
            LITE_PACK_ID,
        )

    plan = _plan_from_row(row)
    _plan_cache[key] = (now, plan)
    return plan


def _plan_from_row(row: Any) -> str:
    if row is None:
        return PLAN_FREE

    role = row["role"]
    if role == "admin":
        return PLAN_PRO

    beta = _parse_jsonb(row["beta_features"])
    enabled = _parse_jsonb(row["enabled_features"])
    is_personal = bool(row["is_personal"])
    pack_id = row["sub_pack_id"]

    # Business: client on a real (non-personal) company that has Werk.
    if role == "client" and not is_personal and enabled.get("matcha_work") is True:
        return PLAN_BUSINESS

    if beta.get("matcha_work_beta_full") is True:
        return PLAN_PRO
    if pack_id == PRO_PACK_ID:
        return PLAN_PRO
    if pack_id == LITE_PACK_ID:
        return PLAN_LITE
    if beta.get("matcha_work_beta_lite") is True:
        return PLAN_LITE
    return PLAN_FREE


def features_for_plan(plan: str) -> dict[str, bool]:
    lite_plus = plan_at_least(plan, PLAN_LITE)
    pro_plus = plan_at_least(plan, PLAN_PRO)
    return {
        "threads_ai": True,  # all plans — free is bounded by the taste quota
        "ai_model_pro": pro_plus,
        "projects_solo": lite_plus,
        "projects_collab": pro_plus,
        "journals_basic": True,
        "journals_full": lite_plus,
        "email_ai": lite_plus,
        "go_live": pro_plus,
        # Paid channels stay an individual-account product rule (see
        # channels.create_channel); business excluded there regardless.
        "paid_channels": plan == PLAN_PRO,
        "business_modes": plan == PLAN_BUSINESS,
    }


async def resolve_entitlements(user_id: UUID | str, company_id: Optional[UUID] = None) -> dict:
    """Full entitlement payload for GET /matcha-work/entitlements."""
    plan = await resolve_plan_for_user(user_id)
    token_limit, window_hours = PLAN_QUOTAS[plan]

    quotas: dict[str, Any] = {"token_limit": token_limit, "window_hours": window_hours}
    try:
        from . import matcha_work_document as doc_svc

        q = await doc_svc.check_token_quota(
            user_id if isinstance(user_id, UUID) else UUID(str(user_id)),
            company_id,
        )
        quotas = {
            "token_limit": q["limit"],
            "window_hours": q["window_hours"],
            "used": q["used"],
            "remaining": q["remaining"],
            "resets_at": q["resets_at"],
        }
    except Exception:
        # Quota detail is informational here — never fail the entitlement read.
        pass

    return {
        "plan": plan,
        "features": features_for_plan(plan),
        "quotas": quotas,
    }


async def require_plan(user_id: UUID | str, minimum: str, feature: str) -> str:
    """Gate helper: raise a structured 403 unless the user's plan >= minimum.

    The detail payload is machine-readable so the Werk client can raise its
    paywall instead of showing a bare error (mirrors the web FeatureGate
    convention of upsell-not-403).
    """
    plan = await resolve_plan_for_user(user_id)
    if not plan_at_least(plan, minimum):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "plan_required",
                "required_plan": minimum,
                "current_plan": plan,
                "feature": feature,
            },
        )
    return plan
