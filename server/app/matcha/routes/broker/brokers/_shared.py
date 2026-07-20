"""Broker-portal shared constants + helpers (J7 split)."""
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


__all__ = [
    "KNOWN_FEATURES",
    "EDITABLE_SETUP_STATUSES",
    "EXPIRABLE_SETUP_STATUSES",
    "_normalize_feature_toggles",
    "_to_dict",
    "_to_list",
    "_coerce_bool",
    "_serialize_setup",
    "_send_broker_client_invite_email",
    "_get_broker_membership",
    "_assert_can_manage_clients",
    "_assert_can_manage_team",
    "_client_invite_signup_url",
    "_fmt_client_invite",
    "_assert_terms_accepted",
    "_expire_stale_setups",
    "_fmt_token_row",
    "_committed_seats",
]


KNOWN_FEATURES = {
    "policies",
    "handbooks",
    "compliance",
    "employees",
    "er_copilot",
    "incidents",
    "time_off",
    "accommodations",
}
EDITABLE_SETUP_STATUSES = {"draft", "invited"}
EXPIRABLE_SETUP_STATUSES = {"draft", "invited"}
def _normalize_feature_toggles(features: Optional[dict[str, bool]]) -> dict[str, bool]:
    normalized: dict[str, bool] = {}
    if not features:
        return normalized

    for key, value in features.items():
        if key not in KNOWN_FEATURES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown feature '{key}' in preconfigured_features",
            )
        normalized[key] = bool(value)
    return normalized
def _to_dict(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
            return decoded if isinstance(decoded, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}
def _to_list(value) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
            return decoded if isinstance(decoded, list) else []
        except json.JSONDecodeError:
            return []
    return []
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
def _serialize_setup(row, *, invite_base_url: str) -> dict:
    invite_token = row.get("invite_token")
    google_workspace_status = row.get("google_workspace_status")
    google_workspace = None
    if google_workspace_status:
        google_workspace_config = _to_dict(row.get("google_workspace_config"))
        google_workspace = {
            "connected": google_workspace_status == "connected",
            "status": google_workspace_status,
            "auto_provision_on_employee_create": _coerce_bool(
                google_workspace_config.get("auto_provision_on_employee_create"),
                True,
            ),
        }
    return {
        "id": str(row["id"]),
        "broker_id": str(row["broker_id"]),
        "company_id": str(row["company_id"]),
        "company_name": row.get("company_name"),
        "company_status": row.get("company_status") or "approved",
        "industry": row.get("industry"),
        "company_size": row.get("company_size"),
        "status": row["status"],
        "link_status": row.get("link_status"),
        "contact_name": row.get("contact_name"),
        "contact_email": row.get("contact_email"),
        "contact_phone": row.get("contact_phone"),
        "headcount_hint": row.get("headcount_hint"),
        "notes": row.get("notes"),
        "locations": _to_list(row.get("locations")),
        "onboarding_stage": row.get("onboarding_stage") or "submitted",
        "preconfigured_features": _to_dict(row.get("preconfigured_features")),
        "onboarding_template": _to_dict(row.get("onboarding_template")),
        "link_permissions": _to_dict(row.get("link_permissions")),
        "invite_token": invite_token,
        "invite_url": f"{invite_base_url}/register/broker-client/{invite_token}" if invite_token else None,
        "invite_expires_at": row.get("invite_expires_at").isoformat() if row.get("invite_expires_at") else None,
        "invited_at": row.get("invited_at").isoformat() if row.get("invited_at") else None,
        "activated_at": row.get("activated_at").isoformat() if row.get("activated_at") else None,
        "expired_at": row.get("expired_at").isoformat() if row.get("expired_at") else None,
        "cancelled_at": row.get("cancelled_at").isoformat() if row.get("cancelled_at") else None,
        "created_at": row.get("created_at").isoformat() if row.get("created_at") else None,
        "updated_at": row.get("updated_at").isoformat() if row.get("updated_at") else None,
        "google_workspace": google_workspace,
    }
async def _send_broker_client_invite_email(*, row: dict, invite_url: str) -> tuple[bool, Optional[str]]:
    contact_email = row.get("contact_email")
    if not contact_email:
        return False, "missing_contact_email"

    email_service = get_email_service()
    if not email_service.is_configured():
        return False, "email_service_not_configured"

    sent = await email_service.send_broker_client_setup_invitation_email(
        to_email=contact_email,
        to_name=row.get("contact_name") or row.get("company_name") or contact_email,
        broker_name=row.get("broker_name") or "Your Broker",
        company_name=row.get("company_name") or "Your Company",
        invite_url=invite_url,
        expires_at=row.get("invite_expires_at"),
    )
    if sent:
        return True, None
    return False, "delivery_failed"
async def _get_broker_membership(conn, *, user_id: UUID):
    membership = await conn.fetchrow(
        """
        SELECT
            bm.broker_id,
            bm.role as member_role,
            bm.permissions,
            bm.is_active,
            b.status as broker_status
        FROM broker_members bm
        JOIN brokers b ON b.id = bm.broker_id
        WHERE bm.user_id = $1
        ORDER BY bm.created_at ASC
        LIMIT 1
        """,
        user_id,
    )
    if not membership or not membership["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No active broker membership found for this account",
        )
    if membership["broker_status"] != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Broker account is not active")
    return membership
def _assert_can_manage_clients(membership) -> None:
    if membership["member_role"] in {"owner", "admin"}:
        return
    permissions = _to_dict(membership["permissions"])
    if permissions.get("can_manage_clients") is not True:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Broker user lacks client onboarding permissions",
        )
def _assert_can_manage_team(membership) -> None:
    if membership["member_role"] in {"owner", "admin"}:
        return
    permissions = _to_dict(membership["permissions"])
    if permissions.get("can_manage_team") is not True:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Broker user lacks team management permissions",
        )
def _client_invite_signup_url(token: str, tier: Optional[str], base_url: str) -> str:
    """Company-pinned seat invites land on the tier's signup page, carrying ?ref=
    so registration consumes the broker token (auto-links + comp-activates)."""
    path = "/matcha-x/signup" if tier == "matcha_x" else "/lite/signup"
    return f"{base_url.rstrip('/')}{path}?ref={token}"
def _fmt_client_invite(row: dict, base_url: str) -> dict:
    tier = row.get("tier") or "matcha_lite"
    redeemed = row.get("redeemed_company_id") is not None
    return {
        "id": str(row["id"]),
        "company_name": row.get("intended_company_name"),
        "seat_count": row.get("seat_count"),
        "tier": tier,
        "status": "redeemed" if redeemed else ("outstanding" if row["is_active"] else "revoked"),
        "redeemed_company_id": str(row["redeemed_company_id"]) if row.get("redeemed_company_id") else None,
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "expires_at": row["expires_at"].isoformat() if row["expires_at"] else None,
        "is_active": row["is_active"],
        "signup_url": _client_invite_signup_url(row["token"], tier, base_url),
    }
async def _assert_terms_accepted(conn, *, broker_id: UUID, user_id: UUID) -> None:
    required_terms_version = await conn.fetchval(
        "SELECT COALESCE(terms_required_version, 'v1') FROM brokers WHERE id = $1",
        broker_id,
    )
    accepted = await conn.fetchval(
        """
        SELECT EXISTS (
            SELECT 1
            FROM broker_terms_acceptances
            WHERE broker_id = $1
              AND user_id = $2
              AND terms_version = $3
        )
        """,
        broker_id,
        user_id,
        required_terms_version,
    )
    if not accepted:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Broker partner terms must be accepted before onboarding clients",
        )
async def _expire_stale_setups(conn, *, broker_id: UUID) -> int:
    stale_rows = await conn.fetch(
        """
        UPDATE broker_client_setups
        SET status = 'expired',
            expired_at = NOW(),
            updated_at = NOW()
        WHERE broker_id = $1
          AND status = ANY($2::text[])
          AND invite_expires_at IS NOT NULL
          AND invite_expires_at < NOW()
        RETURNING company_id
        """,
        broker_id,
        list(EXPIRABLE_SETUP_STATUSES),
    )
    if not stale_rows:
        return 0

    stale_company_ids = [row["company_id"] for row in stale_rows]
    await conn.execute(
        """
        UPDATE broker_company_links
        SET status = 'terminated',
            terminated_at = COALESCE(terminated_at, NOW()),
            updated_at = NOW()
        WHERE broker_id = $1
          AND company_id = ANY($2::uuid[])
          AND status = 'pending'
        """,
        broker_id,
        stale_company_ids,
    )
    return len(stale_rows)
def _fmt_token_row(row: dict, base_url: str) -> dict:
    token = row["token"]
    return {
        "id": str(row["id"]),
        "broker_id": str(row["broker_id"]),
        "token": token,
        "label": row["label"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "expires_at": row["expires_at"].isoformat() if row["expires_at"] else None,
        "is_active": row["is_active"],
        "use_count": row["use_count"],
        "last_used_at": row["last_used_at"].isoformat() if row["last_used_at"] else None,
        "referral_url": f"{base_url.rstrip('/')}/lite/signup?ref={token}",
        "payer": row.get("payer") or "business",
    }
# ── Seat allocation: pool view + company-pinned client seat invites ──────────
async def _committed_seats(conn, broker_id) -> int:
    """Seats apportioned out of the pool. Counts a pinned invite when it is either
    still outstanding (unredeemed + active) or redeemed to a client whose broker
    relationship is still live. Seats free when an outstanding invite is revoked OR
    when a redeemed client is terminated/transferred away from the broker."""
    return int(await conn.fetchval(
        """
        SELECT COALESCE(SUM(t.seat_count), 0)
        FROM broker_lite_referral_tokens t
        LEFT JOIN broker_company_links l
          ON l.broker_id = t.broker_id AND l.company_id = t.redeemed_company_id
        WHERE t.broker_id = $1
          AND t.intended_company_name IS NOT NULL
          AND (
            (t.redeemed_company_id IS NULL AND t.is_active = true)
            OR (t.redeemed_company_id IS NOT NULL
                AND COALESCE(l.status, 'active') NOT IN ('terminated', 'transferred'))
          )
        """,
        broker_id,
    ) or 0)
