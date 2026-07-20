"""Broker client setups routes (J7 split)."""
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
@router.post("/client-setups/{setup_id}/stage")
async def set_broker_client_setup_stage(
    setup_id: UUID,
    request: BrokerSetupStageRequest,
    current_user: CurrentUser = Depends(require_broker),
):
    """Move a client setup between onboarding stages for the Pipeline board.

    Unlike the full PATCH (limited to draft/invited setups), stage transitions
    are allowed at any status — ``status`` (invite lifecycle) and
    ``onboarding_stage`` (onboarding workflow) are orthogonal.
    """
    async with get_connection() as conn:
        membership = await _get_broker_membership(conn, user_id=current_user.id)
        await _assert_terms_accepted(conn, broker_id=membership["broker_id"], user_id=current_user.id)
        _assert_can_manage_clients(membership)

        result = await conn.execute(
            """
            UPDATE broker_client_setups
            SET onboarding_stage = $1, updated_by = $2, updated_at = NOW()
            WHERE id = $3 AND broker_id = $4
            """,
            request.onboarding_stage, current_user.id, setup_id, membership["broker_id"],
        )
    if result.split()[-1] == "0":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Setup not found")
    return {"status": "updated", "onboarding_stage": request.onboarding_stage}
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
    from ....core.services.handbook_service import HandbookService

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
                    COUNT(DISTINCT p.id)::int AS active_policy_count,
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
            active_policy_count = int(policy_stats["active_policy_count"] or 0)
            pending_signatures = int(policy_stats["pending_signatures"] or 0)
        except Exception:
            compliance_rate = 0.0
            active_policy_count = 0
            pending_signatures = 0

        try:
            open_incidents = await conn.fetchval(
                "SELECT COUNT(*)::int FROM ir_incidents WHERE company_id = $1 AND status IN ('reported','investigating','action_required')",
                company_id,
            ) or 0
        except Exception:
            open_incidents = 0

        open_action_items = pending_signatures + open_incidents

        # Risk logic — same as portfolio endpoint. No active policies = "no data",
        # not "at risk"; only let compliance drive the signal when policies exist.
        has_policy_data = active_policy_count > 0
        if has_policy_data and compliance_rate >= 90 and open_action_items == 0:
            risk_signal = "healthy"
        elif open_action_items >= 5 or (has_policy_data and compliance_rate < 75):
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
