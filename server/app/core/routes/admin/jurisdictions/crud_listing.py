"""Admin jurisdictions routes — create/list/tree (split of jurisdictions.py)."""
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


