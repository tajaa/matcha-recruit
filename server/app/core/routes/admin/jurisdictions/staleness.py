"""Admin jurisdictions routes — staleness check + key coverage (split of jurisdictions.py)."""
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



@router.post("/jurisdictions/run-staleness-check", dependencies=[Depends(require_admin)])
async def run_staleness_check(
    jurisdiction_id: Optional[UUID] = Body(None),
    state: Optional[str] = Body(None),
):
    """Run staleness scan and upsert repository_alerts. Admin-triggered, not scheduled."""
    created = 0
    resolved = 0

    async with get_connection() as conn:
        params: list = []
        jur_filter = ""
        if jurisdiction_id:
            params.append(jurisdiction_id)
            jur_filter = f"AND jr.jurisdiction_id = ${len(params)}"
        elif state:
            params.append(state.upper())
            jur_filter = f"AND j.state = ${len(params)}"

        # ── 1. Stale data detection ──
        stale_rows = await conn.fetch(f"""
            SELECT
                jr.id AS requirement_id, jr.jurisdiction_id,
                jr.category, jr.regulation_key,
                EXTRACT(DAY FROM NOW() - jr.last_verified_at)::int AS days_since_verified,
                rkd.id AS key_definition_id,
                rkd.staleness_warning_days, rkd.staleness_critical_days, rkd.staleness_expired_days,
                rkd.name AS key_name,
                j.city, j.state
            FROM jurisdiction_requirements jr
            JOIN jurisdictions j ON j.id = jr.jurisdiction_id
            JOIN regulation_key_definitions rkd
                ON jr.category = rkd.category_slug AND jr.regulation_key = rkd.key
            WHERE jr.status = 'active'
              AND EXTRACT(DAY FROM NOW() - jr.last_verified_at) > rkd.staleness_warning_days
              {jur_filter}
        """, *params)

        for r in stale_rows:
            days = r["days_since_verified"] or 0
            if days >= (r["staleness_expired_days"] or 365):
                alert_type, severity = "stale_expired", "expired"
            elif days >= (r["staleness_critical_days"] or 180):
                alert_type, severity = "stale_critical", "critical"
            else:
                alert_type, severity = "stale_warning", "warning"

            message = f"{r['key_name']} for {r['city']}, {r['state']} is {days} days past verification"
            result = await conn.execute("""
                INSERT INTO repository_alerts
                    (alert_type, severity, jurisdiction_id, key_definition_id, requirement_id,
                     category, regulation_key, message, days_overdue)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (jurisdiction_id, key_definition_id, alert_type)
                    WHERE status = 'open'
                DO UPDATE SET
                    severity = EXCLUDED.severity,
                    message = EXCLUDED.message,
                    days_overdue = EXCLUDED.days_overdue
            """, alert_type, severity, r["jurisdiction_id"], r["key_definition_id"],
                r["requirement_id"], r["category"], r["regulation_key"], message,
                days - (r["staleness_warning_days"] or 90))
            if "INSERT" in result:
                created += 1

        # ── 2. Never-verified / missing data detection ──
        missing_params: list = []
        missing_filter = ""
        if jurisdiction_id:
            missing_params.append(jurisdiction_id)
            missing_filter = f"AND j.id = ${len(missing_params)}"
        elif state:
            missing_params.append(state.upper())
            missing_filter = f"AND j.state = ${len(missing_params)}"

        missing_rows = await conn.fetch(f"""
            SELECT
                j.id AS jurisdiction_id, j.city, j.state,
                rkd.id AS key_definition_id,
                rkd.key, rkd.category_slug, rkd.name AS key_name
            FROM regulation_key_definitions rkd
            CROSS JOIN (
                SELECT DISTINCT j2.id, j2.city, j2.state
                FROM jurisdictions j2
                JOIN jurisdiction_requirements jr2 ON jr2.jurisdiction_id = j2.id
                WHERE j2.level != 'federal'
                {missing_filter}
            ) j
            LEFT JOIN jurisdiction_requirements jr
                ON jr.jurisdiction_id = j.id
                AND jr.category = rkd.category_slug
                AND jr.regulation_key = rkd.key
            WHERE jr.id IS NULL
        """, *missing_params)

        for r in missing_rows:
            message = f"{r['key_name']} has no data for {r['city']}, {r['state']}"
            result = await conn.execute("""
                INSERT INTO repository_alerts
                    (alert_type, severity, jurisdiction_id, key_definition_id,
                     category, regulation_key, message)
                VALUES ('missing_data', 'missing', $1, $2, $3, $4, $5)
                ON CONFLICT (jurisdiction_id, key_definition_id, alert_type)
                    WHERE status = 'open'
                DO NOTHING
            """, r["jurisdiction_id"], r["key_definition_id"],
                r["category_slug"], r["key"], message)
            if "INSERT" in result:
                created += 1

        # ── 3. Auto-resolve: keys that are now verified/present ──
        resolved_count = await conn.fetchval(f"""
            WITH resolvable AS (
                SELECT ra.id
                FROM repository_alerts ra
                JOIN jurisdiction_requirements jr
                    ON jr.jurisdiction_id = ra.jurisdiction_id
                    AND jr.category = ra.category
                    AND jr.regulation_key = ra.regulation_key
                    AND jr.status = 'active'
                JOIN regulation_key_definitions rkd
                    ON rkd.id = ra.key_definition_id
                WHERE ra.status = 'open'
                  AND ra.alert_type IN ('stale_warning', 'stale_critical', 'stale_expired')
                  AND EXTRACT(DAY FROM NOW() - jr.last_verified_at) <= rkd.staleness_warning_days
            )
            UPDATE repository_alerts
            SET status = 'resolved', resolved_at = NOW()
            WHERE id IN (SELECT id FROM resolvable)
            RETURNING id
        """) or 0
        resolved = resolved_count if isinstance(resolved_count, int) else 0

    return {
        "alerts_created": created,
        "alerts_resolved": resolved,
        "stale_found": len(stale_rows),
        "missing_found": len(missing_rows),
    }


@router.get("/jurisdictions/key-coverage", dependencies=[Depends(require_admin)])
async def jurisdiction_key_coverage(
    jurisdiction_id: Optional[UUID] = None,
    category: Optional[str] = None,
    state: Optional[str] = None,
    gaps_only: bool = False,
):
    """Key-level coverage: per-category breakdown of present/missing regulation keys."""
    from app.core.compliance_registry import resolve_weight, CATEGORY_MAP

    async with get_connection() as conn:
        # ── 1. All key definitions ──
        def_params: list = []
        def_filter = ""
        if category:
            def_params.append(category)
            def_filter = f"WHERE rkd.category_slug = ${len(def_params)}"

        all_defs = await conn.fetch(f"""
            SELECT rkd.id, rkd.key, rkd.category_slug, rkd.name,
                   rkd.enforcing_agency, rkd.state_variance, rkd.base_weight,
                   rkd.key_group, rkd.staleness_warning_days,
                   rkd.applicable_industries, rkd.applicable_entity_types,
                   cc."group" AS domain_group
            FROM regulation_key_definitions rkd
            JOIN compliance_categories cc ON cc.id = rkd.category_id
            {def_filter}
            ORDER BY rkd.category_slug, rkd.key
        """, *def_params)

        # ── 2. Present keys per jurisdiction ──
        jr_params: list = []
        jr_filter_parts = ["jr.status = 'active'"]
        if jurisdiction_id:
            jr_params.append(jurisdiction_id)
            jr_filter_parts.append(f"jr.jurisdiction_id = ${len(jr_params)}")
        elif state:
            jr_params.append(state.upper())
            jr_filter_parts.append(f"j.state = ${len(jr_params)}")
        if category:
            jr_params.append(category)
            jr_filter_parts.append(f"jr.category = ${len(jr_params)}")

        jr_filter = " AND ".join(jr_filter_parts)

        present_rows = await conn.fetch(f"""
            SELECT
                jr.category,
                jr.regulation_key,
                COUNT(DISTINCT jr.jurisdiction_id) AS jurisdiction_count,
                MAX(CASE jr.source_tier::text
                    WHEN 'tier_1_government' THEN 3
                    WHEN 'tier_2_official_secondary' THEN 2
                    WHEN 'tier_3_aggregator' THEN 1
                    ELSE 0 END) AS best_tier,
                MAX(EXTRACT(DAY FROM NOW() - jr.last_verified_at))::int AS max_staleness_days,
                MAX(jr.current_value) AS newest_value
            FROM jurisdiction_requirements jr
            JOIN jurisdictions j ON j.id = jr.jurisdiction_id
            WHERE {jr_filter}
            GROUP BY jr.category, jr.regulation_key
        """, *jr_params)

        present_set: Dict[str, dict] = {}
        for r in present_rows:
            k = f"{r['category']}:{r['regulation_key']}"
            present_set[k] = {
                "jurisdiction_count": r["jurisdiction_count"],
                "best_tier": r["best_tier"],
                "days_since_verified": r["max_staleness_days"],
                "newest_value": r["newest_value"],
            }

        # ── 3. Build per-category response ──
        categories_data: Dict[str, dict] = {}
        total_expected = 0
        total_present = 0
        total_weight_expected = 0.0
        total_weight_present = 0.0

        for d in all_defs:
            cat = d["category_slug"]
            if cat not in categories_data:
                cat_def = CATEGORY_MAP.get(cat)
                categories_data[cat] = {
                    "category": cat,
                    "group": d["domain_group"],
                    "label": cat_def.label if cat_def else cat,
                    "expected": 0,
                    "present": 0,
                    "coverage_pct": 0,
                    "weighted_score": 0,
                    "keys": [],
                    "partial_groups": {},
                }

            lookup_key = f"{cat}:{d['key']}"
            is_present = lookup_key in present_set
            presence = present_set.get(lookup_key, {})
            weight = float(d["base_weight"])

            staleness_days = presence.get("days_since_verified")
            if staleness_days is not None and is_present:
                warn = d["staleness_warning_days"] or 90
                if staleness_days >= (d.get("staleness_expired_days") or 365):
                    staleness_level = "expired"
                elif staleness_days >= (d.get("staleness_critical_days") or 180):
                    staleness_level = "critical"
                elif staleness_days >= warn:
                    staleness_level = "warning"
                else:
                    staleness_level = "fresh"
            else:
                staleness_level = "no_data" if not is_present else "fresh"

            key_entry = {
                "id": str(d["id"]),
                "key": d["key"],
                "name": d["name"],
                "enforcing_agency": d["enforcing_agency"],
                "base_weight": weight,
                "state_variance": d["state_variance"],
                "key_group": d["key_group"],
                "status": "present" if is_present else "missing",
                "jurisdiction_count": presence.get("jurisdiction_count", 0),
                "best_tier": presence.get("best_tier", 0),
                "days_since_verified": staleness_days,
                "staleness_level": staleness_level,
                "newest_value": presence.get("newest_value"),
            }

            if not gaps_only or not is_present:
                categories_data[cat]["keys"].append(key_entry)

            categories_data[cat]["expected"] += 1
            total_expected += 1
            total_weight_expected += weight

            if is_present:
                categories_data[cat]["present"] += 1
                total_present += 1
                total_weight_present += weight

            # Track group completeness
            grp = d["key_group"]
            if grp:
                pg = categories_data[cat]["partial_groups"]
                if grp not in pg:
                    pg[grp] = {"present": 0, "expected": 0, "missing": []}
                pg[grp]["expected"] += 1
                if is_present:
                    pg[grp]["present"] += 1
                else:
                    pg[grp]["missing"].append(d["key"])

        # ── 4. Finalize categories ──
        by_category = []
        cats_fully_covered = 0
        cats_with_gaps = 0

        for cat_data in categories_data.values():
            exp = cat_data["expected"]
            pres = cat_data["present"]
            cat_data["coverage_pct"] = round(pres / exp * 100, 1) if exp > 0 else 0

            # Convert partial_groups to list, only include incomplete ones
            pg_list = []
            for grp_name, grp_data in cat_data["partial_groups"].items():
                if 0 < grp_data["present"] < grp_data["expected"]:
                    pg_list.append({
                        "group": grp_name,
                        "present": grp_data["present"],
                        "expected": grp_data["expected"],
                        "missing": grp_data["missing"],
                    })
            cat_data["partial_groups"] = pg_list

            if pres == exp and exp > 0:
                cats_fully_covered += 1
            elif pres < exp:
                cats_with_gaps += 1

            if not gaps_only or pres < exp:
                by_category.append(cat_data)

        # Sort: most gaps first
        by_category.sort(key=lambda c: c["coverage_pct"])

        # ── 5. Stale/alert counts ──
        stale_warning = sum(
            1 for c in by_category
            for k in c["keys"]
            if k["staleness_level"] == "warning"
        )
        stale_critical = sum(
            1 for c in by_category
            for k in c["keys"]
            if k["staleness_level"] in ("critical", "expired")
        )

    return {
        "summary": {
            "total_defined_keys": total_expected,
            "total_present": total_present,
            "key_coverage_pct": round(total_present / total_expected * 100, 1) if total_expected > 0 else 0,
            "weighted_score": round(total_weight_present / total_weight_expected * 100, 1) if total_weight_expected > 0 else 0,
            "categories_fully_covered": cats_fully_covered,
            "categories_with_gaps": cats_with_gaps,
            "stale_warning": stale_warning,
            "stale_critical": stale_critical,
        },
        "by_category": by_category,
    }


