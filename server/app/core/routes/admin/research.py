"""Admin research routes (J5 split)."""
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


@router.get("/overview", dependencies=[Depends(require_admin)])
async def admin_overview():
    """Get platform overview with company and employee stats."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT
                comp.id,
                comp.name,
                comp.industry,
                comp.size,
                comp.status,
                comp.created_at,
                comp.approved_at,
                COUNT(e.id) AS total_employees,
                COUNT(CASE WHEN e.user_id IS NOT NULL AND e.termination_date IS NULL THEN 1 END) AS active_employees,
                COUNT(CASE WHEN e.termination_date IS NOT NULL THEN 1 END) AS terminated_employees,
                COUNT(CASE WHEN e.id IS NOT NULL AND e.user_id IS NULL AND e.termination_date IS NULL THEN 1 END) AS pending_employees
            FROM companies comp
            LEFT JOIN employees e ON e.org_id = comp.id
            WHERE comp.owner_id IS NOT NULL
            GROUP BY comp.id
            ORDER BY comp.created_at DESC
            """
        )

        companies = [
            {
                "id": str(row["id"]),
                "name": row["name"],
                "industry": row["industry"],
                "size": row["size"],
                "status": row["status"] or "approved",
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "approved_at": row["approved_at"].isoformat() if row["approved_at"] else None,
                "total_employees": row["total_employees"],
                "active_employees": row["active_employees"],
                "terminated_employees": row["terminated_employees"],
                "pending_employees": row["pending_employees"],
            }
            for row in rows
        ]

        totals = {
            "total_companies": len(companies),
            "total_employees": sum(c["total_employees"] for c in companies),
            "active_employees": sum(c["active_employees"] for c in companies),
            "pending_employees": sum(c["pending_employees"] for c in companies),
            "terminated_employees": sum(c["terminated_employees"] for c in companies),
        }

        return {"companies": companies, "totals": totals}


@router.post("/specialization-research/discover", dependencies=[Depends(require_admin)])
async def discover_specialization_categories_endpoint(req: SpecializationDiscoverRequest):
    """Discover regulatory categories for a specialization via Gemini."""
    from app.core.services.compliance_service import discover_specialization_categories

    result = await discover_specialization_categories(req.specialization, req.parent_industry)
    return result


@router.post("/specialization-research/run", dependencies=[Depends(require_admin)])
async def run_specialization_research(req: SpecializationResearchRequest):
    """Research specialization categories across jurisdictions. Returns SSE stream."""
    from app.core.services.compliance_service import (
        _get_or_create_jurisdiction,
        research_specialization_for_jurisdiction,
        get_specialization_completeness,
    )

    async def event_stream():
        try:
            async with get_connection() as conn:
                # Phase 1: Resolve jurisdictions — deduplicate states so shared
                # state-level requirements are researched once, not per city.
                yield _to_sse({"type": "status", "message": "Resolving jurisdictions..."})

                # Collect all unique states (explicit + implied by cities)
                state_jurisdictions: dict[str, dict] = {}  # state_norm -> jurisdiction dict
                city_jurisdictions: list[dict] = []

                for state in req.states:
                    state_norm = state.strip().upper()
                    if state_norm not in state_jurisdictions:
                        jid = await _get_or_create_jurisdiction(conn, "", state_norm)
                        state_jurisdictions[state_norm] = {"id": jid, "label": state_norm, "city": "", "state": state_norm}

                for city_entry in req.cities:
                    city = city_entry.get("city", "").strip()
                    state = city_entry.get("state", "").strip().upper()
                    if not city or not state:
                        continue
                    # Ensure parent state is researched first
                    if state not in state_jurisdictions:
                        sid = await _get_or_create_jurisdiction(conn, "", state)
                        state_jurisdictions[state] = {"id": sid, "label": state, "city": "", "state": state}
                    jid = await _get_or_create_jurisdiction(conn, city, state)
                    city_jurisdictions.append({"id": jid, "label": f"{city}, {state}", "city": city, "state": state})

                # Order: states first, then cities — so state-level requirements
                # are in the DB before city research runs. City research will then
                # only add local ordinances (existing_cats check skips duplicates).
                all_jurisdictions = list(state_jurisdictions.values()) + city_jurisdictions
                total_count = len(all_jurisdictions)

                yield _to_sse({
                    "type": "status",
                    "message": f"Resolved {len(state_jurisdictions)} state(s) + {len(city_jurisdictions)} city/cities. Starting research...",
                })

                # Phase 2: Research each jurisdiction (states first, then cities)
                grand_total = 0
                grand_failed = []

                for j_idx, j in enumerate(all_jurisdictions, 1):
                    is_city = bool(j["city"])
                    yield _to_sse({
                        "type": "researching",
                        "jurisdiction": j["label"],
                        "progress": j_idx,
                        "total": total_count,
                    })

                    def progress_cb(cat_idx, cat_total, message):
                        pass  # inner progress handled by category events

                    # Ground this run in fetched statute text where the registry
                    # covers the chain (COMPLIANCE_SYSTEM_GAP_REVIEW.md §3: this
                    # path used to be unconditionally ungrounded). Degrades to
                    # ("", {}) — i.e. the old behaviour — where it doesn't.
                    from app.core.services.scope_registry.research_loop import (
                        corpus_for_jurisdiction,
                    )
                    corpus, citation_index = await corpus_for_jurisdiction(
                        conn, j["id"], req.categories,
                    )
                    result = await research_specialization_for_jurisdiction(
                        conn,
                        j["id"],
                        req.categories,
                        req.industry_tag,
                        industry_context=req.industry_context,
                        progress_callback=progress_cb,
                        grounded_corpus=corpus,
                        citation_index=citation_index,
                    )

                    grand_total += result.get("new", 0)
                    grand_failed.extend(result.get("failed", []))

                    yield _to_sse({
                        "type": "jurisdiction_complete",
                        "jurisdiction": j["label"],
                        "requirements_found": result.get("new", 0),
                        "categories_researched": len(result.get("categories", [])),
                        "failed": result.get("failed", []),
                        "skipped": result.get("skipped", False),
                        "requirements": [
                            {
                                "category": r.get("category", ""),
                                "title": (r.get("title") or "")[:120],
                                "jurisdiction_level": r.get("jurisdiction_level", ""),
                            }
                            for r in (result.get("requirements") or [])[:40]
                        ],
                    })

                # Phase 3: Completeness summary
                completeness = await get_specialization_completeness(
                    conn, req.industry_tag, expected_categories=req.categories,
                )

                yield _to_sse({
                    "type": "completed",
                    "summary": {
                        "specialization": req.specialization,
                        "industry_tag": req.industry_tag,
                        "total_requirements": grand_total,
                        "jurisdictions_researched": len(all_jurisdictions),
                        "categories_requested": len(req.categories),
                        "failed_categories": list(set(grand_failed)),
                        "completeness": completeness,
                    },
                })
        except Exception:
            logger.error("Specialization research failed", exc_info=True)
            yield _to_sse({"type": "error", "message": "Specialization research failed"})
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no"},
    )


@router.get("/specialization-research/completeness", dependencies=[Depends(require_admin)])
async def get_specialization_completeness_endpoint(
    industry_tag: str = Query(...),
    categories: str = Query(""),
):
    """Get completeness data for a specialization across jurisdictions."""
    from app.core.services.compliance_service import get_specialization_completeness

    expected = [c.strip() for c in categories.split(",") if c.strip()] or None
    async with get_connection() as conn:
        result = await get_specialization_completeness(conn, industry_tag, expected_categories=expected)
    return result


@router.get("/industry-profiles", dependencies=[Depends(require_admin)])
async def list_industry_profiles():
    async with get_connection() as conn:
        rows = await conn.fetch(
            "SELECT * FROM industry_compliance_profiles ORDER BY name"
        )
    return [_profile_row_to_dict(r) for r in rows]


@router.post("/industry-profiles", dependencies=[Depends(require_admin)], status_code=201)
async def create_industry_profile(body: IndustryProfileCreate):
    evidence_json = json.dumps(body.category_evidence) if body.category_evidence else None
    async with get_connection() as conn:
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO industry_compliance_profiles (name, description, focused_categories, rate_types, category_order, category_evidence)
                VALUES ($1, $2, $3, $4, $5, $6::jsonb)
                RETURNING *
                """,
                body.name, body.description, body.focused_categories,
                body.rate_types or [], body.category_order, evidence_json,
            )
        except asyncpg.UniqueViolationError:
            raise HTTPException(status_code=409, detail="Profile name already exists")
    return _profile_row_to_dict(row)


@router.put("/industry-profiles/{profile_id}", dependencies=[Depends(require_admin)])
async def update_industry_profile(profile_id: UUID, body: IndustryProfileUpdate):
    sets = []
    vals: list[Any] = []
    idx = 1
    for field in ("name", "description", "focused_categories", "rate_types", "category_order"):
        val = getattr(body, field)
        if val is not None:
            sets.append(f"{field} = ${idx}")
            vals.append(val)
            idx += 1
    if body.category_evidence is not None:
        sets.append(f"category_evidence = ${idx}::jsonb")
        vals.append(json.dumps(body.category_evidence))
        idx += 1
    if not sets:
        raise HTTPException(status_code=400, detail="No fields to update")
    sets.append(f"updated_at = NOW()")
    vals.append(profile_id)
    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"UPDATE industry_compliance_profiles SET {', '.join(sets)} WHERE id = ${idx} RETURNING *",
            *vals,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Profile not found")
    return _profile_row_to_dict(row)


@router.delete("/industry-profiles/{profile_id}", dependencies=[Depends(require_admin)])
async def delete_industry_profile(profile_id: UUID):
    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM industry_compliance_profiles WHERE id = $1", profile_id
        )
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Profile not found")
    return {"deleted": True}


@router.get("/industry-requirements-matrix", dependencies=[Depends(require_admin)])
async def get_industry_requirements_matrix(
    industry: str = Query("healthcare"),
    specialties: Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    payer_contracts: Optional[str] = Query(None),
    state: Optional[str] = Query(None, max_length=2),
    city: Optional[str] = Query(None),
):
    """Return a matrix of compliance categories applicable to an industry,
    annotated with jurisdiction data coverage and trigger-profile sourcing.

    With `state` (and optionally `city`), coverage is scoped to that
    establishment's jurisdiction chain — city ∪ county ∪ state ∪ federal —
    turning the global "does anyone have data for this category" into the
    question that matters: "is this category codified *for Los Angeles*". The
    categories with no data in the chain are the codify worklist for that city.
    """

    specialty_list = [s.strip() for s in specialties.split(",") if s.strip()] if specialties else []
    payer_list = [p.strip() for p in payer_contracts.split(",") if p.strip()] if payer_contracts else []

    # Canonicalize before anything looks the industry up. The runtime compliance
    # path always does this; this endpoint used to compare raw frontend tokens
    # against `compliance_categories.industry_tag` and matched nothing.
    canonical = _resolve_industry(industry) or industry.strip().lower()

    async with get_connection() as conn:
        # 1. Load the industry profile
        profile_row = await _load_industry_profile_row(conn, canonical)
        # 2. Load all compliance categories
        cat_rows = await conn.fetch(
            "SELECT slug, name, description, domain::text, \"group\", industry_tag, sort_order "
            "FROM compliance_categories ORDER BY sort_order, slug"
        )

    if not cat_rows:
        raise HTTPException(status_code=404, detail="No compliance categories found")

    cats_by_slug = {r["slug"]: dict(r) for r in cat_rows}
    focused_categories = list(profile_row["focused_categories"]) if profile_row else []

    # 3. Determine activated trigger profiles
    active_triggers = []
    triggered_cats: dict[str, list[str]] = {}  # slug -> list of trigger keys

    for tp in TRIGGER_PROFILES:
        activated = False
        if tp.attribute_key == "entity_type" and entity_type and tp.attribute_match == entity_type:
            activated = True
        elif tp.attribute_key == "payer_contracts" and tp.attribute_match in payer_list:
            activated = True

        if activated:
            active_triggers.append({
                "key": tp.key,
                "label": tp.label,
                "categories": list(tp.applicable_categories),
            })
            for cat_slug in tp.applicable_categories:
                triggered_cats.setdefault(cat_slug, []).append(tp.key)

    # 4. Classify each category and determine the applicable set
    applicable_slugs: list[str] = []
    source_map: dict[str, str] = {}
    triggered_by_map: dict[str, list[str]] = {}

    for slug, cat in cats_by_slug.items():
        tag = cat.get("industry_tag") or ""
        sources: list[str] = []

        # focused: in the industry profile's focused_categories
        if slug in focused_categories:
            sources.append("focused")

        # base: industry_tag matches the canonical industry exactly
        if tag.lower() == canonical.lower():
            sources.append("base")

        # specialty: industry_tag starts with "industry:" and suffix matches a selected specialty
        if ":" in tag:
            prefix, suffix = tag.split(":", 1)
            if prefix.lower() == canonical.lower() and suffix.lower() in [s.lower() for s in specialty_list]:
                sources.append("specialty")

        # triggered: appears in an activated trigger profile
        if slug in triggered_cats:
            sources.append("triggered")
            triggered_by_map[slug] = triggered_cats[slug]

        if sources:
            applicable_slugs.append(slug)
            # Priority: triggered > specialty > base > focused
            for priority in ("triggered", "specialty", "base", "focused"):
                if priority in sources:
                    source_map[slug] = priority
                    break

    if not applicable_slugs:
        return {
            "summary": {"total": 0, "with_data": 0, "missing_data": 0},
            "industry_profile": {
                "name": profile_row["name"] if profile_row else canonical,
                "focused_categories": focused_categories,
            },
            "scoped_to": None,
            "active_triggers": active_triggers,
            "categories": [],
        }

    # 5. Query jurisdiction data counts for applicable categories, scoped to the
    #    establishment's chain when a location was given.
    scoped_to: Optional[Dict[str, Any]] = None
    # Engine augmentation (per-cell, gated) — only meaningful with a chain.
    engine_cov: Dict[str, Any] = {"registry_definitive": False, "by_category": {}}
    async with get_connection() as conn:
        if state:
            chain = await _resolve_jurisdiction_chain(conn, state.upper(), city)
            if not chain["state_found"]:
                raise HTTPException(
                    status_code=404, detail=f"No jurisdiction record for state {state.upper()}"
                )
            data_rows = await conn.fetch(
                "SELECT category, COUNT(*) AS req_count, COUNT(DISTINCT jurisdiction_id) AS jur_count "
                "FROM jurisdiction_requirements "
                "WHERE category = ANY($1::text[]) AND jurisdiction_id = ANY($2::uuid[]) "
                "GROUP BY category",
                applicable_slugs, chain["ids"],
            )
            # Registry-grounded codified/to-codify per category, but ONLY where the
            # registry definitively classifies this chain's coordinate. Applied
            # per cell in the loop below (never chain-level: a chain covered only
            # by fully-classified labor indexes would otherwise zero out the real
            # bank counts of categories the registry doesn't model yet).
            try:
                from app.core.services.scope_registry.gap_surfaces import (
                    resolve_chain_category_coverage,
                )
                engine_cov = await resolve_chain_category_coverage(
                    conn, chain_ids=chain["ids"], industry=canonical,
                )
            except Exception:
                logger.exception(
                    "industry-matrix: engine coverage failed for %s in %s",
                    canonical, state.upper(),
                )
            scoped_to = {
                "state": state.upper(),
                "city": city,
                # An unknown city is not an error: the chain degrades to
                # state ∪ federal, and the caller is told the city was not found
                # rather than being shown state coverage as if it were the city's.
                "city_found": chain["city_found"] if city else None,
                "jurisdictions_in_chain": len(chain["ids"]),
            }
        else:
            data_rows = await conn.fetch(
                "SELECT category, COUNT(*) AS req_count, COUNT(DISTINCT jurisdiction_id) AS jur_count "
                "FROM jurisdiction_requirements "
                "WHERE category = ANY($1::text[]) "
                "GROUP BY category",
                applicable_slugs,
            )

    data_map = {r["category"]: {"req_count": r["req_count"], "jur_count": r["jur_count"]} for r in data_rows}

    # 6. Build response
    engine_by_cat = engine_cov["by_category"]
    categories_out = []
    with_data = 0
    engine_cells = 0
    for slug in applicable_slugs:
        cat = cats_by_slug[slug]
        counts = data_map.get(slug, {"req_count": 0, "jur_count": 0})
        has_data = counts["jur_count"] > 0
        if has_data:
            with_data += 1
        entry = {
            "slug": slug,
            "name": cat["name"],
            "domain": cat["domain"],
            "group": cat["group"],
            "industry_tag": cat.get("industry_tag"),
            "source": source_map[slug],
            "triggered_by": triggered_by_map.get(slug, []),
            "jurisdiction_count": counts["jur_count"],
            "requirement_count": counts["req_count"],
            "has_data": has_data,
            "registry_source": "bank",
        }
        # Per-cell gate: engine only where the registry actually models this
        # category (slug present in the definitive expected set). Cells the
        # registry doesn't model stay on their bank count.
        engine_cell = engine_by_cat.get(slug)
        if engine_cell:
            engine_cells += 1
            entry.update(
                registry_source="engine",
                engine_codified=engine_cell["codified"],
                engine_to_codify=engine_cell["to_codify"],
                engine_expected=engine_cell["expected"],
            )
        categories_out.append(entry)

    # Summary to-codify totals the ENTIRE definitive worklist for the chain —
    # including registry categories bucketed 'uncategorized' or outside this
    # industry's applicable tags — so the chip is the complete codify backlog
    # even when some of it has no matching cell below.
    engine_to_codify_total = sum(c["to_codify"] for c in engine_by_cat.values())

    return {
        "summary": {
            "total": len(categories_out),
            "with_data": with_data,
            "missing_data": len(categories_out) - with_data,
            "engine_cells": engine_cells,
            "engine_to_codify": engine_to_codify_total,
        },
        "industry_profile": {
            "name": profile_row["name"] if profile_row else canonical,
            "focused_categories": focused_categories,
        },
        "scoped_to": scoped_to,
        "active_triggers": active_triggers,
        "registry_definitive": engine_cov["registry_definitive"],
        "categories": categories_out,
    }


@router.get("/industries/{industry}/specialties", dependencies=[Depends(require_admin)])
async def list_industry_specialties(industry: str):
    """Specialties for an industry, each with the number of categories it resolves to.

    `category_count == 0` marks a specialty that selects nothing when ticked —
    the state seven of the frontend's hardcoded healthcare checkboxes were in.
    """
    from app.core.services import industry_specialties as spec

    canonical = _resolve_industry(industry) or industry.strip().lower()
    async with get_connection() as conn:
        return {
            "industry": canonical,
            "specialties": await spec.list_specialties(conn, canonical),
        }


@router.post("/industries/{industry}/specialties/discover", dependencies=[Depends(require_admin)])
async def discover_industry_specialty(industry: str, payload: SpecialtyDiscoverRequest):
    """Derive the categories a specialty needs beyond its parent's baseline.

    Persists nothing. The admin reviews the proposal and calls `/confirm`.
    """
    from app.core.services import industry_specialties as spec

    canonical = _resolve_industry(industry) or industry.strip().lower()
    slug = spec.slugify(payload.name)
    if not slug:
        raise HTTPException(status_code=400, detail="Specialty name must contain letters or digits")
    # Confirm would reject this slug anyway (it becomes the 30-char category
    # `group` column) — reject it here, before spending a Gemini call on a
    # proposal that can never be saved.
    if len(slug) > spec.MAX_GROUP:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Specialty name is too long once slugified ({len(slug)} chars; max "
                f"{spec.MAX_GROUP}). Use a shorter name, e.g. an accepted abbreviation."
            ),
        )

    async with get_connection() as conn:
        existing = await conn.fetchrow(
            "SELECT industry_tag FROM industry_specialties WHERE industry_tag = $1",
            spec.industry_tag(canonical, slug),
        )

    try:
        result = await spec.discover(canonical, payload.name)
    except Exception as exc:
        logger.exception("specialty discovery failed for %s/%s", canonical, slug)
        raise HTTPException(status_code=502, detail=f"Discovery failed: {exc}") from exc

    # `is_existing` is decided against the DB, not the in-code CATEGORY_KEYS
    # constant — categories confirmed at runtime are absent from the constant and
    # would otherwise be re-proposed as novel.
    async with get_connection() as conn:
        already = await spec.existing_category_slugs(
            conn, [c.get("key") for c in result["categories"] if c.get("key")]
        )
    for cat in result["categories"]:
        cat["is_existing"] = cat.get("key") in already

    result["already_exists"] = existing is not None
    result["industry"] = canonical
    return result


@router.post("/industries/{industry}/specialties/confirm", dependencies=[Depends(require_admin)])
async def confirm_industry_specialty(
    industry: str,
    payload: SpecialtyConfirmRequest,
    current_user=Depends(require_admin),
):
    """Persist the specialty and the categories the admin approved.

    Busts the category cache so the new rows appear in the matrix immediately —
    `_get_required_categories` is DB-derived and process-cached.
    """
    from app.core.services import industry_specialties as spec

    canonical = _resolve_industry(industry) or industry.strip().lower()
    slug = spec.slugify(payload.slug or payload.label)
    if not slug:
        raise HTTPException(status_code=400, detail="Specialty slug could not be derived")

    try:
        async with get_connection() as conn:
            result = await spec.confirm(
                conn,
                parent_industry=canonical,
                slug=slug,
                label=payload.label.strip(),
                research_context=payload.research_context,
                categories=[c.model_dump() for c in payload.categories],
                admin_id=current_user.id,
            )
    except spec.SpecialtyTooLong as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await _get_required_categories(force_refresh=True)
    redis = get_redis_cache()
    if redis:
        await cache_delete(redis, admin_jurisdiction_data_overview_key())
    return result


@router.get("/pending-research", dependencies=[Depends(require_admin)])
async def get_pending_research():
    """Unified admin view of everything Matcha is still researching, across
    BOTH mechanisms — real catalog gaps (`jurisdiction_coverage_requests`) and
    industry-specialty ledger to-dos (dental, etc. — `jurisdiction_vertical_coverage`,
    only surfaced here, never as its own table row). Same data the tenant-facing
    "we're working on it" panel reads from, so what an admin sees here should
    match what a business sees on their Compliance page.

    Returns ONE list, sorted newest-first, each item naming exactly which
    categories are outstanding (not just a count) — admins need to know WHAT
    is queued, not just how much.
    """
    from app.core.services import vertical_coverage

    async with get_connection() as conn:
        cat_rows = await conn.fetch(
            """
            SELECT jcr.id, jcr.city, jcr.state, jcr.county, jcr.status,
                   jcr.admin_notes, jcr.created_at, jcr.location_id,
                   c.name AS company_name,
                   COALESCE(emp_count.cnt, 0) AS employee_count
            FROM jurisdiction_coverage_requests jcr
            JOIN companies c ON c.id = jcr.requested_by_company_id
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS cnt FROM employees e
                WHERE e.work_location_id = jcr.location_id AND e.termination_date IS NULL
            ) emp_count ON true
            WHERE jcr.status IN ('pending', 'in_progress')
            """
        )
        items: List[dict] = []
        for r in cat_rows:
            # admin_notes holds a human-readable label list ("Needs research:
            # Anti-Discrimination, Final Pay — healthcare") on rows written
            # after the readable-names fix, or raw slugs ("missing: anti_dis-
            # crimination, final_pay (healthcare)") on older rows. Parse either
            # out and resolve both formats in one query so every row — old or
            # new — gets full name+description cards, never just the flat note.
            note = r["admin_notes"] or ""
            body = re.sub(r"^(needs research:|missing:)\s*", "", note, flags=re.IGNORECASE)
            body = re.sub(r"\s*—.*$", "", body)
            body = re.sub(r"\s*\([^)]*\)\s*$", "", body)
            labels = [t.strip() for t in body.split(",") if t.strip()]
            categories: List[dict] = []
            if labels:
                cat_defs = await conn.fetch(
                    "SELECT slug, name, description FROM compliance_categories "
                    "WHERE name = ANY($1::text[]) OR slug = ANY($1::text[]) "
                    "ORDER BY sort_order, name",
                    labels,
                )
                resolved_names = {c["name"] for c in cat_defs} | {c["slug"] for c in cat_defs}
                categories = [
                    {"key": c["slug"], "name": c["name"], "description": c["description"]}
                    for c in cat_defs
                ]
                # Any label that didn't resolve still shows up (name-only, no
                # description) rather than silently vanishing from the count.
                for label in labels:
                    if label not in resolved_names:
                        categories.append({"key": None, "name": label, "description": None})

            items.append({
                "id": str(r["id"]),
                "type": "category",
                "city": r["city"],
                "state": r["state"],
                "county": r["county"],
                "status": r["status"],
                "company_name": r["company_name"],
                "employee_count": r["employee_count"],
                "note": r["admin_notes"],
                "categories": categories,
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "sort_at": r["created_at"],
            })

        # Vertical ledger to-dos, per company. No table row exists for these —
        # computed live off the same pure-SQL path the wizard/panel use. Capped
        # at the companies with an active location, which bounds this to real
        # tenants (not every row in the DB).
        comp_rows = await conn.fetch(
            """
            SELECT DISTINCT c.id, c.name, c.created_at
            FROM companies c
            JOIN business_locations bl ON bl.company_id = c.id AND bl.is_active = true
            ORDER BY c.created_at DESC
            LIMIT 200
            """
        )
        for comp in comp_rows:
            try:
                resolved = await vertical_coverage.resolve_vertical(conn, comp["id"])
                if not resolved:
                    continue
                _parent, _slug, v_label, v_tag, _minted = resolved
                cat_slugs = [
                    r["slug"] for r in await conn.fetch(
                        "SELECT slug FROM compliance_categories WHERE industry_tag = $1",
                        v_tag,
                    )
                ]
                if not cat_slugs:
                    continue
                leaf_rows = await conn.fetch(
                    "SELECT jurisdiction_id, city, state FROM business_locations "
                    "WHERE company_id = $1 AND is_active = true AND jurisdiction_id IS NOT NULL",
                    comp["id"],
                )
                if not leaf_rows:
                    continue
                leaf_ids = [r["jurisdiction_id"] for r in leaf_rows]
                leaf_chains = await vertical_coverage.chains_for_leaves(conn, leaf_ids)
                plan, _deferred = await vertical_coverage.plan_fill(
                    conn, leaf_chains, v_tag, cat_slugs
                )
                if plan:
                    # WHAT, not just how many: full name + description per
                    # outstanding category, sort_order-ordered — renders as
                    # cards, not a bare count or a flat comma list.
                    plan_slugs = sorted({p[1] for p in plan})
                    cat_defs = await conn.fetch(
                        "SELECT slug, name, description FROM compliance_categories "
                        "WHERE slug = ANY($1::text[]) ORDER BY sort_order, name",
                        plan_slugs,
                    )
                    categories = [
                        {"key": c["slug"], "name": c["name"], "description": c["description"]}
                        for c in cat_defs
                    ]
                    jurisdictions = sorted({f"{r['city']}, {r['state']}" for r in leaf_rows})
                    items.append({
                        "type": "vertical",
                        "company_id": str(comp["id"]),
                        "company_name": comp["name"],
                        "label": v_label,
                        "areas": len(plan),
                        "categories": categories,
                        "jurisdictions": jurisdictions,
                        "created_at": comp["created_at"].isoformat() if comp["created_at"] else None,
                        "sort_at": comp["created_at"],
                    })
            except Exception as exc:
                logger.warning("pending-research: vertical scan failed for %s: %s", comp["id"], exc)

    items.sort(key=lambda it: it["sort_at"] or datetime.min, reverse=True)
    for it in items:
        del it["sort_at"]

    return {"items": items}


@router.get("/research-queue", dependencies=[Depends(require_admin)])
async def get_research_queue():
    """List city-level jurisdictions with research status."""
    async with get_connection() as conn:
        rows = await conn.fetch("""
            SELECT
                j.id AS jurisdiction_id,
                j.city, j.state, j.county,
                COALESCE(jrc.cnt, 0) AS repo_count,
                COALESCE(lc.location_count, 0) AS location_count,
                COALESCE(lc.company_count, 0) AS company_count,
                j.created_at
            FROM jurisdictions j
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS cnt
                FROM jurisdiction_requirements jr
                WHERE jr.jurisdiction_id = j.id
            ) jrc ON true
            LEFT JOIN LATERAL (
                SELECT COUNT(*) AS location_count,
                       COUNT(DISTINCT bl.company_id) AS company_count
                FROM business_locations bl
                WHERE bl.jurisdiction_id = j.id
            ) lc ON true
            WHERE j.city IS NOT NULL AND j.city != ''
            ORDER BY
                COALESCE(jrc.cnt, 0) ASC,
                COALESCE(lc.location_count, 0) DESC,
                j.state, j.city
        """)
        return [
            {
                "jurisdiction_id": str(r["jurisdiction_id"]),
                "city": r["city"],
                "state": r["state"],
                "county": r["county"],
                "repo_count": r["repo_count"],
                "location_count": r["location_count"],
                "company_count": r["company_count"],
                "status": "researched" if r["repo_count"] > 0 else "needs_research",
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in rows
        ]


@router.post("/research-queue/{jurisdiction_id}/research", dependencies=[Depends(require_admin)])
async def research_jurisdiction(jurisdiction_id: UUID):
    """Trigger Gemini research for a jurisdiction. Returns SSE stream.

    Writes to jurisdiction_requirements (the shared repo). When research adds
    new rows, closes the loop for waiting tenants: projects their compliance
    tabs from the enriched catalog (Gemini-free) and emails their admins.
    """
    async with get_connection() as conn:
        j = await conn.fetchrow(
            "SELECT id FROM jurisdictions WHERE id = $1",
            jurisdiction_id,
        )
        if not j:
            raise HTTPException(status_code=404, detail="Jurisdiction not found")

    async def event_stream():
        total_new = 0
        try:
            async for event in research_jurisdiction_repo_only(jurisdiction_id):
                if event.get("type") == "heartbeat":
                    yield ": heartbeat\n\n"
                else:
                    if event.get("type") == "complete":
                        total_new = event.get("new", 0) or 0
                    yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            yield "data: [DONE]\n\n"
            return

        # Loop-close: publish the enriched catalog to waiting tenants.
        if total_new > 0:
            summary = await _publish_research_to_requesters(jurisdiction_id)
            yield f"data: {json.dumps({'type': 'tenants_notified', **summary})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"X-Accel-Buffering": "no"},
    )


@router.post("/pending-research/run", dependencies=[Depends(require_admin)])
async def run_pending_research(body: PendingResearchRunRequest):
    """Research selected categories from the queue, STAGED (status='pending').
    SSE stream. No publish here — deferred to /research-review/approve.
    """
    from app.core.services.compliance_service import (
        research_specialization_for_jurisdiction,
        _get_or_create_jurisdiction,
        _missing_required_categories,
    )
    from app.core.services import vertical_coverage
    from app.core.services.scope_registry.research_loop import corpus_for_jurisdiction

    async def sse(gen):
        try:
            async for ev in gen:
                if ev.get("type") == "heartbeat":
                    yield ": heartbeat\n\n"
                else:
                    yield f"data: {json.dumps(ev, default=str)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        yield "data: [DONE]\n\n"

    # ---- category item ----
    if body.item_type == "category":
        if not body.state:
            raise HTTPException(status_code=400, detail="state required for a category run")

        async def category_gen():
            async with get_connection() as conn:
                jid = await _get_or_create_jurisdiction(
                    conn, body.city or "", body.state, body.county
                )
                if body.request_id:
                    await conn.execute(
                        "UPDATE jurisdiction_coverage_requests SET status='in_progress' "
                        "WHERE id=$1 AND status='pending'",
                        UUID(body.request_id),
                    )
                yield {"type": "started", "jurisdiction_id": str(jid)}

                # Resolve which categories to research (all outstanding if null).
                cats = body.categories
                if not cats:
                    chain = await _project_chain_to_location_categories(conn, jid)
                    cats = _missing_required_categories(chain)
                if not cats:
                    yield {"type": "complete", "new": 0, "message": "Nothing to research."}
                    return

                yield {"type": "researching", "categories": cats,
                       "message": f"Researching {len(cats)} category area(s), staged for review…"}
                try:
                    corpus, cidx = await corpus_for_jurisdiction(conn, jid, cats)
                except Exception:
                    corpus, cidx = "", {}
                # route_by_level=True: files state/federal rows on their own nodes
                # (default False writes them onto the leaf city — jparent01).
                task = asyncio.create_task(research_specialization_for_jurisdiction(
                    conn, jid, cats, "",
                    skip_existing=False,
                    grounded_corpus=corpus, citation_index=cidx,
                    route_by_level=True,
                    initial_status="pending",
                ))
                async for evt in _heartbeat_while_admin(task):
                    yield evt
                result = task.result() or {}
                yield {"type": "complete", "new": result.get("new", 0),
                       "message": f"Staged {result.get('new', 0)} requirement(s) for review."}

        return StreamingResponse(sse(category_gen()), media_type="text/event-stream",
                                 headers={"X-Accel-Buffering": "no"})

    # ---- vertical item ----
    if body.item_type == "vertical":
        if not body.company_id:
            raise HTTPException(status_code=400, detail="company_id required for a vertical run")
        company_id = UUID(body.company_id)

        async def vertical_gen():
            async with get_connection() as conn:
                resolved = await vertical_coverage.resolve_vertical(conn, company_id)
                if not resolved:
                    yield {"type": "error", "message": "No vertical for this company."}
                    return
                parent, slug, label, tag, _minted = resolved
                categories, context = await vertical_coverage.ensure_specialty(
                    conn, parent, slug, label
                )
                if not categories:
                    yield {"type": "complete", "new": 0, "message": "No specialty categories."}
                    return
                if body.categories:
                    categories = [c for c in categories if c in set(body.categories)]
                leaf_rows = await conn.fetch(
                    "SELECT DISTINCT jurisdiction_id FROM business_locations "
                    "WHERE company_id=$1 AND is_active=true AND jurisdiction_id IS NOT NULL",
                    company_id,
                )
                leaves = [r["jurisdiction_id"] for r in leaf_rows]
                chains = await vertical_coverage.chains_for_leaves(conn, leaves)
                all_nodes = sorted({jid for ch in chains.values() for jid, _ in ch})
                await vertical_coverage.backfill_ledger(conn, all_nodes, tag, categories)
                plan, _deferred = await vertical_coverage.plan_fill(conn, chains, tag, categories)

            if not plan:
                yield {"type": "complete", "new": 0, "message": "Already covered."}
                return
            yield {"type": "researching", "vertical": label, "cells": len(plan),
                   "message": f"Researching {len(plan)} {label} area(s), staged for review…"}

            # fill yields only between (minutes-long) research calls — merge a
            # heartbeat so proxies don't drop the stream.
            queue: asyncio.Queue = asyncio.Queue()

            async def _drive():
                async for ev in vertical_coverage.fill(
                    get_connection, company_id, plan, tag, context,
                    initial_status="pending",
                ):
                    await queue.put(ev)
                await queue.put(None)

            drive_task = asyncio.create_task(_drive())
            total_new = 0
            while True:
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_INTERVAL_ADMIN)
                except asyncio.TimeoutError:
                    yield {"type": "heartbeat"}
                    continue
                if ev is None:
                    break
                total_new += ev.get("new", 0)
                if ev.get("category"):
                    yield {"type": "cell_done", "category": ev["category"], "new": ev.get("new", 0)}
            await drive_task
            yield {"type": "complete", "new": total_new,
                   "message": f"Staged {total_new} {label} requirement(s) for review."}

        return StreamingResponse(sse(vertical_gen()), media_type="text/event-stream",
                                 headers={"X-Accel-Buffering": "no"})

    raise HTTPException(status_code=400, detail=f"Unknown item_type {body.item_type!r}")


@router.get("/research-review", dependencies=[Depends(require_admin)])
async def get_research_review():
    """Staged (status='pending') requirements grouped by jurisdiction+category,
    each annotated with the queue item it satisfies so approve can publish.
    """
    from app.core.services import vertical_coverage

    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT r.id, r.jurisdiction_id, r.category, r.title, r.description,
                   r.current_value, r.source_url, r.source_name, r.created_at,
                   r.regulation_key,
                   j.city, j.state, j.county, j.display_name
            FROM jurisdiction_requirements r
            JOIN jurisdictions j ON j.id = r.jurisdiction_id
            WHERE r.status = 'pending'
            ORDER BY j.state, j.city, r.category, r.title
            """
        )
        if not rows:
            return {"groups": []}

        pending_jids = list({r["jurisdiction_id"] for r in rows})

        # Which pending keys already have a confirmed, non-excluded authority
        # classification — i.e. approve will reconcile them into a real statute
        # citation ("codified"), vs the key still needs classifying in ScopeStudio's
        # cockpit first. Key-level existence (not chain-scoped): a confirmed
        # classification carrying the key is the prerequisite reconcile checks;
        # this is a directional "will it codify" hint, not the reconcile itself.
        pending_keys = list({r["regulation_key"] for r in rows if r["regulation_key"]})
        codifiable_keys: set = set()
        if pending_keys:
            codifiable_keys = {
                r["regulation_key"] for r in await conn.fetch(
                    "SELECT DISTINCT regulation_key FROM authority_item_classifications "
                    "WHERE status='confirmed' AND disposition <> 'excluded' "
                    "AND regulation_key = ANY($1::text[])",
                    pending_keys,
                )
            }

        # Annotate: which in-progress coverage request each pending row satisfies.
        # A category run's rows land on chain NODES (state/federal), so match by
        # the requesting jcr's whole chain, not the leaf.
        jcr_rows = await conn.fetch(
            "SELECT id, city, state, county, requested_by_company_id, admin_notes "
            "FROM jurisdiction_coverage_requests WHERE status = 'in_progress'"
        )
        # Map node jurisdiction_id -> [request_id,...] via each jcr's chain.
        node_to_requests: dict = {}
        for jcr in jcr_rows:
            jid = await conn.fetchval(
                "SELECT id FROM jurisdictions WHERE LOWER(city)=LOWER($1) AND UPPER(state)=UPPER($2) LIMIT 1",
                jcr["city"], jcr["state"],
            )
            if not jid:
                continue
            chains = await vertical_coverage.chains_for_leaves(conn, [jid])
            for _leaf, nodes in chains.items():
                for node_id, _lvl in nodes:
                    node_to_requests.setdefault(node_id, []).append(str(jcr["id"]))

        # Vertical ownership: ledger cell -> requesting company.
        ledger = await conn.fetch(
            "SELECT jurisdiction_id, category, requested_by_company_id "
            "FROM jurisdiction_vertical_coverage "
            "WHERE jurisdiction_id = ANY($1::uuid[]) AND requested_by_company_id IS NOT NULL",
            pending_jids,
        )
        ledger_map = {(l["jurisdiction_id"], l["category"]): l["requested_by_company_id"] for l in ledger}

        # Category display names.
        cat_slugs = list({r["category"] for r in rows})
        cat_names = {c["slug"]: c["name"] for c in await conn.fetch(
            "SELECT slug, name FROM compliance_categories WHERE slug = ANY($1::text[])", cat_slugs
        )}

        groups: dict = {}
        for r in rows:
            key = str(r["jurisdiction_id"])
            g = groups.setdefault(key, {
                "jurisdiction_id": key,
                "label": r["display_name"] or f"{r['city']}, {r['state']}",
                "city": r["city"], "state": r["state"],
                "request_ids": set(),
                "company_ids": set(),
                "rows": [],
            })
            g["rows"].append({
                "id": str(r["id"]),
                "category": r["category"],
                "category_name": cat_names.get(r["category"], r["category"]),
                "title": r["title"],
                "description": r["description"],
                "current_value": r["current_value"],
                "source_url": r["source_url"],
                "source_name": r["source_name"],
                "regulation_key": r["regulation_key"],
                # True → approve reconciles this into a verified statute citation.
                # False → goes live but needs classifying in ScopeStudio first.
                "will_codify": bool(r["regulation_key"] and r["regulation_key"] in codifiable_keys),
            })
            for rid in node_to_requests.get(r["jurisdiction_id"], []):
                g["request_ids"].add(rid)
            owner = ledger_map.get((r["jurisdiction_id"], r["category"]))
            if owner:
                g["company_ids"].add(str(owner))

        return {"groups": [
            {**g, "request_ids": sorted(g["request_ids"]), "company_ids": sorted(g["company_ids"])}
            for g in groups.values()
        ]}


@router.post("/research-review/approve")
async def approve_research_review(body: ResearchReviewDecision,
                                  background_tasks: BackgroundTasks,
                                  current_user=Depends(require_admin)):
    """Activate staged rows, then publish to waiting tenants (project + email).

    Publish context is taken from the request body (request_ids / company_ids),
    NOT re-derived from the activated rows' jurisdiction_id — routed rows sit on
    chain nodes, not the leaf a coverage request references.
    """
    from app.core.services.research_review import approve_staged

    ids = [UUID(i) for i in body.ids]
    # Activate + codify the staged rows (shared core with the Compliance Pilot).
    # Publish to waiting tenants is admin-queue-specific and stays below.
    core = await approve_staged(ids, getattr(current_user, "id", None), source="approve")

    published = 0
    # Category side: resolve each request's jurisdiction and run the publish loop.
    for rid in (body.request_ids or []):
        async with get_connection() as conn:
            jcr = await conn.fetchrow(
                "SELECT city, state, county FROM jurisdiction_coverage_requests WHERE id=$1",
                UUID(rid),
            )
            if not jcr:
                continue
            jid = await conn.fetchval(
                "SELECT id FROM jurisdictions WHERE LOWER(city)=LOWER($1) AND UPPER(state)=UPPER($2) LIMIT 1",
                jcr["city"], jcr["state"],
            )
        if jid:
            await _publish_research_to_requesters(jid)
            published += 1

    # Vertical side: reproject the requesting company's tabs + email its admins.
    for cid in (body.company_ids or []):
        try:
            await _publish_vertical_to_company(UUID(cid))
            published += 1
        except Exception as exc:
            logger.warning("approve: vertical publish failed for %s: %s", cid, exc)

    # Freeze each newly-live row's cited page as evidence, AFTER the response —
    # approve is the tenant-visibility moment (the snapshot that matters most in a
    # later dispute), but the fetches are slow external I/O, so they run via
    # BackgroundTasks. `approve_staged` already activated + codified + built the
    # per-row results; the snap targets ride back for the admin queue to freeze.
    if core["snap_targets"]:
        background_tasks.add_task(_snapshot_requirements_bg, core["snap_targets"], "approve")

    return {
        "activated": core["activated"],
        "published": published,
        "codified": core["codified"],
        "uncodified": core["uncodified"],
        "results": core["results"],
    }


@router.post("/research-review/reject", dependencies=[Depends(require_admin)])
async def reject_research_review(body: ResearchReviewDecision):
    """Delete staged rows; flip their ledger cells to 'failed' so plan_fill
    retries; revert the queue item to pending so it's actionable again.
    """
    ids = [UUID(i) for i in body.ids]
    async with get_connection() as conn:
        deleted = await conn.fetch(
            "DELETE FROM jurisdiction_requirements WHERE id = ANY($1::uuid[]) AND status='pending' "
            "RETURNING jurisdiction_id, category",
            ids,
        )
        # Flip matching vertical ledger cells covered -> failed (else backfill,
        # which counts only active rows, leaves a covered cell with zero rows,
        # never retried).
        pairs = list({(d["jurisdiction_id"], d["category"]) for d in deleted})
        for jid, cat in pairs:
            await conn.execute(
                "UPDATE jurisdiction_vertical_coverage SET status='failed', updated_at=NOW() "
                "WHERE jurisdiction_id=$1 AND category=$2 AND status='covered'",
                jid, cat,
            )
        # Revert queue items so they reappear as actionable.
        for rid in (body.request_ids or []):
            await conn.execute(
                "UPDATE jurisdiction_coverage_requests SET status='pending' "
                "WHERE id=$1 AND status='in_progress'",
                UUID(rid),
            )
    return {"deleted": len(deleted)}


@router.get("/studio/worklist", dependencies=[Depends(require_admin)])
async def get_studio_worklist():
    """One aggregate call powering the Compliance Studio Command Center.

    Merges BOTH funnels — demand (coverage requests → research → review →
    approve → codify) and supply (ingest → classify → confirm → reconcile) —
    into one prioritized action list, so the admin sees "what needs me now"
    instead of hunting across tabs. Aggregation + priority ordering (closest to
    AUTHORITATIVE first); the review/pending sources reuse the existing
    handlers, while the baseline backlog runs its own DEMAND-scoped query (only
    tenant-onboarded jurisdictions — NOT the full research-queue scan, which
    includes admin-paced manual-scoping cities that don't belong in the worklist).
    """
    review = await get_research_review()
    pending = await get_pending_research()

    async with get_connection() as conn:
        # keyless: active, uncodified rows with NO regulation_key — they can't
        # codify (codify_from_requirement's key-equality join 422s them), so
        # they'd otherwise cap the Authoritative meter below 100% invisibly.
        # Surfaced on the meter tooltip, not as a worklist action (no flow to
        # clear them yet — see plan: key-assignment is a follow-up).
        meters_row = await conn.fetchrow(
            "SELECT COUNT(*) FILTER (WHERE COALESCE(jr.status, 'active') = 'active') AS requirements, "
            "COUNT(*) FILTER (WHERE COALESCE(jr.status, 'active') = 'active' "
            f"AND {codified_sql('jr')}) AS codified, "
            "COUNT(*) FILTER (WHERE COALESCE(jr.status, 'active') = 'active' "
            f"AND NOT ({codified_sql('jr')}) AND jr.regulation_key IS NULL) AS keyless "
            "FROM jurisdiction_requirements jr"
        )

        # Baseline backlog — DEMAND-side only: jurisdictions a tenant actually
        # onboarded into (location_count > 0) that have zero researched rows.
        # Deliberately NOT the full /admin/research-queue scan: tenant-less
        # seeded cities are means-#1 (manual scoping) backlog, admin-paced via
        # the Coverage/Library tabs, and don't belong in "what needs me now".
        baseline_rows = await conn.fetch(
            """
            SELECT j.id AS jurisdiction_id, j.city, j.state, j.county,
                   lc.location_count, lc.company_count, j.created_at
            FROM jurisdictions j
            JOIN LATERAL (
                SELECT COUNT(*) AS location_count,
                       COUNT(DISTINCT bl.company_id) AS company_count
                FROM business_locations bl
                WHERE bl.jurisdiction_id = j.id
                  AND COALESCE(bl.is_active, true) = true
            ) lc ON lc.location_count > 0
            WHERE j.city IS NOT NULL AND j.city != ''
              AND NOT EXISTS (
                  SELECT 1 FROM jurisdiction_requirements jr
                  WHERE jr.jurisdiction_id = j.id
              )
            ORDER BY lc.location_count DESC, j.state, j.city
            """
        )

        # Active rows that went live but carry no verified statute citation —
        # the codify backlog. Split into auto_reconcilable (a confirmed
        # authority classification already exists for the key — one global
        # `POST /admin/scope-registry/reconcile` clears these) vs manual (no
        # classification yet — the real Codify-modal backlog). Same predicate
        # `reconcile_codifications` matches on (codify.py).
        #
        # blocked_* is the DEMAND on each row: how many live tenant locations /
        # companies already have it projected and are therefore being SHOWN
        # NOTHING for it, because the codified gate withholds uncited rows from
        # their tab. Without this the backlog is a flat list ordered by age, and
        # the admin cannot tell the row 15 companies are waiting on from the one
        # nobody has. Ordering by it is load-bearing, not cosmetic: `items`
        # truncates to 50 below, so demand-heavy rows must sort first or the
        # signal is cut off exactly where it matters most.
        uncodified_rows = await conn.fetch(
            """
            SELECT r.id, r.title, r.regulation_key, r.description, r.current_value,
                   r.source_url, r.source_name, r.created_at,
                   UPPER(j.state) AS state, LOWER(j.city) AS city,
                   COALESCE(d.blocked_locations, 0) AS blocked_locations,
                   COALESCE(d.blocked_companies, 0) AS blocked_companies,
                   EXISTS (
                       SELECT 1 FROM authority_item_classifications c
                       WHERE c.status = 'confirmed' AND c.disposition <> 'excluded'
                         AND c.regulation_key = r.regulation_key
                   ) AS auto_reconcilable
            FROM jurisdiction_requirements r
            JOIN jurisdictions j ON j.id = r.jurisdiction_id
            LEFT JOIN LATERAL (
                SELECT COUNT(DISTINCT cr.location_id) AS blocked_locations,
                       COUNT(DISTINCT bl.company_id) AS blocked_companies
                FROM compliance_requirements cr
                JOIN business_locations bl ON bl.id = cr.location_id
                                          AND COALESCE(bl.is_active, true) = true
                WHERE cr.jurisdiction_requirement_id = r.id
            ) d ON true
            WHERE COALESCE(r.status, 'active') = 'active'
              AND r.regulation_key IS NOT NULL
              AND NOT (""" + codified_sql("r") + """)
            ORDER BY d.blocked_companies DESC NULLS LAST,
                     d.blocked_locations DESC NULLS LAST,
                     r.created_at DESC
            """
        )

        # Same demand question across the WHOLE uncodified set — including the
        # keyless rows the query above filters out. Those can't codify yet, but
        # a tenant is still being denied them, so the meter must count them or
        # it under-reports what the gate is withholding.
        tenant_blocked = await conn.fetchval(
            """
            SELECT COUNT(*) FROM jurisdiction_requirements r
            WHERE COALESCE(r.status, 'active') = 'active'
              AND NOT (""" + codified_sql("r") + """)
              AND EXISTS (
                  SELECT 1 FROM compliance_requirements cr
                  JOIN business_locations bl ON bl.id = cr.location_id
                                            AND COALESCE(bl.is_active, true) = true
                  WHERE cr.jurisdiction_requirement_id = r.id
              )
            """
        ) or 0

        drift_open = await conn.fetchval(
            "SELECT COUNT(*) FROM authority_index_drift WHERE status = 'open'"
        ) or 0

        authority_indexes = await conn.fetch(
            "SELECT slug, name, unclassified_count FROM authority_indexes "
            "WHERE unclassified_count > 0 ORDER BY unclassified_count DESC"
        )

    manual_rows = [r for r in uncodified_rows if not r["auto_reconcilable"]]
    auto_count = len(uncodified_rows) - len(manual_rows)

    review_count = sum(len(g["rows"]) for g in review["groups"])
    pending_count = len(pending["items"])
    # Shape to the frontend's ResearchItem (same fields /admin/research-queue
    # returns); repo_count is 0 by construction (NOT EXISTS above).
    baseline_needs = [{
        "jurisdiction_id": str(r["jurisdiction_id"]),
        "city": r["city"], "state": r["state"], "county": r["county"],
        "repo_count": 0,
        "location_count": r["location_count"],
        "company_count": r["company_count"],
        "status": "needs_research",
        "created_at": r["created_at"].isoformat() if r["created_at"] else None,
    } for r in baseline_rows]
    confirm_total = sum(int(ix["unclassified_count"] or 0) for ix in authority_indexes)

    actions: list = []
    if review_count:
        actions.append({
            "kind": "review_staged", "priority": 1, "count": review_count,
            "groups": review["groups"],
        })
    if manual_rows or auto_count:
        actions.append({
            "kind": "codify_uncodified", "priority": 2, "count": len(manual_rows),
            "auto_reconcilable": auto_count,
            # Of the backlog, how much has a live tenant waiting on it — split
            # the same way the work is: by hand vs one Reconcile click.
            "tenant_blocked": sum(1 for r in manual_rows if r["blocked_companies"]),
            "tenant_blocked_auto": sum(
                1 for r in uncodified_rows if r["auto_reconcilable"] and r["blocked_companies"]
            ),
            "items": [{
                "id": str(r["id"]), "title": r["title"], "regulation_key": r["regulation_key"],
                "description": r["description"], "current_value": r["current_value"],
                "source_url": r["source_url"], "source_name": r["source_name"],
                "state": r["state"], "city": r["city"],
                "blocked_locations": int(r["blocked_locations"] or 0),
                "blocked_companies": int(r["blocked_companies"] or 0),
            } for r in manual_rows[:50]],
        })
    if pending_count:
        actions.append({
            "kind": "research_coverage", "priority": 3, "count": pending_count,
            "items": pending["items"][:50],
        })
    if confirm_total:
        actions.append({
            "kind": "confirm_authority", "priority": 4, "count": confirm_total,
            "by_index": [{"slug": ix["slug"], "name": ix["name"],
                          "unclassified_count": ix["unclassified_count"]} for ix in authority_indexes],
        })
    if drift_open:
        actions.append({"kind": "ack_drift", "priority": 5, "count": int(drift_open)})
    if baseline_needs:
        actions.append({
            "kind": "research_baseline", "priority": 6, "count": len(baseline_needs),
            "items": baseline_needs[:50],
        })

    open_items = sum(a["count"] for a in actions)

    return {
        "meters": {
            "codified": int(meters_row["codified"] or 0),
            "requirements": int(meters_row["requirements"] or 0),
            "keyless": int(meters_row["keyless"] or 0),
            # Uncodified rows a live tenant already has projected — i.e. what the
            # codified gate is actively withholding from somebody's tab right now.
            # Counts keyless rows too: they can't codify yet, but a tenant is
            # still being denied them.
            "tenant_blocked": int(tenant_blocked),
            "open_items": open_items,
        },
        "actions": actions,
    }


@router.get("/studio/codified-breakdown", dependencies=[Depends(require_admin)])
async def get_codified_breakdown():
    """The corpus as `jurisdiction × domain × category`, each cell `codified/total`.

    The Codified tab's schema. A flat list of 1773 rows cannot answer the only
    question worth asking here — "how much of federal labor law have we actually
    proven?" — so the shape has to be the jurisdiction that imposes the rule
    crossed with the subject it governs.

    Cells key on `jurisdiction_id`, not on the level string, because level does
    NOT identify an authority: `national` in this catalog means a foreign
    country (Mexico, the UK, France, Singapore — 119 rows), while US federal law
    is level `federal`. Collapsing the two — the fold the tenant-side lens does,
    where every row IS American — files Mexican labor law under "Federal" and
    inflates the US denominator from 175 to 294.

    `compliance_categories` is the vocabulary: `.group` is the noun ("federal
    LABOR laws") and `.name` the human label. It's a LEFT JOIN because the
    category set is discovered at runtime (vertical_coverage writes new ones),
    so a row can carry a category the table doesn't know yet — that bucket reads
    'other' rather than vanishing from a total the tab must reconcile.

    One GROUP BY over the whole catalog (~780 cells), so the tab filters
    client-side and never re-queries to open a section.
    """
    trio = codified_sql("jr")
    async with get_connection() as conn:
        rows = await conn.fetch(
            f"""
            SELECT
                j.id AS jurisdiction_id,
                j.level::text AS level,
                j.country_code,
                UPPER(j.state) AS state,
                j.display_name AS jurisdiction_name,
                jr.category,
                cc."group" AS cat_group,
                cc.name AS category_name,
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE {trio}) AS codified
            FROM jurisdiction_requirements jr
            JOIN jurisdictions j ON j.id = jr.jurisdiction_id
            LEFT JOIN compliance_categories cc ON cc.slug = jr.category
            WHERE COALESCE(jr.status, 'active') = 'active'
            GROUP BY 1, 2, 3, 4, 5, 6, 7, 8
            """
        )

    return {
        "rows": [
            {
                "jurisdiction_id": str(r["jurisdiction_id"]),
                "level": r["level"],
                "country_code": r["country_code"],
                "state": r["state"],
                "jurisdiction_name": r["jurisdiction_name"],
                "category": r["category"],
                "group": r["cat_group"] or "other",
                "category_name": r["category_name"] or r["category"],
                "total": int(r["total"]),
                "codified": int(r["codified"]),
            }
            for r in rows
        ]
    }


@router.get("/studio/codified-funnel", dependencies=[Depends(require_admin)])
async def get_codified_funnel(
    state: Optional[str] = None,
    category: Optional[str] = None,
):
    """Stage counts for the Codified tab: scoped → pending → researched → codified.

    Every stage but `scoped` is one GROUP BY over `jurisdiction_requirements`,
    because every stage but `scoped` IS a row in it. `scoped` is the obligation
    we know applies and have not written a row for yet, which only
    `chain_uncodified` can answer, and only per jurisdiction chain — so it stays
    null until a state is picked. It is also labor-domain only (its `labor_only`
    default, matching the Labor scope panel that triggers the research), which
    the tile has to say out loud rather than imply a whole-corpus number.
    """
    from app.core.services.scope_registry.codify import chain_uncodified

    conditions: List[str] = []
    params: List[Any] = []
    if state and state.strip():
        params.append(state.strip().upper())
        conditions.append(f"j.state = ${len(params)}")
    if category and category.strip():
        params.append(category.strip())
        conditions.append(f"jr.category = ${len(params)}")
    where_clause = (" WHERE " + " AND ".join(conditions)) if conditions else ""

    trio = codified_sql("jr")
    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"""
            SELECT
                COUNT(*) FILTER (WHERE jr.status = 'pending') AS pending,
                COUNT(*) FILTER (WHERE COALESCE(jr.status, 'active') = 'active'
                                   AND NOT ({trio})) AS researched,
                COUNT(*) FILTER (WHERE COALESCE(jr.status, 'active') = 'active'
                                   AND {trio}) AS codified,
                COUNT(*) FILTER (WHERE COALESCE(jr.status, 'active') = 'active'
                                   AND NOT ({trio})
                                   AND jr.regulation_key IS NULL) AS keyless
            FROM jurisdiction_requirements jr
            JOIN jurisdictions j ON j.id = jr.jurisdiction_id
            {where_clause}
            """,
            *params,
        )

        scoped = None
        if state and state.strip():
            work = await chain_uncodified(conn, state=state.strip().upper())
            scoped = {"keyed": len(work["keyed"]), "unkeyed": len(work["unkeyed"])}

    return {
        "state": state.strip().upper() if state and state.strip() else None,
        "category": category or None,
        "scoped": scoped,
        "pending": int(row["pending"] or 0),
        "researched": int(row["researched"] or 0),
        "codified": int(row["codified"] or 0),
        "keyless": int(row["keyless"] or 0),
    }


@router.post("/studio/assistant", dependencies=[Depends(require_admin)])
async def studio_assistant(body: StudioAssistantRequest):
    """Read-only guide over the Compliance Studio worklist. Explains the system
    (codify = verified statute citation = authoritative; scope = exhaustive) and
    tells the admin what needs attention and why, grounded on the live worklist
    snapshot the client sends. NO tool calls, NO mutations — every real action
    still goes through its existing endpoint; this only narrates + points.
    """
    import os
    from google import genai
    from app.core.services.genai_client import get_genai_client
    from google.genai import types as genai_types
    from app.core.services.rate_limiter import get_rate_limiter, RateLimitExceeded
    from app.core.services.gemini_compliance import DEFAULT_LITE_MODEL

    limiter = get_rate_limiter()
    try:
        await limiter.check_limit("studio_assistant")
    except RateLimitExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc))

    # Low-stakes narration call — always flash-lite, independent of the
    # configured research-model tier (that governs the heavier research runs).
    model = DEFAULT_LITE_MODEL

    system_prompt = (
        "You are a read-only guide inside Matcha's Compliance Studio, an internal "
        "admin tool. The mission: grow the most authoritative compliance library "
        "anywhere, via two funnels into one repository. SUPPLY funnel: scope a "
        "regulation -> ingest the authority source -> classify -> confirm -> "
        "research a value -> codify. DEMAND funnel: a company onboards -> triggers "
        "a coverage gap -> the gap becomes a coverage request -> research runs -> "
        "the result is staged for review -> an admin approves it (goes live) -> "
        "codify (a verified statute citation is attached). CODIFIED means the row "
        "has a verified statute citation -- that is what makes the data "
        "AUTHORITATIVE. Businesses rely on this to know they are compliant. "
        "SCOPING is the exhaustiveness check -- are we covering everything a "
        "business in a given industry/jurisdiction needs. "
        "You are given the CURRENT worklist as JSON -- a prioritized action list "
        "(review_staged, codify_uncodified, research_coverage, confirm_authority, "
        "ack_drift, research_baseline) each with a count. Answer the admin's "
        "question using ONLY this data -- do not invent counts or claim you did "
        "something. You cannot perform any action; you can only explain what an "
        "action kind means, why it matters, and which one to do next (usually the "
        "lowest 'priority' number with count > 0 -- review_staged and "
        "codify_uncodified are closest to making data authoritative). Be concise, "
        "plain English, 2-4 sentences unless asked to elaborate."
    )
    worklist_json = json.dumps(body.worklist or {}, default=str)
    prompt = f"{system_prompt}\n\nCurrent worklist:\n{worklist_json}\n\nAdmin question: {body.question}"

    async def event_stream():
        try:
            api_key = os.getenv("GEMINI_API_KEY") or get_settings().gemini_api_key
            if not api_key:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Gemini not configured'})}\n\n"
                yield "data: [DONE]\n\n"
                return
            client = get_genai_client(api_key=api_key)
            await limiter.record_call("studio_assistant")
            response = await client.aio.models.generate_content_stream(
                model=model, contents=prompt,
                config=genai_types.GenerateContentConfig(temperature=0.3, max_output_tokens=800),
            )
            async for chunk in response:
                if chunk.text:
                    yield f"data: {json.dumps({'type': 'content', 'text': chunk.text})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get(
    "/error-logs",
    response_model=ErrorLogsResponse,
    dependencies=[Depends(require_admin)],
)
async def get_error_logs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    path_filter: Optional[str] = Query(None, description="Filter by path substring"),
    error_type: Optional[str] = Query(None, description="Filter by error type"),
):
    """Return recent application error logs."""
    async with get_connection() as conn:
        where_clauses = []
        params: list = []
        idx = 1

        if path_filter:
            where_clauses.append(f"path ILIKE ${idx}")
            params.append(f"%{path_filter}%")
            idx += 1
        if error_type:
            where_clauses.append(f"error_type = ${idx}")
            params.append(error_type)
            idx += 1

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM error_logs {where_sql}", *params
        )

        rows = await conn.fetch(
            f"""SELECT id, timestamp, method, path, status_code,
                       error_type, error_message, traceback,
                       user_id, user_role, company_id, query_params
                FROM error_logs {where_sql}
                ORDER BY timestamp DESC
                LIMIT ${idx} OFFSET ${idx + 1}""",
            *params, limit, offset,
        )

    items = [
        ErrorLogItem(
            id=str(r["id"]),
            timestamp=r["timestamp"],
            method=r["method"],
            path=r["path"],
            status_code=r["status_code"],
            error_type=r["error_type"],
            error_message=r["error_message"],
            traceback=r["traceback"],
            user_id=str(r["user_id"]) if r["user_id"] else None,
            user_role=r["user_role"],
            company_id=str(r["company_id"]) if r["company_id"] else None,
            query_params=r["query_params"],
        )
        for r in rows
    ]
    return ErrorLogsResponse(items=items, total=total or 0)


@router.delete("/error-logs", dependencies=[Depends(require_admin)])
async def clear_error_logs():
    """Delete all error logs."""
    async with get_connection() as conn:
        count = await conn.fetchval("DELETE FROM error_logs RETURNING COUNT(*)")
    return {"deleted": count or 0}


@router.get("/payer-policies/overview", dependencies=[Depends(require_admin)])
async def payer_policies_overview():
    """Aggregated view of payer policy data: counts, staleness, field completeness."""
    async with get_connection() as conn:
        summary = await conn.fetchrow("""
            SELECT
                count(*) AS total,
                count(DISTINCT payer_name) AS payer_count,
                count(CASE WHEN coverage_status = 'covered' THEN 1 END) AS covered,
                count(CASE WHEN coverage_status = 'conditional' THEN 1 END) AS conditional,
                count(CASE WHEN coverage_status = 'not_covered' THEN 1 END) AS not_covered,
                count(CASE WHEN research_source = 'cms_api' THEN 1 END) AS from_cms,
                count(CASE WHEN research_source = 'gemini' THEN 1 END) AS from_gemini,
                count(CASE WHEN clinical_criteria IS NOT NULL AND clinical_criteria != '' THEN 1 END) AS has_criteria,
                count(CASE WHEN procedure_codes IS NOT NULL AND array_length(procedure_codes, 1) > 0 THEN 1 END) AS has_codes,
                count(CASE WHEN source_url IS NOT NULL AND source_url != '' THEN 1 END) AS has_source_url,
                max(last_verified_at) AS last_ingest,
                count(CASE WHEN last_verified_at IS NOT NULL
                    AND EXTRACT(DAY FROM NOW() - last_verified_at) > staleness_warning_days THEN 1 END) AS stale_warning,
                count(CASE WHEN last_verified_at IS NOT NULL
                    AND EXTRACT(DAY FROM NOW() - last_verified_at) > staleness_critical_days THEN 1 END) AS stale_critical
            FROM payer_medical_policies
        """)

        by_payer = await conn.fetch("""
            SELECT payer_name, count(*) AS count,
                   count(CASE WHEN coverage_status = 'covered' THEN 1 END) AS covered,
                   count(CASE WHEN coverage_status = 'conditional' THEN 1 END) AS conditional
            FROM payer_medical_policies
            GROUP BY payer_name ORDER BY count(*) DESC
        """)

    s = dict(summary)
    total = s["total"] or 1
    return {
        "total": s["total"],
        "payer_count": s["payer_count"],
        "coverage": {
            "covered": s["covered"],
            "conditional": s["conditional"],
            "not_covered": s["not_covered"],
        },
        "sources": {
            "cms": s["from_cms"],
            "gemini": s["from_gemini"],
        },
        "field_completeness": {
            "clinical_criteria_pct": round(s["has_criteria"] / total * 100, 1),
            "procedure_codes_pct": round(s["has_codes"] / total * 100, 1),
            "source_url_pct": round(s["has_source_url"] / total * 100, 1),
        },
        "staleness": {
            "warning": s["stale_warning"],
            "critical": s["stale_critical"],
        },
        "last_ingest": s["last_ingest"].isoformat() if s["last_ingest"] else None,
        "by_payer": [{"payer": r["payer_name"], "count": r["count"], "covered": r["covered"], "conditional": r["conditional"]} for r in by_payer],
    }


@router.get("/payer-policies/integrity-check", dependencies=[Depends(require_admin)])
async def payer_policies_integrity_check():
    """Integrity check: stale policies, missing fields, low confidence, recent changes."""
    async with get_connection() as conn:
        # Stale policies
        stale = await conn.fetch("""
            SELECT id, payer_name, policy_number, policy_title, coverage_status,
                   EXTRACT(DAY FROM NOW() - last_verified_at)::int AS days_since_verified,
                   staleness_warning_days, staleness_critical_days
            FROM payer_medical_policies
            WHERE last_verified_at IS NOT NULL
              AND EXTRACT(DAY FROM NOW() - last_verified_at) > staleness_warning_days
            ORDER BY EXTRACT(DAY FROM NOW() - last_verified_at) DESC
            LIMIT 200
        """)

        stale_list = []
        for r in stale:
            days = r["days_since_verified"] or 0
            level = "critical" if days >= (r["staleness_critical_days"] or 180) else "warning"
            stale_list.append({
                "id": str(r["id"]),
                "payer": r["payer_name"],
                "policy_number": r["policy_number"],
                "title": r["policy_title"],
                "coverage_status": r["coverage_status"],
                "days_since_verified": days,
                "level": level,
            })

        # Missing fields
        missing_fields = await conn.fetch("""
            SELECT id, payer_name, policy_number, policy_title,
                   CASE WHEN clinical_criteria IS NULL OR clinical_criteria = '' THEN true ELSE false END AS missing_criteria,
                   CASE WHEN procedure_codes IS NULL OR array_length(procedure_codes, 1) IS NULL THEN true ELSE false END AS missing_codes,
                   CASE WHEN source_url IS NULL OR source_url = '' THEN true ELSE false END AS missing_source
            FROM payer_medical_policies
            WHERE (clinical_criteria IS NULL OR clinical_criteria = '')
               OR (procedure_codes IS NULL OR array_length(procedure_codes, 1) IS NULL)
               OR (source_url IS NULL OR source_url = '')
            ORDER BY payer_name, policy_number
            LIMIT 200
        """)

        missing_list = [
            {
                "id": str(r["id"]),
                "payer": r["payer_name"],
                "policy_number": r["policy_number"],
                "title": r["policy_title"],
                "missing": [f for f, col in [
                    ("clinical_criteria", "missing_criteria"),
                    ("procedure_codes", "missing_codes"),
                    ("source_url", "missing_source"),
                ] if r[col]],
            }
            for r in missing_fields
        ]

        # Low confidence (Gemini research)
        low_conf = await conn.fetch("""
            SELECT id, payer_name, policy_number, policy_title,
                   (metadata->>'confidence')::float AS confidence
            FROM payer_medical_policies
            WHERE research_source = 'gemini'
              AND metadata->>'confidence' IS NOT NULL
              AND (metadata->>'confidence')::float < 0.5
            ORDER BY (metadata->>'confidence')::float
            LIMIT 100
        """)

        low_conf_list = [
            {
                "id": str(r["id"]),
                "payer": r["payer_name"],
                "policy_number": r["policy_number"],
                "title": r["policy_title"],
                "confidence": r["confidence"],
            }
            for r in low_conf
        ]

        # Recent changes
        changes = await conn.fetch("""
            SELECT cl.id, cl.policy_id, cl.field_changed, cl.old_value, cl.new_value,
                   cl.change_source, cl.changed_at,
                   p.payer_name, p.policy_number, p.policy_title
            FROM payer_policy_change_log cl
            JOIN payer_medical_policies p ON p.id = cl.policy_id
            WHERE cl.changed_at > NOW() - INTERVAL '30 days'
            ORDER BY cl.changed_at DESC
            LIMIT 100
        """)

        changes_list = [
            {
                "id": str(r["id"]),
                "payer": r["payer_name"],
                "policy_number": r["policy_number"],
                "title": r["policy_title"],
                "field": r["field_changed"],
                "old_value": r["old_value"],
                "new_value": r["new_value"],
                "source": r["change_source"],
                "changed_at": r["changed_at"].isoformat() if r["changed_at"] else None,
            }
            for r in changes
        ]

    return {
        "stale_policies": stale_list,
        "stale_count": len(stale_list),
        "missing_fields": missing_list,
        "missing_fields_count": len(missing_list),
        "low_confidence": low_conf_list,
        "low_confidence_count": len(low_conf_list),
        "recent_changes": changes_list,
        "recent_changes_count": len(changes_list),
    }


@router.post("/payer-policies/run-staleness-check", dependencies=[Depends(require_admin)])
async def payer_run_staleness_check():
    """Scan payer policies for staleness and upsert repository_alerts."""
    created = 0
    resolved = 0

    async with get_connection() as conn:
        stale_rows = await conn.fetch("""
            SELECT id, payer_name, policy_number, policy_title,
                   EXTRACT(DAY FROM NOW() - last_verified_at)::int AS days_since_verified,
                   staleness_warning_days, staleness_critical_days
            FROM payer_medical_policies
            WHERE last_verified_at IS NOT NULL
              AND EXTRACT(DAY FROM NOW() - last_verified_at) > staleness_warning_days
        """)

        for r in stale_rows:
            days = r["days_since_verified"] or 0
            if days >= (r["staleness_critical_days"] or 180):
                alert_type, severity = "payer_stale_critical", "critical"
            else:
                alert_type, severity = "payer_stale_warning", "warning"

            message = f"{r['policy_title'] or r['policy_number']} ({r['payer_name']}) is {days} days past verification"
            # Check if open alert already exists for this policy
            existing_alert = await conn.fetchval(
                "SELECT id FROM repository_alerts WHERE requirement_id = $1 AND alert_type = $2 AND status = 'open'",
                r["id"], alert_type,
            )
            if existing_alert:
                await conn.execute(
                    "UPDATE repository_alerts SET severity = $1, message = $2, days_overdue = $3 WHERE id = $4",
                    severity, message, days - (r["staleness_warning_days"] or 90), existing_alert,
                )
            else:
                await conn.execute("""
                    INSERT INTO repository_alerts
                        (alert_type, severity, requirement_id, category, message, days_overdue, regulation_key)
                    VALUES ($1, $2, $3, 'payer_policy', $4, $5, $6)
                """, alert_type, severity, r["id"], message,
                    days - (r["staleness_warning_days"] or 90), r["policy_number"])
                created += 1
            if "INSERT" in result:
                created += 1

        # Auto-resolve
        resolved = await conn.fetchval("""
            UPDATE repository_alerts
            SET status = 'resolved', resolved_at = NOW()
            WHERE status = 'open'
              AND alert_type IN ('payer_stale_warning', 'payer_stale_critical')
              AND requirement_id NOT IN (
                  SELECT id FROM payer_medical_policies
                  WHERE EXTRACT(DAY FROM NOW() - last_verified_at) > staleness_warning_days
              )
            RETURNING id
        """) or 0

    return {
        "alerts_created": created,
        "alerts_resolved": resolved if isinstance(resolved, int) else 0,
        "stale_found": len(stale_rows),
    }


@router.post("/matcha-lite/invite-tokens")
async def create_matcha_lite_invite_token(
    body: MatchaLiteInviteRequest,
    current_user=Depends(require_admin),
):
    """Generate a one-use comp signup link that activates on registration (no Stripe).

    The token is tier-agnostic — the activated tier is set by which signup page
    the link points to. We return a Lite, Matcha-X, and Compliance link for the
    same token; the admin sends whichever tier they're comping.
    """
    token = secrets.token_urlsafe(48)
    base_url = get_settings().app_base_url.rstrip("/")
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """INSERT INTO matcha_lite_invite_tokens (token, created_by, note)
               VALUES ($1, $2, $3)
               RETURNING id, token, note, created_at""",
            token, current_user.id, body.note,
        )
    return {
        "id": str(row["id"]),
        "token": row["token"],
        "note": row["note"],
        "signup_url": f"{base_url}/lite/signup?invite_token={token}",
        "signup_url_x": f"{base_url}/matcha-x/signup?invite_token={token}",
        "signup_url_compliance": f"{base_url}/compliance/signup?invite_token={token}",
        "created_at": row["created_at"].isoformat(),
    }


@router.get("/matcha-lite/invite-tokens")
async def list_matcha_lite_invite_tokens(current_user=Depends(require_admin)):
    """List all Matcha Lite invite tokens with usage status."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """SELECT t.id, t.token, t.note, t.created_at, t.used_at,
                      c.name AS company_name
               FROM matcha_lite_invite_tokens t
               LEFT JOIN companies c ON c.id = t.used_by_company_id
               ORDER BY t.created_at DESC
               LIMIT 200""",
        )
    base_url = get_settings().app_base_url.rstrip("/")
    return [
        {
            "id": str(r["id"]),
            "token": r["token"],
            "note": r["note"],
            "signup_url": f"{base_url}/lite/signup?invite_token={r['token']}",
            "signup_url_x": f"{base_url}/matcha-x/signup?invite_token={r['token']}",
            "signup_url_compliance": f"{base_url}/compliance/signup?invite_token={r['token']}",
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "used_at": r["used_at"].isoformat() if r["used_at"] else None,
            "company_name": r["company_name"],
        }
        for r in rows
    ]


@router.delete("/matcha-lite/invite-tokens/{token_id}")
async def delete_matcha_lite_invite_token(token_id: UUID, current_user=Depends(require_admin)):
    """Delete an unused Matcha Lite invite token."""
    async with get_connection() as conn:
        result = await conn.execute(
            "DELETE FROM matcha_lite_invite_tokens WHERE id = $1 AND used_at IS NULL",
            token_id,
        )
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Token not found or already used")
    return {"ok": True}


@router.get("/cappe/accounts", dependencies=[Depends(require_admin)])
async def admin_list_cappe_accounts():
    """Roster of Cappe signups with plan + per-account site/order/revenue rollups."""
    async with get_connection() as conn:
        accounts = await conn.fetch(
            """
            SELECT id, email, name, plan, status, account_type, created_at
            FROM cappe_accounts
            ORDER BY created_at DESC
            """
        )
        sites = await conn.fetch(
            """
            SELECT s.id, s.account_id, s.name, s.slug, s.subdomain, s.custom_domain,
                   s.status, s.created_at, s.published_at,
                   COUNT(DISTINCT p.id) AS page_count,
                   COUNT(DISTINCT o.id) AS order_count,
                   COALESCE(SUM(o.subtotal_cents)
                       FILTER (WHERE o.status = ANY($1::text[])), 0) AS revenue_cents
            FROM cappe_sites s
            LEFT JOIN cappe_pages p ON p.site_id = s.id
            LEFT JOIN cappe_orders o ON o.site_id = s.id
            GROUP BY s.id
            ORDER BY s.created_at DESC
            """,
            list(_CAPPE_PAID_STATUSES),
        )

    sites_by_account: Dict[str, list] = {}
    for row in sites:
        sites_by_account.setdefault(str(row["account_id"]), []).append(_cappe_site_row(row))

    out_accounts = []
    plan_counts: Dict[str, int] = {}
    total_sites = 0
    total_published = 0
    total_orders = 0
    total_revenue = 0
    for a in accounts:
        acct_id = str(a["id"])
        acct_sites = sites_by_account.get(acct_id, [])
        published = sum(1 for s in acct_sites if s["status"] == "published")
        orders = sum(s["order_count"] for s in acct_sites)
        revenue = sum(s["revenue_cents"] for s in acct_sites)
        plan = a["plan"] or "free"
        plan_counts[plan] = plan_counts.get(plan, 0) + 1
        total_sites += len(acct_sites)
        total_published += published
        total_orders += orders
        total_revenue += revenue
        out_accounts.append({
            "id": acct_id,
            "email": a["email"],
            "name": a["name"],
            "plan": plan,
            "status": a["status"],
            "account_type": a["account_type"],
            "created_at": a["created_at"].isoformat() if a["created_at"] else None,
            "site_count": len(acct_sites),
            "published_count": published,
            "order_count": orders,
            "revenue_cents": revenue,
            "sites": acct_sites,
        })

    return {
        "accounts": out_accounts,
        "totals": {
            "account_count": len(out_accounts),
            "plan_counts": plan_counts,
            "site_count": total_sites,
            "published_count": total_published,
            "order_count": total_orders,
            "revenue_cents": total_revenue,
        },
    }
