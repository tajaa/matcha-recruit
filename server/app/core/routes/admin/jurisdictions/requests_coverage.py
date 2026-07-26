"""Admin jurisdictions routes — jurisdiction-requests, requirement codify/history/as-of, coverage grids (split of jurisdictions.py). The codify/history/as-of tail lives here (not with requirements.py) purely to preserve original route-registration order."""
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
