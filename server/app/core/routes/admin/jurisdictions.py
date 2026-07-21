"""Admin jurisdictions routes (J5 split)."""
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


@router.post("/jurisdictions", dependencies=[Depends(require_admin)])
async def create_jurisdiction(request: JurisdictionCreateRequest):
    """Create or upsert a jurisdiction. Idempotent on (city, state)."""
    raw_city = request.city.strip()
    state = request.state.upper().strip()[:2]
    county = request.county.strip() if request.county else None

    if not raw_city or not state:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="City and state are required")

    async with get_connection() as conn:
        city = await _canonicalize_city(conn, raw_city, state)

        if not county:
            try:
                county_from_ref = await conn.fetchval(
                    "SELECT county FROM jurisdiction_reference WHERE city = $1 AND state = $2",
                    city,
                    state,
                )
                if county_from_ref:
                    county = county_from_ref
            except asyncpg.UndefinedTableError:
                pass

        # Validate parent_id if provided
        if request.parent_id is not None:
            parent = await conn.fetchrow("SELECT id FROM jurisdictions WHERE id = $1", request.parent_id)
            if not parent:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Parent jurisdiction not found")

            # Reject self-reference before upserting to avoid mutating existing data
            existing = await conn.fetchrow(
                "SELECT id FROM jurisdictions WHERE city = $1 AND state = $2", city, state
            )
            if existing and existing["id"] == request.parent_id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A jurisdiction cannot be its own parent")

        # Use a savepoint so the upsert is rolled back if anything goes wrong,
        # preventing partial mutations on error.
        tr = conn.transaction()
        await tr.start()
        try:
            display_name = f"{raw_city.strip()}, {state}" if city else state
            row = await conn.fetchrow("""
                INSERT INTO jurisdictions (city, state, county, parent_id, display_name)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (COALESCE(city, ''), COALESCE(state, ''), country_code) DO UPDATE SET
                    parent_id = COALESCE(EXCLUDED.parent_id, jurisdictions.parent_id),
                    county = COALESCE(EXCLUDED.county, jurisdictions.county)
                RETURNING *
            """, city, state, county, request.parent_id, display_name)
            await tr.commit()
        except Exception:
            await tr.rollback()
            raise

        # Fetch parent info if set
        parent_city = None
        parent_state = None
        if row["parent_id"]:
            prow = await conn.fetchrow("SELECT city, state FROM jurisdictions WHERE id = $1", row["parent_id"])
            if prow:
                parent_city = prow["city"]
                parent_state = prow["state"]

        def fmt_date(d):
            return d.isoformat() if d else None

        redis = get_redis_cache()
        if redis:
            await cache_delete(redis, admin_jurisdictions_list_key())

        return {
            "id": str(row["id"]),
            "city": row["city"],
            "state": row["state"],
            "county": row["county"],
            "parent_id": str(row["parent_id"]) if row["parent_id"] else None,
            "parent_city": parent_city,
            "parent_state": parent_state,
            "requirement_count": row["requirement_count"] or 0,
            "legislation_count": row["legislation_count"] or 0,
            "last_verified_at": fmt_date(row["last_verified_at"]),
            "created_at": fmt_date(row["created_at"]),
        }


@router.get("/jurisdictions", dependencies=[Depends(require_admin)])
async def list_jurisdictions():
    """List all jurisdictions with requirement/legislation counts and linked locations."""
    redis = get_redis_cache()
    if redis:
        cached = await cache_get(redis, admin_jurisdictions_list_key())
        if cached is not None:
            return cached

    async with get_connection() as conn:
        all_rows = await conn.fetch("""
            SELECT
                j.id,
                j.city,
                j.state,
                j.county,
                j.parent_id,
                pj.city AS parent_city,
                pj.state AS parent_state,
                j.requirement_count,
                j.legislation_count,
                j.last_verified_at,
                j.created_at,
                COUNT(bl.id) AS location_count,
                COUNT(CASE WHEN bl.auto_check_enabled THEN 1 END) AS auto_check_count,
                (SELECT COUNT(*) FROM jurisdictions cj WHERE cj.parent_id = j.id) AS children_count
            FROM jurisdictions j
            LEFT JOIN jurisdictions pj ON pj.id = j.parent_id
            LEFT JOIN business_locations bl ON bl.jurisdiction_id = j.id AND bl.is_active = true
            GROUP BY j.id, pj.city, pj.state
            ORDER BY j.state, j.city
        """)

        # Hide state/county/system rows from the main source-of-truth listing.
        rows = [row for row in all_rows if not _is_non_city_jurisdiction(row["city"])]

        # Collapse duplicate city rows that differ only by casing/alias history.
        duplicate_groups: dict[tuple[str, str], list] = {}
        for row in rows:
            key = (row["state"], _normalize_city_input(row["city"]))
            duplicate_groups.setdefault(key, []).append(row)

        deduped_rows = []
        grouped_rows_by_primary_id: dict[UUID, list] = {}
        for group_rows in duplicate_groups.values():
            def _row_priority(r):
                last_verified_at = r["last_verified_at"]
                created_at = r["created_at"]
                return (
                    (r["requirement_count"] or 0) + (r["legislation_count"] or 0),
                    r["location_count"] or 0,
                    r["auto_check_count"] or 0,
                    1 if last_verified_at is not None else 0,
                    last_verified_at or datetime.min,
                    1 if created_at is not None else 0,
                    created_at or datetime.min,
                )

            primary = max(group_rows, key=_row_priority)
            deduped_rows.append(primary)
            grouped_rows_by_primary_id[primary["id"]] = group_rows

        jurisdiction_ids = [row["id"] for row in rows]
        parent_relationships: dict[UUID, UUID] = {
            row["id"]: row["parent_id"]
            for row in rows
            if row["parent_id"] is not None
        }

        inherits_from_parent_map: dict[UUID, bool] = {}
        if parent_relationships:
            related_jurisdiction_ids = list(set(jurisdiction_ids + list(parent_relationships.values())))

            requirement_rows = await conn.fetch(
                """
                SELECT jurisdiction_id, requirement_key, current_value, numeric_value, effective_date, expiration_date
                FROM jurisdiction_requirements
                WHERE jurisdiction_id = ANY($1::uuid[])
                """,
                related_jurisdiction_ids,
            )
            legislation_rows = await conn.fetch(
                """
                SELECT jurisdiction_id, legislation_key, current_status, expected_effective_date
                FROM jurisdiction_legislation
                WHERE jurisdiction_id = ANY($1::uuid[])
                """,
                related_jurisdiction_ids,
            )

            requirements_by_jurisdiction: dict[UUID, dict[str, tuple[str, str, str, str]]] = {}
            for req in requirement_rows:
                requirements_by_jurisdiction.setdefault(req["jurisdiction_id"], {})[req["requirement_key"]] = (
                    req["current_value"] or "",
                    str(req["numeric_value"]) if req["numeric_value"] is not None else "",
                    req["effective_date"].isoformat() if req["effective_date"] else "",
                    req["expiration_date"].isoformat() if req["expiration_date"] else "",
                )

            legislation_by_jurisdiction: dict[UUID, dict[str, tuple[str, str]]] = {}
            for leg in legislation_rows:
                legislation_by_jurisdiction.setdefault(leg["jurisdiction_id"], {})[leg["legislation_key"]] = (
                    leg["current_status"] or "",
                    leg["expected_effective_date"].isoformat() if leg["expected_effective_date"] else "",
                )

            for child_id, parent_id in parent_relationships.items():
                child_requirements = requirements_by_jurisdiction.get(child_id, {})
                parent_requirements = requirements_by_jurisdiction.get(parent_id, {})
                child_legislation = legislation_by_jurisdiction.get(child_id, {})
                parent_legislation = legislation_by_jurisdiction.get(parent_id, {})

                parent_has_content = bool(parent_requirements) or bool(parent_legislation)
                requirements_match_parent = all(
                    parent_requirements.get(req_key) == req_signature
                    for req_key, req_signature in child_requirements.items()
                )
                legislation_match_parent = all(
                    parent_legislation.get(leg_key) == leg_signature
                    for leg_key, leg_signature in child_legislation.items()
                )

                inherits_from_parent_map[child_id] = (
                    parent_has_content and requirements_match_parent and legislation_match_parent
                )

        # Batch-fetch all locations for all jurisdictions in one query (avoids N+1)
        all_locations = await conn.fetch("""
            SELECT bl.id, bl.jurisdiction_id, bl.name, bl.city, bl.state, bl.company_id,
                   c.name AS company_name, bl.auto_check_enabled, bl.auto_check_interval_days,
                   bl.next_auto_check, bl.last_compliance_check
            FROM business_locations bl
            JOIN companies c ON c.id = bl.company_id
            WHERE bl.jurisdiction_id = ANY($1::uuid[]) AND bl.is_active = true
            ORDER BY c.name, bl.name
        """, jurisdiction_ids)

        # Group locations by jurisdiction_id
        locations_by_jid: dict[UUID, list] = {}
        for loc in all_locations:
            locations_by_jid.setdefault(loc["jurisdiction_id"], []).append(loc)

        jurisdictions = []
        for row in deduped_rows:
            grouped_rows = grouped_rows_by_primary_id.get(row["id"], [row])
            grouped_ids = [r["id"] for r in grouped_rows]

            merged_locations = []
            for gid in grouped_ids:
                merged_locations.extend(locations_by_jid.get(gid, []))

            locations_by_id = {str(loc["id"]): loc for loc in merged_locations}
            locations = list(locations_by_id.values())

            requirement_count = max((r["requirement_count"] or 0) for r in grouped_rows)
            legislation_count = max((r["legislation_count"] or 0) for r in grouped_rows)
            children_count = max((r["children_count"] or 0) for r in grouped_rows)

            parent_row = next((r for r in grouped_rows if r["parent_id"] is not None), row)
            parent_id = parent_row["parent_id"]
            parent_city = parent_row["parent_city"]
            parent_state = parent_row["parent_state"]

            last_verified_values = [r["last_verified_at"] for r in grouped_rows if r["last_verified_at"]]
            last_verified_at = max(last_verified_values) if last_verified_values else None
            created_values = [r["created_at"] for r in grouped_rows if r["created_at"]]
            created_at = min(created_values) if created_values else None

            inherits_from_parent = any(inherits_from_parent_map.get(r["id"], False) for r in grouped_rows)

            jurisdictions.append({
                "id": str(row["id"]),
                "city": row["city"],
                "state": row["state"],
                "county": row["county"],
                "parent_id": str(parent_id) if parent_id else None,
                "parent_city": parent_city,
                "parent_state": parent_state,
                "children_count": children_count,
                "requirement_count": requirement_count,
                "legislation_count": legislation_count,
                "location_count": len(locations),
                "auto_check_count": sum(1 for loc in locations if loc["auto_check_enabled"]),
                "inherits_from_parent": inherits_from_parent,
                "last_verified_at": last_verified_at.isoformat() if last_verified_at else None,
                "created_at": created_at.isoformat() if created_at else None,
                "locations": [
                    {
                        "id": str(loc["id"]),
                        "name": loc["name"],
                        "city": loc["city"],
                        "state": loc["state"],
                        "company_name": loc["company_name"],
                        "auto_check_enabled": loc["auto_check_enabled"],
                        "auto_check_interval_days": loc["auto_check_interval_days"],
                        "next_auto_check": loc["next_auto_check"].isoformat() if loc["next_auto_check"] else None,
                        "last_compliance_check": loc["last_compliance_check"].isoformat() if loc["last_compliance_check"] else None,
                    }
                    for loc in locations
                ],
            })

        total_requirements = sum(int(j["requirement_count"] or 0) for j in jurisdictions)
        total_legislation = sum(int(j["legislation_count"] or 0) for j in jurisdictions)

        # The north-star: how many live requirements carry a verified statute
        # citation. This is what makes the library authoritative rather than just
        # researched — both funnels (ScopeStudio + Jurisdictions) push it up.
        total_codified = await conn.fetchval(
            "SELECT COUNT(*) FROM jurisdiction_requirements "
            "WHERE COALESCE(status, 'active') = 'active' "
            "AND citation_verified_at IS NOT NULL"
        ) or 0

        result = {
            "jurisdictions": jurisdictions,
            "totals": {
                "total_jurisdictions": len(jurisdictions),
                "total_requirements": total_requirements,
                "total_legislation": total_legislation,
                "total_codified": int(total_codified),
            },
        }

    if redis:
        await cache_set(redis, admin_jurisdictions_list_key(), result, ttl=600)

    return result


@router.get("/jurisdictions/tree", dependencies=[Depends(require_admin)])
async def get_jurisdictions_tree():
    """Geography-hierarchy view of the registry for the Library shelf.

    The flat `/admin/jurisdictions` list deliberately HIDES federal/state/county
    rows (`_is_non_city_jurisdiction`), so Library could never show state-level or
    federal general employment law. This returns the full hierarchy — federal
    pinned, then per-state groups carrying the state-level node + its county/city
    children — so the tree can nest and every level's detail is reachable.

    City rows are deduped by normalized city+state (same casing/alias collapse as
    the flat list); state/federal/county rows pass through untouched.
    """
    async with get_connection() as conn:
        rows = await conn.fetch("""
            SELECT j.id, j.city, j.state, j.county, j.parent_id,
                   j.level::text AS level, j.display_name,
                   j.requirement_count, j.legislation_count, j.last_verified_at,
                   COUNT(bl.id) FILTER (WHERE bl.is_active = true) AS location_count
            FROM jurisdictions j
            LEFT JOIN business_locations bl ON bl.jurisdiction_id = j.id
            GROUP BY j.id
        """)

        def node(r) -> dict:
            return {
                "id": str(r["id"]),
                "city": r["city"],
                "state": r["state"],
                "county": r["county"],
                "level": r["level"],
                "parent_id": str(r["parent_id"]) if r["parent_id"] else None,
                "display_name": r["display_name"],
                "requirement_count": r["requirement_count"] or 0,
                "legislation_count": r["legislation_count"] or 0,
                "location_count": int(r["location_count"] or 0),
                "last_verified_at": r["last_verified_at"].isoformat() if r["last_verified_at"] else None,
            }

        federal: list = []
        state_nodes: dict = {}          # state code -> state-level node
        children_by_state: dict = {}    # state code -> [county/city nodes]
        seen_city: dict = {}            # (state, normalized city) -> node (dedupe)

        for r in rows:
            level = r["level"]
            # Some legacy rows carry a NULL state; bucket them under '' so grouping
            # + sort never sees a None (a real TypeError we hit in the wild).
            st = r["state"] or ""
            if level in ("federal", "national"):
                federal.append(node(r))
                continue
            if level == "state":
                # Keep the richest of any duplicate state rows.
                cur = state_nodes.get(st)
                n = node(r)
                if cur is None or (n["requirement_count"] + n["legislation_count"]) > (
                    cur["requirement_count"] + cur["legislation_count"]
                ):
                    state_nodes[st] = n
                continue
            # county / city / everything else → child of its state group
            if not _is_non_city_jurisdiction(r["city"]):
                key = (st, _normalize_city_input(r["city"] or ""))
                existing = seen_city.get(key)
                n = node(r)
                if existing is not None:
                    # Collapse casing/alias dupes; keep the richer row.
                    if (n["requirement_count"] + n["legislation_count"]) <= (
                        existing["requirement_count"] + existing["legislation_count"]
                    ):
                        continue
                    children_by_state[st].remove(existing)
                seen_city[key] = n
            else:
                n = node(r)  # county rows (_county_ prefix) — pass through
            children_by_state.setdefault(st, []).append(n)

        states = []
        for code in sorted(set(list(state_nodes.keys()) + list(children_by_state.keys()))):
            kids = sorted(
                children_by_state.get(code, []),
                key=lambda x: (x["city"] or "").lower(),
            )
            states.append({
                "code": code,
                "state_node": state_nodes.get(code),
                "children": kids,
            })

        # Both counts are active-only, and codified is the full trio — otherwise
        # this tile's ratio disagrees with the Authoritative meter in the studio
        # header directly above it (the denominator used to include pending +
        # under_review + repealed rows, and the numerator a looser predicate).
        total_requirements = await conn.fetchval(
            "SELECT COUNT(*) FROM jurisdiction_requirements "
            "WHERE COALESCE(status, 'active') = 'active'"
        ) or 0
        total_legislation = await conn.fetchval("SELECT COUNT(*) FROM jurisdiction_legislation") or 0
        total_codified = await conn.fetchval(
            "SELECT COUNT(*) FROM jurisdiction_requirements jr "
            f"WHERE COALESCE(jr.status, 'active') = 'active' AND {codified_sql('jr')}"
        ) or 0
        total_places = sum(len(s["children"]) for s in states)

    return {
        "federal": sorted(federal, key=lambda x: x["display_name"] or ""),
        "states": states,
        "totals": {
            "total_jurisdictions": total_places,
            "total_requirements": int(total_requirements),
            "total_legislation": int(total_legislation),
            "total_codified": int(total_codified),
        },
    }


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


@router.get("/jurisdictions/categories/{slug}", dependencies=[Depends(require_admin)])
async def get_category_detail(slug: str, state: str = Query(default=None)):
    """Full detail for a compliance category: description, domain, and all regulation key definitions with coverage stats."""
    async with get_connection() as conn:
        # Get category info
        cat = await conn.fetchrow(
            'SELECT id, slug, name, description, domain::text, "group" FROM compliance_categories WHERE slug = $1',
            slug
        )
        if not cat:
            raise HTTPException(status_code=404, detail="Category not found")

        # Get all key definitions for this category with coverage stats
        state_filter = ""
        params = [slug]
        if state:
            state_filter = "AND jr.jurisdiction_id IN (SELECT id FROM jurisdictions WHERE state = $2)"
            params.append(state)

        keys = await conn.fetch(f"""
            SELECT rkd.id, rkd.key, rkd.name, rkd.description,
                   rkd.state_variance, rkd.enforcing_agency, rkd.base_weight,
                   rkd.key_group, rkd.staleness_warning_days, rkd.created_at,
                   COUNT(jr.id) AS jurisdiction_count,
                   COUNT(jr.id) FILTER (WHERE jr.change_status = 'changed') AS changed_count,
                   COUNT(jr.id) FILTER (WHERE jr.change_status = 'new') AS new_count,
                   MIN(jr.last_verified_at) AS oldest_verified,
                   CASE
                       WHEN COUNT(jr.id) = 0 THEN 'no_data'
                       WHEN MIN(jr.last_verified_at) < NOW() - (rkd.staleness_expired_days || ' days')::interval THEN 'expired'
                       WHEN MIN(jr.last_verified_at) < NOW() - (rkd.staleness_critical_days || ' days')::interval THEN 'critical'
                       WHEN MIN(jr.last_verified_at) < NOW() - (rkd.staleness_warning_days || ' days')::interval THEN 'warning'
                       ELSE 'fresh'
                   END AS staleness_level
            FROM regulation_key_definitions rkd
            LEFT JOIN jurisdiction_requirements jr
                ON jr.key_definition_id = rkd.id {state_filter}
            WHERE rkd.category_slug = $1
            GROUP BY rkd.id
            ORDER BY rkd.key
        """, *params)

        total_reqs = sum(r["jurisdiction_count"] for r in keys)

        # Get states that have jurisdictions (for filter dropdown)
        available_states = await conn.fetch(
            "SELECT DISTINCT state FROM jurisdictions WHERE state IS NOT NULL ORDER BY state"
        )

        def fmt_date(d):
            return d.isoformat() if d else None

        return {
            "slug": cat["slug"],
            "name": cat["name"],
            "description": cat["description"],
            "domain": cat["domain"],
            "group": cat["group"],
            "key_count": len(keys),
            "requirement_count": total_reqs,
            "state_filter": state,
            "available_states": [r["state"] for r in available_states],
            "keys": [
                {
                    "id": str(r["id"]),
                    "key": r["key"],
                    "name": r["name"],
                    "description": r["description"],
                    "state_variance": r["state_variance"],
                    "enforcing_agency": r["enforcing_agency"],
                    "base_weight": float(r["base_weight"]) if r["base_weight"] else 1.0,
                    "key_group": r["key_group"],
                    "jurisdiction_count": r["jurisdiction_count"],
                    "changed_count": r["changed_count"],
                    "new_count": r["new_count"],
                    "staleness_level": r["staleness_level"],
                    "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                }
                for r in keys
            ],
        }


@router.get("/jurisdictions/policies/{key_definition_id}", dependencies=[Depends(require_admin)])
async def get_policy_detail(key_definition_id: UUID):
    """Full detail for a regulation key: definition + all jurisdiction instances + change log."""
    async with get_connection() as conn:
        # Key definition
        kd = await conn.fetchrow("""
            SELECT rkd.id, rkd.key, rkd.category_slug, rkd.name, rkd.description,
                   rkd.state_variance, rkd.enforcing_agency, rkd.base_weight,
                   rkd.authority_source_urls, rkd.applies_to_levels,
                   rkd.staleness_warning_days, rkd.staleness_critical_days,
                   rkd.staleness_expired_days, rkd.key_group, rkd.update_frequency,
                   cc.name AS category_name
            FROM regulation_key_definitions rkd
            JOIN compliance_categories cc ON cc.id = rkd.category_id
            WHERE rkd.id = $1
        """, key_definition_id)
        if not kd:
            raise HTTPException(status_code=404, detail="Key definition not found")

        # All jurisdiction instances
        reqs = await conn.fetch("""
            SELECT jr.id, jr.jurisdiction_id, jr.title, jr.description,
                   jr.current_value, jr.previous_value, jr.previous_description,
                   jr.change_status, jr.effective_date, jr.source_url, jr.source_name,
                   jr.source_url_status, jr.statute_citation, jr.citation_item_id,
                   jr.citation_verified_at, jr.metadata->'drift' AS drift,
                   jr.last_verified_at, jr.last_changed_at, jr.requires_written_policy,
                   j.city, j.state, j.display_name, j.level::text AS jur_level
            FROM jurisdiction_requirements jr
            JOIN jurisdictions j ON j.id = jr.jurisdiction_id
            WHERE jr.key_definition_id = $1
            ORDER BY j.state, j.city NULLS FIRST
        """, key_definition_id)

        # Recent change log entries
        change_log = await conn.fetch("""
            SELECT pcl.field_changed, pcl.old_value, pcl.new_value,
                   pcl.changed_at, pcl.change_source,
                   j.display_name AS jurisdiction_name
            FROM policy_change_log pcl
            JOIN jurisdiction_requirements jr ON jr.id = pcl.requirement_id
            JOIN jurisdictions j ON j.id = jr.jurisdiction_id
            WHERE jr.key_definition_id = $1
            ORDER BY pcl.changed_at DESC
            LIMIT 50
        """, key_definition_id)

        def fmt_date(d):
            return d.isoformat() if d else None

        return {
            "id": str(kd["id"]),
            "key": kd["key"],
            "category_slug": kd["category_slug"],
            "category_name": kd["category_name"],
            "name": kd["name"],
            "description": kd["description"],
            "state_variance": kd["state_variance"],
            "enforcing_agency": kd["enforcing_agency"],
            "base_weight": float(kd["base_weight"]) if kd["base_weight"] else 1.0,
            "authority_source_urls": kd["authority_source_urls"],
            "applies_to_levels": kd["applies_to_levels"],
            "staleness_warning_days": kd["staleness_warning_days"],
            "staleness_critical_days": kd["staleness_critical_days"],
            "update_frequency": kd["update_frequency"],
            "key_group": kd["key_group"],
            "jurisdictions": [
                {
                    "requirement_id": str(r["id"]),
                    "jurisdiction_id": str(r["jurisdiction_id"]),
                    "state": r["state"],
                    "city": r["city"],
                    "display_name": r["display_name"],
                    "level": r["jur_level"],
                    "title": r["title"],
                    "description": r["description"],
                    "current_value": r["current_value"],
                    "previous_value": r["previous_value"],
                    "previous_description": r["previous_description"],
                    "change_status": r["change_status"],
                    "effective_date": fmt_date(r["effective_date"]),
                    "source_url": r["source_url"],
                    "source_name": r["source_name"],
                    "source_url_status": r["source_url_status"],
                    "statute_citation": r["statute_citation"],
                    "citation_item_id": str(r["citation_item_id"]) if r["citation_item_id"] else None,
                    "citation_verified": r["citation_verified_at"] is not None and r["citation_item_id"] is not None,
                    "drift": _row_metadata(r["drift"]) or None,
                    "requires_written_policy": r["requires_written_policy"],
                    "last_verified_at": fmt_date(r["last_verified_at"]),
                    "last_changed_at": fmt_date(r["last_changed_at"]),
                }
                for r in reqs
            ],
            "change_log": [
                {
                    "jurisdiction_name": r["jurisdiction_name"],
                    "field_changed": r["field_changed"],
                    "old_value": r["old_value"],
                    "new_value": r["new_value"],
                    "changed_at": fmt_date(r["changed_at"]),
                    "change_source": r["change_source"],
                }
                for r in change_log
            ],
        }


@router.post("/jurisdictions/evals/run")
async def trigger_eval_run(
    payload: EvalRunRequest,
    background: BackgroundTasks,
    current_user=Depends(require_admin),
):
    """Start an eval run. Network-touching suites go to Celery; the rest run inline."""
    from app.core.services.compliance_evals import network_suites, run_evals

    suites = list(payload.suites)
    if not suites:
        raise HTTPException(status_code=400, detail="At least one suite is required")

    jurisdiction_ids = [str(j) for j in (payload.jurisdiction_ids or [])] or None

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO compliance_eval_runs (suites, trigger_source, triggered_by, params)
            VALUES ($1, 'manual', $2, $3) RETURNING id
            """,
            suites,
            current_user.id,
            json.dumps({
                "jurisdiction_ids": jurisdiction_ids,
                "industries": payload.industries,
            }),
        )
    run_id = row["id"]

    if network_suites() & set(suites):
        from app.workers.tasks.compliance_evals import run_compliance_evals

        run_compliance_evals.delay(
            suites=suites,
            jurisdiction_ids=jurisdiction_ids,
            industries=payload.industries,
            triggered_by=str(current_user.id),
            trigger_source="manual",
            run_id=str(run_id),
        )
        dispatched = "celery"
    else:
        background.add_task(
            run_evals,
            suites=suites,
            jurisdiction_ids=jurisdiction_ids,
            industries=payload.industries,
            triggered_by=current_user.id,
            trigger_source="manual",
            run_id=run_id,
        )
        dispatched = "inline"

    return {
        "run_id": str(run_id),
        "status": "running",
        "dispatched_to": dispatched,
        "suites": suites,
    }


@router.get("/jurisdictions/evals/runs", dependencies=[Depends(require_admin)])
async def list_eval_runs(limit: int = Query(20, ge=1, le=100)):
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT id, suites, status, trigger_source, totals, error_text,
                   started_at, finished_at
            FROM compliance_eval_runs
            ORDER BY started_at DESC
            LIMIT $1
            """,
            limit,
        )
    return {
        "runs": [
            {
                "id": str(r["id"]),
                "suites": list(r["suites"] or []),
                "status": r["status"],
                "trigger_source": r["trigger_source"],
                "totals": _eval_json(r["totals"]),
                "error_text": r["error_text"],
                "started_at": _eval_iso(r["started_at"]),
                "finished_at": _eval_iso(r["finished_at"]),
            }
            for r in rows
        ]
    }


@router.get("/jurisdictions/evals/runs/{run_id}", dependencies=[Depends(require_admin)])
async def get_eval_run(
    run_id: UUID,
    suite: Optional[str] = None,
    severity: Optional[str] = None,
    finding_status: Optional[str] = Query(None, alias="status"),
    jurisdiction_id: Optional[UUID] = None,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    async with get_connection() as conn:
        run = await conn.fetchrow(
            "SELECT id, suites, status, trigger_source, totals, error_text, "
            "started_at, finished_at FROM compliance_eval_runs WHERE id = $1",
            run_id,
        )
        if not run:
            raise HTTPException(status_code=404, detail="Eval run not found")

        clauses = ["f.run_id = $1"]
        params: List[Any] = [run_id]
        for value, column in (
            (suite, "f.suite"),
            (severity, "f.severity"),
            (finding_status, "f.status"),
        ):
            if value:
                params.append(value)
                clauses.append(f"{column} = ${len(params)}")
        if jurisdiction_id:
            params.append(jurisdiction_id)
            clauses.append(f"f.jurisdiction_id = ${len(params)}")

        where = " AND ".join(clauses)
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM compliance_eval_findings f WHERE {where}", *params
        )
        params.extend([limit, offset])
        findings = await conn.fetch(
            f"""
            SELECT f.id, f.suite, f.finding_type, f.severity, f.jurisdiction_id,
                   f.requirement_id, f.requirement_key, f.category, f.industry,
                   f.expected, f.observed, f.status, f.notes, f.created_at,
                   COALESCE(NULLIF(j.city, ''), j.state, j.display_name) AS jurisdiction_label,
                   j.state
            FROM compliance_eval_findings f
            LEFT JOIN jurisdictions j ON j.id = f.jurisdiction_id
            WHERE {where}
            ORDER BY
                CASE f.severity WHEN 'critical' THEN 0 WHEN 'warn' THEN 1 ELSE 2 END,
                f.created_at
            LIMIT ${len(params) - 1} OFFSET ${len(params)}
            """,
            *params,
        )

        counts = await conn.fetch(
            "SELECT finding_type, severity, COUNT(*) AS n FROM compliance_eval_findings "
            "WHERE run_id = $1 GROUP BY finding_type, severity ORDER BY n DESC",
            run_id,
        )

    return {
        "run": {
            "id": str(run["id"]),
            "suites": list(run["suites"] or []),
            "status": run["status"],
            "trigger_source": run["trigger_source"],
            "totals": _eval_json(run["totals"]),
            "error_text": run["error_text"],
            "started_at": _eval_iso(run["started_at"]),
            "finished_at": _eval_iso(run["finished_at"]),
        },
        "finding_counts": [
            {"finding_type": c["finding_type"], "severity": c["severity"], "count": c["n"]}
            for c in counts
        ],
        "total": total,
        "findings": [
            {
                "id": str(f["id"]),
                "suite": f["suite"],
                "finding_type": f["finding_type"],
                "severity": f["severity"],
                "jurisdiction_id": str(f["jurisdiction_id"]) if f["jurisdiction_id"] else None,
                "jurisdiction_label": _jurisdiction_label(f["jurisdiction_label"], f["state"]),
                "requirement_id": str(f["requirement_id"]) if f["requirement_id"] else None,
                "requirement_key": f["requirement_key"],
                "category": f["category"],
                "industry": f["industry"],
                "expected": _eval_json(f["expected"]),
                "observed": _eval_json(f["observed"]),
                "status": f["status"],
                "notes": f["notes"],
                "created_at": _eval_iso(f["created_at"]),
            }
            for f in findings
        ],
    }


@router.get("/jurisdictions/evals/scorecard", dependencies=[Depends(require_admin)])
async def eval_scorecard(
    jurisdiction_id: Optional[UUID] = None,
    industry: Optional[str] = None,
):
    """Latest composite cell per (jurisdiction × industry).

    `DISTINCT ON` over `created_at DESC` so a partial re-run of one suite never
    erases an older cell from a suite it did not measure.
    """
    clauses = ["r.suite = 'composite'"]
    params: List[Any] = []
    if jurisdiction_id:
        params.append(jurisdiction_id)
        clauses.append(f"r.jurisdiction_id = ${len(params)}")
    if industry:
        params.append(industry)
        clauses.append(f"r.industry = ${len(params)}")
    where = " AND ".join(clauses)

    async with get_connection() as conn:
        rows = await conn.fetch(
            f"""
            SELECT DISTINCT ON (r.jurisdiction_id, r.industry)
                   r.jurisdiction_id, r.industry, r.score, r.detail,
                   r.onboarding_ready, r.created_at,
                   COALESCE(NULLIF(j.city, ''), j.state, j.display_name) AS label, j.state
            FROM compliance_eval_results r
            JOIN jurisdictions j ON j.id = r.jurisdiction_id
            WHERE {where}
            ORDER BY r.jurisdiction_id, r.industry, r.created_at DESC
            """,
            *params,
        )

    cells = []
    for r in rows:
        detail = _eval_json(r["detail"]) or {}
        cells.append({
            "jurisdiction_id": str(r["jurisdiction_id"]),
            "jurisdiction_label": _jurisdiction_label(r["label"], r["state"]),
            "industry": r["industry"],
            "composite": float(r["score"]) if r["score"] is not None else None,
            "onboarding_ready": r["onboarding_ready"],
            "status": detail.get("status"),
            "subscores": detail.get("subscores", {}),
            "blocking": detail.get("blocking", []),
            "measured_at": _eval_iso(r["created_at"]),
        })
    return {"cells": cells}


@router.get("/jurisdictions/evals/onboarding-readiness", dependencies=[Depends(require_admin)])
async def eval_onboarding_readiness(
    industry: str,
    state: Optional[str] = None,
    city: Optional[str] = None,
    country_code: str = "US",
    depth: str = Query("core", pattern="^(core|full)$"),
):
    """Can a company in `industry` onboard into this location with the data we hold?

    `depth=core` (default) scores the <=30-key must-have checklist — small enough
    that a human can verify the eval itself. `depth=full` scores the entire
    registry sweep (180 keys for manufacturing). Industries without a curated core
    fall back to `full` rather than pretend a checklist exists.
    """
    from app.core.services.compliance_evals import onboarding_readiness
    from app.core.services.compliance_evals.industry_keysets import has_core, resolve_industry

    if not state:
        raise HTTPException(status_code=400, detail="state is required")

    if depth == "core" and not has_core(resolve_industry(industry) or industry):
        depth = "full"

    async with get_connection() as conn:
        return await onboarding_readiness(
            conn, industry=industry, state=state, city=city,
            country_code=country_code, depth=depth,
        )


@router.get("/jurisdictions/evals/core-checklist", dependencies=[Depends(require_admin)])
async def eval_core_checklist(
    industry: str,
    state: str,
    city: Optional[str] = None,
    country_code: str = "US",
):
    """The <=30-key must-have checklist, one row per key, present/missing.

    Deliberately small: the full sweep expects 180 keys for manufacturing and 237
    for healthcare, which nobody can audit by hand, so a bad expectation set would
    go unnoticed. Every key here is individually defensible and every miss is
    critical by construction.
    """
    from app.core.services.compliance_evals import completeness as completeness_suite
    from app.core.services.compliance_evals.industry_keysets import has_core, resolve_industry

    canonical = resolve_industry(industry) or industry
    if not has_core(canonical):
        raise HTTPException(
            status_code=400,
            detail=f"No core checklist curated for industry '{canonical}'",
        )

    async with get_connection() as conn:
        if city:
            row = await conn.fetchrow(
                "SELECT id FROM jurisdictions WHERE LOWER(city)=LOWER($1) AND state=$2 "
                "AND COALESCE(country_code,'US')=$3 LIMIT 1",
                city, state, country_code,
            )
        else:
            row = await conn.fetchrow(
                "SELECT id FROM jurisdictions WHERE level::text='state' AND state=$1 "
                "AND COALESCE(country_code,'US')=$2 LIMIT 1",
                state, country_code,
            )
        if not row:
            raise HTTPException(status_code=404, detail="No jurisdiction record for this location")

        graph = await completeness_suite.load_jurisdiction_graph(conn)
        checklist = completeness_suite.core_checklist(graph, row["id"], canonical)

    return {
        "industry": canonical,
        "jurisdiction": ", ".join(p for p in (city, state) if p),
        **checklist,
    }


@router.get("/jurisdictions/evals/baseline-checklist", dependencies=[Depends(require_admin)])
async def eval_baseline_checklist():
    """The enumerated federal + CA-state labor master-list, one row per obligation,
    present/missing against each base jurisdiction's own catalog (with citation).

    This is the answer to "is federal/state actually done?" — the baseline suite's
    per-entry detail. Missing entries carry the citation to research next.
    """
    from app.core.services.compliance_evals.baseline import baseline_scorecard

    out = []
    async with get_connection() as conn:
        for card in await baseline_scorecard(conn):
            out.append({
                "label": card["spec"]["label"],
                "jurisdiction_found": card["jid"] is not None,
                "expected": card["expected"],
                "present": len(card["present"]),
                "score": card["score"],
                "items": card["items"],
            })
    return {"jurisdictions": out}


@router.post("/jurisdictions/evals/findings/{finding_id}/resolve")
async def resolve_eval_finding(
    finding_id: UUID,
    payload: FindingResolveRequest,
    current_user=Depends(require_admin),
):
    """Adjudicate a finding.

    Never writes to `jurisdiction_requirements`: marking a finding `fixed` records
    the admin's judgement, and the catalog edit happens through the existing
    requirement-editing surfaces. Keeping the eval read-only is what lets a later
    run independently confirm the fix.
    """
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            UPDATE compliance_eval_findings
            SET status = $2, notes = COALESCE($3, notes),
                resolved_by = $4, resolved_at = NOW()
            WHERE id = $1
            RETURNING id, status
            """,
            finding_id, payload.status, payload.notes, current_user.id,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Finding not found")
    return {"id": str(row["id"]), "status": row["status"]}


@router.get("/jurisdictions/evals/golden", dependencies=[Depends(require_admin)])
async def list_golden_facts():
    """The curated fact corpus with its active/pending/expired state."""
    from datetime import date as _date

    from app.core.services.compliance_evals.golden import load_fixtures

    today = _date.today()
    facts = []
    for fixture in load_fixtures():
        jur = fixture.jurisdiction
        label = ", ".join(p for p in (jur.city, jur.state) if p) or jur.level
        for fact in fixture.facts:
            if fact.active_on(today):
                state_label = "active"
            elif fact.expired_on(today):
                state_label = "expired"
            else:
                state_label = "pending"
            facts.append({
                "jurisdiction": label,
                "requirement_key": fact.requirement_key,
                "category": fact.category,
                "comparator": fact.comparator,
                "severity": fact.severity,
                "effective_from": str(fact.effective_from),
                "effective_to": str(fact.effective_to) if fact.effective_to else None,
                "authority_url": fact.authority_url,
                "curated_by": fact.curated_by,
                "verified_by": fact.verified_by,
                "notes": fact.notes,
                "state": state_label,
            })
    return {
        "facts": facts,
        "total": len(facts),
        "active": sum(1 for f in facts if f["state"] == "active"),
        "unverified": sum(1 for f in facts if not f["verified_by"]),
    }


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


@router.post("/jurisdictions/top-metros/check", dependencies=[Depends(require_admin)])
async def check_top_metros():
    """Run streamed compliance checks for a hardcoded top-15 metro list."""

    async def event_stream():
        total = len(TOP_15_METROS)
        succeeded = 0
        failed = 0
        low_confidence_total = 0

        yield _to_sse(
            {
                "type": "run_started",
                "total": total,
                "metros": [m["label"] for m in TOP_15_METROS],
            }
        )

        for index, metro in enumerate(TOP_15_METROS, start=1):
            city = metro["city"]
            state = metro["state"]
            label = metro["label"]
            overall_percent = int(((index - 1) / total) * 100)

            try:
                jurisdiction_id = await _get_or_create_metro_jurisdiction(city, state)
                yield _to_sse(
                    {
                        "type": "city_started",
                        "city": label,
                        "state": state,
                        "index": index,
                        "total": total,
                        "overall_percent": overall_percent,
                    }
                )

                city_summary = {
                    "new": 0,
                    "updated": 0,
                    "alerts": 0,
                    "low_confidence": 0,
                }
                async for event in _run_jurisdiction_check_events(jurisdiction_id):
                    phase = event.get("type")
                    if phase == "heartbeat":
                        yield ": heartbeat\n\n"
                        continue

                    if phase == "completed":
                        city_summary["new"] = int(event.get("new", 0) or 0)
                        city_summary["updated"] = int(event.get("updated", 0) or 0)
                        city_summary["alerts"] = int(event.get("alerts", 0) or 0)
                        city_summary["low_confidence"] = int(event.get("low_confidence", 0) or 0)
                    elif phase == "error":
                        raise RuntimeError(event.get("message") or "Jurisdiction check failed")

                    yield _to_sse(
                        {
                            "type": "city_progress",
                            "city": label,
                            "state": state,
                            "index": index,
                            "total": total,
                            "phase": phase,
                            "percent": _phase_percent(phase or ""),
                            "message": event.get("message") or event.get("location") or "",
                            "confidence": event.get("confidence"),
                        }
                    )

                succeeded += 1
                low_confidence_total += city_summary["low_confidence"]
                overall_percent = int(((succeeded + failed) / total) * 100)
                yield _to_sse(
                    {
                        "type": "city_completed",
                        "city": label,
                        "state": state,
                        "index": index,
                        "total": total,
                        "overall_percent": overall_percent,
                        "new": city_summary["new"],
                        "updated": city_summary["updated"],
                        "alerts": city_summary["alerts"],
                        "low_confidence": city_summary["low_confidence"],
                    }
                )
            except Exception as exc:
                failed += 1
                overall_percent = int(((succeeded + failed) / total) * 100)
                logger.error("Top metro check failed for %s, %s: %s", label, state, exc, exc_info=True)
                yield _to_sse(
                    {
                        "type": "city_failed",
                        "city": label,
                        "state": state,
                        "index": index,
                        "total": total,
                        "overall_percent": overall_percent,
                        "message": str(exc),
                    }
                )

        yield _to_sse(
            {
                "type": "run_completed",
                "total": total,
                "succeeded": succeeded,
                "failed": failed,
                "low_confidence_total": low_confidence_total,
            }
        )
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no"},
    )


@router.post("/jurisdictions/{jurisdiction_id}/check", dependencies=[Depends(require_admin)])
async def check_jurisdiction(jurisdiction_id: UUID):
    """Run a compliance research check for a jurisdiction. Returns SSE stream with progress."""

    async with get_connection() as conn:
        exists = await conn.fetchval("SELECT 1 FROM jurisdictions WHERE id = $1", jurisdiction_id)
        if not exists:
            raise HTTPException(status_code=404, detail="Jurisdiction not found")

    async def event_stream():
        try:
            async for event in _run_jurisdiction_check_events(
                jurisdiction_id,
                inline_healthcare_research=True,
            ):
                if event.get("type") == "heartbeat":
                    yield ": heartbeat\n\n"
                else:
                    yield _to_sse(event)
        except HTTPException as exc:
            yield _to_sse({"type": "error", "message": str(exc.detail)})
        except Exception:
            logger.error("Jurisdiction check failed for %s", jurisdiction_id, exc_info=True)
            yield _to_sse({"type": "error", "message": "Jurisdiction check failed"})
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no"},
    )


@router.post("/jurisdictions/{jurisdiction_id}/check-specialty", dependencies=[Depends(require_admin)])
async def check_jurisdiction_specialty(jurisdiction_id: UUID):
    """Run healthcare + oncology specialty research for a jurisdiction. Returns SSE stream."""
    from app.core.services.compliance_service import (
        _research_healthcare_requirements_for_jurisdiction,
        _research_oncology_requirements_for_jurisdiction,
        _jurisdiction_row_to_dict,
        _filter_requirements_for_company,
        _filter_city_level_requirements,
        _filter_with_preemption,
        _normalize_requirement_categories,
        _sync_requirements_to_location,
        _lookup_has_local_ordinance,
    )

    async with get_connection() as conn:
        j = await conn.fetchrow("SELECT id, city, state FROM jurisdictions WHERE id = $1", jurisdiction_id)
        if not j:
            raise HTTPException(status_code=404, detail="Jurisdiction not found")
        location_label = f"{_format_city_label(j['city'])}, {j['state']}"

    async def event_stream():
        try:
            async with get_connection() as conn:
                yield _to_sse({"type": "started", "location": location_label})

                # Healthcare research
                yield _to_sse({
                    "type": "researching",
                    "message": f"Researching healthcare-specific compliance for {location_label}...",
                })
                try:
                    hc_result = await _research_healthcare_requirements_for_jurisdiction(
                        conn, jurisdiction_id
                    )
                    hc_new = hc_result.get("new", 0)
                    hc_failed = hc_result.get("failed", [])
                    yield _to_sse({
                        "type": "repository_refresh",
                        "message": f"Healthcare: +{hc_new} requirement(s) added."
                            + (f" Failed: {', '.join(hc_failed)}" if hc_failed else ""),
                    })
                except Exception as exc:
                    logger.warning("Healthcare specialty research failed: %s", exc)
                    yield _to_sse({"type": "warning", "message": f"Healthcare research failed: {exc}"})

                # Oncology research
                yield _to_sse({
                    "type": "researching",
                    "message": f"Researching oncology-specific compliance for {location_label}...",
                })
                try:
                    onc_result = await _research_oncology_requirements_for_jurisdiction(
                        conn, jurisdiction_id
                    )
                    onc_new = onc_result.get("new", 0)
                    onc_failed = onc_result.get("failed", [])
                    yield _to_sse({
                        "type": "repository_refresh",
                        "message": f"Oncology: +{onc_new} requirement(s) added."
                            + (f" Failed: {', '.join(onc_failed)}" if onc_failed else ""),
                    })
                except Exception as exc:
                    logger.warning("Oncology specialty research failed: %s", exc)
                    yield _to_sse({"type": "warning", "message": f"Oncology research failed: {exc}"})

                # Sync to linked locations
                linked = await conn.fetch(
                    """SELECT bl.id, bl.company_id
                       FROM business_locations bl
                       JOIN jurisdictions j ON LOWER(bl.city) = LOWER(j.city)
                           AND UPPER(bl.state) = UPPER(j.state)
                       WHERE j.id = $1""",
                    jurisdiction_id,
                )
                if linked:
                    yield _to_sse({
                        "type": "syncing",
                        "message": f"Syncing specialty updates to {len(linked)} location(s)...",
                    })
                    rows = await conn.fetch(
                        "SELECT * FROM jurisdiction_requirements WHERE jurisdiction_id = $1",
                        jurisdiction_id,
                    )
                    requirements = [_jurisdiction_row_to_dict(dict(r)) for r in rows]
                    # Apply same prep as inline research: filter city-level if no local ordinance, normalize, preemption
                    state = j["state"]
                    has_local = await _lookup_has_local_ordinance(conn, j["city"], state)
                    if has_local is False:
                        requirements = _filter_city_level_requirements(requirements, state)
                    _normalize_requirement_categories(requirements)
                    requirements = await _filter_with_preemption(conn, requirements, state)
                    total_synced = 0
                    for loc in linked:
                        loc_reqs = await _filter_requirements_for_company(
                            conn, loc["company_id"], requirements,
                        )
                        sync_result = await _sync_requirements_to_location(
                            conn, loc["id"], loc["company_id"], loc_reqs, create_alerts=True,
                        )
                        total_synced += sync_result.get("updated", 0)
                    yield _to_sse({
                        "type": "syncing",
                        "message": f"Synced to {len(linked)} location(s), {total_synced} update(s).",
                    })

                yield _to_sse({"type": "completed", "message": "Specialty research complete."})
        except Exception:
            logger.error("Specialty check failed for %s", jurisdiction_id, exc_info=True)
            yield _to_sse({"type": "error", "message": "Specialty research failed"})
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no"},
    )


@router.post("/jurisdictions/{jurisdiction_id}/check-medical-compliance", dependencies=[Depends(require_admin)])
async def check_jurisdiction_medical_compliance(jurisdiction_id: UUID):
    """Run medical compliance research (17 categories) for a jurisdiction. Returns SSE stream with per-category progress."""
    from app.core.compliance_registry import MEDICAL_COMPLIANCE_CATEGORIES, INDUSTRY_TAGS as MC_INDUSTRY_TAGS, CATEGORY_LABELS
    from app.core.services.compliance_service import (
        _lookup_has_local_ordinance,
        _clamp_varchar_fields,
        _upsert_requirements_additive,
        _jurisdiction_row_to_dict,
        _filter_requirements_for_company,
        _filter_city_level_requirements,
        _filter_with_preemption,
        _normalize_requirement_categories,
        _sync_requirements_to_location,
        get_recent_corrections,
        format_corrections_for_prompt,
    )
    from app.core.services.gemini_compliance import get_gemini_compliance_service
    from app.core.services.jurisdiction_context import get_known_sources, build_context_prompt, get_global_authority_sources

    async with get_connection() as conn:
        j = await conn.fetchrow("SELECT id, city, state, county FROM jurisdictions WHERE id = $1", jurisdiction_id)
        if not j:
            raise HTTPException(status_code=404, detail="Jurisdiction not found")
        location_label = f"{_format_city_label(j['city'])}, {j['state']}"

    async def event_stream():
        try:
            async with get_connection() as conn:
                yield _to_sse({"type": "started", "location": location_label})

                city = j["city"]
                state = j["state"]
                county = j.get("county")

                # Determine which categories still need research
                all_medical_cats = sorted(MEDICAL_COMPLIANCE_CATEGORIES)
                existing = await conn.fetch(
                    "SELECT DISTINCT category FROM jurisdiction_requirements WHERE jurisdiction_id = $1",
                    jurisdiction_id,
                )
                existing_cats = {r["category"] for r in existing}
                missing = [cat for cat in all_medical_cats if cat not in existing_cats]

                # Emit manifest: every category with its initial status
                yield _to_sse({
                    "type": "category_manifest",
                    "categories": [
                        {
                            "key": cat,
                            "label": CATEGORY_LABELS.get(cat, cat),
                            "status": "pending" if cat in missing else "complete",
                        }
                        for cat in all_medical_cats
                    ],
                })

                if not missing:
                    yield _to_sse({"type": "completed", "message": "All medical compliance categories already present.", "total_new": 0, "failed": []})
                    yield "data: [DONE]\n\n"
                    return

                # Gather context for Gemini prompts
                has_local_ordinance = await _lookup_has_local_ordinance(conn, city, state)
                known_sources = await get_known_sources(conn, jurisdiction_id)
                source_context = build_context_prompt(known_sources)
                source_context += get_global_authority_sources(list(MEDICAL_COMPLIANCE_CATEGORIES))
                corrections = await get_recent_corrections(jurisdiction_id)
                corrections_context = format_corrections_for_prompt(corrections)

                try:
                    preemption_rows = await conn.fetch(
                        "SELECT category, allows_local_override FROM state_preemption_rules WHERE state = $1",
                        state.upper(),
                    )
                    preemption_rules = {row["category"]: row["allows_local_override"] for row in preemption_rows}
                except Exception:
                    preemption_rules = {}

                service = get_gemini_compliance_service()
                total_new = 0
                failed_categories: List[str] = []
                category_counts: Dict[str, int] = {}

                # Mark all as researching — they run in parallel inside
                # research_location_compliance (concurrency 6-8, timeout+retry built in)
                for cat in missing:
                    yield _to_sse({
                        "type": "category_status",
                        "category": cat,
                        "status": "researching",
                    })

                try:
                    reqs = await service.research_location_compliance(
                        city=city,
                        state=state,
                        county=county,
                        categories=missing,
                        source_context=source_context,
                        corrections_context=corrections_context,
                        preemption_rules=preemption_rules,
                        has_local_ordinance=has_local_ordinance,
                    )
                    reqs = reqs or []

                    for req in reqs:
                        _clamp_varchar_fields(req)
                        cat = req.get("category", "")
                        if not req.get("applicable_industries"):
                            tag = MC_INDUSTRY_TAGS.get(cat, "healthcare")
                            req["applicable_industries"] = [tag]

                    # Count results per category
                    for r in reqs:
                        c = r.get("category", "unknown")
                        category_counts[c] = category_counts.get(c, 0) + 1

                    if reqs:
                        await _upsert_requirements_additive(conn, jurisdiction_id, reqs, research_source="manual")
                        total_new = len(reqs)

                    # Emit per-category status
                    for cat in missing:
                        count = category_counts.get(cat, 0)
                        if count > 0:
                            yield _to_sse({
                                "type": "category_status",
                                "category": cat,
                                "status": "complete",
                                "count": count,
                            })
                        else:
                            yield _to_sse({
                                "type": "category_status",
                                "category": cat,
                                "status": "empty",
                            })
                            failed_categories.append(cat)

                except Exception as e:
                    logger.warning("Medical compliance research failed: %s", e)
                    for cat in missing:
                        if cat not in category_counts:
                            yield _to_sse({
                                "type": "category_status",
                                "category": cat,
                                "status": "failed",
                                "error": str(e),
                            })
                    failed_categories = [c for c in missing if c not in category_counts]

                # Sync to linked locations
                linked = await conn.fetch(
                    """SELECT bl.id, bl.company_id
                       FROM business_locations bl
                       JOIN jurisdictions j ON LOWER(bl.city) = LOWER(j.city)
                           AND UPPER(bl.state) = UPPER(j.state)
                       WHERE j.id = $1""",
                    jurisdiction_id,
                )
                if linked:
                    yield _to_sse({
                        "type": "syncing",
                        "message": f"Syncing medical compliance updates to {len(linked)} location(s)...",
                    })
                    rows = await conn.fetch(
                        "SELECT * FROM jurisdiction_requirements WHERE jurisdiction_id = $1",
                        jurisdiction_id,
                    )
                    requirements = [_jurisdiction_row_to_dict(dict(r)) for r in rows]
                    has_local = await _lookup_has_local_ordinance(conn, city, state)
                    if has_local is False:
                        requirements = _filter_city_level_requirements(requirements, state)
                    _normalize_requirement_categories(requirements)
                    requirements = await _filter_with_preemption(conn, requirements, state)
                    total_synced = 0
                    for loc in linked:
                        loc_reqs = await _filter_requirements_for_company(
                            conn, loc["company_id"], requirements,
                        )
                        sync_result = await _sync_requirements_to_location(
                            conn, loc["id"], loc["company_id"], loc_reqs, create_alerts=True,
                        )
                        total_synced += sync_result.get("updated", 0)
                    yield _to_sse({
                        "type": "syncing",
                        "message": f"Synced to {len(linked)} location(s), {total_synced} update(s).",
                    })

                yield _to_sse({
                    "type": "completed",
                    "message": "Medical compliance research complete.",
                    "total_new": total_new,
                    "failed": failed_categories,
                    "category_counts": category_counts,
                })
        except Exception:
            logger.error("Medical compliance check failed for %s", jurisdiction_id, exc_info=True)
            yield _to_sse({"type": "error", "message": "Medical compliance research failed"})
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no"},
    )


@router.post("/jurisdictions/{jurisdiction_id}/check-life-sciences", dependencies=[Depends(require_admin)])
async def check_jurisdiction_life_sciences(jurisdiction_id: UUID):
    """Run life sciences research (6 categories) for a jurisdiction. Returns SSE stream."""
    from app.core.services.compliance_service import (
        _research_life_sciences_requirements_for_jurisdiction,
        _jurisdiction_row_to_dict,
        _filter_requirements_for_company,
        _filter_city_level_requirements,
        _filter_with_preemption,
        _normalize_requirement_categories,
        _sync_requirements_to_location,
        _lookup_has_local_ordinance,
    )

    async with get_connection() as conn:
        j = await conn.fetchrow("SELECT id, city, state FROM jurisdictions WHERE id = $1", jurisdiction_id)
        if not j:
            raise HTTPException(status_code=404, detail="Jurisdiction not found")
        location_label = f"{_format_city_label(j['city'])}, {j['state']}"

    async def event_stream():
        try:
            async with get_connection() as conn:
                yield _to_sse({"type": "started", "location": location_label})

                yield _to_sse({
                    "type": "researching",
                    "message": f"Researching life sciences compliance for {location_label}...",
                })
                try:
                    ls_result = await _research_life_sciences_requirements_for_jurisdiction(
                        conn, jurisdiction_id
                    )
                    ls_new = ls_result.get("new", 0)
                    ls_failed = ls_result.get("failed", [])
                    yield _to_sse({
                        "type": "repository_refresh",
                        "message": f"Life Sciences: +{ls_new} requirement(s) added."
                            + (f" Failed: {', '.join(ls_failed)}" if ls_failed else ""),
                    })
                except Exception as exc:
                    logger.warning("Life sciences research failed: %s", exc)
                    yield _to_sse({"type": "warning", "message": f"Life sciences research failed: {exc}"})

                # Sync to linked locations
                linked = await conn.fetch(
                    """SELECT bl.id, bl.company_id
                       FROM business_locations bl
                       JOIN jurisdictions j ON LOWER(bl.city) = LOWER(j.city)
                           AND UPPER(bl.state) = UPPER(j.state)
                       WHERE j.id = $1""",
                    jurisdiction_id,
                )
                if linked:
                    yield _to_sse({
                        "type": "syncing",
                        "message": f"Syncing life sciences updates to {len(linked)} location(s)...",
                    })
                    rows = await conn.fetch(
                        "SELECT * FROM jurisdiction_requirements WHERE jurisdiction_id = $1",
                        jurisdiction_id,
                    )
                    requirements = [_jurisdiction_row_to_dict(dict(r)) for r in rows]
                    state = j["state"]
                    has_local = await _lookup_has_local_ordinance(conn, j["city"], state)
                    if has_local is False:
                        requirements = _filter_city_level_requirements(requirements, state)
                    _normalize_requirement_categories(requirements)
                    requirements = await _filter_with_preemption(conn, requirements, state)
                    total_synced = 0
                    for loc in linked:
                        loc_reqs = await _filter_requirements_for_company(
                            conn, loc["company_id"], requirements,
                        )
                        sync_result = await _sync_requirements_to_location(
                            conn, loc["id"], loc["company_id"], loc_reqs, create_alerts=True,
                        )
                        total_synced += sync_result.get("updated", 0)
                    yield _to_sse({
                        "type": "syncing",
                        "message": f"Synced to {len(linked)} location(s), {total_synced} update(s).",
                    })

                yield _to_sse({"type": "completed", "message": "Life sciences research complete."})
        except Exception:
            logger.error("Life sciences check failed for %s", jurisdiction_id, exc_info=True)
            yield _to_sse({"type": "error", "message": "Life sciences research failed"})
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no"},
    )


@router.post("/jurisdictions/{jurisdiction_id}/check-federal-sources", dependencies=[Depends(require_admin)])
async def check_jurisdiction_federal_sources(jurisdiction_id: UUID):
    """Fetch compliance data from government APIs (Federal Register, CMS, Congress.gov). Returns SSE stream."""
    from app.core.services.federal_sources import fetch_federal_sources

    async with get_connection() as conn:
        j = await conn.fetchrow("SELECT id, city, state FROM jurisdictions WHERE id = $1", jurisdiction_id)
        if not j:
            raise HTTPException(status_code=404, detail="Jurisdiction not found")

    async def event_stream():
        try:
            async for event in fetch_federal_sources(jurisdiction_id):
                if event.get("type") == "heartbeat":
                    yield ": heartbeat\n\n"
                else:
                    yield _to_sse(event)
        except Exception:
            logger.error("Federal sources check failed for %s", jurisdiction_id, exc_info=True)
            yield _to_sse({"type": "error", "message": "Federal sources check failed"})
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no"},
    )


@router.post("/jurisdictions/{jurisdiction_id}/apply-federal-sources", dependencies=[Depends(require_admin)])
async def apply_jurisdiction_federal_sources(jurisdiction_id: UUID, payload: Dict = Body(...)):
    """Apply previously fetched federal source requirements."""
    from app.core.services.federal_sources import apply_federal_sources

    async with get_connection() as conn:
        exists = await conn.fetchval("SELECT 1 FROM jurisdictions WHERE id = $1", jurisdiction_id)
        if not exists:
            raise HTTPException(status_code=404, detail="Jurisdiction not found")

    requirements = payload.get("requirements", [])
    if not requirements:
        raise HTTPException(status_code=400, detail="No requirements to apply")

    result = await apply_federal_sources(jurisdiction_id, requirements)
    return {"ok": True, **result}


@router.get("/jurisdiction-requests")
async def list_jurisdiction_requests(
    status: str = "pending",
    current_user=Depends(require_admin),
):
    """List jurisdiction coverage requests with company info and employee counts."""
    async with get_connection() as conn:
        if status == "all":
            rows = await conn.fetch(
                """
                SELECT
                    jcr.id, jcr.city, jcr.state, jcr.county, jcr.status,
                    jcr.admin_notes, jcr.created_at, jcr.location_id,
                    c.name AS company_name,
                    COALESCE(emp_count.cnt, 0) AS employee_count
                FROM jurisdiction_coverage_requests jcr
                JOIN companies c ON c.id = jcr.requested_by_company_id
                LEFT JOIN LATERAL (
                    SELECT COUNT(*) AS cnt FROM employees e
                    WHERE e.work_location_id = jcr.location_id AND e.termination_date IS NULL
                ) emp_count ON true
                ORDER BY jcr.created_at DESC
                """
            )
        else:
            rows = await conn.fetch(
                """
                SELECT
                    jcr.id, jcr.city, jcr.state, jcr.county, jcr.status,
                    jcr.admin_notes, jcr.created_at, jcr.location_id,
                    c.name AS company_name,
                    COALESCE(emp_count.cnt, 0) AS employee_count
                FROM jurisdiction_coverage_requests jcr
                JOIN companies c ON c.id = jcr.requested_by_company_id
                LEFT JOIN LATERAL (
                    SELECT COUNT(*) AS cnt FROM employees e
                    WHERE e.work_location_id = jcr.location_id AND e.termination_date IS NULL
                ) emp_count ON true
                WHERE jcr.status = $1
                ORDER BY jcr.created_at DESC
                """,
                status,
            )

        return [
            {
                "id": str(row["id"]),
                "city": row["city"],
                "state": row["state"],
                "county": row["county"],
                "status": row["status"],
                "company_name": row["company_name"],
                "employee_count": row["employee_count"],
                "admin_notes": row["admin_notes"],
                "location_id": str(row["location_id"]) if row["location_id"] else None,
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            }
            for row in rows
        ]


@router.post("/jurisdiction-requests/{request_id}/process")
async def process_jurisdiction_request(
    request_id: UUID,
    body: JurisdictionProcessRequest,
    background_tasks: BackgroundTasks,
    current_user=Depends(require_admin),
):
    """Admin processes a jurisdiction coverage request — adds reference data and triggers compliance check."""
    async with get_connection() as conn:
        # 1. Fetch the request row
        req = await conn.fetchrow(
            "SELECT * FROM jurisdiction_coverage_requests WHERE id = $1",
            request_id,
        )
        if not req:
            raise HTTPException(status_code=404, detail="Jurisdiction request not found")

        city = req["city"]
        state = req["state"]
        location_id = req["location_id"]
        company_id = req["requested_by_company_id"]
        county = body.county or req["county"]

        # 2. Optionally upsert into jurisdiction_reference
        await conn.execute(
            """
            INSERT INTO jurisdiction_reference (city, state, county, has_local_ordinance)
            VALUES (LOWER($1), UPPER($2), $3, $4)
            ON CONFLICT (city, state) DO UPDATE
                SET county = COALESCE(EXCLUDED.county, jurisdiction_reference.county),
                    has_local_ordinance = EXCLUDED.has_local_ordinance
            """,
            city,
            state,
            county,
            body.has_local_ordinance,
        )

        # 3. Update the request status
        updated = await conn.fetchrow(
            """
            UPDATE jurisdiction_coverage_requests
            SET status = 'completed',
                processed_by = $2,
                processed_at = NOW(),
                admin_notes = COALESCE($3, admin_notes)
            WHERE id = $1
            RETURNING *
            """,
            request_id,
            current_user.id,
            body.admin_notes,
        )

        # 4. Update the associated business_location
        if location_id:
            await conn.execute(
                "UPDATE business_locations SET coverage_status = 'covered' WHERE id = $1",
                location_id,
            )

        # 5. Update ALL business_locations matching the same (city, state) across companies
        await conn.execute(
            """
            UPDATE business_locations
            SET coverage_status = 'covered'
            WHERE LOWER(city) = LOWER($1) AND UPPER(state) = UPPER($2)
              AND coverage_status != 'covered'
            """,
            city,
            state,
        )

        # 6. Trigger background compliance checks for ALL matching locations
        affected_locations = await conn.fetch(
            """
            SELECT bl.id, bl.company_id
            FROM business_locations bl
            WHERE LOWER(bl.city) = LOWER($1) AND UPPER(bl.state) = UPPER($2)
              AND bl.is_active = true
            """,
            city,
            state,
        )
        for loc in affected_locations:
            background_tasks.add_task(
                run_compliance_check_background, loc["id"], loc["company_id"]
            )

        return {
            "id": str(updated["id"]),
            "city": updated["city"],
            "state": updated["state"],
            "county": updated["county"],
            "status": updated["status"],
            "admin_notes": updated["admin_notes"],
            "processed_by": str(updated["processed_by"]) if updated["processed_by"] else None,
            "processed_at": updated["processed_at"].isoformat() if updated["processed_at"] else None,
            "created_at": updated["created_at"].isoformat() if updated["created_at"] else None,
        }


@router.post("/jurisdiction-requests/{request_id}/dismiss")
async def dismiss_jurisdiction_request(
    request_id: UUID,
    body: dict | None = None,
    current_user=Depends(require_admin),
):
    """Dismiss a jurisdiction coverage request (e.g., invalid city)."""
    async with get_connection() as conn:
        req = await conn.fetchrow(
            "SELECT id FROM jurisdiction_coverage_requests WHERE id = $1",
            request_id,
        )
        if not req:
            raise HTTPException(status_code=404, detail="Jurisdiction request not found")

        admin_notes = body.get("admin_notes") if body else None

        updated = await conn.fetchrow(
            """
            UPDATE jurisdiction_coverage_requests
            SET status = 'dismissed',
                processed_by = $2,
                processed_at = NOW(),
                admin_notes = COALESCE($3, admin_notes)
            WHERE id = $1
            RETURNING *
            """,
            request_id,
            current_user.id,
            admin_notes,
        )

        return {
            "id": str(updated["id"]),
            "city": updated["city"],
            "state": updated["state"],
            "county": updated["county"],
            "status": updated["status"],
            "admin_notes": updated["admin_notes"],
            "processed_by": str(updated["processed_by"]) if updated["processed_by"] else None,
            "processed_at": updated["processed_at"].isoformat() if updated["processed_at"] else None,
            "created_at": updated["created_at"].isoformat() if updated["created_at"] else None,
        }


@router.post("/requirements/{requirement_id}/codify", dependencies=[Depends(require_admin)])
async def codify_requirement(
    requirement_id: str,
    body: RequirementCodifyRequest,
    background_tasks: BackgroundTasks,
    current_user=Depends(require_admin),
):
    """Codify a single live requirement — the demand-funnel bridge into the same
    authority registry ScopeStudio writes. Mints the curated index + item +
    confirmed classification the reconcile step needs, then reconciles. The admin
    supplies/confirms the statute citation (a legal record).
    """
    from app.core.services.scope_registry.codify import codify_from_requirement
    from app.core.services.change_context import set_change_context

    req_uuid = UUID(requirement_id)
    async with get_connection() as conn:
        await set_change_context(conn, "codify", getattr(current_user, "id", None))
        try:
            result = await codify_from_requirement(
                conn, req_uuid,
                citation=body.citation,
                heading=body.heading,
                source_url=body.source_url,
                admin_id=getattr(current_user, "id", None),
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    # Freeze the cited page as evidence AFTER the response (slow external fetch —
    # off the request path + off the codify connection). Prefer the citation URL
    # the admin confirmed, else the statute's own source_url.
    snap_url = body.source_url or (result.get("citation_url") if isinstance(result, dict) else None)
    if snap_url:
        background_tasks.add_task(_snapshot_requirements_bg, [(req_uuid, snap_url)], "codify")
    return result


@router.get("/requirements/{requirement_id}/history", dependencies=[Depends(require_admin)])
async def get_requirement_history(requirement_id: str):
    """Transaction-time version log for one requirement (migration jrver01).

    Every INSERT/UPDATE/DELETE is captured by a trigger, so this is the full
    defensibility trail: what the row said, when we recorded it, and (where a
    write path labeled it) who/what changed it. Newest first. Plus the frozen
    source snapshots captured at approve/codify.
    """
    # asyncpg returns JSONB as raw text (no codec registered) — decode to objects.
    def _jsonb(v):
        return json.loads(v) if isinstance(v, str) else v

    req_uuid = UUID(requirement_id)
    async with get_connection() as conn:
        versions = await conn.fetch(
            """
            SELECT id, op, row_data, recorded_at, superseded_at, change_source, actor_id
            FROM jurisdiction_requirement_versions
            WHERE requirement_id = $1
            ORDER BY recorded_at DESC, id DESC
            """,
            req_uuid,
        )
        snapshots = await conn.fetch(
            """
            SELECT id, source_url, content_hash, http_status, context, fetched_at,
                   (content_text IS NOT NULL) AS has_text
            FROM requirement_source_snapshots
            WHERE requirement_id = $1
            ORDER BY fetched_at DESC
            """,
            req_uuid,
        )
    return {
        "requirement_id": requirement_id,
        "versions": [{
            "id": v["id"],
            "op": v["op"],
            "row_data": _jsonb(v["row_data"]),
            "recorded_at": v["recorded_at"].isoformat() if v["recorded_at"] else None,
            "superseded_at": v["superseded_at"].isoformat() if v["superseded_at"] else None,
            "change_source": v["change_source"],
            "actor_id": str(v["actor_id"]) if v["actor_id"] else None,
        } for v in versions],
        "snapshots": [{
            "id": str(s["id"]),
            "source_url": s["source_url"],
            "content_hash": s["content_hash"],
            "http_status": s["http_status"],
            "context": s["context"],
            "has_text": s["has_text"],
            "fetched_at": s["fetched_at"].isoformat() if s["fetched_at"] else None,
        } for s in snapshots],
    }


@router.get("/requirements/{requirement_id}/as-of", dependencies=[Depends(require_admin)])
async def get_requirement_as_of(
    requirement_id: str,
    ts: str = Query(..., description="ISO-8601 transaction-time instant to reconstruct at"),
):
    """Reconstruct the requirement row exactly as it was RECORDED at instant ``ts``.

    The defensibility query: "what did this row say, as we knew it, on date X?".
    Returns the version whose transaction-time interval [recorded_at, superseded_at)
    contains ts. 404 if the row didn't exist yet (or was deleted) at ts.
    """
    from datetime import datetime

    req_uuid = UUID(requirement_id)
    try:
        as_of = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=400, detail="ts must be ISO-8601")

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT op, row_data, recorded_at, superseded_at, change_source, actor_id
            FROM jurisdiction_requirement_versions
            WHERE requirement_id = $1
              AND recorded_at <= $2
              AND (superseded_at IS NULL OR superseded_at > $2)
            ORDER BY recorded_at DESC, id DESC
            LIMIT 1
            """,
            req_uuid, as_of,
        )
    if not row or row["op"] == "D":
        raise HTTPException(status_code=404, detail="No version recorded as of that instant")
    return {
        "requirement_id": requirement_id,
        "as_of": as_of.isoformat(),
        "recorded_at": row["recorded_at"].isoformat() if row["recorded_at"] else None,
        "change_source": row["change_source"],
        "actor_id": str(row["actor_id"]) if row["actor_id"] else None,
        "row_data": json.loads(row["row_data"]) if isinstance(row["row_data"], str) else row["row_data"],
    }


@router.get("/jurisdictions/general-coverage", dependencies=[Depends(require_admin)])
async def get_general_coverage(
    state: str = Query(..., description="Two-letter state (federal chain is always included)"),
    city: Optional[str] = Query(None),
):
    """Industry-agnostic (core-labor) coverage status per category for a coordinate.

    Distinguishes `covered` (rows exist) / `empty` (researched, nothing applies) /
    `unchecked` (never researched) so the Coverage tab stops rendering a
    never-checked category as a silent green. Self-populating: backfills `covered`
    cells from existing rows on first view (idempotent), then folds the general
    ledger across the location's jurisdiction chain.
    """
    from app.core.services import vertical_coverage
    from app.core.services.scope_registry.jurisdiction_chain import resolve_jurisdiction_chain

    async with get_connection() as conn:
        chain = await resolve_jurisdiction_chain(conn, state.strip().upper(), (city or "").strip() or None)
        ids = chain["ids"]
        await vertical_coverage.backfill_general(conn, ids)
        coverage = await vertical_coverage.general_coverage_map(conn, ids)
        # Attach display names for the categories.
        names = {r["slug"]: r["name"] for r in await conn.fetch(
            "SELECT slug, name FROM compliance_categories WHERE industry_tag IS NULL"
        )}

    covered = sum(1 for s in coverage.values() if s == "covered")
    empty = sum(1 for s in coverage.values() if s == "empty")
    unchecked = sum(1 for s in coverage.values() if s == "unchecked")
    return {
        "state": state.strip().upper(),
        "city": (city or "").strip() or None,
        "city_found": chain.get("city_found", False),
        "summary": {"covered": covered, "empty": empty, "unchecked": unchecked,
                    "total": len(coverage)},
        "categories": [
            {"slug": slug, "name": names.get(slug, slug), "status": status}
            for slug, status in sorted(coverage.items())
        ],
    }


@router.get("/vertical-coverage", dependencies=[Depends(require_admin)])
async def get_vertical_coverage_grid(
    industry_tag: Optional[str] = Query(None, description="Industry tag; omit to list industries only"),
):
    """Cross-jurisdiction coverage for ONE industry — the Coverage tab's missing
    industry-wide view (Means-1 scoping cockpit: "show me Manufacturing everywhere,
    where's thin, what to research next").

    Reads the `jurisdiction_vertical_coverage` LEDGER, whose statuses
    (pending/in_progress/covered/empty/failed) reflect the fill PIPELINE — NOT the
    registry-resolution "covered" the labor-scope panel shows. Kept deliberately
    separate so the two notions never silently disagree.

    Without `industry_tag`: returns the industries picker list only. With it: the
    industries list + the category columns + one row per jurisdiction that has any
    ledger cell for the industry, each row carrying its per-category status.
    """
    async with get_connection() as conn:
        # Picker: every industry that has ledger cells OR a catalog category.
        industries = await conn.fetch(
            """
            SELECT tag, COALESCE(SUM(cells), 0)::int AS cells,
                   COALESCE(SUM(covered), 0)::int AS covered
            FROM (
                SELECT industry_tag AS tag, COUNT(*) AS cells,
                       COUNT(*) FILTER (WHERE status = 'covered') AS covered
                FROM jurisdiction_vertical_coverage
                GROUP BY industry_tag
                UNION ALL
                SELECT industry_tag AS tag, 0 AS cells, 0 AS covered
                FROM compliance_categories
                WHERE industry_tag IS NOT NULL
                GROUP BY industry_tag
            ) u
            GROUP BY tag
            ORDER BY tag
            """
        )
        industries_out = [
            {"tag": r["tag"], "cells": r["cells"], "covered": r["covered"]}
            for r in industries
        ]

        if not industry_tag:
            return {"industry_tag": None, "industries": industries_out,
                    "categories": [], "jurisdictions": []}

        tag = industry_tag.strip()
        cells = await conn.fetch(
            """
            SELECT jvc.jurisdiction_id, j.display_name, j.city, j.state,
                   j.level::text AS level, j.parent_id,
                   jvc.category, jvc.status, jvc.requirements_written, jvc.updated_at
            FROM jurisdiction_vertical_coverage jvc
            JOIN jurisdictions j ON j.id = jvc.jurisdiction_id
            WHERE jvc.industry_tag = $1
            ORDER BY j.state NULLS FIRST, j.city NULLS FIRST, jvc.category
            """,
            tag,
        )
        # Category columns present for this industry, with display names.
        cat_slugs = sorted({c["category"] for c in cells})
        names = {r["slug"]: r["name"] for r in await conn.fetch(
            "SELECT slug, name FROM compliance_categories WHERE slug = ANY($1::text[])",
            cat_slugs,
        )} if cat_slugs else {}
        categories = [{"slug": s, "name": names.get(s, s)} for s in cat_slugs]

        rows: dict = {}
        for c in cells:
            jid = str(c["jurisdiction_id"])
            row = rows.get(jid)
            if row is None:
                row = rows[jid] = {
                    "jurisdiction_id": jid,
                    "display_name": c["display_name"],
                    "city": c["city"],
                    "state": c["state"],
                    "level": c["level"],
                    "cells": {},
                    "summary": {"covered": 0, "empty": 0, "in_progress": 0,
                                "pending": 0, "failed": 0},
                }
            row["cells"][c["category"]] = {
                "status": c["status"],
                "written": c["requirements_written"],
            }
            if c["status"] in row["summary"]:
                row["summary"][c["status"]] += 1

        # Federal first, then state, then city — same ordering intent as the tree.
        _level_rank = {"federal": 0, "national": 0, "state": 1, "county": 2, "city": 3}
        jurisdictions_out = sorted(
            rows.values(),
            key=lambda r: (_level_rank.get(r["level"], 9), r["state"] or "", r["city"] or ""),
        )
        return {"industry_tag": tag, "industries": industries_out,
                "categories": categories, "jurisdictions": jurisdictions_out}
