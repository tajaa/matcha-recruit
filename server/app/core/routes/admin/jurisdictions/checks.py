"""Admin jurisdictions routes — SSE research checks (split of jurisdictions.py). top-metros/check MUST register before {jurisdiction_id}/check (no :uuid converter there) — preserved by keeping this file's internal order untouched."""
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


