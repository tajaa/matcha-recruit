"""Admin jurisdictions routes — data/policy/penalty overviews + api-sources (split of jurisdictions.py)."""
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



@router.get("/jurisdictions/data-overview", dependencies=[Depends(require_admin)])
async def jurisdiction_data_overview(bust: bool = False):
    """Aggregated view of the jurisdiction data repository."""
    import time

    redis = get_redis_cache()
    if not bust and redis:
        cached = await cache_get(redis, admin_jurisdiction_data_overview_key())
        if cached is not None:
            return cached

    # Legacy in-memory fallback
    global _data_overview_cache, _data_overview_cached_at
    now = time.monotonic()
    if not bust and not redis and _data_overview_cache and (now - _data_overview_cached_at) < _DATA_OVERVIEW_CACHE_TTL:
        return _data_overview_cache

    async with get_connection() as conn:
        # ── 1. All jurisdictions with their requirements ──
        rows = await conn.fetch("""
            SELECT
                j.id, j.city, j.state, j.country_code, j.last_verified_at,
                COALESCE(
                    array_agg(DISTINCT jr.category) FILTER (WHERE jr.category IS NOT NULL),
                    '{}'
                ) AS categories,
                COALESCE(
                    json_agg(json_build_object(
                        'tier', COALESCE(jr.source_tier::text, 'tier_3_aggregator'),
                        'category', jr.category,
                        'last_verified', jr.last_verified_at
                    )) FILTER (WHERE jr.id IS NOT NULL),
                    '[]'
                ) AS req_details
            FROM jurisdictions j
            LEFT JOIN jurisdiction_requirements jr ON jr.jurisdiction_id = j.id
            WHERE (j.city IS NULL OR (j.city NOT LIKE '_county_%' AND j.city <> ''))
              AND j.level != 'federal'
            GROUP BY j.id, j.city, j.state, j.country_code, j.last_verified_at
            ORDER BY j.state, j.city
        """)

        # ── 1b. Inherited categories from state + federal jurisdictions ──
        inherited_rows = await conn.fetch("""
            SELECT j.state, j.level::text AS level,
                   COALESCE(
                       array_agg(DISTINCT jr.category) FILTER (WHERE jr.category IS NOT NULL),
                       '{}'
                   ) AS categories
            FROM jurisdictions j
            LEFT JOIN jurisdiction_requirements jr ON jr.jurisdiction_id = j.id
            WHERE j.level IN ('state', 'federal')
            GROUP BY j.state, j.level
        """)

        federal_categories: set = set()
        state_categories: dict[str, set] = {}
        for irow in inherited_rows:
            cats = set(irow["categories"] or [])
            if irow["level"] == "federal":
                federal_categories |= cats
            else:
                state_categories.setdefault(irow["state"], set()).update(cats)

        # ── 2. Preemption rules ──
        try:
            preemption_rows = await conn.fetch("""
                SELECT state, category, allows_local_override, notes
                FROM state_preemption_rules
                ORDER BY state, category
            """)
        except Exception:
            preemption_rows = []

        # ── 3. Structured data sources ──
        try:
            source_rows = await conn.fetch("""
                SELECT source_name, source_type, categories, record_count,
                       last_fetched_at, last_fetch_status, is_active
                FROM structured_data_sources
                ORDER BY source_name
            """)
        except Exception:
            source_rows = []

    # ── Build state → cities map ──
    from datetime import datetime as dt, timezone
    stale_cutoff = dt.now(timezone.utc).replace(tzinfo=None) - timedelta(days=90)
    required_categories = await _get_required_categories(force_refresh=bust)
    req_cats = set(required_categories)

    states_map: dict[str, dict] = {}
    total_cities = 0
    total_requirements = 0
    tier_counts = {1: 0, 2: 0, 3: 0}
    stale_count = 0
    freshness = {"7d": 0, "30d": 0, "90d": 0, "stale": 0}
    now_dt = dt.now(timezone.utc).replace(tzinfo=None)

    for row in rows:
        state = row["state"] or ""
        country_code = row.get("country_code", "US") or "US"
        # Group international jurisdictions by country_code to avoid mixing with US states
        state_group_key = f"{state}:{country_code}" if country_code != "US" else state
        if state_group_key not in states_map:
            states_map[state_group_key] = {"state": state, "country_code": country_code, "cities": []}

        direct_cats = set(c for c in (row["categories"] or []) if c in req_cats)
        # Only inherit from federal/state for US jurisdictions
        if country_code == "US":
            inherited = (federal_categories | state_categories.get(state, set())) & req_cats
        else:
            inherited = set()
        cats_present = sorted(direct_cats | inherited)
        cats_missing = sorted(req_cats - set(cats_present))
        req_list = json.loads(row["req_details"]) if isinstance(row["req_details"], str) else row["req_details"]

        city_tier_counts = {1: 0, 2: 0, 3: 0}
        for r in req_list:
            if r.get("category"):
                t = r.get("tier", 3)
                if t in city_tier_counts:
                    city_tier_counts[t] += 1
                    tier_counts[t] += 1
                total_requirements += 1
                # Freshness
                lv = r.get("last_verified")
                if lv:
                    if isinstance(lv, str):
                        try:
                            lv = dt.fromisoformat(lv.replace("Z", "+00:00")).replace(tzinfo=None)
                        except Exception:
                            lv = None
                    if lv:
                        age = (now_dt - lv).days
                        if age <= 7:
                            freshness["7d"] += 1
                        elif age <= 30:
                            freshness["30d"] += 1
                        elif age <= 90:
                            freshness["90d"] += 1
                        else:
                            freshness["stale"] += 1

        last_v = row["last_verified_at"]
        is_stale = last_v is not None and last_v < stale_cutoff
        if is_stale:
            stale_count += 1

        city_data = {
            "id": str(row["id"]),
            "city": row["city"],
            "country_code": row.get("country_code", "US"),
            "categories_present": sorted(cats_present),
            "categories_missing": cats_missing,
            "tier_breakdown": city_tier_counts,
            "last_verified_at": last_v.isoformat() if last_v else None,
            "is_stale": is_stale,
        }
        states_map[state_group_key]["cities"].append(city_data)
        total_cities += 1

    # Enrich state entries
    states_list = []
    for s_data in states_map.values():
        cities = s_data["cities"]
        all_cats = set()
        for c in cities:
            all_cats.update(c["categories_present"])
        s_data["city_count"] = len(cities)
        s_data["coverage_pct"] = round(len(all_cats) / len(req_cats) * 100) if req_cats else 0
        states_list.append(s_data)

    unique_states = len(states_map)
    total_req_slots = total_cities * len(req_cats)
    category_coverage_pct = round(total_requirements / total_req_slots * 100) if total_req_slots else 0
    tier_total = sum(tier_counts.values())
    tier1_pct = round(tier_counts[1] / tier_total * 100) if tier_total else 0

    # Preemption
    preemption_rules = [
        {
            "state": r["state"],
            "category": r["category"],
            "allows_local_override": r["allows_local_override"],
            "notes": r["notes"],
        }
        for r in preemption_rows
    ]

    # Structured sources
    structured_sources = [
        {
            "source_name": r["source_name"],
            "source_type": r["source_type"],
            "categories": r["categories"],
            "record_count": r["record_count"],
            "last_fetched_at": r["last_fetched_at"].isoformat() if r["last_fetched_at"] else None,
            "last_fetch_status": r["last_fetch_status"],
            "is_active": r["is_active"],
        }
        for r in source_rows
    ]

    result = {
        "summary": {
            "total_states": unique_states,
            "total_cities": total_cities,
            "total_requirements": total_requirements,
            "category_coverage_pct": category_coverage_pct,
            "tier1_pct": tier1_pct,
            "tier_breakdown": tier_counts,
            "stale_count": stale_count,
            "freshness": freshness,
            "required_categories": required_categories,
        },
        "states": states_list,
        "preemption_rules": preemption_rules,
        "structured_sources": structured_sources,
    }

    _data_overview_cache = result
    _data_overview_cached_at = now

    if redis:
        await cache_set(redis, admin_jurisdiction_data_overview_key(), result, ttl=3600)

    return result


@router.get("/jurisdictions/policy-overview", dependencies=[Depends(require_admin)])
async def jurisdiction_policy_overview(category: Optional[str] = Query(None)):
    """Policy browser: overview by domain→category, or detail for a single category."""
    redis = get_redis_cache()
    if redis:
        cached = await cache_get(redis, admin_jurisdiction_policy_overview_key(category))
        if cached is not None:
            return cached

    async with get_connection() as conn:
        if category:
            # ── Detail mode: all requirements for one category ──
            rows = await conn.fetch("""
                SELECT jr.id, j.city, j.state, j.level AS jurisdiction_level,
                       jr.jurisdiction_name, jr.title, jr.current_value, jr.numeric_value,
                       jr.source_url, jr.source_name, jr.effective_date,
                       jr.last_verified_at,
                       COALESCE(jr.source_tier::text, 'tier_3_aggregator') AS source_tier,
                       COALESCE(jr.status::text, 'active') AS status,
                       jr.statute_citation
                FROM jurisdiction_requirements jr
                JOIN jurisdictions j ON j.id = jr.jurisdiction_id
                WHERE jr.category = $1
                ORDER BY j.state, j.city NULLS FIRST
            """, category)
            domain = _CATEGORY_DOMAIN.get(category, "unknown")
            result = {
                "category": {
                    "slug": category,
                    "name": _CATEGORY_LABELS.get(category, category),
                    "domain": domain,
                    "group": domain,
                },
                "requirements": [
                    {
                        "id": str(r["id"]),
                        "jurisdiction_name": r["jurisdiction_name"],
                        "jurisdiction_level": r["jurisdiction_level"] or "city",
                        "state": r["state"],
                        "city": r["city"],
                        "title": r["title"],
                        "current_value": r["current_value"],
                        "numeric_value": float(r["numeric_value"]) if r["numeric_value"] is not None else None,
                        "source_tier": r["source_tier"],
                        "status": r["status"],
                        "statute_citation": r.get("statute_citation"),
                        "effective_date": r["effective_date"].isoformat() if r["effective_date"] else None,
                        "last_verified_at": r["last_verified_at"].isoformat() if r["last_verified_at"] else None,
                    }
                    for r in rows
                ],
            }
            if redis:
                await cache_set(redis, admin_jurisdiction_policy_overview_key(category), result, ttl=600)
            return result

        # ── Overview mode: domain → category tree with counts ──
        cat_rows = await conn.fetch("""
            SELECT jr.category,
                   COUNT(*) AS requirement_count,
                   COUNT(DISTINCT j.id) AS jurisdiction_count,
                   COUNT(*) FILTER (WHERE COALESCE(jr.source_tier::text, 'tier_3_aggregator') = 'tier_1_government') AS tier_1,
                   COUNT(*) FILTER (WHERE COALESCE(jr.source_tier::text, 'tier_3_aggregator') = 'tier_2_official_secondary') AS tier_2,
                   COUNT(*) FILTER (WHERE COALESCE(jr.source_tier::text, 'tier_3_aggregator') = 'tier_3_aggregator') AS tier_3,
                   MAX(jr.last_verified_at) AS latest_verified
            FROM jurisdiction_requirements jr
            JOIN jurisdictions j ON j.id = jr.jurisdiction_id
            GROUP BY jr.category
            ORDER BY jr.category
        """)

        total_jurisdictions_row = await conn.fetchval(
            "SELECT COUNT(DISTINCT id) FROM jurisdictions"
        )

    # Build domain → categories structure. Done outside the connection block —
    # none of this needs `conn`, and `_get_required_categories()` below may hit
    # the DB itself on a cache miss, so there's no reason to hold this
    # connection open for it (mirrors jurisdiction_data_overview).
    domains_map: dict[str, dict] = {}
    total_requirements = 0
    cats_with_data = 0

    for r in cat_rows:
        cat = r["category"]
        domain = _CATEGORY_DOMAIN.get(cat, "unknown")
        if domain not in domains_map:
            domains_map[domain] = {
                "domain": domain,
                "label": _DOMAIN_LABELS.get(domain, domain.replace("_", " ").title()),
                "category_count": 0,
                "requirement_count": 0,
                "categories": [],
            }
        d = domains_map[domain]
        req_count = r["requirement_count"]
        d["category_count"] += 1
        d["requirement_count"] += req_count
        total_requirements += req_count
        cats_with_data += 1
        d["categories"].append({
            "slug": cat,
            "name": _CATEGORY_LABELS.get(cat, cat),
            "group": domain,
            "requirement_count": req_count,
            "jurisdiction_count": r["jurisdiction_count"],
            "tier_breakdown": {
                "tier_1_government": r["tier_1"],
                "tier_2_official_secondary": r["tier_2"],
                "tier_3_aggregator": r["tier_3"],
            },
            "latest_verified": r["latest_verified"].isoformat() if r["latest_verified"] else None,
        })

    # Sort domains by the order they appear in the required-categories list
    required_categories = await _get_required_categories()
    domain_order = list(dict.fromkeys(_CATEGORY_DOMAIN[c] for c in required_categories if c in _CATEGORY_DOMAIN))
    domains_list = []
    for d in domain_order:
        if d in domains_map:
            domains_list.append(domains_map[d])
    # Append any extra domains not in the ordering
    for d, val in domains_map.items():
        if d not in domain_order:
            domains_list.append(val)

    result = {
        "summary": {
            "total_requirements": total_requirements,
            "total_categories_with_data": cats_with_data,
            "total_domains": len(domains_map),
            "total_jurisdictions": total_jurisdictions_row or 0,
        },
        "domains": domains_list,
    }

    if redis:
        await cache_set(redis, admin_jurisdiction_policy_overview_key(None), result, ttl=600)

    return result


@router.get("/jurisdictions/penalty-overview", dependencies=[Depends(require_admin)])
async def get_penalty_overview():
    """Get penalty coverage overview across all categories and sample penalty data."""
    async with get_connection() as conn:
        # Coverage by category
        coverage = await conn.fetch("""
            SELECT category,
                   COUNT(*) as total,
                   SUM(CASE WHEN metadata ? 'penalties' THEN 1 ELSE 0 END) as has_penalty,
                   SUM(CASE WHEN metadata->'penalties'->>'grounding' = 'grounded' THEN 1 ELSE 0 END) as grounded
            FROM jurisdiction_requirements WHERE status = 'active'
            GROUP BY category ORDER BY total DESC
        """)

        # Detailed penalty data per category (one sample per category from governing/federal)
        details = await conn.fetch("""
            SELECT DISTINCT ON (category)
                   category, title,
                   metadata->'penalties'->>'enforcing_agency' as enforcing_agency,
                   (metadata->'penalties'->>'civil_penalty_min')::text as penalty_min,
                   (metadata->'penalties'->>'civil_penalty_max')::text as penalty_max,
                   metadata->'penalties'->>'per_violation' as per_violation,
                   metadata->'penalties'->>'annual_cap' as annual_cap,
                   metadata->'penalties'->>'criminal' as criminal,
                   metadata->'penalties'->>'summary' as summary,
                   metadata->'penalties'->>'source_url' as source_url,
                   metadata->'penalties'->>'verified_date' as verified_date,
                   metadata->'penalties'->>'grounding' as grounding
            FROM jurisdiction_requirements
            WHERE status = 'active' AND metadata ? 'penalties'
            ORDER BY category, jurisdiction_level ASC
        """)

        # Requirements with highest max penalties
        top_penalties = await conn.fetch("""
            SELECT category, title, jurisdiction_name, jurisdiction_level,
                   (metadata->'penalties'->>'civil_penalty_max')::numeric as max_penalty,
                   metadata->'penalties'->>'summary' as summary,
                   metadata->'penalties'->>'enforcing_agency' as enforcing_agency
            FROM jurisdiction_requirements
            WHERE status = 'active'
              AND metadata ? 'penalties'
              AND (metadata->'penalties'->>'civil_penalty_max') IS NOT NULL
              AND (metadata->'penalties'->>'civil_penalty_max') != 'null'
            ORDER BY (metadata->'penalties'->>'civil_penalty_max')::numeric DESC
            LIMIT 20
        """)

    return {
        "coverage": [
            {
                "category": r["category"],
                "total": r["total"],
                "has_penalty": r["has_penalty"],
                "grounded": r["grounded"],
                "pct": round(r["has_penalty"] / r["total"] * 100) if r["total"] > 0 else 0,
            }
            for r in coverage
        ],
        "details": [
            {
                "category": r["category"],
                "title": r["title"],
                "enforcing_agency": r["enforcing_agency"],
                "penalty_min": r["penalty_min"],
                "penalty_max": r["penalty_max"],
                "per_violation": r["per_violation"],
                "annual_cap": r["annual_cap"],
                "criminal": r["criminal"],
                "summary": r["summary"],
                "source_url": r["source_url"],
                "verified_date": r["verified_date"],
                "grounding": r["grounding"],
            }
            for r in details
        ],
        "top_penalties": [
            {
                "category": r["category"],
                "title": r["title"],
                "jurisdiction": f"{r['jurisdiction_name']} ({r['jurisdiction_level']})",
                "max_penalty": float(r["max_penalty"]) if r["max_penalty"] else None,
                "summary": r["summary"],
                "enforcing_agency": r["enforcing_agency"],
            }
            for r in top_penalties
        ],
    }


@router.get("/jurisdictions/api-sources", dependencies=[Depends(require_admin)])
async def get_api_sources_overview():
    """Get all requirements grouped by research_source with stats."""
    async with get_connection() as conn:
        # Counts by research_source
        source_counts = await conn.fetch("""
            SELECT
                COALESCE(metadata->>'research_source', 'unknown') AS research_source,
                COUNT(*) AS total,
                COUNT(DISTINCT category) AS category_count,
                COUNT(DISTINCT jurisdiction_id) AS jurisdiction_count,
                MIN(created_at) AS earliest,
                MAX(updated_at) AS latest
            FROM jurisdiction_requirements
            GROUP BY COALESCE(metadata->>'research_source', 'unknown')
            ORDER BY total DESC
        """)

        # Recent official_api entries
        recent_api = await conn.fetch("""
            SELECT jr.id, jr.category, jr.title, jr.description, jr.current_value,
                   jr.source_name, jr.source_url,
                   jr.effective_date, jr.created_at, jr.updated_at, jr.jurisdiction_level,
                   jr.jurisdiction_name, jr.last_verified_at,
                   j.city, j.state
            FROM jurisdiction_requirements jr
            JOIN jurisdictions j ON j.id = jr.jurisdiction_id
            WHERE jr.metadata->>'research_source' = 'official_api'
            ORDER BY COALESCE(jr.updated_at, jr.created_at) DESC
            LIMIT 100
        """)

        # Category breakdown for official_api
        api_by_category = await conn.fetch("""
            SELECT category, COUNT(*) AS count
            FROM jurisdiction_requirements
            WHERE metadata->>'research_source' = 'official_api'
            GROUP BY category
            ORDER BY count DESC
        """)

        def fmt(d):
            return d.isoformat() if d else None

        return {
            "source_counts": [
                {
                    "research_source": r["research_source"],
                    "total": r["total"],
                    "category_count": r["category_count"],
                    "jurisdiction_count": r["jurisdiction_count"],
                    "earliest": fmt(r["earliest"]),
                    "latest": fmt(r["latest"]),
                }
                for r in source_counts
            ],
            "recent_api": [
                {
                    "id": str(r["id"]),
                    "category": r["category"],
                    "title": r["title"],
                    "description": r["description"],
                    "current_value": r["current_value"],
                    "source_name": r["source_name"],
                    "source_url": r["source_url"],
                    "effective_date": fmt(r["effective_date"]),
                    "created_at": fmt(r["created_at"]),
                    "updated_at": fmt(r["updated_at"]),
                    "jurisdiction_level": r["jurisdiction_level"],
                    "jurisdiction_name": r["jurisdiction_name"],
                    "last_verified_at": fmt(r["last_verified_at"]),
                    "city": r["city"],
                    "state": r["state"],
                }
                for r in recent_api
            ],
            "api_by_category": [
                {"category": r["category"], "count": r["count"]}
                for r in api_by_category
            ],
        }


