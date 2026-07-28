"""Admin jurisdictions routes — cleanup duplicates + delete (split of jurisdictions.py)."""
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



@router.post("/jurisdictions/cleanup-duplicates", dependencies=[Depends(require_admin)])
async def cleanup_duplicate_jurisdictions(
    dry_run: bool = Query(True),
):
    """Merge duplicate city jurisdictions by normalized city+state key."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT id, city, state, county, parent_id, requirement_count, legislation_count,
                   created_at, last_verified_at
            FROM jurisdictions
            ORDER BY state, city, created_at ASC
            """
        )

        city_rows = [row for row in rows if not _is_non_city_jurisdiction(row["city"])]
        grouped: dict[tuple[str, str], list] = {}
        for row in city_rows:
            key = (row["state"], _normalize_city_input(row["city"]))
            grouped.setdefault(key, []).append(row)

        duplicate_groups = [group for group in grouped.values() if len(group) > 1]
        if not duplicate_groups:
            return {
                "status": "ok",
                "dry_run": dry_run,
                "groups_found": 0,
                "groups_merged": 0,
                "duplicates_removed": 0,
                "locations_relinked": 0,
                "children_relinked": 0,
                "details": [],
            }

        def _priority(row) -> tuple:
            return (
                (row["requirement_count"] or 0) + (row["legislation_count"] or 0),
                1 if row["last_verified_at"] is not None else 0,
                row["last_verified_at"] or datetime.min,
                1 if row["created_at"] is not None else 0,
                row["created_at"] or datetime.min,
            )

        details = []
        groups_merged = 0
        duplicates_removed = 0
        locations_relinked = 0
        children_relinked = 0

        for group in duplicate_groups:
            primary = max(group, key=_priority)
            duplicates = [row for row in group if row["id"] != primary["id"]]
            details.append({
                "state": primary["state"],
                "city_key": _normalize_city_input(primary["city"]),
                "primary_id": str(primary["id"]),
                "primary_city": primary["city"],
                "duplicate_ids": [str(row["id"]) for row in duplicates],
                "duplicate_cities": [row["city"] for row in duplicates],
            })

            if dry_run:
                continue

            groups_merged += 1
            primary_parent_id = primary["parent_id"]
            primary_county = primary["county"]

            for dup in duplicates:
                # Preserve hierarchy/county metadata if missing on primary.
                if primary_parent_id is None and dup["parent_id"] is not None:
                    await conn.execute(
                        "UPDATE jurisdictions SET parent_id = $2 WHERE id = $1",
                        primary["id"],
                        dup["parent_id"],
                    )
                    primary_parent_id = dup["parent_id"]

                if not primary_county and dup["county"]:
                    await conn.execute(
                        "UPDATE jurisdictions SET county = $2 WHERE id = $1",
                        primary["id"],
                        dup["county"],
                    )
                    primary_county = dup["county"]

                dup_requirements = await conn.fetch(
                    """
                    SELECT requirement_key, category, rate_type, jurisdiction_level, jurisdiction_name,
                           title, description, current_value, numeric_value, source_url, source_name,
                           effective_date, expiration_date, previous_value, last_changed_at, last_verified_at
                    FROM jurisdiction_requirements
                    WHERE jurisdiction_id = $1
                    """,
                    dup["id"],
                )
                for req in dup_requirements:
                    await conn.execute(
                        """
                        INSERT INTO jurisdiction_requirements
                            (jurisdiction_id, requirement_key, category, rate_type, jurisdiction_level, jurisdiction_name,
                             title, description, current_value, numeric_value, source_url, source_name,
                             effective_date, expiration_date, previous_value, last_changed_at, last_verified_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
                        ON CONFLICT (jurisdiction_id, requirement_key) DO NOTHING
                        """,
                        primary["id"],
                        req["requirement_key"],
                        req["category"],
                        req["rate_type"],
                        req["jurisdiction_level"],
                        req["jurisdiction_name"],
                        req["title"],
                        req["description"],
                        req["current_value"],
                        req["numeric_value"],
                        req["source_url"],
                        req["source_name"],
                        req["effective_date"],
                        req["expiration_date"],
                        req["previous_value"],
                        req["last_changed_at"],
                        req["last_verified_at"],
                    )

                dup_legislation = await conn.fetch(
                    """
                    SELECT legislation_key, category, title, description, current_status,
                           expected_effective_date, impact_summary, source_url, source_name,
                           confidence, last_verified_at
                    FROM jurisdiction_legislation
                    WHERE jurisdiction_id = $1
                    """,
                    dup["id"],
                )
                for leg in dup_legislation:
                    await conn.execute(
                        """
                        INSERT INTO jurisdiction_legislation
                            (jurisdiction_id, legislation_key, category, title, description, current_status,
                             expected_effective_date, impact_summary, source_url, source_name, confidence, last_verified_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                        ON CONFLICT (jurisdiction_id, legislation_key) DO NOTHING
                        """,
                        primary["id"],
                        leg["legislation_key"],
                        leg["category"],
                        leg["title"],
                        leg["description"],
                        leg["current_status"],
                        leg["expected_effective_date"],
                        leg["impact_summary"],
                        leg["source_url"],
                        leg["source_name"],
                        leg["confidence"],
                        leg["last_verified_at"],
                    )

                moved_locations = await conn.fetchval(
                    """
                    WITH moved AS (
                        UPDATE business_locations
                        SET jurisdiction_id = $1
                        WHERE jurisdiction_id = $2
                        RETURNING id
                    )
                    SELECT COUNT(*) FROM moved
                    """,
                    primary["id"],
                    dup["id"],
                )
                locations_relinked += int(moved_locations or 0)

                moved_children = await conn.fetchval(
                    """
                    WITH moved AS (
                        UPDATE jurisdictions
                        SET parent_id = $1
                        WHERE parent_id = $2
                        RETURNING id
                    )
                    SELECT COUNT(*) FROM moved
                    """,
                    primary["id"],
                    dup["id"],
                )
                children_relinked += int(moved_children or 0)

                await conn.execute("DELETE FROM jurisdiction_requirements WHERE jurisdiction_id = $1", dup["id"])
                await conn.execute("DELETE FROM jurisdiction_legislation WHERE jurisdiction_id = $1", dup["id"])
                await conn.execute("DELETE FROM jurisdictions WHERE id = $1", dup["id"])
                duplicates_removed += 1

            requirement_count = await conn.fetchval(
                "SELECT COUNT(*) FROM jurisdiction_requirements WHERE jurisdiction_id = $1",
                primary["id"],
            )
            legislation_count = await conn.fetchval(
                "SELECT COUNT(*) FROM jurisdiction_legislation WHERE jurisdiction_id = $1",
                primary["id"],
            )
            await conn.execute(
                """
                UPDATE jurisdictions
                SET requirement_count = $2, legislation_count = $3, updated_at = NOW()
                WHERE id = $1
                """,
                primary["id"],
                requirement_count,
                legislation_count,
            )

        return {
            "status": "ok",
            "dry_run": dry_run,
            "groups_found": len(duplicate_groups),
            "groups_merged": groups_merged,
            "duplicates_removed": duplicates_removed,
            "locations_relinked": locations_relinked,
            "children_relinked": children_relinked,
            "details": details,
        }


@router.post("/jurisdictions/cleanup-duplicate-requirements", dependencies=[Depends(require_admin)])
async def cleanup_duplicate_requirements(
    dry_run: bool = Query(True),
    jurisdiction_id: Optional[UUID] = Query(None, description="Scope to a single jurisdiction"),
):
    """Find and remove semantically duplicate requirements within each jurisdiction+category.

    Uses three safety layers to avoid false positives:
    1. Jaccard token overlap >= 0.7 (strict)
    2. Poison-token pairs block matches between distinct regulation types
    3. When both rows have a regulation_key prefix, they must match

    Default is dry_run=true — returns what WOULD be deleted without touching data.
    """
    import re as _re

    # Pairs of tokens that indicate DIFFERENT regulations — if one title
    # contains the first and the other contains the second, never merge.
    _POISON_PAIRS = [
        ("meal", "rest"), ("rest", "meal"),
        ("tipped", "state"), ("state", "tipped"),
        ("tipped", "general"), ("general", "tipped"),
        ("tipped", "exempt"), ("exempt", "tipped"),
        ("sick", "family"), ("family", "sick"),
        ("sick", "prenatal"), ("prenatal", "sick"),
        ("sick", "disability"), ("disability", "sick"),
        ("sick", "bereavement"), ("bereavement", "sick"),
        ("family", "disability"), ("disability", "family"),
        ("family", "pregnancy"), ("pregnancy", "family"),
        ("family", "bereavement"), ("bereavement", "family"),
        ("termination", "resignation"), ("resignation", "termination"),
        ("termination", "layoff"), ("layoff", "termination"),
        ("resignation", "layoff"), ("layoff", "resignation"),
        ("daily", "weekly"), ("weekly", "daily"),
        ("minimum", "exempt"), ("exempt", "minimum"),
        ("large", "small"), ("small", "large"),
        ("meal", "lactation"), ("lactation", "meal"),
        ("rest", "lactation"), ("lactation", "rest"),
        ("14", "16"), ("16", "14"),
        ("hourly", "salary"), ("salary", "hourly"),
        ("contractor", "private"), ("private", "contractor"),
        ("religion", "disability"), ("disability", "religion"),
    ]
    _POISON_SET = set(_POISON_PAIRS)

    def _title_tokens(title: str) -> set:
        s = title.lower().strip()
        # Remove parentheses but KEEP their content (age groups, employer sizes live here)
        s = s.replace("(", " ").replace(")", " ")
        s = _re.sub(r"\bcalifornia\b|\bnew york\b|\btexas\b|\bflorida\b|\billinois\b|\bchicago\b", " ", s)
        s = _re.sub(r"\bca\b|\bny\b|\btx\b|\bfl\b|\bil\b", " ", s)
        s = _re.sub(r"\bstate\b|\bcity\b|\bcounty\b|\bfederal\b|\bbaseline\b|\bgeneral\b", " ", s)
        s = _re.sub(r"\brequirements?\b|\bregulations?\b|\blaws?\b|\brules?\b|\bact\b", " ", s)
        s = _re.sub(r"[^a-z0-9]+", " ", s)
        return {t for t in s.split() if len(t) > 1}

    def _jaccard(a: set, b: set) -> float:
        if not a or not b:
            return 0.0
        return len(a & b) / len(a | b)

    def _has_poison_conflict(tokens_a: set, tokens_b: set) -> bool:
        for ta in tokens_a:
            for tb in tokens_b:
                if (ta, tb) in _POISON_SET:
                    return True
        return False

    def _regulation_key_prefix(req_key: str) -> str:
        """Extract the category:regulation part, ignoring title-based suffixes."""
        # Keys look like 'leave:fmla' or 'leave:paid sick leave healthy workplaces...'
        # Canonical keys are short: 'leave:fmla', 'leave:state_paid_sick_leave'
        # Title-based keys are long with spaces: 'leave:paid sick leave ...'
        parts = req_key.split(":", 1)
        if len(parts) < 2:
            return ""
        val = parts[1].strip()
        # Title-based keys contain spaces; canonical keys use underscores only
        if " " in val:
            return ""  # title-based, no stable prefix
        return val

    def _is_match(req_a: dict, req_b: dict, tokens_a: set, tokens_b: set) -> bool:
        # Guard 1: Both have canonical regulation_key → must match exactly
        prefix_a = _regulation_key_prefix(req_a.get("requirement_key", ""))
        prefix_b = _regulation_key_prefix(req_b.get("requirement_key", ""))
        if prefix_a and prefix_b:
            return prefix_a == prefix_b

        # Guard 2: Poison token pairs → never merge
        if _has_poison_conflict(tokens_a, tokens_b):
            return False

        # Guard 3: Jaccard >= 0.7
        return _jaccard(tokens_a, tokens_b) >= 0.7

    async with get_connection() as conn:
        where_clause = "WHERE jr.status = 'active'"
        params: list = []
        if jurisdiction_id:
            where_clause += " AND jr.jurisdiction_id = $1"
            params.append(jurisdiction_id)

        rows = await conn.fetch(
            f"""
            SELECT jr.id, jr.jurisdiction_id, jr.category, jr.requirement_key,
                   jr.title, jr.applicable_industries,
                   jr.last_verified_at, jr.updated_at, jr.created_at,
                   j.display_name AS jurisdiction_name
            FROM jurisdiction_requirements jr
            JOIN jurisdictions j ON jr.jurisdiction_id = j.id
            {where_clause}
            ORDER BY jr.jurisdiction_id, jr.category, jr.last_verified_at DESC NULLS LAST
            """,
            *params,
        )

        from collections import defaultdict
        groups: dict[tuple, list] = defaultdict(list)
        for r in rows:
            groups[(r["jurisdiction_id"], r["category"])].append(dict(r))

        total_duplicates = 0
        total_groups_with_dupes = 0
        details = []

        for (jid, cat), reqs in groups.items():
            if len(reqs) < 2:
                continue

            clusters: list[list[dict]] = []
            assigned = set()

            for i, req_a in enumerate(reqs):
                if i in assigned:
                    continue
                cluster = [req_a]
                assigned.add(i)
                tokens_a = _title_tokens(req_a["title"] or "")

                for j, req_b in enumerate(reqs):
                    if j in assigned:
                        continue
                    tokens_b = _title_tokens(req_b["title"] or "")
                    if _is_match(req_a, req_b, tokens_a, tokens_b):
                        cluster.append(req_b)
                        assigned.add(j)

                if len(cluster) > 1:
                    clusters.append(cluster)

            if not clusters:
                continue

            total_groups_with_dupes += 1
            jur_name = reqs[0].get("jurisdiction_name", str(jid))

            for cluster in clusters:
                primary = cluster[0]  # sorted by last_verified_at DESC
                duplicates = cluster[1:]
                total_duplicates += len(duplicates)

                merged_industries = set()
                for r in cluster:
                    for ind in (r.get("applicable_industries") or []):
                        merged_industries.add(ind)

                details.append({
                    "jurisdiction": jur_name,
                    "category": cat,
                    "keep": {
                        "id": str(primary["id"]),
                        "title": primary["title"],
                        "requirement_key": primary["requirement_key"],
                    },
                    "remove": [
                        {
                            "id": str(d["id"]),
                            "title": d["title"],
                            "requirement_key": d["requirement_key"],
                        }
                        for d in duplicates
                    ],
                    "merged_industries": sorted(merged_industries) if merged_industries else None,
                })

                if not dry_run:
                    if merged_industries:
                        await conn.execute(
                            """UPDATE jurisdiction_requirements
                               SET applicable_industries = $2, updated_at = NOW()
                               WHERE id = $1""",
                            primary["id"],
                            sorted(merged_industries),
                        )
                    dup_ids = [d["id"] for d in duplicates]
                    await conn.execute(
                        "DELETE FROM jurisdiction_requirements WHERE id = ANY($1)",
                        dup_ids,
                    )

        if not dry_run and details:
            await conn.execute(
                """
                UPDATE jurisdictions j
                SET requirement_count = sub.cnt, updated_at = NOW()
                FROM (
                    SELECT jurisdiction_id, COUNT(*) AS cnt
                    FROM jurisdiction_requirements
                    GROUP BY jurisdiction_id
                ) sub
                WHERE j.id = sub.jurisdiction_id
                """
            )

        return {
            "status": "ok",
            "dry_run": dry_run,
            "categories_with_duplicates": total_groups_with_dupes,
            "duplicate_rows": total_duplicates,
            "clusters": len(details),
            "details": details[:200],
        }


@router.delete("/jurisdictions/{jurisdiction_id}", dependencies=[Depends(require_admin)])
async def delete_jurisdiction(jurisdiction_id: UUID):
    """Delete a jurisdiction if it has no linked business locations."""
    async with get_connection() as conn:
        jurisdiction = await conn.fetchrow(
            "SELECT id, city, state FROM jurisdictions WHERE id = $1",
            jurisdiction_id,
        )
        if not jurisdiction:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Jurisdiction not found")

        linked_location_count = await conn.fetchval(
            "SELECT COUNT(*) FROM business_locations WHERE jurisdiction_id = $1",
            jurisdiction_id,
        )
        if linked_location_count and linked_location_count > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Cannot delete {jurisdiction['city']}, {jurisdiction['state']} while "
                    f"{linked_location_count} location(s) are linked."
                ),
            )

        detached_children = await conn.fetchval(
            "SELECT COUNT(*) FROM jurisdictions WHERE parent_id = $1",
            jurisdiction_id,
        )
        await conn.execute("DELETE FROM jurisdictions WHERE id = $1", jurisdiction_id)

        redis = get_redis_cache()
        if redis:
            await cache_delete(redis, admin_jurisdictions_list_key())
            await cache_delete(redis, admin_jurisdiction_detail_key(jurisdiction_id))

        return {
            "status": "deleted",
            "id": str(jurisdiction["id"]),
            "city": jurisdiction["city"],
            "state": jurisdiction["state"],
            "detached_children": int(detached_children or 0),
        }


