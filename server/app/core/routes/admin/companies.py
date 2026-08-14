"""Admin companies routes (J5 split)."""
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
from app.core.feature_flags import (
    ALL_FEATURES,
    BUILTIN_TIER_META,
    assert_feature_allowed,
    assert_feature_dependencies,
    feature_dependency_violations,
    merge_company_features,
)
from app.core.services.company_features import update_company_features
from app.core.services.feature_beta import load_beta_features, set_beta_status
from app.core.services.feature_provenance import (
    GRANT_TYPES,
    clear_grant,
    feature_provenance,
    load_active_packs,
    load_grants,
    record_feature_changes,
    resolve_addons,
    resolve_plan,
    set_grant,
)
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
from app.matcha.services.billing import billing_service as mw_billing_service
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


@router.get("/test-accounts", dependencies=[Depends(require_admin)])
async def list_test_accounts():
    """List every tenant designated safe for demo/beta use and dev/prod sync."""
    async with get_connection() as conn:
        if not await is_test_column_exists(conn):
            return {"test_accounts": []}
        rows = await conn.fetch(
            """
            SELECT comp.id, comp.name AS company_name, comp.industry, comp.size,
                   comp.status, comp.created_at, comp.signup_source,
                   COALESCE(owner.email, client_owner.email) AS owner_email,
                   COALESCE(client.name, client_owner.name) AS owner_name
            FROM companies comp
            LEFT JOIN users owner ON owner.id = comp.owner_id
            LEFT JOIN clients client ON client.company_id = comp.id AND client.user_id = comp.owner_id
            LEFT JOIN LATERAL (
                SELECT u.email, c.name
                FROM clients c
                JOIN users u ON u.id = c.user_id
                WHERE c.company_id = comp.id
                ORDER BY c.created_at NULLS LAST, c.id
                LIMIT 1
            ) AS client_owner ON true
            WHERE comp.is_test = true AND comp.deleted_at IS NULL
            ORDER BY comp.created_at DESC, comp.name
            """
        )
    return {
        "test_accounts": [
            {
                "id": str(row["id"]),
                "company_name": row["company_name"],
                "industry": row["industry"],
                "company_size": row["size"],
                "status": row["status"] or "approved",
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "signup_source": row["signup_source"],
                "owner_email": row["owner_email"],
                "owner_name": row["owner_name"],
            }
            for row in rows
        ]
    }


@router.get("/company-features", dependencies=[Depends(require_admin)])
async def list_company_features():
    """List all companies with their EFFECTIVE (not just stored) features.

    Bug fixed here: this previously called merge_company_features with no
    signup_source, and signup_source wasn't even selected — so a Matcha-X
    company's overlay-forced flags (training, discipline, handbook_audit,
    ...) rendered OFF here while being ON in the actual product. The tier
    overlay (TIER_REQUIRED_FEATURES) only ever applies when signup_source is
    passed in.
    """
    async with get_connection() as conn:
        is_test_col = "is_test" if await is_test_column_exists(conn) else "FALSE AS is_test"
        rows = await conn.fetch(
            f"""
            SELECT id, name as company_name, industry, size, status, enabled_features,
                   signup_source, {is_test_col}
            FROM companies
            ORDER BY name
            """
        )

        return [
            {
                "id": str(row["id"]),
                "company_name": row["company_name"],
                "industry": row["industry"],
                "size": row["size"],
                "status": row["status"] or "approved",
                "enabled_features": merge_company_features(row["enabled_features"], row["signup_source"]),
                "is_test": bool(row["is_test"]),
            }
            for row in rows
        ]


@router.get("/feature-flags", dependencies=[Depends(require_admin)])
async def list_feature_flags():
    """Beta/ready status per feature (code default + admin DB override —
    see feature_beta.load_beta_features), plus a remediation signal: which
    non-test companies already have a beta feature enabled. See
    feature_flags.py's "Beta gating" section and feature_beta.py.
    """
    async with get_connection() as conn:
        beta_features = await load_beta_features(conn)
        counts: dict[str, dict[str, Any]] = {}
        if beta_features:
            is_test_col = "is_test" if await is_test_column_exists(conn) else "FALSE AS is_test"
            rows = await conn.fetch(
                f"""
                SELECT id, name as company_name, enabled_features, signup_source, {is_test_col}
                FROM companies
                """
            )
            for row in rows:
                if bool(row["is_test"]):
                    continue
                merged = merge_company_features(row["enabled_features"], row["signup_source"])
                for key in beta_features:
                    if merged.get(key):
                        entry = counts.setdefault(key, {"count": 0, "companies": []})
                        entry["count"] += 1
                        entry["companies"].append(
                            {"id": str(row["id"]), "company_name": row["company_name"]}
                        )

        return [
            {
                "key": key,
                "is_beta": key in beta_features,
                "non_test_enabled_count": counts.get(key, {}).get("count", 0),
                "non_test_companies": counts.get(key, {}).get("companies", []),
            }
            for key in sorted(ALL_FEATURES)
        ]


class BetaStatusUpdate(BaseModel):
    is_beta: bool


@router.patch("/feature-flags/{feature_key}", dependencies=[Depends(require_admin)])
async def update_feature_beta_status(
    feature_key: str, body: BetaStatusUpdate, current_user=Depends(require_admin),
):
    """Move a feature from beta to ready, or back, without a deploy — writes
    an override row (feature_beta.set_beta_status); the code constant
    feature_flags.BETA_FEATURES is untouched and still applies to every key
    with no override row.
    """
    async with get_connection() as conn:
        try:
            await set_beta_status(conn, feature_key, body.is_beta, actor_user_id=current_user.id)
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {"key": feature_key, "is_beta": body.is_beta}


@router.patch("/company-features/{company_id}", dependencies=[Depends(require_admin)])
async def toggle_company_feature(
    company_id: UUID, request: FeatureToggleRequest, current_user=Depends(require_admin),
):
    """Toggle a single feature on/off for a company."""
    async with get_connection() as conn:
        try:
            result = await update_company_features(
                conn,
                company_id=company_id,
                updates={request.feature: request.enabled},
                actor_user_id=current_user.id,
                source="admin_toggle",
            )
        except LookupError:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return {"enabled_features": result.effective_features}


@router.get("/company-features/{company_id}/provenance", dependencies=[Depends(require_admin)])
async def company_feature_provenance(company_id: UUID):
    """What plan this company is on, its active add-ons, and per-feature
    provenance: which package/tier bundle, which purchased add-on, which
    custom product, or which admin/webhook write explains each currently-
    enabled feature. See feature_provenance.feature_provenance for the
    classification rules — `admin_grant` is the fallback bucket for a feature
    only an admin (or broker, at creation) could have turned on; `grants`
    below is where that gets classified as comped/invoiced/trial/internal.
    """
    async with get_connection() as conn:
        company_row = await conn.fetchrow(
            "SELECT id, enabled_features, signup_source FROM companies WHERE id = $1",
            company_id,
        )
        if company_row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")

        from app.core.services.product_definitions import SELECT_COLUMNS, row_to_product

        product_rows = await conn.fetch(f"SELECT {SELECT_COLUMNS} FROM product_definitions")
        products_by_slug = {r["slug"]: row_to_product(r) for r in product_rows}

        active_packs = await load_active_packs(conn, company_id)
        provenance = await feature_provenance(conn, company_row, products_by_slug, active_packs)
        plan = resolve_plan(company_row["signup_source"], products_by_slug)
        addons = resolve_addons(active_packs)
        grants = await load_grants(conn, company_id)

    return {
        "company_id": str(company_id),
        "plan": plan,
        "addons": addons,
        "features": provenance,
        "grants": grants,
        "grant_types": sorted(GRANT_TYPES),
    }


class GrantUpdate(BaseModel):
    grant_type: str
    note: Optional[str] = None


@router.put("/company-features/{company_id}/grants/{feature}", dependencies=[Depends(require_admin)])
async def put_company_feature_grant(
    company_id: UUID, feature: str, body: GrantUpdate, current_user=Depends(require_admin),
):
    """Classify WHY an admin-granted feature was given (comped / invoiced /
    trial / internal) + an optional note. Separate from provenance, which
    answers WHERE the flag came from — see feature_provenance.py.
    """
    async with get_connection() as conn:
        try:
            await set_grant(
                conn, company_id, feature, body.grant_type,
                note=body.note, actor_user_id=current_user.id,
            )
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {"feature": feature, "grant_type": body.grant_type, "note": body.note}


@router.delete("/company-features/{company_id}/grants/{feature}", dependencies=[Depends(require_admin)])
async def delete_company_feature_grant(company_id: UUID, feature: str):
    async with get_connection() as conn:
        await clear_grant(conn, company_id, feature)
    return {"ok": True}


@router.post("/companies/{company_id}/credits")
async def adjust_company_credits(
    company_id: UUID,
    request: CompanyCreditsAdjustRequest,
    current_user=Depends(require_admin),
):
    """Grant or adjust Matcha Work credits for a company."""
    result = await mw_billing_service.grant_credits(
        company_id=company_id,
        credits=int(request.credits),
        description=request.description,
        granted_by=current_user.id,
    )
    balance = result["balance"]
    transaction = result["transaction"]
    return {
        "company_id": str(company_id),
        "credits_remaining": balance["credits_remaining"],
        "total_credits_purchased": balance["total_credits_purchased"],
        "total_credits_granted": balance["total_credits_granted"],
        "transaction": {
            "id": str(transaction["id"]),
            "transaction_type": transaction["transaction_type"],
            "credits_delta": transaction["credits_delta"],
            "credits_after": transaction["credits_after"],
            "description": transaction["description"],
            "created_at": transaction["created_at"].isoformat() if transaction["created_at"] else None,
            "created_by": str(transaction["created_by"]) if transaction["created_by"] else None,
        },
    }


@router.get("/companies", dependencies=[Depends(require_admin)])
async def list_companies_admin():
    """List all companies with user counts."""
    async with get_connection() as conn:
        rows = await conn.fetch("""
            SELECT
                c.id, c.name, c.industry, c.healthcare_specialties,
                c.size, c.status, c.headquarters_state, c.headquarters_city,
                c.created_at,
                (SELECT COUNT(*) FROM employees e WHERE e.org_id = c.id AND e.termination_date IS NULL) AS user_count,
                (SELECT COUNT(*) FROM business_locations bl WHERE bl.company_id = c.id) AS location_count
            FROM companies c
            WHERE c.deleted_at IS NULL
            ORDER BY c.name
        """)
        return [
            {
                "id": str(r["id"]),
                "name": r["name"],
                "industry": r["industry"],
                "healthcare_specialties": list(r["healthcare_specialties"] or []),
                "size": r["size"],
                "status": r["status"] or "approved",
                "headquarters_state": r["headquarters_state"],
                "headquarters_city": r["headquarters_city"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "user_count": r["user_count"],
                "location_count": r["location_count"],
            }
            for r in rows
        ]


@router.get("/companies/{company_id}", dependencies=[Depends(require_admin)])
async def get_company_admin(company_id: UUID):
    """Get full company details including users."""
    async with get_connection() as conn:
        row = await conn.fetchrow("""
            SELECT id, name, industry, healthcare_specialties, size, status,
                   headquarters_state, headquarters_city, created_at, enabled_features
            FROM companies WHERE id = $1
        """, company_id)
        if not row:
            raise HTTPException(status_code=404, detail="Company not found")

        admins = await conn.fetch("""
            SELECT u.id, u.email, u.role, u.created_at, cl.name, cl.job_title
            FROM clients cl
            JOIN users u ON u.id = cl.user_id
            WHERE cl.company_id = $1
            ORDER BY u.created_at
        """, company_id)

        jurisdictions = await conn.fetch("""
            SELECT
                bl.state,
                array_agg(DISTINCT bl.city ORDER BY bl.city) AS cities,
                COUNT(DISTINCT e.id) AS employee_count
            FROM business_locations bl
            LEFT JOIN employees e ON e.org_id = bl.company_id
                AND e.work_state = bl.state
                AND e.termination_date IS NULL
            WHERE bl.company_id = $1
            GROUP BY bl.state
            ORDER BY bl.state
        """, company_id)

        employee_count = await conn.fetchval(
            "SELECT COUNT(*) FROM employees WHERE org_id = $1 AND termination_date IS NULL",
            company_id,
        )

        return {
            "id": str(row["id"]),
            "name": row["name"],
            "industry": row["industry"],
            "healthcare_specialties": list(row["healthcare_specialties"] or []),
            "size": row["size"],
            "status": row["status"] or "approved",
            "headquarters_state": row["headquarters_state"],
            "headquarters_city": row["headquarters_city"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "enabled_features": row["enabled_features"] or {},
            "employee_count": employee_count,
            "users": [
                {
                    "id": str(u["id"]),
                    "email": u["email"],
                    "name": u["name"],
                    "role": u["role"],
                    "job_title": u["job_title"],
                    "created_at": u["created_at"].isoformat() if u["created_at"] else None,
                }
                for u in admins
            ],
            "jurisdictions": [
                {
                    "state": j["state"],
                    "cities": list(j["cities"]),
                    "employee_count": j["employee_count"],
                }
                for j in jurisdictions
            ],
        }


@router.get("/companies/{company_id}/overview", dependencies=[Depends(require_admin)])
async def get_company_overview_admin(company_id: UUID):
    """Comprehensive company overview for admin detail page."""
    async with get_connection() as conn:
        company = await conn.fetchrow("""
            SELECT id, name, industry, healthcare_specialties, size, status,
                   headquarters_state, created_at, enabled_features
            FROM companies WHERE id = $1
        """, company_id)
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

        # Employees with department/job info
        employees = await conn.fetch("""
            SELECT id, email, first_name, last_name, department, job_title,
                   employment_type, work_state, start_date, termination_date
            FROM employees WHERE org_id = $1
            ORDER BY termination_date NULLS FIRST, first_name
        """, company_id)

        active_count = sum(1 for e in employees if e["termination_date"] is None)

        # Risk assessment snapshot
        risk_row = await conn.fetchrow("""
            SELECT overall_score, overall_band, computed_at
            FROM risk_assessment_snapshots WHERE company_id = $1
        """, company_id)

        # IR summary
        ir_rows = await conn.fetch("""
            SELECT severity, COUNT(*) AS cnt
            FROM ir_incidents
            WHERE company_id = $1 AND status IN ('reported','investigating','action_required')
            GROUP BY severity
        """, company_id)
        ir_map = {r["severity"]: r["cnt"] for r in ir_rows}
        ir_total = sum(ir_map.values())
        ir_recent = await conn.fetchval("""
            SELECT COUNT(*) FROM ir_incidents
            WHERE company_id = $1 AND created_at > NOW() - INTERVAL '30 days'
        """, company_id)

        # ER summary
        er_rows = await conn.fetch("""
            SELECT status, COUNT(*) AS cnt
            FROM er_cases WHERE company_id = $1 AND status NOT IN ('closed','resolved')
            GROUP BY status
        """, company_id)
        er_map = {r["status"]: r["cnt"] for r in er_rows}
        er_total = sum(er_map.values())

        # Compliance summary
        location_count = await conn.fetchval(
            "SELECT COUNT(*) FROM business_locations WHERE company_id = $1 AND is_active = true", company_id)
        req_count = await conn.fetchval("""
            SELECT COUNT(*) FROM compliance_requirements cr
            JOIN business_locations bl ON bl.id = cr.location_id
            WHERE bl.company_id = $1 AND bl.is_active = true
        """, company_id)
        critical_alerts = await conn.fetchval("""
            SELECT COUNT(*) FROM compliance_alerts
            WHERE company_id = $1 AND severity = 'critical' AND status != 'resolved'
        """, company_id)
        warning_alerts = await conn.fetchval("""
            SELECT COUNT(*) FROM compliance_alerts
            WHERE company_id = $1 AND severity = 'warning' AND status != 'resolved'
        """, company_id)

        # Policies
        active_policies = await conn.fetchval(
            "SELECT COUNT(*) FROM policies WHERE company_id = $1 AND status = 'active'", company_id)
        stale_policies = await conn.fetchval("""
            SELECT COUNT(*) FROM policies
            WHERE company_id = $1 AND status = 'active'
              AND updated_at < NOW() - INTERVAL '180 days'
        """, company_id)

        # Recent incidents for table
        recent_incidents = await conn.fetch("""
            SELECT id, incident_number, title, severity, status, created_at
            FROM ir_incidents WHERE company_id = $1
            ORDER BY created_at DESC LIMIT 10
        """, company_id)

        # Recent ER cases for table
        recent_er = await conn.fetch("""
            SELECT id, case_number, title, status, category, created_at
            FROM er_cases WHERE company_id = $1
            ORDER BY created_at DESC LIMIT 10
        """, company_id)

    return {
        "company": {
            "id": str(company["id"]),
            "name": company["name"],
            "industry": company["industry"],
            "healthcare_specialties": list(company["healthcare_specialties"] or []),
            "size": company["size"],
            "status": company["status"] or "approved",
            "headquarters_state": company["headquarters_state"],
            "created_at": company["created_at"].isoformat() if company["created_at"] else None,
            "enabled_features": company["enabled_features"] or {},
            "active_employee_count": active_count,
        },
        "employees": [
            {
                "id": str(e["id"]), "email": e["email"],
                "name": f"{e['first_name']} {e['last_name']}".strip(),
                "department": e["department"], "job_title": e["job_title"],
                "employment_type": e["employment_type"], "work_state": e["work_state"],
                "start_date": e["start_date"].isoformat() if e["start_date"] else None,
                "active": e["termination_date"] is None,
            }
            for e in employees
        ],
        "risk": {
            "overall_score": risk_row["overall_score"],
            "overall_band": risk_row["overall_band"],
            "computed_at": risk_row["computed_at"].isoformat() if risk_row["computed_at"] else None,
        } if risk_row else None,
        "ir_summary": {
            "total_open": ir_total,
            "critical": ir_map.get("critical", 0),
            "high": ir_map.get("high", 0),
            "medium": ir_map.get("medium", 0),
            "low": ir_map.get("low", 0),
            "recent_30_days": ir_recent or 0,
        },
        "er_summary": {
            "total_open": er_total,
            "open": er_map.get("open", 0),
            "in_review": er_map.get("in_review", 0),
            "pending_determination": er_map.get("pending_determination", 0),
        },
        "compliance": {
            "total_locations": location_count or 0,
            "total_requirements": req_count or 0,
            "critical_alerts": critical_alerts or 0,
            "warning_alerts": warning_alerts or 0,
        },
        "policies": {
            "total_active": active_policies or 0,
            "stale_count": stale_policies or 0,
        },
        "recent_incidents": [
            {
                "id": str(r["id"]), "incident_number": r["incident_number"],
                "title": r["title"], "severity": r["severity"],
                "status": r["status"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in recent_incidents
        ],
        "recent_er_cases": [
            {
                "id": str(r["id"]), "case_number": r["case_number"],
                "title": r["title"], "status": r["status"],
                "category": r["category"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in recent_er
        ],
    }


@router.get("/companies/{company_id}/employees", dependencies=[Depends(require_admin)])
async def get_company_employees_admin(company_id: UUID):
    """Lazy-load full employee list for a company."""
    async with get_connection() as conn:
        rows = await conn.fetch("""
            SELECT id, email, first_name, last_name, employment_type,
                   work_state, start_date, termination_date
            FROM employees
            WHERE org_id = $1
            ORDER BY termination_date NULLS FIRST, first_name, last_name
        """, company_id)
        return [
            {
                "id": str(r["id"]),
                "email": r["email"],
                "name": f"{r['first_name']} {r['last_name']}".strip(),
                "employment_type": r["employment_type"],
                "work_state": r["work_state"],
                "start_date": r["start_date"].isoformat() if r["start_date"] else None,
                "termination_date": r["termination_date"].isoformat() if r["termination_date"] else None,
                "active": r["termination_date"] is None,
            }
            for r in rows
        ]


@router.get("/employees/{employee_id}", dependencies=[Depends(require_admin)])
async def get_employee_admin(employee_id: UUID):
    """Get full employee profile including credentials."""
    async with get_connection() as conn:
        row = await conn.fetchrow("""
            SELECT
                e.id, e.org_id, e.email, e.personal_email, e.first_name, e.last_name,
                e.phone, e.address, e.job_title, e.department, e.employment_type,
                e.employment_status, e.pay_classification, e.pay_rate,
                e.work_state, e.work_city, e.start_date, e.termination_date,
                e.status_reason, e.emergency_contact, e.created_at,
                mgr.first_name || ' ' || mgr.last_name AS manager_name
            FROM employees e
            LEFT JOIN employees mgr ON mgr.id = e.manager_id
            WHERE e.id = $1
        """, employee_id)
        if not row:
            raise HTTPException(status_code=404, detail="Employee not found")

        creds = await conn.fetchrow("""
            SELECT license_type, license_number, license_state, license_expiration,
                   npi_number, dea_number, dea_expiration,
                   board_certification, board_certification_expiration,
                   clinical_specialty, oig_last_checked, oig_status,
                   malpractice_carrier, malpractice_policy_number, malpractice_expiration,
                   health_clearances
            FROM employee_credentials WHERE employee_id = $1
        """, employee_id)

        ec = dict(row["emergency_contact"] or {})
        creds_data = None
        if creds:
            dc = decrypt_credential_fields(dict(creds))
            creds_data = {
                "license_type": dc["license_type"],
                "license_number": dc["license_number"],
                "license_state": dc["license_state"],
                "license_expiration": creds["license_expiration"].isoformat() if creds["license_expiration"] else None,
                "npi_number": dc["npi_number"],
                "dea_number": dc["dea_number"],
                "dea_expiration": creds["dea_expiration"].isoformat() if creds["dea_expiration"] else None,
                "board_certification": dc["board_certification"],
                "board_certification_expiration": creds["board_certification_expiration"].isoformat() if creds["board_certification_expiration"] else None,
                "clinical_specialty": dc["clinical_specialty"],
                "oig_last_checked": creds["oig_last_checked"].isoformat() if creds["oig_last_checked"] else None,
                "oig_status": dc["oig_status"],
                "malpractice_carrier": dc["malpractice_carrier"],
                "malpractice_policy_number": dc["malpractice_policy_number"],
                "malpractice_expiration": creds["malpractice_expiration"].isoformat() if creds["malpractice_expiration"] else None,
                "health_clearances": creds["health_clearances"] or {},
            }
        result = {
            "id": str(row["id"]),
            "org_id": str(row["org_id"]),
            "email": row["email"],
            "personal_email": row["personal_email"],
            "first_name": row["first_name"],
            "last_name": row["last_name"],
            "phone": row["phone"],
            "address": row["address"],
            "job_title": row["job_title"],
            "department": row["department"],
            "employment_type": row["employment_type"],
            "employment_status": row["employment_status"],
            "pay_classification": row["pay_classification"],
            "pay_rate": str(row["pay_rate"]) if row["pay_rate"] else None,
            "work_state": row["work_state"],
            "work_city": row["work_city"],
            "start_date": row["start_date"].isoformat() if row["start_date"] else None,
            "termination_date": row["termination_date"].isoformat() if row["termination_date"] else None,
            "status_reason": row["status_reason"],
            "manager_name": row["manager_name"],
            "emergency_contact": ec,
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "credentials": creds_data,
        }
        return result


@router.patch("/companies/{company_id}", dependencies=[Depends(require_admin)])
async def update_company_admin(company_id: UUID, body: CompanyProfileUpdate, current_user=Depends(require_admin)):
    """Update company profile fields."""
    fields = body.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    set_clauses = []
    values = []
    for i, (key, val) in enumerate(fields.items(), start=1):
        set_clauses.append(f"{key} = ${i}")
        values.append(val)
    values.append(company_id)

    async with get_connection() as conn:
        # `is_test` opts a company out of PII anonymization (anonymize_dev.sql)
        # AND into unattended bidirectional writes to live prod on every
        # deploy (sync-test-tenants.sh --auto). Flipping it TRUE on a real,
        # currently-paying customer would silently do both. An active Stripe
        # subscription is the clean signal: bespoke/Pro contract customers
        # (invoiced, no mw_subscriptions row) and un-monetized demo companies
        # both pass through untouched.
        if fields.get("is_test") is True:
            has_active_sub = await conn.fetchval(
                "SELECT 1 FROM mw_subscriptions WHERE company_id = $1 AND status = 'active' LIMIT 1",
                company_id,
            )
            if has_active_sub:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot mark is_test=true: company has an active paid subscription. "
                           "Cancel the subscription first if this is genuinely a demo/test tenant.",
                )
        row = await conn.fetchrow(
            f"UPDATE companies SET {', '.join(set_clauses)} WHERE id = ${len(values)} RETURNING id",
            *values,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Company not found")
    if "is_test" in fields:
        logger.info(
            "Admin set companies.is_test: company=%s is_test=%s admin=%s",
            company_id, fields["is_test"], current_user.id,
        )
    from app.matcha.services.matcha_work.matcha_work_document import invalidate_company_profile_cache
    invalidate_company_profile_cache(company_id)
    return {"ok": True}


@router.delete("/companies/{company_id}", dependencies=[Depends(require_admin)])
async def delete_company_admin(company_id: UUID):
    """Soft-delete a company so it no longer appears in lists."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            "UPDATE companies SET deleted_at = NOW() WHERE id = $1 AND deleted_at IS NULL RETURNING id",
            company_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail="Company not found or already deleted")
        from app.matcha.services.matcha_work.matcha_work_document import invalidate_company_profile_cache
        invalidate_company_profile_cache(company_id)
    return {"ok": True}


@router.get("/companies/{company_id}/compliance")
async def admin_company_compliance(
    company_id: UUID,
    current_user=Depends(require_admin),
):
    """Company compliance overview: locations with requirement category counts."""
    async with get_connection() as conn:
        company = await conn.fetchrow(
            "SELECT id, name, industry FROM companies WHERE id = $1",
            company_id,
        )
        if not company:
            raise HTTPException(404, "Company not found")

    locations = await get_locations(company_id)

    # Batch category breakdown for all locations in one query
    loc_ids = [loc["id"] for loc in locations]
    cat_map: dict[str, dict[str, int]] = {str(lid): {} for lid in loc_ids}
    if loc_ids:
        async with get_connection() as conn:
            rows = await conn.fetch(
                "SELECT location_id, category, COUNT(*) AS cnt FROM compliance_requirements WHERE location_id = ANY($1) GROUP BY location_id, category",
                loc_ids,
            )
            for r in rows:
                cat_map.setdefault(str(r["location_id"]), {})[r["category"]] = r["cnt"]
    for loc in locations:
        loc["category_counts"] = cat_map.get(str(loc["id"]), {})

    return {
        "company": {"id": str(company["id"]), "name": company["name"], "industry": company["industry"]},
        "locations": locations,
    }


@router.get("/companies/{company_id}/locations/{location_id}/requirements")
async def admin_location_requirements(
    company_id: UUID,
    location_id: UUID,
    category: Optional[str] = Query(None),
    current_user=Depends(require_admin),
):
    """Full requirement list for a location, including governance_source."""
    reqs = await get_location_requirements(location_id, company_id, category)

    # Enrich with governance_source
    async with get_connection() as conn:
        gov_rows = await conn.fetch(
            "SELECT id, governance_source FROM compliance_requirements WHERE location_id = $1",
            location_id,
        )
        gov_map = {str(r["id"]): r["governance_source"] for r in gov_rows}

    enriched = []
    for r in reqs:
        d = r.dict() if hasattr(r, "dict") else r
        d["governance_source"] = gov_map.get(d["id"], "not_evaluated")
        enriched.append(d)

    return {"requirements": enriched}


@router.post("/companies/{company_id}/locations")
async def admin_create_location(
    company_id: UUID,
    data: LocationCreate,
    background_tasks: BackgroundTasks,
    current_user=Depends(require_admin),
):
    """Admin creates a location for a company, auto-syncs compliance requirements."""
    async with get_connection() as conn:
        exists = await conn.fetchval("SELECT 1 FROM companies WHERE id = $1", company_id)
        if not exists:
            raise HTTPException(404, "Company not found")

    location, has_coverage = await create_location(company_id, data)

    if not has_coverage:
        background_tasks.add_task(run_compliance_check_background, location["id"], company_id)

    return {"location": location, "has_coverage": has_coverage}


@router.post("/companies/{company_id}/locations/{location_id}/requirements")
async def admin_add_requirement(
    company_id: UUID,
    location_id: UUID,
    body: AdminAddRequirementRequest,
    current_user=Depends(require_admin),
):
    """Cherry-pick a jurisdiction requirement into a company location."""
    try:
        row = await admin_add_requirement_to_location(
            location_id, company_id, body.jurisdiction_requirement_id,
        )
        return {"requirement": row}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/companies/{company_id}/locations/{location_id}/requirements/{requirement_id}")
async def admin_remove_requirement(
    company_id: UUID,
    location_id: UUID,
    requirement_id: UUID,
    current_user=Depends(require_admin),
):
    """Remove an admin-added requirement from a location."""
    async with get_connection() as conn:
        deleted = await conn.fetchval(
            """
            DELETE FROM compliance_requirements
            WHERE id = $1 AND location_id = $2 AND governance_source = 'admin_override'
            RETURNING id
            """,
            requirement_id, location_id,
        )
    if not deleted:
        raise HTTPException(404, "Requirement not found or not admin-added")
    return {"deleted": True}


@router.get("/companies/{company_id}/locations/{location_id}/repository")
async def admin_browse_repository(
    company_id: UUID,
    location_id: UUID,
    current_user=Depends(require_admin),
):
    """Browse jurisdiction requirements not yet assigned to this location."""
    async with get_connection() as conn:
        jurisdiction_id = await conn.fetchval(
            "SELECT jurisdiction_id FROM business_locations WHERE id = $1 AND company_id = $2",
            location_id, company_id,
        )
        if not jurisdiction_id:
            raise HTTPException(404, "Location not found")

        rows = await conn.fetch(
            """
            SELECT jr.id, jr.category, jr.regulation_key, jr.jurisdiction_level,
                   jr.jurisdiction_name, jr.title, jr.description,
                   jr.current_value, jr.source_url, jr.effective_date
            FROM jurisdiction_requirements jr
            WHERE jr.jurisdiction_id = $1
              AND NOT EXISTS (
                  SELECT 1 FROM compliance_requirements cr
                  WHERE cr.location_id = $2
                    AND (
                      cr.jurisdiction_requirement_id = jr.id
                      OR cr.requirement_key = jr.category || ':' || COALESCE(jr.regulation_key, jr.title)
                    )
              )
            ORDER BY jr.category, jr.title
            """,
            jurisdiction_id, location_id,
        )

    return {"requirements": [dict(r) for r in rows]}


@router.patch("/companies/{company_id}/tier", dependencies=[Depends(require_admin)])
async def admin_change_tier(
    company_id: UUID, body: TierChangeBody, current_user=Depends(require_admin),
):
    """Switch a company's tier — rewrites signup_source + enabled_features.

    Tier mutation is destructive: features get stomped to the target tier's
    preset, so a Free → Lite move loses any one-off flags that were toggled
    individually.

    Stripe sub side-effects:
    - **Lite/X/Compliance → non-paid**: cancels the active Stripe subscription
      immediately. Otherwise the customer keeps getting charged for a tier
      they no longer have.
    - **non-paid → Lite/X/Compliance**: refused. Activating any of these
      requires a Stripe checkout (or a broker-pays/comped referral) so
      payment is established; admin should not bypass that. Use the
      customer's signup link.
    - **Bespoke ↔ IR Cap**: no Stripe coupling, just preset rewrite.
    """
    preset = _TIER_FEATURE_PRESETS.get(body.tier)
    if preset is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown tier '{body.tier}'. Valid: {', '.join(_TIER_FEATURE_PRESETS)}",
        )
    async with get_connection() as conn:
        is_test_col = "is_test" if await is_test_column_exists(conn) else "FALSE AS is_test"
        current = await conn.fetchrow(
            f"SELECT signup_source, enabled_features, {is_test_col} FROM companies WHERE id = $1",
            company_id,
        )
        if not current:
            raise HTTPException(status_code=404, detail="Company not found")
        current_tier = current["signup_source"]
        current_features = merge_company_features(current["enabled_features"])

        # A tier preset can grant a beta default-off flag (e.g. handbook_pilot,
        # labor_relations on 'bespoke') the same way the single-feature toggle
        # can — assert_feature_allowed is the gate for that path, so it must
        # run here too, not just in toggle_company_feature.
        beta_features = await load_beta_features(conn)
        for feature_key, value in preset.items():
            if value is not True:
                continue
            try:
                assert_feature_allowed(
                    feature_key, True,
                    beta_features=beta_features, company_row=current,
                )
            except ValueError as e:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

        # Same reasoning as the beta-gate loop just above: a tier preset can
        # in principle enable a flag that needs another one (none of the
        # built-in presets currently do — huume/werk_lite aren't in any tier
        # overlay — but this stays honest if that changes). Validate the
        # merged/effective shape, since that's what actually gates routes.
        try:
            assert_feature_dependencies(merge_company_features(preset, body.tier))
        except ValueError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

        # Paid tiers whose paid gate is established via Stripe checkout,
        # keyed to the flag name each one's webhook flips (incidents for
        # Lite/X, compliance for Compliance). Sourced from BUILTIN_TIER_META
        # so this list can't drift from what /admin/products shows.
        _stripe_gate_flag = {
            slug: meta["stripe_gate_flag"]
            for slug, meta in BUILTIN_TIER_META.items()
            if meta.get("stripe_gate_flag")
        }
        _stripe_gated = set(_stripe_gate_flag)

        # Refuse activating a paid tier's gate unless it's already on. Checked
        # against the actual flag, not just current_tier != body.tier — every
        # self-serve signup already has signup_source == its target tier
        # before payment completes (e.g. a pending matcha_compliance company
        # IS current_tier == "matcha_compliance" with compliance=False), so a
        # same-tier PATCH would otherwise skip this guard entirely and grant
        # the paid preset for free.
        if body.tier in _stripe_gated and not current_features.get(_stripe_gate_flag[body.tier]):
            _meta = BUILTIN_TIER_META.get(body.tier, {})
            _label = _meta.get("label", body.tier)
            _path = _meta.get("signup_path") or "/lite/signup"
            raise HTTPException(
                status_code=400,
                detail=f"Activating {_label} requires Stripe checkout. Send the customer to {_path} or use a broker referral token; admin cannot promote into a paid tier without payment.",
            )

        # Paid tier → anything else: cancel the active Stripe sub first. An
        # admin-composed product ('product:<slug>') is Stripe-billed the same
        # way, so moving one of those tenants off must also stop the sub —
        # otherwise the customer keeps paying for a tier they no longer have.
        from app.core.services.product_definitions import SIGNUP_SOURCE_PREFIX as _PRODUCT_PREFIX
        _leaving_paid = current_tier in _stripe_gated or (
            (current_tier or "").startswith(_PRODUCT_PREFIX)
        )
        if _leaving_paid and body.tier != current_tier:
            sub_row = await conn.fetchrow(
                """SELECT stripe_subscription_id
                     FROM mw_subscriptions
                    WHERE company_id = $1 AND status = 'active'
                    ORDER BY created_at DESC
                    LIMIT 1""",
                company_id,
            )
            if sub_row:
                stripe_service = StripeService()
                try:
                    await stripe_service.cancel_subscription(
                        sub_row["stripe_subscription_id"],
                        at_period_end=False,
                    )
                except StripeServiceError as exc:
                    raise HTTPException(
                        status_code=502,
                        detail=f"Cannot change tier: Stripe cancellation failed: {exc}",
                    )

        result = await conn.execute(
            """UPDATE companies
                  SET signup_source = $1,
                      enabled_features = $2::jsonb
                WHERE id = $3""",
            body.tier, json.dumps(preset), company_id,
        )
        if result != "UPDATE 0":
            await record_feature_changes(
                conn, company_id, current_features, preset,
                source="tier_change", actor_user_id=current_user.id,
            )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Company not found")
    logger.info(
        "Admin changed tier: company=%s from=%s to=%s",
        company_id, current_tier, body.tier,
    )
    return {"ok": True, "tier": body.tier, "previous_tier": current_tier}


@router.post("/companies/{company_id}/cancel-subscription", dependencies=[Depends(require_admin)])
async def admin_cancel_subscription(
    company_id: UUID,
    immediate: bool = Query(False, description="If true, end the sub now instead of at period end"),
):
    """Cancel the active mw_subscriptions row for a company via Stripe."""
    async with get_connection() as conn:
        sub_row = await conn.fetchrow(
            """SELECT stripe_subscription_id, status
                 FROM mw_subscriptions
                WHERE company_id = $1 AND status = 'active'
                ORDER BY created_at DESC
                LIMIT 1""",
            company_id,
        )
    if not sub_row:
        raise HTTPException(status_code=404, detail="No active subscription on this company")
    stripe_service = StripeService()
    try:
        await stripe_service.cancel_subscription(
            sub_row["stripe_subscription_id"],
            at_period_end=not immediate,
        )
    except StripeServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {"ok": True, "stripe_subscription_id": sub_row["stripe_subscription_id"], "immediate": immediate}


@router.get("/companies/{company_id}/charges", dependencies=[Depends(require_admin)])
async def admin_list_company_charges(company_id: UUID):
    """List recent Stripe charges for the company's customer (refund modal)."""
    async with get_connection() as conn:
        sub_row = await conn.fetchrow(
            """SELECT stripe_customer_id
                 FROM mw_subscriptions
                WHERE company_id = $1
                ORDER BY (status = 'active') DESC, created_at DESC
                LIMIT 1""",
            company_id,
        )
    if not sub_row:
        return {"charges": []}
    stripe_service = StripeService()
    try:
        charges = await stripe_service.list_charges(sub_row["stripe_customer_id"])
    except StripeServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return {
        "charges": [
            ChargeSummary(
                id=c["id"],
                amount=c["amount"],
                amount_refunded=c.get("amount_refunded", 0),
                currency=c["currency"],
                created=c["created"],
                status=c["status"],
                description=c.get("description"),
            ).model_dump()
            for c in charges.get("data", [])
        ]
    }


@router.post("/companies/{company_id}/refund", dependencies=[Depends(require_admin)])
async def admin_refund_charge(company_id: UUID, body: RefundBody):
    """Issue a (partial or full) Stripe refund for a charge belonging to this company."""
    # We don't enforce that charge_id belongs to the company at the DB level,
    # but the admin chose it from the company's listed charges so the linkage
    # is implicit. Stripe enforces ownership on the server side anyway.
    stripe_service = StripeService()
    try:
        refund = await stripe_service.create_refund(
            body.charge_id,
            amount_cents=body.amount_cents,
            reason=body.reason,
        )
    except StripeServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    logger.info(
        "Admin refunded charge=%s company=%s amount=%s reason=%s",
        body.charge_id, company_id, body.amount_cents, body.reason,
    )
    return {
        "ok": True,
        "refund_id": refund["id"],
        "amount": refund["amount"],
        "status": refund["status"],
    }


@router.delete("/companies/{company_id}", dependencies=[Depends(require_admin)])
async def admin_soft_delete_company(company_id: UUID):
    """Soft-delete a company. Sets deleted_at; rows stay for audit."""
    async with get_connection() as conn:
        result = await conn.execute(
            "UPDATE companies SET deleted_at = NOW() WHERE id = $1 AND deleted_at IS NULL",
            company_id,
        )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Company not found or already deleted")
    return {"ok": True}


@router.post("/companies/{company_id}/restore", dependencies=[Depends(require_admin)])
async def admin_restore_company(company_id: UUID):
    """Reverse a soft-delete."""
    async with get_connection() as conn:
        result = await conn.execute(
            "UPDATE companies SET deleted_at = NULL WHERE id = $1 AND deleted_at IS NOT NULL",
            company_id,
        )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Company not deleted")
    return {"ok": True}
