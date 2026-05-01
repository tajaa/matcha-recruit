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


class BrokerClientSetupCreateRequest(BaseModel):
    company_name: str = Field(..., min_length=2, max_length=255)
    industry: Optional[str] = Field(default=None, max_length=100)
    company_size: Optional[str] = Field(default=None, max_length=50)
    headcount: Optional[int] = Field(default=None, ge=1, le=100_000)
    contact_name: Optional[str] = Field(default=None, max_length=255)
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = Field(default=None, max_length=50)
    notes: Optional[str] = Field(default=None, max_length=2000)
    locations: list[dict] = Field(default_factory=list)
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
    notes: Optional[str] = Field(default=None, max_length=2000)
    locations: Optional[list[dict]] = None
    preconfigured_features: Optional[dict[str, bool]] = None
    onboarding_template: Optional[dict] = None


class BrokerBatchClientSetupRequest(BaseModel):
    clients: list[BrokerClientSetupCreateRequest] = Field(..., min_length=1, max_length=50)


class BrokerClientSetupInviteRequest(BaseModel):
    expires_days: int = Field(default=14, ge=1, le=90)


class LiteReferralTokenCreateRequest(BaseModel):
    label: Optional[str] = Field(default=None, max_length=255)
    expires_days: Optional[int] = Field(default=None, ge=1, le=3650)
    payer: str = Field(default="business", pattern="^(broker|business)$")


class LiteReferralTokenResponse(BaseModel):
    id: str
    broker_id: str
    token: str
    label: Optional[str]
    created_at: str
    expires_at: Optional[str]
    is_active: bool
    use_count: int
    last_used_at: Optional[str]
    referral_url: str
    payer: str


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
                    notes, locations, onboarding_stage,
                    invite_token, invite_expires_at, invited_at,
                    created_by, updated_by, updated_at
                )
                VALUES (
                    $1, $2, $3, $4, $5, $6,
                    $7, $8, $9::jsonb, $10::jsonb,
                    $11, $12::jsonb, 'submitted',
                    $13, $14, $15,
                    $16, $16, NOW()
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
                request.notes,
                json.dumps(request.locations or []),
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


@router.post("/client-setups/batch")
async def batch_create_broker_client_setups(
    request: BrokerBatchClientSetupRequest,
    current_user: CurrentUser = Depends(require_broker),
):
    async with get_connection() as conn:
        membership = await _get_broker_membership(conn, user_id=current_user.id)
        await _assert_terms_accepted(conn, broker_id=membership["broker_id"], user_id=current_user.id)
        _assert_can_manage_clients(membership)

        created_setup_ids: list[UUID] = []
        errors: list[dict] = []

        for idx, client in enumerate(request.clients):
            try:
                normalized_features = _normalize_feature_toggles(client.preconfigured_features)
                merged_features = merge_company_features(default_company_features_json())
                merged_features.update(normalized_features)

                async with conn.transaction():
                    company = await conn.fetchrow(
                        """
                        INSERT INTO companies (name, industry, size, status, enabled_features)
                        VALUES ($1, $2, $3, 'pending', $4::jsonb)
                        RETURNING id
                        """,
                        client.company_name.strip(),
                        client.industry,
                        client.company_size,
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
                        json.dumps(client.link_permissions or {}),
                        current_user.id,
                    )

                    setup = await conn.fetchrow(
                        """
                        INSERT INTO broker_client_setups (
                            broker_id, company_id, status, contact_name, contact_email, contact_phone,
                            company_size_hint, headcount_hint, preconfigured_features, onboarding_template,
                            notes, locations, onboarding_stage,
                            created_by, updated_by, updated_at
                        )
                        VALUES (
                            $1, $2, 'draft', $3, $4, $5,
                            $6, $7, $8::jsonb, $9::jsonb,
                            $10, $11::jsonb, 'submitted',
                            $12, $12, NOW()
                        )
                        RETURNING id
                        """,
                        membership["broker_id"],
                        company["id"],
                        client.contact_name,
                        client.contact_email,
                        client.contact_phone,
                        client.company_size,
                        client.headcount,
                        json.dumps(normalized_features),
                        json.dumps(client.onboarding_template or {}),
                        client.notes,
                        json.dumps(client.locations or []),
                        current_user.id,
                    )
                    created_setup_ids.append(setup["id"])
            except HTTPException as exc:
                errors.append({"index": idx, "company_name": client.company_name, "error": exc.detail})
            except Exception as exc:
                errors.append({"index": idx, "company_name": client.company_name, "error": str(exc)})

        setups_serialized: list[dict] = []
        if created_setup_ids:
            rows = await conn.fetch(
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
                WHERE s.id = ANY($1::uuid[])
                ORDER BY s.created_at ASC
                """,
                created_setup_ids,
            )
            base_url = get_settings().app_base_url.rstrip("/")
            setups_serialized = [_serialize_setup(row, invite_base_url=base_url) for row in rows]

    return {
        "status": "created",
        "count": len(created_setup_ids),
        "setups": setups_serialized,
        "errors": errors,
    }


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
        if request.notes is not None:
            setup_updates.append(f"notes = ${len(setup_values) + 1}")
            setup_values.append(request.notes)
        if request.locations is not None:
            setup_updates.append(f"locations = ${len(setup_values) + 1}::jsonb")
            setup_values.append(json.dumps(request.locations))

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


@router.get("/companies/{company_id}")
async def get_broker_company_detail(
    company_id: UUID,
    current_user: CurrentUser = Depends(require_broker),
):
    """Return detailed read-only data about one of the broker's linked clients."""
    from ...core.services.handbook_service import HandbookService

    async with get_connection() as conn:
        membership = await _get_broker_membership(conn, user_id=current_user.id)
        broker_id = membership["broker_id"]

        # Verify broker has an active link to this company
        link = await conn.fetchrow(
            "SELECT status FROM broker_company_links WHERE broker_id = $1 AND company_id = $2 AND status <> 'terminated'",
            broker_id,
            company_id,
        )
        if not link:
            raise HTTPException(status_code=403, detail="No active link to this company")

        # ── 1. Company header ────────────────────────────────────────
        try:
            header = await conn.fetchrow(
                """
                SELECT c.id, c.name, c.industry, c.size, c.status,
                       l.status AS link_status,
                       COALESCE(s.status, 'none') AS setup_status,
                       s.onboarding_stage
                FROM companies c
                JOIN broker_company_links l ON l.company_id = c.id AND l.broker_id = $1
                LEFT JOIN broker_client_setups s ON s.company_id = c.id AND s.broker_id = $1
                WHERE c.id = $2
                """,
                broker_id,
                company_id,
            )
        except Exception:
            header = None

        if not header:
            raise HTTPException(status_code=404, detail="Company not found")

        try:
            active_employee_count = await conn.fetchval(
                "SELECT COUNT(*)::int FROM employees WHERE org_id = $1 AND termination_date IS NULL",
                company_id,
            ) or 0
        except Exception:
            active_employee_count = 0

        try:
            policy_stats = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) FILTER (WHERE ps.status = 'pending')::int AS pending_signatures,
                    CASE WHEN COUNT(*) = 0 THEN 0
                         ELSE ROUND((COUNT(*) FILTER (WHERE ps.status = 'signed')::numeric / COUNT(*)::numeric) * 100, 1)
                    END AS policy_compliance_rate
                FROM policies p
                LEFT JOIN policy_signatures ps ON ps.policy_id = p.id
                WHERE p.company_id = $1 AND p.status = 'active'
                """,
                company_id,
            )
            compliance_rate = float(policy_stats["policy_compliance_rate"] or 0)
            pending_signatures = int(policy_stats["pending_signatures"] or 0)
        except Exception:
            compliance_rate = 0.0
            pending_signatures = 0

        try:
            open_incidents = await conn.fetchval(
                "SELECT COUNT(*)::int FROM ir_incidents WHERE company_id = $1 AND status IN ('reported','investigating','action_required')",
                company_id,
            ) or 0
        except Exception:
            open_incidents = 0

        open_action_items = pending_signatures + open_incidents

        # Risk logic — same as portfolio endpoint
        if compliance_rate >= 90 and open_action_items == 0:
            risk_signal = "healthy"
        elif compliance_rate < 75 or open_action_items >= 5:
            risk_signal = "at_risk"
        else:
            risk_signal = "watch"

        company_data = {
            "id": str(header["id"]),
            "name": header["name"],
            "industry": header["industry"],
            "size": header["size"],
            "status": header["status"],
            "link_status": header["link_status"],
            "setup_status": header["setup_status"],
            "onboarding_stage": header["onboarding_stage"],
            "active_employee_count": active_employee_count,
            "policy_compliance_rate": compliance_rate,
            "open_action_items": open_action_items,
            "risk_signal": risk_signal,
        }

        # ── 2. Compliance locations ──────────────────────────────────
        try:
            loc_rows = await conn.fetch(
                """
                SELECT bl.id, bl.name, bl.city, bl.state,
                       cr.category, COUNT(cr.id) AS cat_count
                FROM business_locations bl
                LEFT JOIN compliance_requirements cr ON cr.location_id = bl.id
                WHERE bl.company_id = $1 AND bl.is_active = true
                GROUP BY bl.id, bl.name, bl.city, bl.state, cr.category
                ORDER BY bl.state, bl.city
                """,
                company_id,
            )
            locations_map: dict = {}
            total_requirements = 0
            for lr in loc_rows:
                lid = str(lr["id"])
                if lid not in locations_map:
                    locations_map[lid] = {
                        "id": lid,
                        "name": lr["name"],
                        "city": lr["city"],
                        "state": lr["state"],
                        "categories": {},
                        "total_requirements": 0,
                    }
                if lr["category"]:
                    cnt = int(lr["cat_count"] or 0)
                    locations_map[lid]["categories"][lr["category"]] = cnt
                    locations_map[lid]["total_requirements"] += cnt
                    total_requirements += cnt
            locations_list = list(locations_map.values())
        except Exception:
            locations_list = []
            total_requirements = 0

        compliance_data = {
            "locations": locations_list,
            "total_locations": len(locations_list),
            "total_requirements": total_requirements,
        }

        # ── 3. Policies with signature rates ─────────────────────────
        try:
            policy_rows = await conn.fetch(
                """
                SELECT p.id, p.title, p.category, p.status,
                       COUNT(ps.id) FILTER (WHERE ps.status = 'pending')::int AS pending_count,
                       COUNT(ps.id) FILTER (WHERE ps.status = 'signed')::int AS signed_count,
                       COUNT(ps.id)::int AS total_count
                FROM policies p
                LEFT JOIN policy_signatures ps ON ps.policy_id = p.id
                WHERE p.company_id = $1 AND p.status = 'active'
                GROUP BY p.id, p.title, p.category, p.status
                ORDER BY p.title
                """,
                company_id,
            )
            policy_items = []
            total_signed_all = 0
            total_sigs_all = 0
            for pr in policy_rows:
                tc = int(pr["total_count"] or 0)
                sc = int(pr["signed_count"] or 0)
                sig_rate = round(sc / tc * 100, 1) if tc > 0 else 0.0
                total_signed_all += sc
                total_sigs_all += tc
                policy_items.append({
                    "id": str(pr["id"]),
                    "title": pr["title"],
                    "category": pr["category"],
                    "status": pr["status"],
                    "pending_count": int(pr["pending_count"] or 0),
                    "signed_count": sc,
                    "total_count": tc,
                    "signature_rate": sig_rate,
                })
            overall_policy_rate = round(total_signed_all / total_sigs_all * 100, 1) if total_sigs_all > 0 else 0.0
        except Exception:
            policy_items = []
            overall_policy_rate = 0.0

        policies_data = {
            "total_active": len(policy_items),
            "compliance_rate": overall_policy_rate,
            "items": policy_items,
        }

        # ── 4. IR summary ────────────────────────────────────────────
        try:
            ir_row = await conn.fetchrow(
                """
                SELECT
                    COUNT(*) FILTER (WHERE status IN ('reported','investigating','action_required'))::int AS total_open,
                    COUNT(*) FILTER (WHERE severity = 'critical' AND status IN ('reported','investigating','action_required'))::int AS critical,
                    COUNT(*) FILTER (WHERE severity = 'high' AND status IN ('reported','investigating','action_required'))::int AS high,
                    COUNT(*) FILTER (WHERE severity = 'medium' AND status IN ('reported','investigating','action_required'))::int AS medium,
                    COUNT(*) FILTER (WHERE severity = 'low' AND status IN ('reported','investigating','action_required'))::int AS low,
                    COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '30 days')::int AS recent_30_days
                FROM ir_incidents WHERE company_id = $1
                """,
                company_id,
            )
            ir_summary = {
                "total_open": int(ir_row["total_open"] or 0),
                "by_severity": {
                    "critical": int(ir_row["critical"] or 0),
                    "high": int(ir_row["high"] or 0),
                    "medium": int(ir_row["medium"] or 0),
                    "low": int(ir_row["low"] or 0),
                },
                "recent_30_days": int(ir_row["recent_30_days"] or 0),
            }
        except Exception:
            ir_summary = {"total_open": 0, "by_severity": {"critical": 0, "high": 0, "medium": 0, "low": 0}, "recent_30_days": 0}

        # ── 5. ER summary ────────────────────────────────────────────
        try:
            er_rows = await conn.fetch(
                """
                SELECT status, COUNT(*)::int AS count
                FROM er_cases WHERE company_id = $1 AND status NOT IN ('closed','resolved')
                GROUP BY status
                """,
                company_id,
            )
            er_by_status = {row["status"]: row["count"] for row in er_rows}
            er_total_open = sum(er_by_status.values())
        except Exception:
            er_by_status = {}
            er_total_open = 0

        er_summary = {"total_open": er_total_open, "by_status": er_by_status}

        # ── 6. Handbook coverage ─────────────────────────────────────
        try:
            handbooks = await HandbookService.compute_coverage_summaries([str(company_id)])
        except Exception:
            handbooks = []

        # ── 7. Recent activity (last 15 entries) ─────────────────────
        try:
            activity_rows = await conn.fetch(
                """
                (
                    SELECT al.action, al.created_at AS timestamp, 'ir' AS source
                    FROM ir_audit_log al
                    JOIN ir_incidents i ON i.id = al.incident_id
                    WHERE i.company_id = $1
                )
                UNION ALL
                (
                    SELECT al.action, al.created_at AS timestamp, 'er' AS source
                    FROM er_audit_log al
                    JOIN er_cases ec ON ec.id = al.case_id
                    WHERE ec.company_id = $1
                )
                ORDER BY timestamp DESC
                LIMIT 15
                """,
                company_id,
            )
            recent_activity = [
                {
                    "action": row["action"],
                    "timestamp": row["timestamp"].isoformat() if row["timestamp"] else None,
                    "source": row["source"],
                }
                for row in activity_rows
            ]
        except Exception:
            recent_activity = []

    return {
        "company": company_data,
        "compliance": compliance_data,
        "policies": policies_data,
        "ir_summary": ir_summary,
        "er_summary": er_summary,
        "handbooks": handbooks,
        "recent_activity": recent_activity,
    }


@router.get("/reporting/portfolio")
async def get_broker_portfolio_reporting(current_user: CurrentUser = Depends(require_broker)):
    async with get_connection() as conn:
        membership = await _get_broker_membership(conn, user_id=current_user.id)
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

        try:
            rows = await conn.fetch(
                """
                SELECT
                    c.id AS company_id,
                    c.name AS company_name,
                    l.status AS link_status,
                    COALESCE(s.status, 'none') AS setup_status,
                    COALESCE(ps.pending_signatures, 0) AS pending_signatures,
                    COALESCE(ps.policy_compliance_rate, 0)::numeric AS policy_compliance_rate,
                    COALESCE(isum.open_incidents, 0) AS open_incidents,
                    COALESCE(es.active_employees, 0) AS active_employees,
                    COALESCE(ptm.total_checks, 0) AS total_checks,
                    COALESCE(ptm.avg_separation_risk, 0) AS avg_separation_risk,
                    COALESCE(ptm.override_rate, 0) AS override_rate
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
                LEFT JOIN LATERAL (
                    SELECT
                        COUNT(*)::int AS total_checks,
                        COALESCE(AVG(overall_score), 0)::int AS avg_separation_risk,
                        CASE
                            WHEN COUNT(*) FILTER (WHERE overall_band IN ('high', 'critical')) = 0 THEN 0
                            ELSE ROUND(
                                COUNT(*) FILTER (WHERE overall_band IN ('high', 'critical') AND outcome = 'proceeded')::numeric /
                                NULLIF(COUNT(*) FILTER (WHERE overall_band IN ('high', 'critical')), 0)::numeric,
                                2
                            )
                        END AS override_rate
                    FROM pre_termination_checks ptc
                    WHERE ptc.company_id = c.id
                      AND ptc.computed_at > NOW() - INTERVAL '12 months'
                ) ptm ON true
                WHERE l.broker_id = $1
                  AND l.status <> 'terminated'
                ORDER BY c.name
                """,
                membership["broker_id"],
            )
            has_pre_term = True
        except Exception:
            has_pre_term = False
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

        metrics = {
            "company_id": str(row["company_id"]),
            "company_name": row["company_name"],
            "link_status": row["link_status"],
            "setup_status": row["setup_status"],
            "policy_compliance_rate": compliance_rate,
            "open_action_items": open_action_items,
            "active_employee_count": int(row["active_employees"] or 0),
            "risk_signal": risk_signal,
        }
        if has_pre_term:
            metrics["pre_term_checks"] = int(row.get("total_checks") or 0)
            metrics["avg_separation_risk"] = int(row.get("avg_separation_risk") or 0)
            metrics["separation_override_rate"] = float(row.get("override_rate") or 0)

        company_metrics.append(metrics)

    company_count = len(company_metrics)
    avg_compliance_rate = round(total_compliance_rate / company_count, 1) if company_count else 0.0

    summary = {
        "total_linked_companies": company_count,
        "active_link_count": sum(1 for row in company_metrics if row["link_status"] in {"active", "grace"}),
        "pending_setup_count": setup_status_counts.get("draft", 0) + setup_status_counts.get("invited", 0),
        "expired_setup_count": setup_status_counts.get("expired", 0),
        "healthy_companies": healthy_count,
        "at_risk_companies": at_risk_count,
        "average_policy_compliance_rate": avg_compliance_rate,
        "open_action_item_total": action_item_total,
    }
    if has_pre_term:
        summary["total_pre_term_checks"] = sum(m.get("pre_term_checks", 0) for m in company_metrics)
        summary["avg_portfolio_override_rate"] = round(
            sum(m.get("separation_override_rate", 0) for m in company_metrics) / max(len(company_metrics), 1), 2
        ) if company_metrics else 0

    return {
        "summary": summary,
        "setup_status_counts": setup_status_counts,
        "companies": company_metrics,
        "redaction": {
            "employee_level_pii_included": False,
            "incident_detail_included": False,
            "note": "Broker portfolio reporting is intentionally aggregated for privacy and minimum necessary access.",
        },
    }


@router.get("/referred-clients")
async def list_referred_clients(current_user: CurrentUser = Depends(require_broker)):
    """List all companies that came through this broker's referral link or client setup flow."""
    async with get_connection() as conn:
        membership = await _get_broker_membership(conn, user_id=current_user.id)
        broker_id = membership["broker_id"]

        rows = await conn.fetch(
            """
            SELECT
                c.id AS company_id,
                c.name AS company_name,
                c.industry,
                c.size AS company_size,
                c.status AS company_status,
                bcl.status AS link_status,
                bcl.linked_at,
                bcl.activated_at,
                COUNT(DISTINCT e.id) FILTER (WHERE e.termination_date IS NULL) AS active_employee_count,
                c.enabled_features
            FROM broker_company_links bcl
            JOIN companies c ON c.id = bcl.company_id
            LEFT JOIN employees e ON e.org_id = c.id
            WHERE bcl.broker_id = $1
            GROUP BY c.id, c.name, c.industry, c.size, c.status,
                     bcl.status, bcl.linked_at, bcl.activated_at,
                     c.enabled_features
            ORDER BY bcl.linked_at DESC
            """,
            broker_id,
        )

        broker_slug = await conn.fetchval("SELECT slug FROM brokers WHERE id = $1", broker_id)

        clients = []
        for row in rows:
            features = row["enabled_features"]
            if isinstance(features, str):
                try:
                    features = json.loads(features)
                except Exception:
                    features = {}
            enabled_count = sum(1 for v in (features or {}).values() if v)
            clients.append({
                "company_id": str(row["company_id"]),
                "company_name": row["company_name"],
                "industry": row["industry"],
                "company_size": row["company_size"],
                "company_status": row["company_status"],
                "link_status": row["link_status"],
                "linked_at": row["linked_at"].isoformat() if row["linked_at"] else None,
                "activated_at": row["activated_at"].isoformat() if row["activated_at"] else None,
                "active_employee_count": row["active_employee_count"] or 0,
                "enabled_feature_count": enabled_count,
            })

        return {
            "broker_slug": broker_slug,
            "total": len(clients),
            "clients": clients,
        }


@router.get("/reporting/handbook-coverage")
async def get_broker_handbook_coverage(current_user: CurrentUser = Depends(require_broker)):
    from ...core.services.handbook_service import HandbookService

    async with get_connection() as conn:
        membership = await _get_broker_membership(conn, user_id=current_user.id)

        company_ids = [
            str(row["company_id"])
            for row in await conn.fetch(
                "SELECT company_id FROM broker_company_links WHERE broker_id = $1 AND status <> 'terminated'",
                membership["broker_id"],
            )
        ]

    summaries = await HandbookService.compute_coverage_summaries(company_ids)
    return summaries


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
