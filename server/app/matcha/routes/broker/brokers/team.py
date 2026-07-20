"""Broker team routes (J7 split)."""
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


@router.get("/seats")
async def get_broker_seats(current_user: CurrentUser = Depends(require_broker)):
    """Seat pool summary + per-client apportionment for the broker portal."""
    async with get_connection() as conn:
        membership = await _get_broker_membership(conn, user_id=current_user.id)
        broker_id = membership["broker_id"]
        allocated = int(await conn.fetchval("SELECT allocated_seats FROM brokers WHERE id = $1", broker_id) or 0)
        rows = await conn.fetch(
            """
            SELECT t.id, t.token, t.intended_company_name, t.seat_count, t.tier,
                   t.redeemed_company_id, t.is_active, t.created_at, t.expires_at,
                   c.name AS redeemed_company_name,
                   COALESCE((
                       SELECT COUNT(*) FROM employees e
                       WHERE e.org_id = t.redeemed_company_id AND e.termination_date IS NULL
                   ), 0) AS employees_used
            FROM broker_lite_referral_tokens t
            LEFT JOIN companies c ON c.id = t.redeemed_company_id
            LEFT JOIN broker_company_links l
              ON l.broker_id = t.broker_id AND l.company_id = t.redeemed_company_id
            WHERE t.broker_id = $1
              AND t.intended_company_name IS NOT NULL
              AND (
                (t.redeemed_company_id IS NULL AND t.is_active = true)
                OR (t.redeemed_company_id IS NOT NULL
                    AND COALESCE(l.status, 'active') NOT IN ('terminated', 'transferred'))
              )
            ORDER BY t.created_at DESC
            """,
            broker_id,
        )
        base_url = get_settings().app_base_url
        committed = 0
        clients = []
        for r in rows:
            committed += int(r["seat_count"] or 0)
            d = _fmt_client_invite(dict(r), base_url)
            d["redeemed_company_name"] = r["redeemed_company_name"]
            d["employees_used"] = int(r["employees_used"] or 0)
            clients.append(d)
        return {
            "allocated": allocated,
            "committed": committed,
            "remaining": max(0, allocated - committed),
            "clients": clients,
        }
@router.post("/client-invites")
async def create_client_seat_invite(
    request: ClientSeatInviteCreateRequest,
    current_user: CurrentUser = Depends(require_broker),
):
    """Mint a company-pinned, single-use signup link that debits the seat pool.
    Recipient lands on the tier's signup page with the company name prefilled."""
    async with get_connection() as conn:
        membership = await _get_broker_membership(conn, user_id=current_user.id)
        _assert_can_manage_clients(membership)
        broker_id = membership["broker_id"]

        async with conn.transaction():
            # Lock the broker row so concurrent mints can't both pass the seat check.
            allocated = int(await conn.fetchval(
                "SELECT allocated_seats FROM brokers WHERE id = $1 FOR UPDATE", broker_id
            ) or 0)
            committed = await _committed_seats(conn, broker_id)
            remaining = max(0, allocated - committed)
            if request.seat_count > remaining:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Not enough seats: {remaining} remaining, {request.seat_count} requested",
                )
            token = secrets.token_urlsafe(32)
            expires_at = datetime.utcnow() + timedelta(days=request.expires_days) if request.expires_days else None
            row = await conn.fetchrow(
                """
                INSERT INTO broker_lite_referral_tokens
                    (broker_id, token, label, created_by, expires_at, payer,
                     intended_company_name, seat_count, tier)
                VALUES ($1, $2, $3, $4, $5, 'broker', $6, $7, $8)
                RETURNING *
                """,
                broker_id, token, request.company_name.strip(), current_user.id,
                expires_at, request.company_name.strip(), request.seat_count, request.tier,
            )
        return _fmt_client_invite(dict(row), get_settings().app_base_url)
@router.get("/client-invites")
async def list_client_seat_invites(
    include_revoked: bool = Query(False),
    current_user: CurrentUser = Depends(require_broker),
):
    async with get_connection() as conn:
        membership = await _get_broker_membership(conn, user_id=current_user.id)
        broker_id = membership["broker_id"]
        rows = await conn.fetch(
            """
            SELECT t.*, c.name AS redeemed_company_name,
                   COALESCE((
                       SELECT COUNT(*) FROM employees e
                       WHERE e.org_id = t.redeemed_company_id AND e.termination_date IS NULL
                   ), 0) AS employees_used
            FROM broker_lite_referral_tokens t
            LEFT JOIN companies c ON c.id = t.redeemed_company_id
            WHERE t.broker_id = $1
              AND t.intended_company_name IS NOT NULL
              AND ($2::bool OR t.is_active = true OR t.redeemed_company_id IS NOT NULL)
            ORDER BY t.created_at DESC
            """,
            broker_id, include_revoked,
        )
        base_url = get_settings().app_base_url
        invites = []
        for r in rows:
            d = _fmt_client_invite(dict(r), base_url)
            d["redeemed_company_name"] = r["redeemed_company_name"]
            d["employees_used"] = int(r["employees_used"] or 0)
            invites.append(d)
        return {"invites": invites, "total": len(invites)}
@router.delete("/client-invites/{invite_id}")
async def revoke_client_seat_invite(
    invite_id: str,
    current_user: CurrentUser = Depends(require_broker),
):
    """Revoke an outstanding (unredeemed) client invite — frees its seats back to the pool."""
    async with get_connection() as conn:
        membership = await _get_broker_membership(conn, user_id=current_user.id)
        _assert_can_manage_clients(membership)
        broker_id = membership["broker_id"]
        row = await conn.fetchrow(
            """
            UPDATE broker_lite_referral_tokens
            SET is_active = false
            WHERE id = $1 AND broker_id = $2
              AND intended_company_name IS NOT NULL
              AND redeemed_company_id IS NULL
            RETURNING id
            """,
            UUID(invite_id), broker_id,
        )
        if not row:
            raise HTTPException(
                status_code=404,
                detail="Outstanding client invite not found (redeemed invites can't be revoked)",
            )
        return {"status": "revoked"}
# ── Broker team: self-service broker user accounts ───────────────────────────
@router.post("/members")
async def create_broker_member(
    request: BrokerMemberCreateRequest,
    current_user: CurrentUser = Depends(require_broker),
):
    """Create an additional broker user under this brokerage (owner/admin only)."""
    from ....core.services.auth import hash_password  # lazy: avoid import cycle

    generated_password = not bool(request.password and request.password.strip())
    member_password = request.password.strip() if request.password else secrets.token_urlsafe(12)

    async with get_connection() as conn:
        membership = await _get_broker_membership(conn, user_id=current_user.id)
        _assert_can_manage_team(membership)
        broker_id = membership["broker_id"]
        broker = await conn.fetchrow("SELECT name, slug FROM brokers WHERE id = $1", broker_id)

        async with conn.transaction():
            if await conn.fetchval("SELECT id FROM users WHERE email = $1", request.email):
                raise HTTPException(status_code=400, detail="Email is already registered")
            user = await conn.fetchrow(
                """
                INSERT INTO users (email, password_hash, role)
                VALUES ($1, $2, 'broker')
                RETURNING id, email
                """,
                request.email, hash_password(member_password),
            )
            await conn.execute(
                """
                INSERT INTO broker_members (broker_id, user_id, role, permissions, is_active)
                VALUES ($1, $2, $3, $4::jsonb, true)
                """,
                broker_id, user["id"], request.role,
                json.dumps({"can_manage_clients": True, "can_manage_team": request.role == "admin"}),
            )

    email_sent = False
    try:
        email_sent = await get_email_service().send_broker_welcome_email(
            to_email=request.email, to_name=request.name,
            broker_name=broker["name"], broker_slug=broker["slug"], password=member_password,
        )
    except Exception:
        pass

    return {
        "status": "created",
        "member": {
            "user_id": str(user["id"]),
            "name": request.name,
            "email": user["email"],
            "role": request.role,
        },
        "generated_password": generated_password,
        "password": member_password,
        "email_sent": email_sent,
    }
@router.get("/members")
async def list_broker_members(current_user: CurrentUser = Depends(require_broker)):
    async with get_connection() as conn:
        membership = await _get_broker_membership(conn, user_id=current_user.id)
        broker_id = membership["broker_id"]
        rows = await conn.fetch(
            """
            SELECT bm.id, bm.user_id, bm.role, bm.is_active, bm.created_at, u.email, u.last_login
            FROM broker_members bm
            JOIN users u ON u.id = bm.user_id
            WHERE bm.broker_id = $1
            ORDER BY bm.created_at ASC
            """,
            broker_id,
        )
        members = [
            {
                "id": str(r["id"]),
                "user_id": str(r["user_id"]),
                "email": r["email"],
                "role": r["role"],
                "is_active": r["is_active"],
                "last_login": r["last_login"].isoformat() if r["last_login"] else None,
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "is_self": str(r["user_id"]) == str(current_user.id),
            }
            for r in rows
        ]
        return {"members": members, "total": len(members)}
@router.delete("/members/{member_id}")
async def deactivate_broker_member(
    member_id: str,
    current_user: CurrentUser = Depends(require_broker),
):
    async with get_connection() as conn:
        membership = await _get_broker_membership(conn, user_id=current_user.id)
        _assert_can_manage_team(membership)
        broker_id = membership["broker_id"]
        target = await conn.fetchrow(
            "SELECT id, user_id, role FROM broker_members WHERE id = $1 AND broker_id = $2",
            UUID(member_id), broker_id,
        )
        if not target:
            raise HTTPException(status_code=404, detail="Member not found")
        if target["role"] == "owner":
            raise HTTPException(status_code=400, detail="Cannot deactivate the broker owner")
        if str(target["user_id"]) == str(current_user.id):
            raise HTTPException(status_code=400, detail="Cannot deactivate yourself")
        await conn.execute(
            "UPDATE broker_members SET is_active = false, updated_at = NOW() WHERE id = $1",
            target["id"],
        )
        return {"status": "deactivated"}
