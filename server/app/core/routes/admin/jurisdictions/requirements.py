"""Admin jurisdictions routes — jurisdiction detail + requirement editing (split of jurisdictions.py). Jurisdiction detail lives here (not with detail_evals) purely to preserve original route-registration order."""
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



@router.get("/jurisdictions/{jurisdiction_id:uuid}", dependencies=[Depends(require_admin)])
async def get_jurisdiction_detail(jurisdiction_id: UUID):
    """Get full detail for a jurisdiction: requirements, legislation, linked locations."""
    redis = get_redis_cache()
    if redis:
        cached = await cache_get(redis, admin_jurisdiction_detail_key(jurisdiction_id))
        if cached is not None:
            return cached

    async with get_connection() as conn:
        j = await conn.fetchrow("SELECT * FROM jurisdictions WHERE id = $1", jurisdiction_id)
        if not j:
            raise HTTPException(status_code=404, detail="Jurisdiction not found")
        # Only validate city for city-level jurisdictions used in research
        # State/federal/county rows and detail lookups should always be viewable
        j_level = j["level"] if "level" in j.keys() else "city"

        # Fetch children
        children = await conn.fetch(
            "SELECT id, city, state FROM jurisdictions WHERE parent_id = $1 ORDER BY state, city",
            jurisdiction_id
        )

        requirements = await conn.fetch("""
            SELECT id, requirement_key, category, jurisdiction_level, jurisdiction_name,
                   applicable_industries,
                   title, description, current_value, numeric_value,
                   source_url, source_url_status, source_name, effective_date, expiration_date,
                   previous_value, previous_description, change_status,
                   last_changed_at, last_verified_at, is_bookmarked,
                   sort_order, created_at, updated_at
            FROM jurisdiction_requirements
            WHERE jurisdiction_id = $1
            ORDER BY category, sort_order, title
        """, jurisdiction_id)

        legislation = await conn.fetch("""
            SELECT id, legislation_key, category, title, description,
                   current_status, expected_effective_date, impact_summary,
                   source_url, source_name, confidence, last_verified_at, created_at, updated_at
            FROM jurisdiction_legislation
            WHERE jurisdiction_id = $1
            ORDER BY expected_effective_date ASC NULLS LAST, title
        """, jurisdiction_id)

        locations = await conn.fetch("""
            SELECT bl.id, bl.name, bl.city, bl.state, bl.company_id, c.name AS company_name,
                   bl.auto_check_enabled, bl.auto_check_interval_days,
                   bl.next_auto_check, bl.last_compliance_check
            FROM business_locations bl
            JOIN companies c ON c.id = bl.company_id
            WHERE bl.jurisdiction_id = $1 AND bl.is_active = true
            ORDER BY c.name, bl.name
        """, jurisdiction_id)

        def fmt_date(d):
            return d.isoformat() if d else None

        def fmt_decimal(v):
            return float(v) if v is not None else None

        result = {
            "id": str(j["id"]),
            "city": j["city"],
            "state": j["state"],
            "county": j["county"],
            "parent_id": str(j["parent_id"]) if j["parent_id"] else None,
            "children": [
                {"id": str(c["id"]), "city": c["city"], "state": c["state"]}
                for c in children
            ],
            "requirement_count": j["requirement_count"] or 0,
            "legislation_count": j["legislation_count"] or 0,
            "last_verified_at": fmt_date(j["last_verified_at"]),
            "created_at": fmt_date(j["created_at"]),
            "requirements": [
                {
                    "id": str(r["id"]),
                    "requirement_key": r["requirement_key"],
                    "category": r["category"],
                    "jurisdiction_level": r["jurisdiction_level"],
                    "jurisdiction_name": r["jurisdiction_name"],
                    "applicable_industries": list(r["applicable_industries"]) if r["applicable_industries"] else [],
                    "title": r["title"],
                    "description": r["description"],
                    "current_value": r["current_value"],
                    "numeric_value": fmt_decimal(r["numeric_value"]),
                    "source_url": r["source_url"],
                    "source_url_status": r["source_url_status"],
                    "source_name": r["source_name"],
                    "effective_date": fmt_date(r["effective_date"]),
                    "expiration_date": fmt_date(r["expiration_date"]),
                    "previous_value": r["previous_value"],
                    "previous_description": r["previous_description"],
                    "change_status": r["change_status"],
                    "last_changed_at": fmt_date(r["last_changed_at"]),
                    "last_verified_at": fmt_date(r["last_verified_at"]),
                    "is_bookmarked": r["is_bookmarked"],
                    "sort_order": r["sort_order"],
                    "updated_at": fmt_date(r["updated_at"]),
                }
                for r in requirements
            ],
            "legislation": [
                {
                    "id": str(l["id"]),
                    "legislation_key": l["legislation_key"],
                    "category": l["category"],
                    "title": l["title"],
                    "description": l["description"],
                    "current_status": l["current_status"],
                    "expected_effective_date": fmt_date(l["expected_effective_date"]),
                    "impact_summary": l["impact_summary"],
                    "source_url": l["source_url"],
                    "source_name": l["source_name"],
                    "confidence": fmt_decimal(l["confidence"]),
                    "last_verified_at": fmt_date(l["last_verified_at"]),
                    "updated_at": fmt_date(l["updated_at"]),
                }
                for l in legislation
            ],
            "locations": [
                {
                    "id": str(loc["id"]),
                    "name": loc["name"],
                    "city": loc["city"],
                    "state": loc["state"],
                    "company_name": loc["company_name"],
                    "auto_check_enabled": loc["auto_check_enabled"],
                    "auto_check_interval_days": loc["auto_check_interval_days"],
                    "next_auto_check": fmt_date(loc["next_auto_check"]),
                    "last_compliance_check": fmt_date(loc["last_compliance_check"]),
                }
                for loc in locations
            ],
        }

    if redis:
        await cache_set(redis, admin_jurisdiction_detail_key(jurisdiction_id), result, ttl=600)

    return result


@router.patch("/jurisdictions/requirements/{requirement_id}")
async def update_requirement(requirement_id: UUID, body: RequirementUpdate,
                             current_user=Depends(require_admin)):
    """Partially update a jurisdiction requirement (e.g. add applicability notes)."""
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")

    set_parts = []
    params: list[Any] = []
    for i, (col, val) in enumerate(updates.items(), start=1):
        set_parts.append(f"{col} = ${i}")
        params.append(val)

    # A hand-edited source_url invalidates the old liveness verdict — it was
    # about the previous URL. Reset to 'unchecked' until the next research pass.
    if "source_url" in updates:
        set_parts.append("source_url_status = 'unchecked'")
        set_parts.append("source_checked_at = NULL")

    # A hand-edited statute_citation is not registry-verified — only reconcile
    # (against a real authority_index_item) may stamp a citation as verified.
    if "statute_citation" in updates:
        set_parts.append("citation_verified_at = NULL")
        set_parts.append("citation_item_id = NULL")

    params.append(requirement_id)
    id_idx = len(params)

    sql = f"""
        UPDATE jurisdiction_requirements
        SET {', '.join(set_parts)}, updated_at = NOW()
        WHERE id = ${id_idx}
        RETURNING id, jurisdiction_id, requirement_key, category, jurisdiction_level, jurisdiction_name,
                  title, description, current_value, numeric_value,
                  source_url, source_url_status, source_name, effective_date, expiration_date,
                  statute_citation, citation_verified_at,
                  previous_value, last_changed_at, last_verified_at, is_bookmarked,
                  sort_order, created_at, updated_at
    """

    async with get_connection() as conn:
        # Label this write for the version-history trigger (jrver01).
        from app.core.services.change_context import set_change_context
        await set_change_context(conn, "admin_edit", getattr(current_user, "id", None))
        row = await conn.fetchrow(sql, *params)
        if not row:
            raise HTTPException(status_code=404, detail="Requirement not found")

    redis = get_redis_cache()
    if redis:
        await cache_delete(redis, admin_jurisdiction_detail_key(row["jurisdiction_id"]))
        await cache_delete(redis, admin_jurisdiction_policy_overview_key(row["category"]))
        await cache_delete(redis, admin_jurisdiction_policy_overview_key(None))

    def fmt_date(d):
        return d.isoformat() if d else None

    return {
        "id": str(row["id"]),
        "requirement_key": row["requirement_key"],
        "category": row["category"],
        "jurisdiction_level": row["jurisdiction_level"],
        "jurisdiction_name": row["jurisdiction_name"],
        "title": row["title"],
        "description": row["description"],
        "current_value": row["current_value"],
        "numeric_value": float(row["numeric_value"]) if row["numeric_value"] is not None else None,
        "source_url": row["source_url"],
        "source_url_status": row["source_url_status"],
        "source_name": row["source_name"],
        "statute_citation": row["statute_citation"],
        "citation_verified_at": fmt_date(row["citation_verified_at"]),
        "effective_date": fmt_date(row["effective_date"]),
        "expiration_date": fmt_date(row["expiration_date"]),
        "previous_value": row["previous_value"],
        "last_changed_at": fmt_date(row["last_changed_at"]),
        "last_verified_at": fmt_date(row["last_verified_at"]),
        "is_bookmarked": row["is_bookmarked"],
        "sort_order": row["sort_order"],
        "updated_at": fmt_date(row["updated_at"]),
    }


@router.post("/jurisdictions/requirements/{requirement_id}/resolve-review", dependencies=[Depends(require_admin)])
async def resolve_requirement_review(requirement_id: UUID):
    """Clear a drift-raised ``needs_review`` after an admin has re-checked the row
    against the (changed) authority: restore the pre-drift change_status, drop the
    metadata.drift breadcrumb, and re-stamp last_verified_at.

    Guarded on the ``drift`` breadcrumb so it is a true no-op on a row that was
    never drift-flagged: without it, a stray call (or a double-click after the
    breadcrumb is already gone) would force ``change_status='unchanged'`` and
    re-stamp ``last_verified_at``, silently wiping a real ``changed`` signal."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            UPDATE jurisdiction_requirements
            SET change_status = COALESCE(metadata->'drift'->>'prior_change_status', 'unchanged'),
                metadata = COALESCE(metadata, '{}'::jsonb) - 'drift',
                last_verified_at = NOW(),
                updated_at = NOW()
            WHERE id = $1 AND metadata ? 'drift'
            RETURNING id, jurisdiction_id, category, change_status
            """,
            requirement_id,
        )
        if not row:
            # Nothing to resolve. Distinguish a missing id (404) from an
            # already-resolved / never-flagged row (return current state, untouched).
            existing = await conn.fetchrow(
                "SELECT id, jurisdiction_id, category, change_status "
                "FROM jurisdiction_requirements WHERE id = $1",
                requirement_id,
            )
            if not existing:
                raise HTTPException(status_code=404, detail="Requirement not found")
            return {"id": str(existing["id"]), "change_status": existing["change_status"],
                    "resolved": False}

    redis = get_redis_cache()
    if redis:
        await cache_delete(redis, admin_jurisdiction_detail_key(row["jurisdiction_id"]))
        await cache_delete(redis, admin_jurisdiction_policy_overview_key(row["category"]))
        await cache_delete(redis, admin_jurisdiction_policy_overview_key(None))
        # The quality-audit surface (needs_review flag + verified/gemini counters)
        # is cached per param-combo under a hashed key — drop the whole namespace so
        # the just-resolved row doesn't read as still pending for up to the TTL.
        await cache_delete_pattern(redis, "admin:quality-audit:v2:")

    return {"id": str(row["id"]), "change_status": row["change_status"], "resolved": True}


@router.post("/jurisdictions/requirements/{requirement_id}/bookmark", dependencies=[Depends(require_admin)])
async def toggle_requirement_bookmark(requirement_id: UUID):
    """Toggle the is_bookmarked flag on a jurisdiction requirement."""
    async with get_connection() as conn:
        row = await conn.fetchrow("""
            UPDATE jurisdiction_requirements
            SET is_bookmarked = NOT is_bookmarked, updated_at = NOW()
            WHERE id = $1
            RETURNING id, is_bookmarked, jurisdiction_id
        """, requirement_id)
        if not row:
            raise HTTPException(status_code=404, detail="Requirement not found")

    redis = get_redis_cache()
    if redis:
        await cache_delete(redis, admin_bookmarked_requirements_key())
        await cache_delete(redis, admin_jurisdiction_detail_key(row["jurisdiction_id"]))

    return {"id": str(row["id"]), "is_bookmarked": row["is_bookmarked"]}


@router.get("/jurisdictions/requirements/bookmarked", dependencies=[Depends(require_admin)])
async def list_bookmarked_requirements():
    """List all bookmarked jurisdiction requirements across all cities."""
    redis = get_redis_cache()
    if redis:
        cached = await cache_get(redis, admin_bookmarked_requirements_key())
        if cached is not None:
            return cached

    async with get_connection() as conn:
        rows = await conn.fetch("""
            SELECT jr.id, jr.requirement_key, jr.category, jr.jurisdiction_level,
                   jr.jurisdiction_name, jr.title, jr.description, jr.current_value,
                   jr.numeric_value, jr.source_url, jr.source_url_status, jr.source_name,
                   jr.effective_date,
                   jr.expiration_date, jr.previous_value, jr.last_changed_at,
                   jr.last_verified_at, jr.is_bookmarked, jr.sort_order,
                   jr.created_at, jr.updated_at,
                   j.id AS jurisdiction_id, j.city, j.state
            FROM jurisdiction_requirements jr
            JOIN jurisdictions j ON j.id = jr.jurisdiction_id
            WHERE jr.is_bookmarked = true
            ORDER BY jr.updated_at DESC
        """)

    def fmt_date(d):
        return d.isoformat() if d else None

    result = [
        {
            "id": str(r["id"]),
            "jurisdiction_id": str(r["jurisdiction_id"]),
            "requirement_key": r["requirement_key"],
            "category": r["category"],
            "jurisdiction_level": r["jurisdiction_level"],
            "jurisdiction_name": r["jurisdiction_name"],
            "title": r["title"],
            "description": r["description"],
            "current_value": r["current_value"],
            "numeric_value": float(r["numeric_value"]) if r["numeric_value"] is not None else None,
            "source_url": r["source_url"],
            "source_url_status": r["source_url_status"],
            "source_name": r["source_name"],
            "effective_date": fmt_date(r["effective_date"]),
            "expiration_date": fmt_date(r["expiration_date"]),
            "previous_value": r["previous_value"],
            "last_changed_at": fmt_date(r["last_changed_at"]),
            "last_verified_at": fmt_date(r["last_verified_at"]),
            "is_bookmarked": r["is_bookmarked"],
            "sort_order": r["sort_order"],
            "updated_at": fmt_date(r["updated_at"]),
            "city": r["city"],
            "state": r["state"],
        }
        for r in rows
    ]

    if redis:
        await cache_set(redis, admin_bookmarked_requirements_key(), result, ttl=600)

    return result


@router.put("/jurisdictions/requirements/reorder", dependencies=[Depends(require_admin)])
async def reorder_requirements(body: dict[str, Any] = Body(...)):
    """Bulk-update sort_order for jurisdiction requirements."""
    order = body.get("order")
    if not order or not isinstance(order, list):
        raise HTTPException(status_code=400, detail="'order' must be a non-empty list")

    async with get_connection() as conn:
        async with conn.transaction():
            updated = 0
            for item in order:
                rid = item.get("id")
                sort_order = item.get("sort_order")
                if rid is None or sort_order is None:
                    continue
                result = await conn.execute(
                    "UPDATE jurisdiction_requirements SET sort_order = $1, updated_at = NOW() WHERE id = $2",
                    sort_order, UUID(rid),
                )
                if result and result.endswith("1"):
                    updated += 1
    return {"updated": updated}


