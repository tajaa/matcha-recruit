"""Admin invites routes (J5 split)."""
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


@router.get("/business-registrations", response_model=BusinessRegistrationListResponse, dependencies=[Depends(require_admin)])
async def list_business_registrations(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status: pending, approved, rejected"),
    signup_source: Optional[str] = Query(None, description="Filter by signup_source value (resources_free, matcha_lite, matcha_x, bespoke, ir_only_self_serve)"),
    tier: Optional[str] = Query(None, description="Tier chip: free | lite | x | compliance | platform | personal"),
    include_deleted: bool = Query(False, description="Include soft-deleted companies"),
):
    """List all business registrations with optional status/tier filters."""
    async with get_connection() as conn:
        query = _BUSINESS_REGISTRATION_SELECT + " WHERE comp.owner_id IS NOT NULL"
        params: list = []

        if not include_deleted:
            query += " AND comp.deleted_at IS NULL"

        if status_filter:
            params.append(status_filter)
            query += f" AND comp.status = ${len(params)}"

        if signup_source:
            params.append(signup_source)
            query += f" AND comp.signup_source = ${len(params)}"

        tier_clause, tier_params = _tier_filter_clause(tier)
        if tier_clause:
            query += tier_clause
            params.extend(tier_params)

        query += " ORDER BY comp.created_at DESC"

        rows = await conn.fetch(query, *params)
        registrations = [_row_to_registration(row) for row in rows]
        return BusinessRegistrationListResponse(
            registrations=registrations,
            total=len(registrations),
        )


@router.get("/business-registrations/{company_id}", response_model=BusinessRegistrationResponse, dependencies=[Depends(require_admin)])
async def get_business_registration(company_id: UUID):
    """Get details of a specific business registration."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            _BUSINESS_REGISTRATION_SELECT + " WHERE comp.id = $1 AND comp.owner_id IS NOT NULL",
            company_id,
        )

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Business registration not found",
            )

        return _row_to_registration(row)


@router.patch("/business-registrations/{company_id}", response_model=BusinessRegistrationResponse, dependencies=[Depends(require_admin)])
async def update_business_registration(
    company_id: UUID,
    request: UpdateBusinessRegistrationRequest,
):
    """Update business registration company and owner details."""
    payload = request.model_dump(exclude_unset=True)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one field must be provided",
        )

    def _clean_optional_text(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    async with get_connection() as conn:
        async with conn.transaction():
            owner_row = await conn.fetchrow(
                """
                SELECT comp.id, comp.owner_id
                FROM companies comp
                WHERE comp.id = $1 AND comp.owner_id IS NOT NULL
                """,
                company_id,
            )
            if not owner_row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Business registration not found",
                )

            owner_id = owner_row["owner_id"]

            if "company_name" in payload:
                company_name = (request.company_name or "").strip()
                if not company_name:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Company name cannot be empty",
                    )
                await conn.execute(
                    "UPDATE companies SET name = $1 WHERE id = $2",
                    company_name,
                    company_id,
                )

            if "industry" in payload:
                await conn.execute(
                    "UPDATE companies SET industry = $1 WHERE id = $2",
                    _clean_optional_text(request.industry),
                    company_id,
                )

            if "company_size" in payload:
                await conn.execute(
                    "UPDATE companies SET size = $1 WHERE id = $2",
                    _clean_optional_text(request.company_size),
                    company_id,
                )

            if "owner_email" in payload:
                owner_email = str(request.owner_email).strip().lower() if request.owner_email else ""
                if not owner_email:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Owner email cannot be empty",
                    )

                existing_user_id = await conn.fetchval(
                    "SELECT id FROM users WHERE lower(email) = lower($1) AND id <> $2",
                    owner_email,
                    owner_id,
                )
                if existing_user_id:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Another user already uses this email",
                    )

                await conn.execute(
                    "UPDATE users SET email = $1 WHERE id = $2",
                    owner_email,
                    owner_id,
                )

            client_fields: list[str] = []
            client_params: list[Any] = []
            idx = 1

            if "owner_name" in payload:
                owner_name = (request.owner_name or "").strip()
                if not owner_name:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Owner name cannot be empty",
                    )
                client_fields.append(f"name = ${idx}")
                client_params.append(owner_name)
                idx += 1

            if "owner_phone" in payload:
                client_fields.append(f"phone = ${idx}")
                client_params.append(_clean_optional_text(request.owner_phone))
                idx += 1

            if "owner_job_title" in payload:
                client_fields.append(f"job_title = ${idx}")
                client_params.append(_clean_optional_text(request.owner_job_title))
                idx += 1

            if client_fields:
                client_params.extend([owner_id, company_id])
                result = await conn.execute(
                    f"""
                    UPDATE clients
                    SET {", ".join(client_fields)}
                    WHERE user_id = ${idx} AND company_id = ${idx + 1}
                    """,
                    *client_params,
                )
                if result == "UPDATE 0":
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Business owner profile not found for this company",
                    )

        row = await conn.fetchrow(
            """
            SELECT
                comp.id,
                comp.name as company_name,
                comp.industry,
                comp.size as company_size,
                u.email as owner_email,
                c.name as owner_name,
                c.phone as owner_phone,
                c.job_title as owner_job_title,
                comp.status,
                comp.rejection_reason,
                comp.approved_at,
                approver.email as approved_by_email,
                comp.created_at
            FROM companies comp
            JOIN users u ON u.id = comp.owner_id
            JOIN clients c ON c.user_id = comp.owner_id AND c.company_id = comp.id
            LEFT JOIN users approver ON comp.approved_by = approver.id
            WHERE comp.id = $1 AND comp.owner_id IS NOT NULL
            """,
            company_id,
        )

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Business registration not found",
            )

        from app.matcha.services.matcha_work_document import invalidate_company_profile_cache
        invalidate_company_profile_cache(company_id)

        return BusinessRegistrationResponse(
            id=row["id"],
            company_name=row["company_name"],
            industry=row["industry"],
            company_size=row["company_size"],
            owner_email=row["owner_email"],
            owner_name=row["owner_name"],
            owner_phone=row["owner_phone"],
            owner_job_title=row["owner_job_title"],
            status=row["status"] or "approved",
            rejection_reason=row["rejection_reason"],
            approved_at=row["approved_at"],
            approved_by_email=row["approved_by_email"],
            created_at=row["created_at"],
        )


@router.post("/business-registrations/{company_id}/approve", dependencies=[Depends(require_admin)])
async def approve_business_registration(
    company_id: UUID,
    current_user=Depends(require_admin)
):
    """Approve a pending business registration."""
    async with get_connection() as conn:
        # Get company and owner info
        company = await conn.fetchrow(
            """
            SELECT comp.id, comp.name, comp.status, u.email, c.name as owner_name
            FROM companies comp
            JOIN clients c ON c.company_id = comp.id
            JOIN users u ON c.user_id = u.id
            WHERE comp.id = $1
            """,
            company_id
        )

        if not company:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Business registration not found"
            )

        if company["status"] == "approved":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Business is already approved"
            )

        # Approve the company
        await conn.execute(
            """
            UPDATE companies
            SET status = 'approved', approved_at = NOW(), approved_by = $1
            WHERE id = $2
            """,
            current_user.id, company_id
        )

        # Send approval email
        email_service = get_email_service()
        await email_service.send_business_approved_email(
            to_email=company["email"],
            to_name=company["owner_name"],
            company_name=company["name"]
        )

        return {"status": "approved", "message": f"Business '{company['name']}' has been approved"}


@router.post("/business-registrations/{company_id}/reject", dependencies=[Depends(require_admin)])
async def reject_business_registration(
    company_id: UUID,
    request: RejectRequest,
    current_user=Depends(require_admin)
):
    """Reject a pending business registration with a reason."""
    if not request.reason or not request.reason.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Rejection reason is required"
        )

    async with get_connection() as conn:
        # Get company and owner info
        company = await conn.fetchrow(
            """
            SELECT comp.id, comp.name, comp.status, u.email, c.name as owner_name
            FROM companies comp
            JOIN clients c ON c.company_id = comp.id
            JOIN users u ON c.user_id = u.id
            WHERE comp.id = $1
            """,
            company_id
        )

        if not company:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Business registration not found"
            )

        if company["status"] == "rejected":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Business is already rejected"
            )

        # Reject the company
        await conn.execute(
            """
            UPDATE companies
            SET status = 'rejected', rejection_reason = $1, approved_by = $2
            WHERE id = $3
            """,
            request.reason.strip(), current_user.id, company_id
        )

        # Send rejection email
        email_service = get_email_service()
        await email_service.send_business_rejected_email(
            to_email=company["email"],
            to_name=company["owner_name"],
            company_name=company["name"],
            reason=request.reason.strip()
        )

        return {"status": "rejected", "message": f"Business '{company['name']}' has been rejected"}


@router.post("/business-invites", dependencies=[Depends(require_admin)])
async def create_business_invite(
    request: CreateBusinessInviteRequest = CreateBusinessInviteRequest(),
    current_user=Depends(require_admin),
):
    """Generate a new business invite link. Businesses registering with this link are auto-approved."""
    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(days=request.expires_days)

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO business_invitations (token, created_by, expires_at, note)
            VALUES ($1, $2, $3, $4)
            RETURNING id, token, status, expires_at, created_at
            """,
            token, current_user.id, expires_at, request.note,
        )

        base_url = get_settings().app_base_url.rstrip("/")
        invite_url = f"{base_url}/register/invite/{token}"

        return {
            "id": str(row["id"]),
            "token": row["token"],
            "invite_url": invite_url,
            "status": row["status"],
            "note": request.note,
            "expires_at": row["expires_at"].isoformat(),
            "created_at": row["created_at"].isoformat(),
        }


@router.get("/business-invites", dependencies=[Depends(require_admin)])
async def list_business_invites():
    """List all business invite links."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT
                bi.id, bi.token, bi.status, bi.note,
                bi.expires_at, bi.used_at, bi.created_at,
                u.email as created_by_email,
                c.name as used_by_company_name
            FROM business_invitations bi
            JOIN users u ON bi.created_by = u.id
            LEFT JOIN companies c ON bi.used_by_company_id = c.id
            ORDER BY bi.created_at DESC
            """
        )

        invites = []
        for row in rows:
            # Auto-expire if past expiry
            row_status = row["status"]
            if row_status == "pending" and row["expires_at"] < datetime.utcnow():
                row_status = "expired"

            invites.append({
                "id": str(row["id"]),
                "token": row["token"],
                "invite_url": f"{get_settings().app_base_url.rstrip('/')}/register/invite/{row['token']}",
                "status": row_status,
                "note": row["note"],
                "created_by_email": row["created_by_email"],
                "used_by_company_name": row["used_by_company_name"],
                "expires_at": row["expires_at"].isoformat(),
                "used_at": row["used_at"].isoformat() if row["used_at"] else None,
                "created_at": row["created_at"].isoformat(),
            })

        return {"invites": invites, "total": len(invites)}


@router.delete("/business-invites/{invite_id}", dependencies=[Depends(require_admin)])
async def cancel_business_invite(invite_id: UUID):
    """Cancel a pending business invite link."""
    async with get_connection() as conn:
        result = await conn.execute(
            "UPDATE business_invitations SET status = 'cancelled' WHERE id = $1 AND status = 'pending'",
            invite_id,
        )
        rows_affected = int(result.split()[-1])

        if rows_affected == 0:
            row = await conn.fetchrow(
                "SELECT status FROM business_invitations WHERE id = $1",
                invite_id,
            )
            if not row:
                raise HTTPException(status_code=404, detail="Invite not found")
            raise HTTPException(status_code=400, detail=f"Cannot cancel invite with status '{row['status']}'")

        return {"status": "cancelled", "message": "Invite link has been cancelled"}


@router.post("/beta-invitations")
async def send_beta_invitations(
    body: BetaInviteRequest,
    current_user=Depends(require_admin),
):
    """Send private beta invitations for Matcha Work."""
    from app.config import get_settings
    settings = get_settings()
    base_url = settings.app_base_url.rstrip("/")

    email_svc = get_email_service()
    sent = 0
    skipped: list[str] = []

    async with get_connection() as conn:
        for email in body.emails:
            email_lower = email.lower().strip()
            # Skip if already invited (pending) or already registered
            existing = await conn.fetchrow(
                "SELECT status FROM beta_invitations WHERE email = $1 AND status IN ('pending', 'registered') LIMIT 1",
                email_lower,
            )
            if existing:
                skipped.append(email_lower)
                continue

            token = secrets.token_hex(32)
            await conn.execute(
                """INSERT INTO beta_invitations (email, token, invited_by)
                   VALUES ($1, $2, $3)""",
                email_lower, token, current_user.id,
            )

            invite_url = f"{base_url}/register/beta?token={token}"
            html = f"""
            <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 480px; margin: 0 auto; padding: 32px 0;">
                <h2 style="color: #e4e4e7; font-size: 20px; margin-bottom: 8px;">You're invited to Matcha Work</h2>
                <p style="color: #a1a1aa; font-size: 14px; line-height: 1.6; margin-bottom: 24px;">
                    You've been selected for the private beta of Matcha Work — an AI-powered workspace
                    for HR, compliance, and recruiting professionals.
                </p>
                <a href="{invite_url}"
                   style="display: inline-block; background: #10b981; color: white; padding: 12px 28px;
                          border-radius: 8px; text-decoration: none; font-size: 14px; font-weight: 600;">
                    Create Your Account
                </a>
                <p style="color: #71717a; font-size: 12px; margin-top: 24px;">
                    This invitation is for <strong>{email_lower}</strong> and can only be used once.
                </p>
            </div>
            """
            try:
                if email_svc.is_configured():
                    await email_svc.send_email(
                        to_email=email_lower,
                        to_name=email_lower.split("@")[0],
                        subject="You're invited to Matcha Work (Private Beta)",
                        html_content=html,
                    )
            except Exception as e:
                logger.warning(f"Failed to send beta invite to {email_lower}: {e}")
                # Remove the invite row so admin can retry
                await conn.execute("DELETE FROM beta_invitations WHERE token = $1", token)
                skipped.append(email_lower)
                continue

            sent += 1

    return {"sent": sent, "skipped": skipped}


@router.post("/individual-invites")
async def create_individual_invite(
    body: IndividualInviteRequest,
    current_user=Depends(require_admin),
):
    """Generate a matcha-work individual signup URL without sending email.

    Creates a beta_invitation row and returns the invite URL for the admin
    to copy and share manually. The invited user registers at /register/beta
    which provisions a personal workspace (auth.py register_individual flow).
    """
    from app.config import get_settings
    settings = get_settings()
    base_url = settings.app_base_url.rstrip("/")

    email_lower = body.email.lower().strip()

    async with get_connection() as conn:
        existing = await conn.fetchrow(
            "SELECT id, token, status FROM beta_invitations WHERE email = $1 AND status IN ('pending', 'registered') LIMIT 1",
            email_lower,
        )
        if existing:
            if existing["status"] == "registered":
                raise HTTPException(status_code=409, detail="Already registered")
            # Reuse the pending invite
            return {
                "email": email_lower,
                "invite_url": f"{base_url}/register/beta?token={existing['token']}",
                "reused": True,
            }

        token = secrets.token_hex(32)
        await conn.execute(
            """INSERT INTO beta_invitations (email, token, invited_by)
               VALUES ($1, $2, $3)""",
            email_lower, token, current_user.id,
        )

    return {
        "email": email_lower,
        "invite_url": f"{base_url}/register/beta?token={token}",
        "reused": False,
    }


@router.get("/beta-invitations")
async def list_beta_invitations(current_user=Depends(require_admin)):
    """List all beta invitations."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT id, email, status, created_at, registered_at
               FROM beta_invitations
               ORDER BY created_at DESC
               LIMIT 200"""
        )
    return [
        {
            "id": str(r["id"]),
            "email": r["email"],
            "status": r["status"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "registered_at": r["registered_at"].isoformat() if r["registered_at"] else None,
        }
        for r in rows
    ]


@router.delete("/beta-invitations/{invite_id}")
async def revoke_beta_invitation(invite_id: UUID, current_user=Depends(require_admin)):
    """Revoke a pending beta invitation."""
    async with get_connection() as conn:
        deleted = await conn.execute(
            "DELETE FROM beta_invitations WHERE id = $1 AND status = 'pending'",
            invite_id,
        )
    if deleted == "DELETE 0":
        raise HTTPException(status_code=404, detail="Invitation not found or already used")
    return {"ok": True}
