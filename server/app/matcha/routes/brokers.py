"""Broker portal routes for client onboarding and redacted book reporting."""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field

from ...config import get_settings
from ...core.feature_flags import default_company_features_json, merge_company_features
from ...core.models.auth import CurrentUser
from ...core.services.email import get_email_service
from ...database import get_connection
from ..dependencies import require_broker

router = APIRouter()

KNOWN_FEATURES = {
    "offer_letters",
    "offer_letters_plus",
    "policies",
    "handbooks",
    "compliance",
    "compliance_plus",
    "employees",
    "vibe_checks",
    "enps",
    "performance_reviews",
    "er_copilot",
    "incidents",
    "time_off",
    "accommodations",
    "internal_mobility",
}

EDITABLE_SETUP_STATUSES = {"draft", "invited"}
EXPIRABLE_SETUP_STATUSES = {"draft", "invited"}


class BrokerClientSetupCreateRequest(BaseModel):
    company_name: str = Field(..., min_length=2, max_length=255)
    industry: Optional[str] = Field(default=None, max_length=100)
    company_size: Optional[str] = Field(default=None, max_length=50)
    headcount: Optional[int] = Field(default=None, ge=1, le=100_000)
    contact_name: Optional[str] = Field(default=None, max_length=255)
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = Field(default=None, max_length=50)
    preconfigured_features: dict[str, bool] = Field(default_factory=dict)
    onboarding_template: dict = Field(default_factory=dict)
    link_permissions: dict = Field(default_factory=dict)
    invite_immediately: bool = False
    invite_expires_days: int = Field(default=14, ge=1, le=90)


class BrokerClientSetupUpdateRequest(BaseModel):
    company_name: Optional[str] = Field(default=None, min_length=2, max_length=255)
    industry: Optional[str] = Field(default=None, max_length=100)
    company_size: Optional[str] = Field(default=None, max_length=50)
    headcount: Optional[int] = Field(default=None, ge=1, le=100_000)
    contact_name: Optional[str] = Field(default=None, max_length=255)
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = Field(default=None, max_length=50)
    preconfigured_features: Optional[dict[str, bool]] = None
    onboarding_template: Optional[dict] = None


class BrokerClientSetupInviteRequest(BaseModel):
    expires_days: int = Field(default=14, ge=1, le=90)


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
    invite_token = row["invite_token"]
    google_workspace_status = row["google_workspace_status"]
    google_workspace = None
    if google_workspace_status:
        google_workspace_config = _to_dict(row["google_workspace_config"])
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
        "company_name": row["company_name"],
        "company_status": row["company_status"] or "approved",
        "industry": row["industry"],
        "company_size": row["company_size"],
        "status": row["status"],
        "link_status": row["link_status"],
        "contact_name": row["contact_name"],
        "contact_email": row["contact_email"],
        "contact_phone": row["contact_phone"],
        "headcount_hint": row["headcount_hint"],
        "preconfigured_features": _to_dict(row["preconfigured_features"]),
        "onboarding_template": _to_dict(row["onboarding_template"]),
        "link_permissions": _to_dict(row["link_permissions"]),
        "invite_token": invite_token,
        "invite_url": f"{invite_base_url}/register/broker-client/{invite_token}" if invite_token else None,
        "invite_expires_at": row["invite_expires_at"].isoformat() if row["invite_expires_at"] else None,
        "invited_at": row["invited_at"].isoformat() if row["invited_at"] else None,
        "activated_at": row["activated_at"].isoformat() if row["activated_at"] else None,
        "expired_at": row["expired_at"].isoformat() if row["expired_at"] else None,
        "cancelled_at": row["cancelled_at"].isoformat() if row["cancelled_at"] else None,
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
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


@router.post("/client-setups")
async def create_broker_client_setup(
    request: BrokerClientSetupCreateRequest,
    current_user: CurrentUser = Depends(require_broker),
):
    async with get_connection() as conn:
        membership = await _get_broker_membership(conn, user_id=current_user.id)
        await _assert_terms_accepted(conn, broker_id=membership["broker_id"], user_id=current_user.id)
        _assert_can_manage_clients(membership)

        normalized_features = _normalize_feature_toggles(request.preconfigured_features)
        merged_features = merge_company_features(default_company_features_json())
        merged_features.update(normalized_features)

        if request.invite_immediately and not request.contact_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="contact_email is required when invite_immediately is true",
            )

        invite_token = secrets.token_urlsafe(32) if request.invite_immediately else None
        invite_expires_at = (
            datetime.utcnow() + timedelta(days=request.invite_expires_days)
            if request.invite_immediately
            else None
        )
        setup_status = "invited" if request.invite_immediately else "draft"
        invited_at = datetime.utcnow() if request.invite_immediately else None

        async with conn.transaction():
            company = await conn.fetchrow(
                """
                INSERT INTO companies (name, industry, size, status, enabled_features)
                VALUES ($1, $2, $3, 'pending', $4::jsonb)
                RETURNING id
                """,
                request.company_name.strip(),
                request.industry,
                request.company_size,
                json.dumps(merged_features),
            )

            await conn.execute(
                """
                INSERT INTO broker_company_links (
                    broker_id, company_id, status, permissions, linked_at, created_by, updated_at
                )
                VALUES ($1, $2, 'pending', $3::jsonb, NOW(), $4, NOW())
                ON CONFLICT (broker_id, company_id)
                DO UPDATE SET
                    status = 'pending',
                    permissions = EXCLUDED.permissions,
                    updated_at = NOW()
                """,
                membership["broker_id"],
                company["id"],
                json.dumps(request.link_permissions or {}),
                current_user.id,
            )

            setup = await conn.fetchrow(
                """
                INSERT INTO broker_client_setups (
                    broker_id, company_id, status, contact_name, contact_email, contact_phone,
                    company_size_hint, headcount_hint, preconfigured_features, onboarding_template,
                    invite_token, invite_expires_at, invited_at,
                    created_by, updated_by, updated_at
                )
                VALUES (
                    $1, $2, $3, $4, $5, $6,
                    $7, $8, $9::jsonb, $10::jsonb,
                    $11, $12, $13,
                    $14, $14, NOW()
                )
                RETURNING id
                """,
                membership["broker_id"],
                company["id"],
                setup_status,
                request.contact_name,
                request.contact_email,
                request.contact_phone,
                request.company_size,
                request.headcount,
                json.dumps(normalized_features),
                json.dumps(request.onboarding_template or {}),
                invite_token,
                invite_expires_at,
                invited_at,
                current_user.id,
            )

        row = await conn.fetchrow(
            """
            SELECT
                s.*,
                c.name as company_name,
                c.status as company_status,
                c.industry,
                c.size as company_size,
                b.name as broker_name,
                l.status as link_status,
                l.permissions as link_permissions,
                ic.status as google_workspace_status,
                ic.config as google_workspace_config
            FROM broker_client_setups s
            JOIN companies c ON c.id = s.company_id
            JOIN brokers b ON b.id = s.broker_id
            LEFT JOIN broker_company_links l
                ON l.broker_id = s.broker_id
               AND l.company_id = s.company_id
            LEFT JOIN integration_connections ic
                ON ic.company_id = s.company_id
               AND ic.provider = 'google_workspace'
            WHERE s.id = $1
            """,
            setup["id"],
        )

    base_url = get_settings().app_base_url.rstrip("/")
    serialized = _serialize_setup(row, invite_base_url=base_url)
    response = {"status": "created", "setup": serialized}
    if request.invite_immediately and serialized.get("invite_url"):
        email_sent, email_error = await _send_broker_client_invite_email(
            row=dict(row),
            invite_url=serialized["invite_url"],
        )
        response["invite_email_sent"] = email_sent
        if email_error:
            response["invite_email_error"] = email_error
    return response


@router.get("/client-setups")
async def list_broker_client_setups(
    status_filter: Optional[str] = Query(default=None, alias="status"),
    current_user: CurrentUser = Depends(require_broker),
):
    async with get_connection() as conn:
        membership = await _get_broker_membership(conn, user_id=current_user.id)
        await _assert_terms_accepted(conn, broker_id=membership["broker_id"], user_id=current_user.id)
        _assert_can_manage_clients(membership)

        expired_count = await _expire_stale_setups(conn, broker_id=membership["broker_id"])

        query = """
            SELECT
                s.*,
                c.name as company_name,
                c.status as company_status,
                c.industry,
                c.size as company_size,
                l.status as link_status,
                l.permissions as link_permissions,
                ic.status as google_workspace_status,
                ic.config as google_workspace_config
            FROM broker_client_setups s
            JOIN companies c ON c.id = s.company_id
            LEFT JOIN broker_company_links l
                ON l.broker_id = s.broker_id
               AND l.company_id = s.company_id
            LEFT JOIN integration_connections ic
                ON ic.company_id = s.company_id
               AND ic.provider = 'google_workspace'
            WHERE s.broker_id = $1
        """
        params: list = [membership["broker_id"]]
        if status_filter:
            query += " AND s.status = $2"
            params.append(status_filter)
        query += " ORDER BY s.created_at DESC"

        rows = await conn.fetch(query, *params)

    base_url = get_settings().app_base_url.rstrip("/")
    return {
        "setups": [_serialize_setup(row, invite_base_url=base_url) for row in rows],
        "total": len(rows),
        "expired_count": expired_count,
    }


@router.patch("/client-setups/{setup_id}")
async def update_broker_client_setup(
    setup_id: UUID,
    request: BrokerClientSetupUpdateRequest,
    current_user: CurrentUser = Depends(require_broker),
):
    async with get_connection() as conn:
        membership = await _get_broker_membership(conn, user_id=current_user.id)
        await _assert_terms_accepted(conn, broker_id=membership["broker_id"], user_id=current_user.id)
        _assert_can_manage_clients(membership)

        setup_row = await conn.fetchrow(
            """
            SELECT id, broker_id, company_id, status
            FROM broker_client_setups
            WHERE id = $1 AND broker_id = $2
            """,
            setup_id,
            membership["broker_id"],
        )
        if not setup_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Setup not found")
        if setup_row["status"] not in EDITABLE_SETUP_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Setup cannot be edited in status '{setup_row['status']}'",
            )

        normalized_features = None
        if request.preconfigured_features is not None:
            normalized_features = _normalize_feature_toggles(request.preconfigured_features)
            merged_features = merge_company_features(default_company_features_json())
            merged_features.update(normalized_features)
            await conn.execute(
                """
                UPDATE companies
                SET enabled_features = $1::jsonb
                WHERE id = $2
                """,
                json.dumps(merged_features),
                setup_row["company_id"],
            )

        company_updates = []
        company_values: list = []
        if request.company_name is not None:
            company_updates.append(f"name = ${len(company_values) + 1}")
            company_values.append(request.company_name.strip())
        if request.industry is not None:
            company_updates.append(f"industry = ${len(company_values) + 1}")
            company_values.append(request.industry)
        if request.company_size is not None:
            company_updates.append(f"size = ${len(company_values) + 1}")
            company_values.append(request.company_size)
        if company_updates:
            company_values.append(setup_row["company_id"])
            await conn.execute(
                f"""
                UPDATE companies
                SET {', '.join(company_updates)}
                WHERE id = ${len(company_values)}
                """,
                *company_values,
            )

        setup_updates = []
        setup_values: list = []
        if request.contact_name is not None:
            setup_updates.append(f"contact_name = ${len(setup_values) + 1}")
            setup_values.append(request.contact_name)
        if request.contact_email is not None:
            setup_updates.append(f"contact_email = ${len(setup_values) + 1}")
            setup_values.append(request.contact_email)
        if request.contact_phone is not None:
            setup_updates.append(f"contact_phone = ${len(setup_values) + 1}")
            setup_values.append(request.contact_phone)
        if request.headcount is not None:
            setup_updates.append(f"headcount_hint = ${len(setup_values) + 1}")
            setup_values.append(request.headcount)
        if request.company_size is not None:
            setup_updates.append(f"company_size_hint = ${len(setup_values) + 1}")
            setup_values.append(request.company_size)
        if normalized_features is not None:
            setup_updates.append(f"preconfigured_features = ${len(setup_values) + 1}::jsonb")
            setup_values.append(json.dumps(normalized_features))
        if request.onboarding_template is not None:
            setup_updates.append(f"onboarding_template = ${len(setup_values) + 1}::jsonb")
            setup_values.append(json.dumps(request.onboarding_template))

        if setup_updates:
            setup_updates.extend(
                [
                    f"updated_by = ${len(setup_values) + 1}",
                    "updated_at = NOW()",
                ]
            )
            setup_values.append(current_user.id)
            setup_values.append(setup_id)
            await conn.execute(
                f"""
                UPDATE broker_client_setups
                SET {', '.join(setup_updates)}
                WHERE id = ${len(setup_values)}
                """,
                *setup_values,
            )

        row = await conn.fetchrow(
            """
            SELECT
                s.*,
                c.name as company_name,
                c.status as company_status,
                c.industry,
                c.size as company_size,
                l.status as link_status,
                l.permissions as link_permissions,
                ic.status as google_workspace_status,
                ic.config as google_workspace_config
            FROM broker_client_setups s
            JOIN companies c ON c.id = s.company_id
            LEFT JOIN broker_company_links l
                ON l.broker_id = s.broker_id
               AND l.company_id = s.company_id
            LEFT JOIN integration_connections ic
                ON ic.company_id = s.company_id
               AND ic.provider = 'google_workspace'
            WHERE s.id = $1
            """,
            setup_id,
        )

    base_url = get_settings().app_base_url.rstrip("/")
    return {"status": "updated", "setup": _serialize_setup(row, invite_base_url=base_url)}


@router.post("/client-setups/{setup_id}/send-invite")
async def send_broker_client_invite(
    setup_id: UUID,
    request: BrokerClientSetupInviteRequest,
    current_user: CurrentUser = Depends(require_broker),
):
    async with get_connection() as conn:
        membership = await _get_broker_membership(conn, user_id=current_user.id)
        await _assert_terms_accepted(conn, broker_id=membership["broker_id"], user_id=current_user.id)
        _assert_can_manage_clients(membership)

        setup_row = await conn.fetchrow(
            """
            SELECT id, status, contact_email
            FROM broker_client_setups
            WHERE id = $1 AND broker_id = $2
            """,
            setup_id,
            membership["broker_id"],
        )
        if not setup_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Setup not found")
        if setup_row["status"] not in EDITABLE_SETUP_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot send invite for setup in status '{setup_row['status']}'",
            )
        if not setup_row["contact_email"]:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Setup is missing contact_email")

        invite_token = secrets.token_urlsafe(32)
        invite_expires_at = datetime.utcnow() + timedelta(days=request.expires_days)
        await conn.execute(
            """
            UPDATE broker_client_setups
            SET status = 'invited',
                invite_token = $1,
                invite_expires_at = $2,
                invited_at = NOW(),
                expired_at = NULL,
                cancelled_at = NULL,
                updated_by = $3,
                updated_at = NOW()
            WHERE id = $4
            """,
            invite_token,
            invite_expires_at,
            current_user.id,
            setup_id,
        )

        row = await conn.fetchrow(
            """
            SELECT
                s.*,
                c.name as company_name,
                c.status as company_status,
                c.industry,
                c.size as company_size,
                b.name as broker_name,
                l.status as link_status,
                l.permissions as link_permissions,
                ic.status as google_workspace_status,
                ic.config as google_workspace_config
            FROM broker_client_setups s
            JOIN companies c ON c.id = s.company_id
            JOIN brokers b ON b.id = s.broker_id
            LEFT JOIN broker_company_links l
                ON l.broker_id = s.broker_id
               AND l.company_id = s.company_id
            LEFT JOIN integration_connections ic
                ON ic.company_id = s.company_id
               AND ic.provider = 'google_workspace'
            WHERE s.id = $1
            """,
            setup_id,
        )

    base_url = get_settings().app_base_url.rstrip("/")
    serialized = _serialize_setup(row, invite_base_url=base_url)
    email_sent, email_error = await _send_broker_client_invite_email(
        row=dict(row),
        invite_url=serialized["invite_url"],
    )
    response = {"status": "invited", "setup": serialized, "invite_email_sent": email_sent}
    if email_error:
        response["invite_email_error"] = email_error
    return response


@router.post("/client-setups/{setup_id}/cancel")
async def cancel_broker_client_setup(
    setup_id: UUID,
    current_user: CurrentUser = Depends(require_broker),
):
    async with get_connection() as conn:
        membership = await _get_broker_membership(conn, user_id=current_user.id)
        await _assert_terms_accepted(conn, broker_id=membership["broker_id"], user_id=current_user.id)
        _assert_can_manage_clients(membership)

        setup_row = await conn.fetchrow(
            """
            SELECT id, company_id, status
            FROM broker_client_setups
            WHERE id = $1 AND broker_id = $2
            """,
            setup_id,
            membership["broker_id"],
        )
        if not setup_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Setup not found")
        if setup_row["status"] == "activated":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Activated setups cannot be cancelled",
            )
        if setup_row["status"] == "cancelled":
            return {"status": "cancelled"}

        async with conn.transaction():
            await conn.execute(
                """
                UPDATE broker_client_setups
                SET status = 'cancelled',
                    cancelled_at = NOW(),
                    updated_by = $1,
                    updated_at = NOW()
                WHERE id = $2
                """,
                current_user.id,
                setup_id,
            )
            await conn.execute(
                """
                UPDATE broker_company_links
                SET status = 'terminated',
                    terminated_at = COALESCE(terminated_at, NOW()),
                    updated_at = NOW()
                WHERE broker_id = $1
                  AND company_id = $2
                  AND status = 'pending'
                """,
                membership["broker_id"],
                setup_row["company_id"],
            )

    return {"status": "cancelled"}


@router.post("/client-setups/expire-stale")
async def expire_stale_broker_client_setups(current_user: CurrentUser = Depends(require_broker)):
    async with get_connection() as conn:
        membership = await _get_broker_membership(conn, user_id=current_user.id)
        await _assert_terms_accepted(conn, broker_id=membership["broker_id"], user_id=current_user.id)
        _assert_can_manage_clients(membership)
        expired_count = await _expire_stale_setups(conn, broker_id=membership["broker_id"])
    return {"status": "ok", "expired_count": expired_count}


@router.get("/reporting/portfolio")
async def get_broker_portfolio_reporting(current_user: CurrentUser = Depends(require_broker)):
    async with get_connection() as conn:
        membership = await _get_broker_membership(conn, user_id=current_user.id)
        await _assert_terms_accepted(conn, broker_id=membership["broker_id"], user_id=current_user.id)
        await _expire_stale_setups(conn, broker_id=membership["broker_id"])

        setup_counts = await conn.fetch(
            """
            SELECT status, COUNT(*)::int AS count
            FROM broker_client_setups
            WHERE broker_id = $1
            GROUP BY status
            """,
            membership["broker_id"],
        )
        setup_status_counts = {row["status"]: row["count"] for row in setup_counts}

        rows = await conn.fetch(
            """
            SELECT
                c.id as company_id,
                c.name as company_name,
                l.status as link_status,
                COALESCE(s.status, 'none') as setup_status,
                COALESCE(ps.pending_signatures, 0) as pending_signatures,
                COALESCE(ps.policy_compliance_rate, 0)::numeric as policy_compliance_rate,
                COALESCE(isum.open_incidents, 0) as open_incidents,
                COALESCE(es.active_employees, 0) as active_employees
            FROM broker_company_links l
            JOIN companies c ON c.id = l.company_id
            LEFT JOIN broker_client_setups s
                ON s.broker_id = l.broker_id
               AND s.company_id = l.company_id
            LEFT JOIN LATERAL (
                SELECT
                    COUNT(*) FILTER (WHERE ps.status = 'pending')::int AS pending_signatures,
                    CASE
                        WHEN COUNT(*) = 0 THEN 0
                        ELSE ROUND(
                            (COUNT(*) FILTER (WHERE ps.status = 'signed')::numeric / COUNT(*)::numeric) * 100,
                            1
                        )
                    END AS policy_compliance_rate
                FROM policies p
                LEFT JOIN policy_signatures ps ON ps.policy_id = p.id
                WHERE p.company_id = c.id
                  AND p.status = 'active'
            ) ps ON true
            LEFT JOIN LATERAL (
                SELECT COUNT(*)::int AS open_incidents
                FROM ir_incidents i
                WHERE i.company_id = c.id
                  AND i.status IN ('reported', 'investigating', 'action_required')
            ) isum ON true
            LEFT JOIN LATERAL (
                SELECT COUNT(*)::int AS active_employees
                FROM employees e
                WHERE e.org_id = c.id
                  AND e.termination_date IS NULL
            ) es ON true
            WHERE l.broker_id = $1
              AND l.status <> 'terminated'
            ORDER BY c.name
            """,
            membership["broker_id"],
        )

    company_metrics = []
    healthy_count = 0
    at_risk_count = 0
    total_compliance_rate = 0.0
    action_item_total = 0
    for row in rows:
        compliance_rate = float(row["policy_compliance_rate"] or 0)
        pending_signatures = int(row["pending_signatures"] or 0)
        open_incidents = int(row["open_incidents"] or 0)
        open_action_items = pending_signatures + open_incidents
        action_item_total += open_action_items
        total_compliance_rate += compliance_rate

        if compliance_rate >= 90 and open_action_items == 0:
            risk_signal = "healthy"
            healthy_count += 1
        elif compliance_rate < 75 or open_action_items >= 5:
            risk_signal = "at_risk"
            at_risk_count += 1
        else:
            risk_signal = "watch"

        company_metrics.append(
            {
                "company_id": str(row["company_id"]),
                "company_name": row["company_name"],
                "link_status": row["link_status"],
                "setup_status": row["setup_status"],
                "policy_compliance_rate": compliance_rate,
                "open_action_items": open_action_items,
                "active_employee_count": int(row["active_employees"] or 0),
                "risk_signal": risk_signal,
            }
        )

    company_count = len(company_metrics)
    avg_compliance_rate = round(total_compliance_rate / company_count, 1) if company_count else 0.0

    return {
        "summary": {
            "total_linked_companies": company_count,
            "active_link_count": sum(1 for row in company_metrics if row["link_status"] in {"active", "grace"}),
            "pending_setup_count": setup_status_counts.get("draft", 0) + setup_status_counts.get("invited", 0),
            "expired_setup_count": setup_status_counts.get("expired", 0),
            "healthy_companies": healthy_count,
            "at_risk_companies": at_risk_count,
            "average_policy_compliance_rate": avg_compliance_rate,
            "open_action_item_total": action_item_total,
        },
        "setup_status_counts": setup_status_counts,
        "companies": company_metrics,
        "redaction": {
            "employee_level_pii_included": False,
            "incident_detail_included": False,
            "note": "Broker portfolio reporting is intentionally aggregated for privacy and minimum necessary access.",
        },
    }
