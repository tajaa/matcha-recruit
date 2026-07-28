"""Admin jurisdictions routes — quality audit, coverage matrix, integrity check (split of jurisdictions.py)."""
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



@router.get("/jurisdictions/quality-audit", dependencies=[Depends(require_admin)])
async def get_quality_audit(
    state: Optional[str] = None,
    jurisdiction_id: Optional[UUID] = None,
    category: Optional[str] = None,
    min_completeness: Optional[int] = None,
    max_completeness: Optional[int] = None,
    stale_only: bool = False,
    tier: Optional[str] = None,
    source: Optional[str] = None,
    citation: Optional[str] = None,
    needs_review: bool = False,
    limit: int = 200,
    offset: int = 0,
):
    """Data quality audit: requirements with completeness scores, staleness, and provenance.

    ``citation=verified|unverified`` filters on registry-verified statute
    citations; ``needs_review=true`` surfaces the drift-flagged re-verify queue.
    """
    import hashlib

    cache_key = "admin:quality-audit:v4:" + hashlib.md5(
        f"{state}:{jurisdiction_id}:{category}:{min_completeness}:{max_completeness}:{stale_only}:{tier}:{source}:{citation}:{needs_review}:{limit}:{offset}".encode()
    ).hexdigest()

    redis = get_redis_cache()
    if redis:
        cached = await cache_get(redis, cache_key)
        if cached is not None:
            return cached

    async with get_connection() as conn:
        # A citation is "registry-verified" only while its backing authority item
        # still exists: citation_item_id is nulled by ON DELETE SET NULL when the
        # item is deleted, so verified_at alone would render a phantom ✓ badge with
        # a dead statute-reader link. Kept as one predicate so the filter and the
        # summary counters below can never diverge.
        cite_verified_sql = codified_sql("jr")
        cite_unverified_sql = f"NOT ({cite_verified_sql})"

        # Base WHERE conditions for paginated results
        conditions = ["jr.status = 'active'"]
        params: List[Any] = []

        if state:
            params.append(state.upper())
            conditions.append(f"j.state = ${len(params)}")
        if jurisdiction_id:
            # The Codified tab's schema selects an AUTHORITY, and an authority is
            # a jurisdiction row — not a (level, state) pair, which cannot tell
            # US federal law from Mexico's (both would be "no state").
            params.append(jurisdiction_id)
            conditions.append(f"j.id = ${len(params)}")
        if category:
            params.append(category)
            conditions.append(f"jr.category = ${len(params)}")
        if tier:
            params.append(tier)
            conditions.append(f"jr.source_tier::text = ${len(params)}")
        if source:
            if source == "unknown":
                conditions.append("jr.metadata->>'research_source' IS NULL")
            else:
                params.append(source)
                conditions.append(f"jr.metadata->>'research_source' = ${len(params)}")
        if stale_only:
            conditions.append("(jr.last_verified_at IS NULL OR jr.last_verified_at < NOW() - INTERVAL '90 days')")
        if citation == "verified":
            conditions.append(cite_verified_sql)
        elif citation == "unverified":
            conditions.append(cite_unverified_sql)
        if needs_review:
            conditions.append("jr.change_status = 'needs_review'")

        where_clause = " AND ".join(conditions)

        # Summary query (no limit/offset)
        summary_sql = f"""
            SELECT
                COUNT(*) AS total,
                AVG(
                    CASE WHEN jr.title IS NOT NULL AND jr.title != '' THEN 25 ELSE 0 END +
                    CASE WHEN jr.description IS NOT NULL AND jr.description != '' THEN 30 ELSE 0 END +
                    CASE WHEN jr.source_url IS NOT NULL AND jr.source_url != '' THEN 20 ELSE 0 END +
                    CASE WHEN jr.effective_date IS NOT NULL THEN 15 ELSE 0 END +
                    CASE WHEN jr.current_value IS NOT NULL AND jr.current_value != '' THEN 10 ELSE 0 END
                )::int AS avg_completeness,
                COUNT(*) FILTER (WHERE jr.last_verified_at IS NULL OR jr.last_verified_at < NOW() - INTERVAL '90 days') AS stale_count,
                COUNT(*) FILTER (WHERE jr.source_url IS NULL OR jr.source_url = '') AS missing_source_url,
                COUNT(*) FILTER (WHERE jr.source_url_status = 'dead') AS dead_source_url,
                COUNT(*) FILTER (WHERE {cite_verified_sql}) AS verified_citation,
                COUNT(*) FILTER (WHERE {cite_unverified_sql}) AS unverified_citation,
                COUNT(*) FILTER (WHERE {cite_unverified_sql}
                                   AND jr.metadata->>'research_source' = 'gemini') AS gemini_unverified,
                COUNT(*) FILTER (WHERE jr.change_status = 'needs_review') AS needs_review
            FROM jurisdiction_requirements jr
            JOIN jurisdictions j ON j.id = jr.jurisdiction_id
            WHERE {where_clause}
        """
        summary_row = await conn.fetchrow(summary_sql, *params)

        tier_rows = await conn.fetch(f"""
            SELECT COALESCE(jr.source_tier::text, 'unknown') AS tier, COUNT(*) AS cnt
            FROM jurisdiction_requirements jr
            JOIN jurisdictions j ON j.id = jr.jurisdiction_id
            WHERE {where_clause}
            GROUP BY COALESCE(jr.source_tier::text, 'unknown')
        """, *params)

        provenance_rows = await conn.fetch(f"""
            SELECT COALESCE(jr.metadata->>'research_source', 'unknown') AS src, COUNT(*) AS cnt
            FROM jurisdiction_requirements jr
            JOIN jurisdictions j ON j.id = jr.jurisdiction_id
            WHERE {where_clause}
            GROUP BY COALESCE(jr.metadata->>'research_source', 'unknown')
        """, *params)

        # Completeness filter (applied after scoring, so we use a subquery)
        having_conditions: List[str] = []
        post_params = list(params)
        if min_completeness is not None:
            post_params.append(min_completeness)
            having_conditions.append(f"completeness_score >= ${len(post_params)}")
        if max_completeness is not None:
            post_params.append(max_completeness)
            having_conditions.append(f"completeness_score <= ${len(post_params)}")

        post_params.append(limit)
        limit_param = len(post_params)
        post_params.append(offset)
        offset_param = len(post_params)

        having_clause = f"WHERE {' AND '.join(having_conditions)}" if having_conditions else ""

        rows_sql = f"""
            SELECT *
            FROM (
                SELECT
                    jr.id, jr.jurisdiction_id, jr.category, jr.title, jr.description,
                    jr.source_url, jr.source_url_status,
                    jr.statute_citation, jr.citation_verified_at, jr.citation_item_id,
                    jr.change_status, jr.regulation_key,
                    jr.source_tier::text AS source_tier, jr.status::text AS status,
                    jr.current_value, jr.effective_date, jr.last_verified_at, jr.is_bookmarked,
                    jr.created_at, jr.updated_at, jr.metadata,
                    j.display_name AS jurisdiction_name, j.state, j.city,
                    (
                        CASE WHEN jr.title IS NOT NULL AND jr.title != '' THEN 25 ELSE 0 END +
                        CASE WHEN jr.description IS NOT NULL AND jr.description != '' THEN 30 ELSE 0 END +
                        CASE WHEN jr.source_url IS NOT NULL AND jr.source_url != '' THEN 20 ELSE 0 END +
                        CASE WHEN jr.effective_date IS NOT NULL THEN 15 ELSE 0 END +
                        CASE WHEN jr.current_value IS NOT NULL AND jr.current_value != '' THEN 10 ELSE 0 END
                    ) AS completeness_score,
                    EXTRACT(DAY FROM NOW() - jr.last_verified_at)::int AS staleness_days
                FROM jurisdiction_requirements jr
                JOIN jurisdictions j ON j.id = jr.jurisdiction_id
                WHERE {where_clause}
            ) scored
            {having_clause}
            ORDER BY completeness_score ASC, staleness_days DESC NULLS FIRST
            LIMIT ${limit_param} OFFSET ${offset_param}
        """
        rows = await conn.fetch(rows_sql, *post_params)

        def fmt(d):
            return d.isoformat() if d else None

        result = {
            "summary": {
                "total": summary_row["total"],
                "avg_completeness": summary_row["avg_completeness"] or 0,
                "stale_count": summary_row["stale_count"],
                "missing_source_url": summary_row["missing_source_url"],
                "dead_source_url": summary_row["dead_source_url"],
                "verified_citation": summary_row["verified_citation"],
                "unverified_citation": summary_row["unverified_citation"],
                "gemini_unverified": summary_row["gemini_unverified"],
                "needs_review": summary_row["needs_review"],
                "tier_breakdown": {r["tier"]: r["cnt"] for r in tier_rows},
                "provenance_breakdown": {r["src"]: r["cnt"] for r in provenance_rows},
            },
            "requirements": [
                {
                    "id": str(r["id"]),
                    "jurisdiction_id": str(r["jurisdiction_id"]),
                    "category": r["category"],
                    "title": r["title"],
                    "description": r["description"],
                    "source_url": r["source_url"],
                    "source_url_status": r["source_url_status"],
                    "source_tier": r["source_tier"],
                    "current_value": r["current_value"],
                    "effective_date": fmt(r["effective_date"]),
                    "last_verified_at": fmt(r["last_verified_at"]),
                    "is_bookmarked": r["is_bookmarked"],
                    "created_at": fmt(r["created_at"]),
                    "updated_at": fmt(r["updated_at"]),
                    "jurisdiction_name": r["jurisdiction_name"],
                    "state": r["state"],
                    "city": r["city"],
                    "completeness_score": r["completeness_score"],
                    "staleness_days": r["staleness_days"],
                    "research_source": _row_metadata(r["metadata"]).get("research_source"),
                    "statute_citation": r["statute_citation"],
                    "citation_verified": r["citation_verified_at"] is not None and r["citation_item_id"] is not None,
                    "citation_verified_at": fmt(r["citation_verified_at"]),
                    # The Codified tab needs this to know whether a row CAN codify:
                    # a keyless row 422s at POST /requirements/{id}/codify, so it
                    # gets a badge instead of a button.
                    "regulation_key": r["regulation_key"],
                    "change_status": r["change_status"],
                }
                for r in rows
            ],
        }

    if redis:
        await cache_set(redis, cache_key, result, ttl=300)

    return result


@router.get("/jurisdictions/coverage-matrix", dependencies=[Depends(require_admin)])
async def get_coverage_matrix(
    state: Optional[str] = None,
    domain: Optional[str] = None,
):
    """Coverage matrix: jurisdiction × category grid with tier, completeness, and staleness."""
    import hashlib

    cache_key = "admin:coverage-matrix:" + hashlib.md5(
        f"{state}:{domain}".encode()
    ).hexdigest()

    redis = get_redis_cache()
    if redis:
        cached = await cache_get(redis, cache_key)
        if cached is not None:
            return cached

    async with get_connection() as conn:
        where_conditions = ["1=1"]
        join_conditions = ["jr.jurisdiction_id = j.id", "jr.status = 'active'"]
        params: List[Any] = []

        if state:
            params.append(state.upper())
            where_conditions.append(f"j.state = ${len(params)}")

        domain_cats = DOMAIN_CATEGORIES.get(domain) if domain else None
        if domain_cats:
            params.append(domain_cats)
            join_conditions.append(f"jr.category = ANY(${len(params)})")

        where_clause = " AND ".join(where_conditions)
        join_clause = " AND ".join(join_conditions)

        rows = await conn.fetch(f"""
            SELECT
                j.id, j.display_name, j.state, j.city,
                jr.category,
                COUNT(jr.id) AS req_count,
                MAX(CASE jr.source_tier::text
                    WHEN 'tier_1_government' THEN 3
                    WHEN 'tier_2_official_secondary' THEN 2
                    WHEN 'tier_3_aggregator' THEN 1
                    ELSE 0 END) AS best_tier,
                AVG(
                    CASE WHEN jr.title IS NOT NULL AND jr.title != '' THEN 25 ELSE 0 END +
                    CASE WHEN jr.description IS NOT NULL AND jr.description != '' THEN 30 ELSE 0 END +
                    CASE WHEN jr.source_url IS NOT NULL AND jr.source_url != '' THEN 20 ELSE 0 END +
                    CASE WHEN jr.effective_date IS NOT NULL THEN 15 ELSE 0 END +
                    CASE WHEN jr.current_value IS NOT NULL AND jr.current_value != '' THEN 10 ELSE 0 END
                )::int AS avg_completeness,
                MAX(EXTRACT(DAY FROM NOW() - jr.last_verified_at))::int AS max_staleness_days
            FROM jurisdictions j
            LEFT JOIN jurisdiction_requirements jr ON {join_clause}
            WHERE {where_clause}
            GROUP BY j.id, j.display_name, j.state, j.city, jr.category
            ORDER BY j.state, j.display_name, jr.category
        """, *params)

        jurisdictions_seen: Dict[str, Any] = {}
        categories_seen: set = set(domain_cats) if domain_cats else set()
        cells: Dict[str, Any] = {}

        for r in rows:
            jid = str(r["id"])
            if jid not in jurisdictions_seen:
                jurisdictions_seen[jid] = {
                    "id": jid,
                    "name": r["display_name"],
                    "state": r["state"],
                    "city": r["city"],
                }
            cat = r["category"]
            if cat is not None:
                categories_seen.add(cat)
                cells[f"{jid}:{cat}"] = {
                    "req_count": r["req_count"],
                    "best_tier": r["best_tier"],
                    "avg_completeness": r["avg_completeness"],
                    "max_staleness_days": r["max_staleness_days"],
                }

        result = {
            "jurisdictions": list(jurisdictions_seen.values()),
            "categories": sorted(categories_seen),
            "cells": cells,
        }

    if redis:
        await cache_set(redis, cache_key, result, ttl=600)

    return result


@router.get("/jurisdictions/integrity-check", dependencies=[Depends(require_admin)])
async def jurisdiction_integrity_check(
    jurisdiction_id: Optional[UUID] = None,
    state: Optional[str] = None,
):
    """Bidirectional integrity check: missing keys, orphaned records, stale data, partial groups."""
    async with get_connection() as conn:
        # ── 1. Missing keys: defined in registry but absent from DB ──
        jur_filter = ""
        params: list = []
        if jurisdiction_id:
            params.append(jurisdiction_id)
            jur_filter = f"AND j.id = ${len(params)}"
        elif state:
            params.append(state.upper())
            jur_filter = f"AND j.state = ${len(params)}"

        missing_rows = await conn.fetch(f"""
            SELECT
                j.id AS jurisdiction_id, j.city, j.state,
                rkd.key, rkd.category_slug, rkd.name AS key_name,
                rkd.key_group, rkd.base_weight
            FROM regulation_key_definitions rkd
            CROSS JOIN jurisdictions j
            LEFT JOIN jurisdiction_requirements jr
                ON jr.jurisdiction_id = j.id
                AND jr.category = rkd.category_slug
                AND jr.regulation_key = rkd.key
            WHERE jr.id IS NULL
              AND j.level != 'federal'
              {jur_filter}
            ORDER BY j.state, j.city, rkd.category_slug, rkd.key
            LIMIT 500
        """, *params)

        missing_keys = [
            {
                "jurisdiction_id": str(r["jurisdiction_id"]),
                "city": r["city"],
                "state": r["state"],
                "key": r["key"],
                "category": r["category_slug"],
                "key_name": r["key_name"],
                "key_group": r["key_group"],
                "weight": float(r["base_weight"]),
            }
            for r in missing_rows
        ]

        # ── 2. Orphaned records: in DB but not matching any key definition ──
        orphan_params: list = []
        orphan_filter = ""
        if jurisdiction_id:
            orphan_params.append(jurisdiction_id)
            orphan_filter = f"AND jr.jurisdiction_id = ${len(orphan_params)}"
        elif state:
            orphan_params.append(state.upper())
            orphan_filter = f"AND j.state = ${len(orphan_params)}"

        orphan_rows = await conn.fetch(f"""
            SELECT
                jr.id, jr.jurisdiction_id, j.city, j.state,
                jr.category, jr.regulation_key, jr.title,
                jr.source_tier::text AS source_tier
            FROM jurisdiction_requirements jr
            JOIN jurisdictions j ON j.id = jr.jurisdiction_id
            LEFT JOIN regulation_key_definitions rkd
                ON jr.category = rkd.category_slug
                AND jr.regulation_key = rkd.key
            WHERE rkd.id IS NULL
              AND jr.status = 'active'
              {orphan_filter}
            ORDER BY j.state, j.city, jr.category
            LIMIT 500
        """, *orphan_params)

        orphaned_records = [
            {
                "id": str(r["id"]),
                "jurisdiction_id": str(r["jurisdiction_id"]),
                "city": r["city"],
                "state": r["state"],
                "category": r["category"],
                "regulation_key": r["regulation_key"],
                "title": r["title"],
                "source_tier": r["source_tier"],
            }
            for r in orphan_rows
        ]

        # ── 3. Stale keys: past staleness thresholds ──
        stale_params: list = []
        stale_filter = ""
        if jurisdiction_id:
            stale_params.append(jurisdiction_id)
            stale_filter = f"AND jr.jurisdiction_id = ${len(stale_params)}"
        elif state:
            stale_params.append(state.upper())
            stale_filter = f"AND j.state = ${len(stale_params)}"

        stale_rows = await conn.fetch(f"""
            SELECT
                jr.id, j.city, j.state,
                jr.category, jr.regulation_key, jr.title,
                EXTRACT(DAY FROM NOW() - jr.last_verified_at)::int AS days_since_verified,
                rkd.staleness_warning_days,
                rkd.staleness_critical_days,
                rkd.staleness_expired_days,
                rkd.name AS key_name
            FROM jurisdiction_requirements jr
            JOIN jurisdictions j ON j.id = jr.jurisdiction_id
            JOIN regulation_key_definitions rkd
                ON jr.category = rkd.category_slug
                AND jr.regulation_key = rkd.key
            WHERE jr.status = 'active'
              AND EXTRACT(DAY FROM NOW() - jr.last_verified_at) > rkd.staleness_warning_days
              {stale_filter}
            ORDER BY EXTRACT(DAY FROM NOW() - jr.last_verified_at) DESC
            LIMIT 200
        """, *stale_params)

        stale_keys = []
        for r in stale_rows:
            days = r["days_since_verified"] or 0
            if days >= (r["staleness_expired_days"] or 365):
                level = "expired"
            elif days >= (r["staleness_critical_days"] or 180):
                level = "critical"
            else:
                level = "warning"
            stale_keys.append({
                "id": str(r["id"]),
                "city": r["city"],
                "state": r["state"],
                "category": r["category"],
                "regulation_key": r["regulation_key"],
                "key_name": r["key_name"],
                "days_since_verified": days,
                "staleness_level": level,
            })

        # ── 4. Partial groups: key groups with incomplete coverage ──
        group_params: list = []
        group_filter = ""
        if jurisdiction_id:
            group_params.append(jurisdiction_id)
            group_filter = f"AND j.id = ${len(group_params)}"
        elif state:
            group_params.append(state.upper())
            group_filter = f"AND j.state = ${len(group_params)}"

        group_rows = await conn.fetch(f"""
            WITH expected AS (
                SELECT rkd.key_group, rkd.category_slug, count(*) AS expected_count
                FROM regulation_key_definitions rkd
                WHERE rkd.key_group IS NOT NULL
                GROUP BY rkd.key_group, rkd.category_slug
            ),
            present AS (
                SELECT rkd.key_group, rkd.category_slug, j.id AS jurisdiction_id, j.city, j.state,
                       count(DISTINCT jr.regulation_key) AS present_count
                FROM regulation_key_definitions rkd
                CROSS JOIN jurisdictions j
                LEFT JOIN jurisdiction_requirements jr
                    ON jr.jurisdiction_id = j.id
                    AND jr.category = rkd.category_slug
                    AND jr.regulation_key = rkd.key
                    AND jr.status = 'active'
                WHERE rkd.key_group IS NOT NULL
                  AND j.level != 'federal'
                  {group_filter}
                GROUP BY rkd.key_group, rkd.category_slug, j.id, j.city, j.state
            )
            SELECT p.key_group, p.category_slug, p.city, p.state,
                   p.present_count, e.expected_count
            FROM present p
            JOIN expected e ON e.key_group = p.key_group AND e.category_slug = p.category_slug
            WHERE p.present_count > 0 AND p.present_count < e.expected_count
            ORDER BY (p.present_count::float / e.expected_count), p.key_group
            LIMIT 200
        """, *group_params)

        partial_groups = [
            {
                "key_group": r["key_group"],
                "category": r["category_slug"],
                "city": r["city"],
                "state": r["state"],
                "present": r["present_count"],
                "expected": r["expected_count"],
                "coverage_pct": round(r["present_count"] / r["expected_count"] * 100, 1),
            }
            for r in group_rows
        ]

        # ── 5. Summary counts ──
        total_defined = await conn.fetchval("SELECT count(*) FROM regulation_key_definitions")
        total_records = await conn.fetchval(
            "SELECT count(*) FROM jurisdiction_requirements WHERE status = 'active'"
        )
        linked_count = await conn.fetchval(
            "SELECT count(*) FROM jurisdiction_requirements WHERE key_definition_id IS NOT NULL AND status = 'active'"
        )

    return {
        "missing_keys": missing_keys,
        "missing_count": len(missing_rows),
        "orphaned_records": orphaned_records,
        "orphaned_count": len(orphan_rows),
        "stale_keys": stale_keys,
        "stale_count": len(stale_keys),
        "partial_groups": partial_groups,
        "partial_group_count": len(partial_groups),
        "total_defined_keys": total_defined,
        "total_db_records": total_records,
        "linked_records": linked_count,
        "integrity_score": round(
            (linked_count / total_records * 100) if total_records > 0 else 0, 1
        ),
    }


