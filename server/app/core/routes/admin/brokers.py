"""Admin brokers routes (J5 split)."""
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


@router.post("/brokers", dependencies=[Depends(require_admin)])
async def create_broker(
    request: BrokerCreateRequest,
    current_user=Depends(require_admin),
):
    """Create a broker org, owner user, owner membership, and initial active contract."""
    _validate_broker_enums(
        support_routing=request.support_routing,
        billing_mode=request.billing_mode,
        invoice_owner=request.invoice_owner,
    )

    slug_base = _slugify_broker_name(request.slug or request.broker_name)
    generated_password = not bool(request.owner_password and request.owner_password.strip())
    owner_password = request.owner_password.strip() if request.owner_password else secrets.token_urlsafe(12)

    async with get_connection() as conn:
        async with conn.transaction():
            existing = await conn.fetchval("SELECT id FROM users WHERE email = $1", request.owner_email)
            if existing:
                raise HTTPException(status_code=400, detail="Owner email is already registered")

            slug = slug_base
            suffix = 2
            while await conn.fetchval("SELECT EXISTS(SELECT 1 FROM brokers WHERE slug = $1)", slug):
                slug = f"{slug_base}-{suffix}"
                suffix += 1

            user = await conn.fetchrow(
                """
                INSERT INTO users (email, password_hash, role)
                VALUES ($1, $2, 'broker')
                RETURNING id, email, role, created_at
                """,
                request.owner_email,
                hash_password(owner_password),
            )

            broker = await conn.fetchrow(
                """
                INSERT INTO brokers (
                    name, slug, status, support_routing, billing_mode, invoice_owner,
                    terms_required_version, allocated_seats, plan, created_by
                )
                VALUES ($1, $2, 'active', $3, $4, $5, $6, $7, $8, $9)
                RETURNING id, name, slug, status, support_routing, billing_mode, invoice_owner, terms_required_version, allocated_seats, plan, created_at
                """,
                request.broker_name.strip(),
                slug,
                request.support_routing,
                request.billing_mode,
                request.invoice_owner,
                request.terms_required_version.strip(),
                request.allocated_seats,
                request.plan,
                current_user.id,
            )

            await conn.execute(
                """
                INSERT INTO broker_members (broker_id, user_id, role, permissions, is_active)
                VALUES ($1, $2, 'owner', $3::jsonb, true)
                """,
                broker["id"],
                user["id"],
                json.dumps({"can_manage_team": True, "can_manage_contracts": True, "can_manage_clients": True}),
            )

            contract = await conn.fetchrow(
                """
                INSERT INTO broker_contracts (
                    broker_id, status, billing_mode, invoice_owner, currency,
                    base_platform_fee, pepm_rate, minimum_monthly_commit,
                    pricing_rules, effective_at, created_by
                )
                VALUES ($1, 'active', $2, $3, 'USD', 0, 0, 0, '{}'::jsonb, NOW(), $4)
                RETURNING id
                """,
                broker["id"],
                request.billing_mode,
                request.invoice_owner,
                current_user.id,
            )

            await conn.execute(
                """
                INSERT INTO broker_branding_configs (
                    broker_id, branding_mode, brand_display_name, created_by, updated_by
                )
                VALUES ($1, 'direct', $2, $3, $3)
                ON CONFLICT (broker_id) DO NOTHING
                """,
                broker["id"],
                request.broker_name.strip(),
                current_user.id,
            )

    email_sent = False
    try:
        email_service = get_email_service()
        email_sent = await email_service.send_broker_welcome_email(
            to_email=request.owner_email,
            to_name=request.owner_name,
            broker_name=request.broker_name.strip(),
            broker_slug=slug,
            password=owner_password,
        )
    except Exception as e:
        logger.error("Failed to send broker welcome email to %s: %s", request.owner_email, e)

    return {
        "status": "created",
        "broker": {
            "id": str(broker["id"]),
            "name": broker["name"],
            "slug": broker["slug"],
            "status": broker["status"],
            "support_routing": broker["support_routing"],
            "billing_mode": broker["billing_mode"],
            "invoice_owner": broker["invoice_owner"],
            "terms_required_version": broker["terms_required_version"],
            "allocated_seats": broker["allocated_seats"],
            "plan": broker["plan"],
            "created_at": broker["created_at"].isoformat() if broker["created_at"] else None,
        },
        "owner": {
            "user_id": str(user["id"]),
            "email": user["email"],
            "name": request.owner_name,
            "generated_password": generated_password,
            "password": owner_password,
            "email_sent": email_sent,
        },
        "contract_id": str(contract["id"]),
    }


@router.get("/brokers", dependencies=[Depends(require_admin)])
async def list_brokers():
    """List brokers with contract, member, and linked-company counts."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT
                b.id, b.name, b.slug, b.status, b.support_routing, b.billing_mode,
                b.invoice_owner, b.terms_required_version, b.allocated_seats, b.plan, b.created_at,
                COALESCE(bb.branding_mode, 'direct') as branding_mode,
                COUNT(DISTINCT bm.user_id) FILTER (WHERE bm.is_active = true) AS active_member_count,
                COUNT(DISTINCT bcl.company_id) FILTER (WHERE bcl.status IN ('active', 'grace')) AS active_company_count,
                COALESCE((
                    SELECT SUM(t.seat_count)
                    FROM broker_lite_referral_tokens t
                    LEFT JOIN broker_company_links l
                      ON l.broker_id = t.broker_id AND l.company_id = t.redeemed_company_id
                    WHERE t.broker_id = b.id
                      AND t.intended_company_name IS NOT NULL
                      AND (
                        (t.redeemed_company_id IS NULL AND t.is_active = true)
                        OR (t.redeemed_company_id IS NOT NULL
                            AND COALESCE(l.status, 'active') NOT IN ('terminated', 'transferred'))
                      )
                ), 0) AS seats_used,
                bc.id AS active_contract_id,
                bc.currency,
                bc.base_platform_fee,
                bc.pepm_rate,
                bc.minimum_monthly_commit
            FROM brokers b
            LEFT JOIN broker_branding_configs bb ON bb.broker_id = b.id
            LEFT JOIN broker_members bm ON bm.broker_id = b.id
            LEFT JOIN broker_company_links bcl ON bcl.broker_id = b.id
            LEFT JOIN LATERAL (
                SELECT id, currency, base_platform_fee, pepm_rate, minimum_monthly_commit
                FROM broker_contracts
                WHERE broker_id = b.id AND status = 'active'
                ORDER BY effective_at DESC
                LIMIT 1
            ) bc ON true
            GROUP BY
                b.id, b.name, b.slug, b.status, b.support_routing, b.billing_mode,
                b.invoice_owner, b.terms_required_version, b.allocated_seats, b.plan, b.created_at, bb.branding_mode,
                bc.id, bc.currency, bc.base_platform_fee, bc.pepm_rate, bc.minimum_monthly_commit
            ORDER BY b.created_at DESC
            """
        )

        return {
            "brokers": [
                {
                    "id": str(row["id"]),
                    "name": row["name"],
                    "slug": row["slug"],
                    "status": row["status"],
                    "support_routing": row["support_routing"],
                    "billing_mode": row["billing_mode"],
                    "invoice_owner": row["invoice_owner"],
                    "terms_required_version": row["terms_required_version"],
                    "allocated_seats": row["allocated_seats"],
                    "plan": row["plan"],
                    "seats_used": int(row["seats_used"] or 0),
                    "branding_mode": row["branding_mode"],
                    "active_member_count": row["active_member_count"],
                    "active_company_count": row["active_company_count"],
                    "active_contract": {
                        "id": str(row["active_contract_id"]) if row["active_contract_id"] else None,
                        "currency": row["currency"],
                        "base_platform_fee": float(row["base_platform_fee"]) if row["base_platform_fee"] is not None else None,
                        "pepm_rate": float(row["pepm_rate"]) if row["pepm_rate"] is not None else None,
                        "minimum_monthly_commit": float(row["minimum_monthly_commit"]) if row["minimum_monthly_commit"] is not None else None,
                    },
                    "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                }
                for row in rows
            ],
            "total": len(rows),
        }


@router.patch("/brokers/{broker_id}", dependencies=[Depends(require_admin)])
async def update_broker(broker_id: UUID, request: BrokerUpdateRequest):
    """Update broker governance fields (status, routing, terms, lifecycle controls)."""
    _validate_broker_enums(
        status_value=request.status,
        support_routing=request.support_routing,
        post_termination_mode=request.post_termination_mode,
    )

    updates = []
    values: list = []
    if request.status is not None:
        updates.append(f"status = ${len(values) + 1}")
        values.append(request.status)
    if request.support_routing is not None:
        updates.append(f"support_routing = ${len(values) + 1}")
        values.append(request.support_routing)
    if request.terms_required_version is not None:
        updates.append(f"terms_required_version = ${len(values) + 1}")
        values.append(request.terms_required_version.strip())
    if request.terminated_at is not None:
        updates.append(f"terminated_at = ${len(values) + 1}")
        values.append(request.terminated_at)
    if request.grace_until is not None:
        updates.append(f"grace_until = ${len(values) + 1}")
        values.append(request.grace_until)
    if request.post_termination_mode is not None:
        updates.append(f"post_termination_mode = ${len(values) + 1}")
        values.append(request.post_termination_mode)
    if request.allocated_seats is not None:
        updates.append(f"allocated_seats = ${len(values) + 1}")
        values.append(request.allocated_seats)
    if request.plan is not None:
        updates.append(f"plan = ${len(values) + 1}")
        values.append(request.plan)

    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided for update")

    updates.append("updated_at = NOW()")
    values.append(broker_id)

    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"""
            UPDATE brokers
            SET {', '.join(updates)}
            WHERE id = ${len(values)}
            RETURNING id, name, slug, status, support_routing, billing_mode, invoice_owner, terms_required_version,
                     allocated_seats, plan, terminated_at, grace_until, post_termination_mode, updated_at
            """,
            *values,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Broker not found")

    return {
        "status": "updated",
        "broker": {
            "id": str(row["id"]),
            "name": row["name"],
            "slug": row["slug"],
            "status": row["status"],
            "support_routing": row["support_routing"],
            "billing_mode": row["billing_mode"],
            "invoice_owner": row["invoice_owner"],
            "terms_required_version": row["terms_required_version"],
            "allocated_seats": row["allocated_seats"],
            "plan": row["plan"],
            "terminated_at": row["terminated_at"].isoformat() if row["terminated_at"] else None,
            "grace_until": row["grace_until"].isoformat() if row["grace_until"] else None,
            "post_termination_mode": row["post_termination_mode"],
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        },
    }


@router.put("/brokers/{broker_id}/contract", dependencies=[Depends(require_admin)])
async def upsert_broker_contract(
    broker_id: UUID,
    request: BrokerContractRequest,
    current_user=Depends(require_admin),
):
    """Create a new broker contract version and optionally replace active contract."""
    _validate_broker_enums(
        contract_status=request.status,
        billing_mode=request.billing_mode,
        invoice_owner=request.invoice_owner,
    )
    currency = request.currency.upper().strip()
    if len(currency) != 3:
        raise HTTPException(status_code=400, detail="Currency must be a 3-letter ISO code")

    async with get_connection() as conn:
        async with conn.transaction():
            exists = await conn.fetchval("SELECT EXISTS(SELECT 1 FROM brokers WHERE id = $1)", broker_id)
            if not exists:
                raise HTTPException(status_code=404, detail="Broker not found")

            if request.status == "active":
                await conn.execute(
                    """
                    UPDATE broker_contracts
                    SET status = 'suspended', updated_at = NOW()
                    WHERE broker_id = $1 AND status = 'active'
                    """,
                    broker_id,
                )

            contract = await conn.fetchrow(
                """
                INSERT INTO broker_contracts (
                    broker_id, status, billing_mode, invoice_owner, currency,
                    base_platform_fee, pepm_rate, minimum_monthly_commit,
                    pricing_rules, effective_at, created_by
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, NOW(), $10)
                RETURNING id, broker_id, status, billing_mode, invoice_owner, currency,
                          base_platform_fee, pepm_rate, minimum_monthly_commit, pricing_rules, effective_at, created_at
                """,
                broker_id,
                request.status,
                request.billing_mode,
                request.invoice_owner,
                currency,
                request.base_platform_fee,
                request.pepm_rate,
                request.minimum_monthly_commit,
                json.dumps(request.pricing_rules or {}),
                current_user.id,
            )

            await conn.execute(
                """
                UPDATE brokers
                SET billing_mode = $1, invoice_owner = $2, updated_at = NOW()
                WHERE id = $3
                """,
                request.billing_mode,
                request.invoice_owner,
                broker_id,
            )

    return {
        "status": "saved",
        "contract": {
            "id": str(contract["id"]),
            "broker_id": str(contract["broker_id"]),
            "status": contract["status"],
            "billing_mode": contract["billing_mode"],
            "invoice_owner": contract["invoice_owner"],
            "currency": contract["currency"],
            "base_platform_fee": float(contract["base_platform_fee"]),
            "pepm_rate": float(contract["pepm_rate"]),
            "minimum_monthly_commit": float(contract["minimum_monthly_commit"]),
            "pricing_rules": contract["pricing_rules"] if isinstance(contract["pricing_rules"], dict) else {},
            "effective_at": contract["effective_at"].isoformat() if contract["effective_at"] else None,
            "created_at": contract["created_at"].isoformat() if contract["created_at"] else None,
        },
    }


@router.put("/brokers/{broker_id}/companies/{company_id}", dependencies=[Depends(require_admin)])
async def upsert_broker_company_link(
    broker_id: UUID,
    company_id: UUID,
    request: BrokerCompanyLinkRequest,
    current_user=Depends(require_admin),
):
    """Create/update broker-to-company linkage and delegated permissions."""
    _validate_broker_enums(link_status=request.status, post_termination_mode=request.post_termination_mode)

    async with get_connection() as conn:
        async with conn.transaction():
            broker_exists = await conn.fetchval("SELECT EXISTS(SELECT 1 FROM brokers WHERE id = $1)", broker_id)
            if not broker_exists:
                raise HTTPException(status_code=404, detail="Broker not found")

            company_exists = await conn.fetchval("SELECT EXISTS(SELECT 1 FROM companies WHERE id = $1)", company_id)
            if not company_exists:
                raise HTTPException(status_code=404, detail="Company not found")

            row = await conn.fetchrow(
                """
                INSERT INTO broker_company_links (
                    broker_id, company_id, status, permissions, linked_at, activated_at,
                    grace_until, post_termination_mode, created_by, updated_at
                )
                VALUES (
                    $1, $2, $3, $4::jsonb, NOW(),
                    CASE WHEN $3 IN ('active', 'grace') THEN NOW() ELSE NULL END,
                    $5, $6, $7, NOW()
                )
                ON CONFLICT (broker_id, company_id)
                DO UPDATE SET
                    status = EXCLUDED.status,
                    permissions = EXCLUDED.permissions,
                    activated_at = CASE
                        WHEN broker_company_links.activated_at IS NULL
                             AND EXCLUDED.status IN ('active', 'grace') THEN NOW()
                        ELSE broker_company_links.activated_at
                    END,
                    grace_until = EXCLUDED.grace_until,
                    post_termination_mode = EXCLUDED.post_termination_mode,
                    updated_at = NOW()
                RETURNING id, broker_id, company_id, status, permissions, linked_at, activated_at, terminated_at,
                          grace_until, post_termination_mode, updated_at
                """,
                broker_id,
                company_id,
                request.status,
                json.dumps(request.permissions or {}),
                request.grace_until,
                request.post_termination_mode,
                current_user.id,
            )

    return {
        "status": "linked",
        "link": {
            "id": str(row["id"]),
            "broker_id": str(row["broker_id"]),
            "company_id": str(row["company_id"]),
            "status": row["status"],
            "permissions": row["permissions"] if isinstance(row["permissions"], dict) else {},
            "linked_at": row["linked_at"].isoformat() if row["linked_at"] else None,
            "activated_at": row["activated_at"].isoformat() if row["activated_at"] else None,
            "terminated_at": row["terminated_at"].isoformat() if row["terminated_at"] else None,
            "grace_until": row["grace_until"].isoformat() if row["grace_until"] else None,
            "post_termination_mode": row["post_termination_mode"],
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        },
    }


@router.get("/brokers/{broker_id}/client-setups", dependencies=[Depends(require_admin)])
async def get_broker_client_setups_admin(broker_id: UUID):
    """Get all client setups submitted by a broker (admin view)."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT s.id, s.status, s.contact_name, s.contact_email, s.contact_phone,
                   s.headcount_hint, s.notes, s.locations, s.onboarding_template,
                   s.preconfigured_features, s.created_at, s.updated_at,
                   c.name as company_name, c.industry, c.size as company_size,
                   c.status as company_status
            FROM broker_client_setups s
            JOIN companies c ON c.id = s.company_id
            WHERE s.broker_id = $1
            ORDER BY s.created_at DESC
            """,
            broker_id,
        )
    import json as _json
    setups = []
    for r in rows:
        locs = r.get("locations")
        if isinstance(locs, str):
            try: locs = _json.loads(locs)
            except Exception: locs = []
        template = r.get("onboarding_template")
        if isinstance(template, str):
            try: template = _json.loads(template)
            except Exception: template = {}
        setups.append({
            "id": str(r["id"]),
            "company_name": r["company_name"],
            "company_status": r.get("company_status"),
            "industry": r.get("industry"),
            "company_size": r.get("company_size"),
            "status": r["status"],
            "contact_name": r.get("contact_name"),
            "contact_email": r.get("contact_email"),
            "contact_phone": r.get("contact_phone"),
            "headcount": r.get("headcount_hint"),
            "notes": r.get("notes"),
            "locations": locs if isinstance(locs, list) else [],
            "specialties": (template or {}).get("specialties"),
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
        })
    return {"setups": setups, "total": len(setups)}


@router.get("/brokers/{broker_id}/branding", dependencies=[Depends(require_admin)])
async def get_broker_branding(broker_id: UUID):
    """Get broker white-label/co-brand branding configuration."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                b.id as broker_id,
                b.name as broker_name,
                b.slug as broker_slug,
                b.support_routing,
                cfg.id,
                COALESCE(cfg.branding_mode, 'direct') as branding_mode,
                COALESCE(cfg.brand_display_name, b.name) as brand_display_name,
                cfg.brand_legal_name,
                cfg.logo_url,
                cfg.favicon_url,
                cfg.primary_color,
                cfg.secondary_color,
                cfg.login_subdomain,
                cfg.custom_login_url,
                cfg.support_email,
                cfg.support_phone,
                cfg.support_url,
                cfg.email_from_name,
                cfg.email_from_address,
                COALESCE(cfg.powered_by_badge, true) as powered_by_badge,
                COALESCE(cfg.hide_matcha_identity, false) as hide_matcha_identity,
                COALESCE(cfg.mobile_branding_enabled, false) as mobile_branding_enabled,
                COALESCE(cfg.theme, '{}'::jsonb) as theme,
                cfg.created_at,
                cfg.updated_at
            FROM brokers b
            LEFT JOIN broker_branding_configs cfg ON cfg.broker_id = b.id
            WHERE b.id = $1
            """,
            broker_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Broker not found")

    return {
        "broker_id": str(row["broker_id"]),
        "broker_name": row["broker_name"],
        "broker_slug": row["broker_slug"],
        "support_routing": row["support_routing"],
        "branding_mode": row["branding_mode"],
        "brand_display_name": row["brand_display_name"],
        "brand_legal_name": row["brand_legal_name"],
        "logo_url": row["logo_url"],
        "favicon_url": row["favicon_url"],
        "primary_color": row["primary_color"],
        "secondary_color": row["secondary_color"],
        "login_subdomain": row["login_subdomain"],
        "custom_login_url": row["custom_login_url"],
        "support_email": row["support_email"],
        "support_phone": row["support_phone"],
        "support_url": row["support_url"],
        "email_from_name": row["email_from_name"],
        "email_from_address": row["email_from_address"],
        "powered_by_badge": row["powered_by_badge"],
        "hide_matcha_identity": row["hide_matcha_identity"],
        "mobile_branding_enabled": row["mobile_branding_enabled"],
        "theme": row["theme"] if isinstance(row["theme"], dict) else {},
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


@router.put("/brokers/{broker_id}/branding", dependencies=[Depends(require_admin)])
async def upsert_broker_branding(
    broker_id: UUID,
    request: BrokerBrandingRequest,
    current_user=Depends(require_admin),
):
    """Upsert broker branding/runtime config for co-branded or white-label delivery."""
    _validate_broker_enums(branding_mode=request.branding_mode)
    if request.login_subdomain and not re.fullmatch(r"[a-z0-9-]{2,120}", request.login_subdomain):
        raise HTTPException(status_code=400, detail="login_subdomain must be 2-120 chars [a-z0-9-]")
    if request.custom_login_url and not request.custom_login_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="custom_login_url must start with http:// or https://")

    async with get_connection() as conn:
        broker = await conn.fetchrow("SELECT id, name, slug, support_routing FROM brokers WHERE id = $1", broker_id)
        if not broker:
            raise HTTPException(status_code=404, detail="Broker not found")

        row = await conn.fetchrow(
            """
            INSERT INTO broker_branding_configs (
                broker_id, branding_mode, brand_display_name, brand_legal_name, logo_url, favicon_url,
                primary_color, secondary_color, login_subdomain, custom_login_url,
                support_email, support_phone, support_url,
                email_from_name, email_from_address,
                powered_by_badge, hide_matcha_identity, mobile_branding_enabled,
                theme, metadata, created_by, updated_by, updated_at
            )
            VALUES (
                $1, $2, $3, $4, $5, $6,
                $7, $8, $9, $10,
                $11, $12, $13,
                $14, $15,
                $16, $17, $18,
                $19::jsonb, $20::jsonb, $21, $21, NOW()
            )
            ON CONFLICT (broker_id)
            DO UPDATE SET
                branding_mode = EXCLUDED.branding_mode,
                brand_display_name = EXCLUDED.brand_display_name,
                brand_legal_name = EXCLUDED.brand_legal_name,
                logo_url = EXCLUDED.logo_url,
                favicon_url = EXCLUDED.favicon_url,
                primary_color = EXCLUDED.primary_color,
                secondary_color = EXCLUDED.secondary_color,
                login_subdomain = EXCLUDED.login_subdomain,
                custom_login_url = EXCLUDED.custom_login_url,
                support_email = EXCLUDED.support_email,
                support_phone = EXCLUDED.support_phone,
                support_url = EXCLUDED.support_url,
                email_from_name = EXCLUDED.email_from_name,
                email_from_address = EXCLUDED.email_from_address,
                powered_by_badge = EXCLUDED.powered_by_badge,
                hide_matcha_identity = EXCLUDED.hide_matcha_identity,
                mobile_branding_enabled = EXCLUDED.mobile_branding_enabled,
                theme = EXCLUDED.theme,
                metadata = EXCLUDED.metadata,
                updated_by = EXCLUDED.updated_by,
                updated_at = NOW()
            RETURNING *
            """,
            broker_id,
            request.branding_mode,
            request.brand_display_name,
            request.brand_legal_name,
            request.logo_url,
            request.favicon_url,
            request.primary_color,
            request.secondary_color,
            request.login_subdomain,
            request.custom_login_url,
            request.support_email,
            request.support_phone,
            request.support_url,
            request.email_from_name,
            request.email_from_address,
            request.powered_by_badge,
            request.hide_matcha_identity,
            request.mobile_branding_enabled,
            json.dumps(request.theme or {}),
            json.dumps(request.metadata or {}),
            current_user.id,
        )

    return {
        "status": "saved",
        "branding": {
            "id": str(row["id"]),
            "broker_id": str(row["broker_id"]),
            "branding_mode": row["branding_mode"],
            "brand_display_name": row["brand_display_name"],
            "brand_legal_name": row["brand_legal_name"],
            "logo_url": row["logo_url"],
            "favicon_url": row["favicon_url"],
            "primary_color": row["primary_color"],
            "secondary_color": row["secondary_color"],
            "login_subdomain": row["login_subdomain"],
            "custom_login_url": row["custom_login_url"],
            "support_email": row["support_email"],
            "support_phone": row["support_phone"],
            "support_url": row["support_url"],
            "email_from_name": row["email_from_name"],
            "email_from_address": row["email_from_address"],
            "powered_by_badge": row["powered_by_badge"],
            "hide_matcha_identity": row["hide_matcha_identity"],
            "mobile_branding_enabled": row["mobile_branding_enabled"],
            "theme": row["theme"] if isinstance(row["theme"], dict) else {},
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        },
    }


@router.get("/brokers/{broker_id}/companies/{company_id}/transitions", dependencies=[Depends(require_admin)])
async def list_broker_company_transitions(broker_id: UUID, company_id: UUID):
    """List offboarding/transfer transitions for a broker-company relationship."""
    async with get_connection() as conn:
        exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM broker_company_links WHERE broker_id = $1 AND company_id = $2)",
            broker_id,
            company_id,
        )
        if not exists:
            raise HTTPException(status_code=404, detail="Broker-company link not found")

        rows = await conn.fetch(
            """
            SELECT
                t.id, t.mode, t.status, t.transfer_target_broker_id, tb.name as transfer_target_broker_name,
                t.grace_until, t.matcha_managed_until,
                t.data_handoff_status, t.data_handoff_notes,
                t.started_at, t.completed_at, t.metadata, t.created_at, t.updated_at
            FROM broker_company_transitions t
            LEFT JOIN brokers tb ON tb.id = t.transfer_target_broker_id
            WHERE t.broker_id = $1 AND t.company_id = $2
            ORDER BY t.created_at DESC
            """,
            broker_id,
            company_id,
        )

    return {
        "transitions": [
            {
                "id": str(row["id"]),
                "mode": row["mode"],
                "status": row["status"],
                "transfer_target_broker_id": str(row["transfer_target_broker_id"]) if row["transfer_target_broker_id"] else None,
                "transfer_target_broker_name": row["transfer_target_broker_name"],
                "grace_until": row["grace_until"].isoformat() if row["grace_until"] else None,
                "matcha_managed_until": row["matcha_managed_until"].isoformat() if row["matcha_managed_until"] else None,
                "data_handoff_status": row["data_handoff_status"],
                "data_handoff_notes": row["data_handoff_notes"],
                "started_at": row["started_at"].isoformat() if row["started_at"] else None,
                "completed_at": row["completed_at"].isoformat() if row["completed_at"] else None,
                "metadata": row["metadata"] if isinstance(row["metadata"], dict) else {},
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
            }
            for row in rows
        ],
        "total": len(rows),
    }


@router.post("/brokers/{broker_id}/companies/{company_id}/transitions", dependencies=[Depends(require_admin)])
async def create_broker_company_transition(
    broker_id: UUID,
    company_id: UUID,
    request: BrokerCompanyTransitionRequest,
    current_user=Depends(require_admin),
):
    """Create a broker-company transition (convert/transfer/sunset/matcha-managed)."""
    _validate_broker_enums(
        post_termination_mode=request.mode,
        transition_status=request.status,
        data_handoff_status=request.data_handoff_status,
    )
    if request.transfer_target_broker_id and request.mode != "transfer_to_broker":
        raise HTTPException(status_code=400, detail="transfer_target_broker_id is only valid for transfer_to_broker mode")
    if request.mode == "transfer_to_broker" and not request.transfer_target_broker_id:
        raise HTTPException(status_code=400, detail="transfer_target_broker_id is required for transfer_to_broker mode")
    if request.mode == "matcha_managed" and request.matcha_managed_until is None:
        raise HTTPException(status_code=400, detail="matcha_managed_until is required for matcha_managed mode")

    async with get_connection() as conn:
        async with conn.transaction():
            link = await conn.fetchrow(
                """
                SELECT id, status, metadata
                FROM broker_company_links
                WHERE broker_id = $1 AND company_id = $2
                FOR UPDATE
                """,
                broker_id,
                company_id,
            )
            if not link:
                raise HTTPException(status_code=404, detail="Broker-company link not found")

            active_transition = await conn.fetchval(
                """
                SELECT id
                FROM broker_company_transitions
                WHERE broker_id = $1
                  AND company_id = $2
                  AND status IN ('planned', 'in_progress')
                """,
                broker_id,
                company_id,
            )
            if active_transition:
                raise HTTPException(status_code=409, detail="An active transition already exists for this broker-company link")

            if request.transfer_target_broker_id:
                if request.transfer_target_broker_id == broker_id:
                    raise HTTPException(status_code=400, detail="transfer_target_broker_id must be different from broker_id")
                target_exists = await conn.fetchval(
                    "SELECT EXISTS(SELECT 1 FROM brokers WHERE id = $1)",
                    request.transfer_target_broker_id,
                )
                if not target_exists:
                    raise HTTPException(status_code=404, detail="Transfer target broker not found")

            data_handoff_status = request.data_handoff_status
            if request.mode == "sunset" and data_handoff_status == "pending":
                data_handoff_status = "not_required"
            _validate_broker_enums(data_handoff_status=data_handoff_status)

            started_at = datetime.utcnow() if request.status in {"in_progress", "completed"} else None
            completed_at = datetime.utcnow() if request.status == "completed" else None

            transition = await conn.fetchrow(
                """
                INSERT INTO broker_company_transitions (
                    broker_id, company_id, source_link_id, mode, status,
                    transfer_target_broker_id, grace_until, matcha_managed_until,
                    data_handoff_status, data_handoff_notes,
                    started_at, completed_at, metadata, created_by, updated_by, updated_at
                )
                VALUES (
                    $1, $2, $3, $4, $5,
                    $6, $7, $8,
                    $9, $10,
                    $11, $12, $13::jsonb, $14, $14, NOW()
                )
                RETURNING *
                """,
                broker_id,
                company_id,
                link["id"],
                request.mode,
                request.status,
                request.transfer_target_broker_id,
                request.grace_until,
                request.matcha_managed_until,
                data_handoff_status,
                request.data_handoff_notes,
                started_at,
                completed_at,
                json.dumps(request.metadata or {}),
                current_user.id,
            )

            transition_state = _transition_state_for(request.mode, request.status)
            next_link_status = _link_status_for(request.mode, request.status, link["status"])
            _validate_broker_enums(link_status=next_link_status, link_transition_state=transition_state)

            link_metadata_patch = {
                "transition_id": str(transition["id"]),
                "transition_mode": request.mode,
            }
            if request.transfer_target_broker_id:
                link_metadata_patch["transfer_target_broker_id"] = str(request.transfer_target_broker_id)
            if request.matcha_managed_until:
                link_metadata_patch["matcha_managed_until"] = request.matcha_managed_until.isoformat()

            terminated_at = (
                datetime.utcnow()
                if request.status == "completed" and request.mode in {"convert_to_direct", "transfer_to_broker", "sunset"}
                else None
            )
            post_termination_mode = request.mode if request.status != "cancelled" else None

            link_row = await conn.fetchrow(
                """
                UPDATE broker_company_links
                SET status = $3,
                    post_termination_mode = $4,
                    grace_until = COALESCE($5, broker_company_links.grace_until),
                    transition_state = $6,
                    transition_updated_at = NOW(),
                    data_handoff_status = $7,
                    data_handoff_notes = $8,
                    current_transition_id = $9,
                    terminated_at = CASE WHEN $10::timestamptz IS NOT NULL THEN $10 ELSE broker_company_links.terminated_at END,
                    metadata = COALESCE(broker_company_links.metadata, '{}'::jsonb) || $11::jsonb,
                    updated_at = NOW()
                WHERE broker_id = $1 AND company_id = $2
                RETURNING id, broker_id, company_id, status, transition_state, post_termination_mode, current_transition_id,
                          data_handoff_status, data_handoff_notes, grace_until, terminated_at, updated_at
                """,
                broker_id,
                company_id,
                next_link_status,
                post_termination_mode,
                request.grace_until,
                transition_state,
                data_handoff_status,
                request.data_handoff_notes,
                transition["id"],
                terminated_at,
                json.dumps(link_metadata_patch),
            )

    return {
        "status": "created",
        "transition": {
            "id": str(transition["id"]),
            "mode": transition["mode"],
            "status": transition["status"],
            "transfer_target_broker_id": str(transition["transfer_target_broker_id"]) if transition["transfer_target_broker_id"] else None,
            "grace_until": transition["grace_until"].isoformat() if transition["grace_until"] else None,
            "matcha_managed_until": transition["matcha_managed_until"].isoformat() if transition["matcha_managed_until"] else None,
            "data_handoff_status": transition["data_handoff_status"],
            "data_handoff_notes": transition["data_handoff_notes"],
            "started_at": transition["started_at"].isoformat() if transition["started_at"] else None,
            "completed_at": transition["completed_at"].isoformat() if transition["completed_at"] else None,
            "metadata": transition["metadata"] if isinstance(transition["metadata"], dict) else {},
            "created_at": transition["created_at"].isoformat() if transition["created_at"] else None,
            "updated_at": transition["updated_at"].isoformat() if transition["updated_at"] else None,
        },
        "link": {
            "id": str(link_row["id"]),
            "broker_id": str(link_row["broker_id"]),
            "company_id": str(link_row["company_id"]),
            "status": link_row["status"],
            "transition_state": link_row["transition_state"],
            "post_termination_mode": link_row["post_termination_mode"],
            "current_transition_id": str(link_row["current_transition_id"]) if link_row["current_transition_id"] else None,
            "data_handoff_status": link_row["data_handoff_status"],
            "data_handoff_notes": link_row["data_handoff_notes"],
            "grace_until": link_row["grace_until"].isoformat() if link_row["grace_until"] else None,
            "terminated_at": link_row["terminated_at"].isoformat() if link_row["terminated_at"] else None,
            "updated_at": link_row["updated_at"].isoformat() if link_row["updated_at"] else None,
        },
    }


@router.patch("/brokers/{broker_id}/companies/{company_id}/transitions/{transition_id}", dependencies=[Depends(require_admin)])
async def update_broker_company_transition(
    broker_id: UUID,
    company_id: UUID,
    transition_id: UUID,
    request: BrokerCompanyTransitionUpdateRequest,
    current_user=Depends(require_admin),
):
    """Update transition status, handoff progress, or completion markers."""
    _validate_broker_enums(
        transition_status=request.status,
        data_handoff_status=request.data_handoff_status,
    )

    async with get_connection() as conn:
        async with conn.transaction():
            transition = await conn.fetchrow(
                """
                SELECT *
                FROM broker_company_transitions
                WHERE id = $1 AND broker_id = $2 AND company_id = $3
                FOR UPDATE
                """,
                transition_id,
                broker_id,
                company_id,
            )
            if not transition:
                raise HTTPException(status_code=404, detail="Transition not found")

            link = await conn.fetchrow(
                """
                SELECT id, status
                FROM broker_company_links
                WHERE broker_id = $1 AND company_id = $2
                FOR UPDATE
                """,
                broker_id,
                company_id,
            )
            if not link:
                raise HTTPException(status_code=404, detail="Broker-company link not found")

            updated_status = request.status or transition["status"]
            updated_grace_until = request.grace_until if request.grace_until is not None else transition["grace_until"]
            updated_matcha_managed_until = (
                request.matcha_managed_until
                if request.matcha_managed_until is not None
                else transition["matcha_managed_until"]
            )
            updated_data_handoff_status = request.data_handoff_status or transition["data_handoff_status"]
            updated_data_handoff_notes = (
                request.data_handoff_notes
                if request.data_handoff_notes is not None
                else transition["data_handoff_notes"]
            )

            _validate_broker_enums(
                transition_status=updated_status,
                data_handoff_status=updated_data_handoff_status,
            )
            if transition["mode"] == "matcha_managed" and updated_matcha_managed_until is None:
                raise HTTPException(status_code=400, detail="matcha_managed_until is required for matcha_managed transitions")

            started_at = transition["started_at"]
            if updated_status in {"in_progress", "completed"} and started_at is None:
                started_at = datetime.utcnow()

            completed_at = transition["completed_at"]
            if updated_status == "completed":
                completed_at = request.completed_at or datetime.utcnow()
            elif request.completed_at is not None:
                completed_at = request.completed_at

            metadata_update = request.metadata if request.metadata is not None else {}
            transition_row = await conn.fetchrow(
                """
                UPDATE broker_company_transitions
                SET status = $1,
                    grace_until = $2,
                    matcha_managed_until = $3,
                    data_handoff_status = $4,
                    data_handoff_notes = $5,
                    started_at = $6,
                    completed_at = $7,
                    metadata = COALESCE(broker_company_transitions.metadata, '{}'::jsonb) || $8::jsonb,
                    updated_by = $9,
                    updated_at = NOW()
                WHERE id = $10
                RETURNING *
                """,
                updated_status,
                updated_grace_until,
                updated_matcha_managed_until,
                updated_data_handoff_status,
                updated_data_handoff_notes,
                started_at,
                completed_at,
                json.dumps(metadata_update),
                current_user.id,
                transition_id,
            )

            transition_state = _transition_state_for(transition_row["mode"], transition_row["status"])
            next_link_status = _link_status_for(transition_row["mode"], transition_row["status"], link["status"])
            _validate_broker_enums(link_status=next_link_status, link_transition_state=transition_state)

            terminated_at = (
                datetime.utcnow()
                if transition_row["status"] == "completed" and transition_row["mode"] in {"convert_to_direct", "transfer_to_broker", "sunset"}
                else None
            )
            clear_terminated = transition_row["status"] == "cancelled"
            post_termination_mode = transition_row["mode"] if transition_row["status"] != "cancelled" else None
            current_transition_id = transition_row["id"] if transition_row["status"] != "cancelled" else None

            link_metadata_patch = {
                "transition_id": str(transition_row["id"]),
                "transition_mode": transition_row["mode"],
                "transition_status": transition_row["status"],
            }
            if transition_row["transfer_target_broker_id"]:
                link_metadata_patch["transfer_target_broker_id"] = str(transition_row["transfer_target_broker_id"])
            if transition_row["matcha_managed_until"]:
                link_metadata_patch["matcha_managed_until"] = transition_row["matcha_managed_until"].isoformat()

            link_row = await conn.fetchrow(
                """
                UPDATE broker_company_links
                SET status = $3,
                    post_termination_mode = $4,
                    grace_until = COALESCE($5, broker_company_links.grace_until),
                    transition_state = $6,
                    transition_updated_at = NOW(),
                    data_handoff_status = $7,
                    data_handoff_notes = $8,
                    current_transition_id = $9,
                    terminated_at = CASE
                        WHEN $10::timestamptz IS NOT NULL THEN $10
                        WHEN $11::boolean THEN NULL
                        ELSE broker_company_links.terminated_at
                    END,
                    metadata = COALESCE(broker_company_links.metadata, '{}'::jsonb) || $12::jsonb,
                    updated_at = NOW()
                WHERE broker_id = $1 AND company_id = $2
                RETURNING id, broker_id, company_id, status, transition_state, post_termination_mode, current_transition_id,
                          data_handoff_status, data_handoff_notes, grace_until, terminated_at, updated_at
                """,
                broker_id,
                company_id,
                next_link_status,
                post_termination_mode,
                transition_row["grace_until"],
                transition_state,
                transition_row["data_handoff_status"],
                transition_row["data_handoff_notes"],
                current_transition_id,
                terminated_at,
                clear_terminated,
                json.dumps(link_metadata_patch),
            )

    return {
        "status": "updated",
        "transition": {
            "id": str(transition_row["id"]),
            "mode": transition_row["mode"],
            "status": transition_row["status"],
            "transfer_target_broker_id": str(transition_row["transfer_target_broker_id"]) if transition_row["transfer_target_broker_id"] else None,
            "grace_until": transition_row["grace_until"].isoformat() if transition_row["grace_until"] else None,
            "matcha_managed_until": transition_row["matcha_managed_until"].isoformat() if transition_row["matcha_managed_until"] else None,
            "data_handoff_status": transition_row["data_handoff_status"],
            "data_handoff_notes": transition_row["data_handoff_notes"],
            "started_at": transition_row["started_at"].isoformat() if transition_row["started_at"] else None,
            "completed_at": transition_row["completed_at"].isoformat() if transition_row["completed_at"] else None,
            "metadata": transition_row["metadata"] if isinstance(transition_row["metadata"], dict) else {},
            "updated_at": transition_row["updated_at"].isoformat() if transition_row["updated_at"] else None,
        },
        "link": {
            "id": str(link_row["id"]),
            "broker_id": str(link_row["broker_id"]),
            "company_id": str(link_row["company_id"]),
            "status": link_row["status"],
            "transition_state": link_row["transition_state"],
            "post_termination_mode": link_row["post_termination_mode"],
            "current_transition_id": str(link_row["current_transition_id"]) if link_row["current_transition_id"] else None,
            "data_handoff_status": link_row["data_handoff_status"],
            "data_handoff_notes": link_row["data_handoff_notes"],
            "grace_until": link_row["grace_until"].isoformat() if link_row["grace_until"] else None,
            "terminated_at": link_row["terminated_at"].isoformat() if link_row["terminated_at"] else None,
            "updated_at": link_row["updated_at"].isoformat() if link_row["updated_at"] else None,
        },
    }
