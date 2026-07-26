"""Admin jurisdictions routes — category/policy detail + evals (split of jurisdictions.py)."""
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


