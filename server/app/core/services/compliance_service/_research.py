"""compliance_service.research — J6 split of compliance_service.py."""
from typing import Optional, List, AsyncGenerator, Dict, Any, Callable, Tuple
from uuid import UUID
from datetime import date, datetime, timedelta
import asyncio
import json
import logging
import re

import asyncpg
import httpx
from fastapi import HTTPException

from app.core.services.scope_registry.codify import codified_sql
from app.core.services.company_contacts import get_company_name_and_contacts
from app.core.services.jurisdiction_context import (
    get_known_sources,
    record_source,
    extract_domain,
    build_context_prompt,
    get_source_reputations,
    update_source_accuracy,
)
from app.core.models.compliance import (
    BusinessLocation,
    ComplianceRequirement,
    ComplianceAlert,
    LocationCreate,
    LocationUpdate,
    AutoCheckSettings,
    RequirementResponse,
    AlertResponse,
    CheckLogEntry,
    UpcomingLegislationResponse,
    VerificationResult,
    ComplianceSummary,
)
from app.core.compliance_registry import (
    LABOR_CATEGORIES as REQUIRED_LABOR_CATEGORIES,
    HEALTHCARE_CATEGORIES,
    ONCOLOGY_CATEGORIES,
    MEDICAL_COMPLIANCE_CATEGORIES,
    LIFE_SCIENCES_CATEGORIES,
    INDUSTRY_TAGS as MEDICAL_COMPLIANCE_INDUSTRY_TAGS,
)

logger = logging.getLogger(__name__)

from app.core.services.compliance_service._shared import (
    _heartbeat_while,
)
from app.core.services.compliance_service._normalize import (
    _CODE_TO_STATE_NAME,
    _INDUSTRY_SPECIFIC_RATE_TYPES,
    _clamp_varchar_fields,
    _missing_required_categories,
    _normalize_category,
    _normalize_rate_type,
    _normalize_requirement_categories,
)
from app.core.services.compliance_service._industry import (
    _INDUSTRY_RESEARCH_CONTEXT,
)
from app.core.services.compliance_service._verification import (
    format_corrections_for_prompt,
    get_recent_corrections,
)
from app.core.services.compliance_service._jurisdictions import (
    _get_state_jurisdiction_id,
    _jurisdiction_row_to_dict,
    _load_jurisdiction_requirements,
    _lookup_has_local_ordinance,
    _try_load_state_requirements,
)
from app.core.services.compliance_service._hierarchy import (
    _filter_city_level_requirements,
    _filter_with_preemption,
)
from app.core.services.compliance_service._catalog_writes import (
    _upsert_jurisdiction_requirements_routed,
    _upsert_requirements_additive,
)



async def _research_healthcare_requirements_for_jurisdiction(
    conn,
    jurisdiction_id: UUID,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> Dict[str, Any]:
    """Research missing healthcare-only categories inline for a jurisdiction."""
    from app.core.services.gemini_compliance import get_gemini_compliance_service
    from app.core.services.jurisdiction_context import get_known_sources, build_context_prompt, get_global_authority_sources

    j = await conn.fetchrow(
        "SELECT id, city, state, county FROM jurisdictions WHERE id = $1",
        jurisdiction_id,
    )
    if not j:
        return {"error": "Jurisdiction not found", "new": 0, "categories": [], "failed": []}

    city = j["city"]
    state = j["state"]
    county = j.get("county")
    location_name = f"{city}, {state}"

    has_local_ordinance = await _lookup_has_local_ordinance(conn, city, state)
    known_sources = await get_known_sources(conn, jurisdiction_id)
    source_context = build_context_prompt(known_sources)
    source_context += get_global_authority_sources(list(HEALTHCARE_CATEGORIES))
    corrections = await get_recent_corrections(jurisdiction_id)
    corrections_context = format_corrections_for_prompt(corrections)

    try:
        preemption_rows = await conn.fetch(
            "SELECT category, allows_local_override FROM state_preemption_rules WHERE state = $1",
            state.upper(),
        )
        preemption_rules = {
            row["category"]: row["allows_local_override"] for row in preemption_rows
        }
    except asyncpg.UndefinedTableError:
        preemption_rules = {}
    except Exception as e:
        logger.warning(f"preemption rules lookup failed: {e}")
        preemption_rules = {}

    existing = await conn.fetch(
        "SELECT DISTINCT category FROM jurisdiction_requirements WHERE jurisdiction_id = $1",
        jurisdiction_id,
    )
    existing_cats = {r["category"] for r in existing}
    missing = sorted(cat for cat in HEALTHCARE_CATEGORIES if cat not in existing_cats)

    if not missing:
        print(f"[Healthcare Research] All healthcare categories already present for {location_name}")
        return {
            "new": 0,
            "location": location_name,
            "categories": [],
            "failed": [],
            "requirements": [],
            "skipped": True,
        }

    print(
        f"[Healthcare Research] Researching {len(missing)} healthcare categories "
        f"for {location_name}: {', '.join(missing)}"
    )

    service = get_gemini_compliance_service()
    total_new = 0
    failed_categories: List[str] = []
    added_requirements: List[Dict[str, Any]] = []

    for idx, category in enumerate(missing, start=1):
        print(
            f"[Healthcare Research] [{idx}/{len(missing)}] Researching {category} "
            f"for {location_name}..."
        )
        if progress_callback:
            progress_callback(
                idx,
                len(missing),
                f"Researching {category.replace('_', ' ')} for {location_name}...",
            )

        try:
            reqs = await service.research_location_compliance(
                city=city,
                state=state,
                county=county,
                categories=[category],
                source_context=source_context,
                corrections_context=corrections_context,
                preemption_rules=preemption_rules,
                has_local_ordinance=has_local_ordinance,
            )
            reqs = reqs or []

            for req in reqs:
                _clamp_varchar_fields(req)
                if not req.get("applicable_industries"):
                    req["applicable_industries"] = ["healthcare"]

            if reqs:
                await _upsert_requirements_additive(conn, jurisdiction_id, reqs, research_source="gemini")
                total_new += len(reqs)
                added_requirements.extend(reqs)
                print(
                    f"[Healthcare Research]   -> {len(reqs)} requirements saved "
                    f"for {category}"
                )
            else:
                print(f"[Healthcare Research]   -> No results for {category}")
        except Exception as e:
            failed_categories.append(category)
            print(f"[Healthcare Research]   -> Error researching {category}: {e}")

    print(
        f"[Healthcare Research] Complete for {location_name}: {total_new} new, "
        f"{len(failed_categories)} failed"
    )

    if failed_categories and total_new == 0:
        raise RuntimeError(
            f"All healthcare categories failed for {location_name}: "
            f"{', '.join(failed_categories)}"
        )

    # ── Phase 2: Triggered research based on facility attributes ──
    from app.core.compliance_registry import get_activated_profiles

    try:
        loc_rows = await conn.fetch(
            "SELECT facility_attributes FROM business_locations WHERE jurisdiction_id = $1",
            jurisdiction_id,
        )
        all_facility_attrs = set()
        for lr in loc_rows:
            fa = lr["facility_attributes"]
            if isinstance(fa, str):
                try:
                    fa = json.loads(fa)
                except (json.JSONDecodeError, TypeError):
                    continue
            if fa:
                # Collect unique profiles across all linked locations
                for profile in get_activated_profiles(fa):
                    all_facility_attrs.add(profile.key)
    except Exception as e:
        print(f"[Healthcare Research] Error loading facility attributes: {e}")
        all_facility_attrs = set()

    if all_facility_attrs:
        from app.core.compliance_registry import TRIGGER_PROFILES

        activated_profiles = [p for p in TRIGGER_PROFILES if p.key in all_facility_attrs]
        for profile in activated_profiles:
            trigger_cats = [
                c for c in profile.applicable_categories
                if c in HEALTHCARE_CATEGORIES or c in MEDICAL_COMPLIANCE_CATEGORIES
            ]
            if not trigger_cats:
                continue

            print(
                f"[Healthcare Research] Phase 2: Triggered research for "
                f"{profile.label} ({len(trigger_cats)} categories)"
            )
            if progress_callback:
                progress_callback(
                    0, 0,
                    f"Researching {profile.label}-specific requirements...",
                )

            try:
                triggered_reqs = await service.research_triggered_requirements(
                    city=city,
                    state=state,
                    county=county,
                    profile_key=profile.key,
                    profile_label=profile.label,
                    trigger_condition=profile.trigger_condition,
                    research_instruction=profile.research_instruction,
                    categories=trigger_cats,
                    source_context=source_context,
                )

                for req in triggered_reqs:
                    _clamp_varchar_fields(req)
                    if not req.get("applicable_industries"):
                        req["applicable_industries"] = ["healthcare"]

                if triggered_reqs:
                    await _upsert_requirements_additive(conn, jurisdiction_id, triggered_reqs, research_source="gemini")
                    total_new += len(triggered_reqs)
                    added_requirements.extend(triggered_reqs)
                    print(
                        f"[Healthcare Research]   -> {len(triggered_reqs)} "
                        f"{profile.label}-specific requirements saved"
                    )
            except Exception as e:
                print(f"[Healthcare Research]   -> Error in triggered research for {profile.key}: {e}")

    return {
        "new": total_new,
        "location": location_name,
        "categories": missing,
        "failed": failed_categories,
        "requirements": added_requirements,
    }




async def _research_oncology_requirements_for_jurisdiction(
    conn,
    jurisdiction_id: UUID,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> Dict[str, Any]:
    """Research missing oncology-only categories for a jurisdiction."""
    from app.core.services.gemini_compliance import get_gemini_compliance_service
    from app.core.services.jurisdiction_context import get_known_sources, build_context_prompt, get_global_authority_sources

    j = await conn.fetchrow(
        "SELECT id, city, state, county FROM jurisdictions WHERE id = $1",
        jurisdiction_id,
    )
    if not j:
        return {"error": "Jurisdiction not found", "new": 0, "categories": [], "failed": []}

    city = j["city"]
    state = j["state"]
    county = j.get("county")
    location_name = f"{city}, {state}"

    has_local_ordinance = await _lookup_has_local_ordinance(conn, city, state)
    known_sources = await get_known_sources(conn, jurisdiction_id)
    source_context = build_context_prompt(known_sources)
    source_context += get_global_authority_sources(list(ONCOLOGY_CATEGORIES))
    corrections = await get_recent_corrections(jurisdiction_id)
    corrections_context = format_corrections_for_prompt(corrections)

    try:
        preemption_rows = await conn.fetch(
            "SELECT category, allows_local_override FROM state_preemption_rules WHERE state = $1",
            state.upper(),
        )
        preemption_rules = {
            row["category"]: row["allows_local_override"] for row in preemption_rows
        }
    except asyncpg.UndefinedTableError:
        preemption_rules = {}
    except Exception as e:
        logger.warning(f"preemption rules lookup failed: {e}")
        preemption_rules = {}

    existing = await conn.fetch(
        "SELECT DISTINCT category FROM jurisdiction_requirements WHERE jurisdiction_id = $1",
        jurisdiction_id,
    )
    existing_cats = {r["category"] for r in existing}
    missing = sorted(cat for cat in ONCOLOGY_CATEGORIES if cat not in existing_cats)

    if not missing:
        print(f"[Oncology Research] All oncology categories already present for {location_name}")
        return {
            "new": 0,
            "location": location_name,
            "categories": [],
            "failed": [],
            "requirements": [],
            "skipped": True,
        }

    print(
        f"[Oncology Research] Researching {len(missing)} oncology categories "
        f"for {location_name}: {', '.join(missing)}"
    )

    service = get_gemini_compliance_service()
    total_new = 0
    failed_categories: List[str] = []
    added_requirements: List[Dict[str, Any]] = []

    if progress_callback:
        progress_callback(1, 1, f"Researching {len(missing)} oncology categories for {location_name}...")

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
            if not req.get("applicable_industries"):
                req["applicable_industries"] = ["healthcare:oncology"]

        if reqs:
            await _upsert_requirements_additive(conn, jurisdiction_id, reqs, research_source="gemini")
            total_new = len(reqs)
            added_requirements.extend(reqs)
            # Log per-category breakdown
            by_cat: Dict[str, int] = {}
            for r in reqs:
                by_cat[r.get("category", "unknown")] = by_cat.get(r.get("category", "unknown"), 0) + 1
            for cat, count in sorted(by_cat.items()):
                print(f"[Oncology Research]   -> {count} requirements saved for {cat}")
        else:
            print(f"[Oncology Research]   -> No results returned")
            failed_categories = list(missing)
    except Exception as e:
        failed_categories = list(missing)
        print(f"[Oncology Research]   -> Error: {e}")

    print(
        f"[Oncology Research] Complete for {location_name}: {total_new} new, "
        f"{len(failed_categories)} failed"
    )

    if failed_categories and total_new == 0:
        raise RuntimeError(
            f"All oncology categories failed for {location_name}: "
            f"{', '.join(failed_categories)}"
        )

    return {
        "new": total_new,
        "location": location_name,
        "categories": missing,
        "failed": failed_categories,
        "requirements": added_requirements,
    }




async def _research_life_sciences_requirements_for_jurisdiction(
    conn,
    jurisdiction_id: UUID,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> Dict[str, Any]:
    """Research missing life-sciences-only categories for a jurisdiction."""
    from app.core.services.gemini_compliance import get_gemini_compliance_service
    from app.core.services.jurisdiction_context import get_known_sources, build_context_prompt, get_global_authority_sources

    j = await conn.fetchrow(
        "SELECT id, city, state, county FROM jurisdictions WHERE id = $1",
        jurisdiction_id,
    )
    if not j:
        return {"error": "Jurisdiction not found", "new": 0, "categories": [], "failed": []}

    city = j["city"]
    state = j["state"]
    county = j.get("county")
    location_name = f"{city}, {state}"

    has_local_ordinance = await _lookup_has_local_ordinance(conn, city, state)
    known_sources = await get_known_sources(conn, jurisdiction_id)
    source_context = build_context_prompt(known_sources)
    source_context += get_global_authority_sources(list(LIFE_SCIENCES_CATEGORIES))
    corrections = await get_recent_corrections(jurisdiction_id)
    corrections_context = format_corrections_for_prompt(corrections)

    try:
        preemption_rows = await conn.fetch(
            "SELECT category, allows_local_override FROM state_preemption_rules WHERE state = $1",
            state.upper(),
        )
        preemption_rules = {
            row["category"]: row["allows_local_override"] for row in preemption_rows
        }
    except asyncpg.UndefinedTableError:
        preemption_rules = {}
    except Exception as e:
        logger.warning(f"preemption rules lookup failed: {e}")
        preemption_rules = {}

    existing = await conn.fetch(
        "SELECT DISTINCT category FROM jurisdiction_requirements WHERE jurisdiction_id = $1",
        jurisdiction_id,
    )
    existing_cats = {r["category"] for r in existing}
    missing = sorted(cat for cat in LIFE_SCIENCES_CATEGORIES if cat not in existing_cats)

    if not missing:
        print(f"[Life Sciences Research] All life sciences categories already present for {location_name}")
        return {
            "new": 0,
            "location": location_name,
            "categories": [],
            "failed": [],
            "requirements": [],
            "skipped": True,
        }

    print(
        f"[Life Sciences Research] Researching {len(missing)} life sciences categories "
        f"for {location_name}: {', '.join(missing)}"
    )

    service = get_gemini_compliance_service()
    total_new = 0
    failed_categories: List[str] = []
    added_requirements: List[Dict[str, Any]] = []

    if progress_callback:
        progress_callback(1, 1, f"Researching {len(missing)} life sciences categories for {location_name}...")

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
            if not req.get("applicable_industries"):
                req["applicable_industries"] = ["biotech"]

        if reqs:
            await _upsert_requirements_additive(conn, jurisdiction_id, reqs, research_source="gemini")
            total_new = len(reqs)
            added_requirements.extend(reqs)
            by_cat: Dict[str, int] = {}
            for r in reqs:
                by_cat[r.get("category", "unknown")] = by_cat.get(r.get("category", "unknown"), 0) + 1
            for cat, count in sorted(by_cat.items()):
                print(f"[Life Sciences Research]   -> {count} requirements saved for {cat}")
        else:
            print(f"[Life Sciences Research]   -> No results returned")
            failed_categories = list(missing)
    except Exception as e:
        failed_categories = list(missing)
        print(f"[Life Sciences Research]   -> Error: {e}")

    print(
        f"[Life Sciences Research] Complete for {location_name}: {total_new} new, "
        f"{len(failed_categories)} failed"
    )

    if failed_categories and total_new == 0:
        raise RuntimeError(
            f"All life sciences categories failed for {location_name}: "
            f"{', '.join(failed_categories)}"
        )

    return {
        "new": total_new,
        "location": location_name,
        "categories": missing,
        "failed": failed_categories,
        "requirements": added_requirements,
    }




async def _research_medical_compliance_for_jurisdiction(
    conn,
    jurisdiction_id: UUID,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> Dict[str, Any]:
    """Research missing medical compliance categories for a jurisdiction.

    Covers 17 categories from the US Medical Compliance Policy Reference
    (health IT, cybersecurity, pharmacy, telehealth, devices, etc.).
    """
    from app.core.services.gemini_compliance import get_gemini_compliance_service
    from app.core.services.jurisdiction_context import get_known_sources, build_context_prompt, get_global_authority_sources

    j = await conn.fetchrow(
        "SELECT id, city, state, county FROM jurisdictions WHERE id = $1",
        jurisdiction_id,
    )
    if not j:
        return {"error": "Jurisdiction not found", "new": 0, "categories": [], "failed": []}

    city = j["city"]
    state = j["state"]
    county = j.get("county")
    location_name = f"{city}, {state}"

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
        preemption_rules = {
            row["category"]: row["allows_local_override"] for row in preemption_rows
        }
    except asyncpg.UndefinedTableError:
        preemption_rules = {}
    except Exception as e:
        logger.warning(f"preemption rules lookup failed: {e}")
        preemption_rules = {}

    existing = await conn.fetch(
        "SELECT DISTINCT category FROM jurisdiction_requirements WHERE jurisdiction_id = $1",
        jurisdiction_id,
    )
    existing_cats = {r["category"] for r in existing}
    missing = sorted(cat for cat in MEDICAL_COMPLIANCE_CATEGORIES if cat not in existing_cats)

    if not missing:
        print(f"[Medical Compliance] All medical compliance categories already present for {location_name}")
        return {
            "new": 0,
            "location": location_name,
            "categories": [],
            "failed": [],
            "requirements": [],
            "skipped": True,
        }

    print(
        f"[Medical Compliance] Researching {len(missing)} categories "
        f"for {location_name}: {', '.join(missing)}"
    )

    service = get_gemini_compliance_service()
    total_new = 0
    failed_categories: List[str] = []
    added_requirements: List[Dict[str, Any]] = []

    # Batch categories into groups of 4 to reduce Gemini calls (4-5 calls
    # instead of 17) while keeping each prompt small enough for accuracy.
    batch_size = 4
    batches = [missing[i:i + batch_size] for i in range(0, len(missing), batch_size)]

    for batch_idx, batch in enumerate(batches, start=1):
        batch_label = ", ".join(c.replace("_", " ") for c in batch)
        print(
            f"[Medical Compliance] [batch {batch_idx}/{len(batches)}] Researching "
            f"{batch_label} for {location_name}..."
        )
        if progress_callback:
            progress_callback(
                batch_idx,
                len(batches),
                f"Researching {batch_label} for {location_name}...",
            )

        try:
            reqs = await service.research_location_compliance(
                city=city,
                state=state,
                county=county,
                categories=batch,
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
                    tag = MEDICAL_COMPLIANCE_INDUSTRY_TAGS.get(cat, "healthcare")
                    req["applicable_industries"] = [tag]

            if reqs:
                await _upsert_requirements_additive(conn, jurisdiction_id, reqs, research_source="gemini")
                total_new += len(reqs)
                added_requirements.extend(reqs)
                by_cat: Dict[str, int] = {}
                for r in reqs:
                    by_cat[r.get("category", "unknown")] = by_cat.get(r.get("category", "unknown"), 0) + 1
                for cat, count in sorted(by_cat.items()):
                    print(f"[Medical Compliance]   -> {count} requirements saved for {cat}")
            else:
                print(f"[Medical Compliance]   -> No results for batch")
                failed_categories.extend(batch)
        except Exception as e:
            failed_categories.extend(batch)
            print(f"[Medical Compliance]   -> Error researching batch: {e}")

    print(
        f"[Medical Compliance] Complete for {location_name}: {total_new} new, "
        f"{len(failed_categories)} failed"
    )

    if failed_categories and total_new == 0:
        raise RuntimeError(
            f"All medical compliance categories failed for {location_name}: "
            f"{', '.join(failed_categories)}"
        )

    return {
        "new": total_new,
        "location": location_name,
        "categories": missing,
        "failed": failed_categories,
        "requirements": added_requirements,
    }




async def _fill_from_state_fallback(
    conn,
    service,
    jurisdiction_id: UUID,
    city: str,
    state: str,
    county: Optional[str],
    has_local_ordinance: Optional[bool],
    requirements: List[Dict],
    still_missing: List[str],
    threshold_days: int,
) -> List[Dict]:
    """For categories still missing after Tier 3, try state cache then Gemini state research."""
    state_name = _CODE_TO_STATE_NAME.get(state.upper(), state)

    # 1. Try state cache with lenient threshold
    state_reqs = await _try_load_state_requirements(
        conn, jurisdiction_id, threshold_days
    )
    if state_reqs:
        target_set = set(still_missing)
        fill = [
            r
            for r in state_reqs
            if (_normalize_category(r.get("category")) or r.get("category"))
            in target_set
        ]
        if fill:
            print(
                f"[Compliance] State-level fallback filled {len(fill)} missing categories for {city}: {still_missing}"
            )
            return requirements + fill

    # 2. State cache empty or stale — research at state level via Gemini
    print(
        f"[Compliance] Researching {still_missing} at state level ({state}) for {city}"
    )
    state_researched = await service.research_location_compliance(
        city="",
        state=state,
        county="",
        categories=still_missing,
        source_context="",
        corrections_context="",
        preemption_rules={},
        has_local_ordinance=None,
        on_retry=None,
    )
    if state_researched:
        # Annotate as state-level and note city follows state law for this category
        for r in state_researched:
            r["jurisdiction_level"] = "state"
            r["jurisdiction_name"] = state_name
            desc = r.get("description") or ""
            note = f" [Applies via {state_name} state law; {city} has no local ordinance for this category.]"
            if note not in desc:
                r["description"] = desc + note

        _normalize_requirement_categories(state_researched)
        # Cache to state jurisdiction additively (don't delete existing state rows)
        state_jid = await _get_state_jurisdiction_id(conn, jurisdiction_id)
        if state_jid:
            await _upsert_requirements_additive(conn, state_jid, state_researched, research_source="gemini")
            print(
                f"[Compliance] Cached {len(state_researched)} state-level reqs to jurisdiction {state_jid}"
            )

        return requirements + state_researched

    return requirements




async def _refresh_repository_missing_categories(
    conn,
    service,
    *,
    jurisdiction_id: UUID,
    city: str,
    state: str,
    county: Optional[str],
    has_local_ordinance: Optional[bool],
    current_requirements: List[Dict[str, Any]],
    missing_categories: List[str],
    on_retry: Optional[Callable[[int, str], Any]] = None,
    industry_context: str = "",
) -> List[Dict[str, Any]]:
    """Refresh missing categories, merge with current requirements, and upsert source-of-truth."""
    if not missing_categories:
        return list(current_requirements)

    known_sources = await get_known_sources(conn, jurisdiction_id)
    if not known_sources:
        discovered = await service.discover_jurisdiction_sources(
            city=city,
            state=state,
            county=county,
        )
        for src in discovered:
            domain = (src.get("domain") or "").lower()
            if domain:
                for cat in src.get("categories", []):
                    await record_source(
                        conn, jurisdiction_id, domain, src.get("name"), cat
                    )
        known_sources = await get_known_sources(conn, jurisdiction_id)

    source_context = build_context_prompt(known_sources)
    corrections = await get_recent_corrections(jurisdiction_id)
    corrections_context = format_corrections_for_prompt(corrections)

    try:
        preemption_rows = await conn.fetch(
            "SELECT category, allows_local_override FROM state_preemption_rules WHERE state = $1",
            state.upper(),
        )
        preemption_rules = {
            row["category"]: row["allows_local_override"] for row in preemption_rows
        }
    except asyncpg.UndefinedTableError:
        preemption_rules = {}

    refreshed_requirements = await service.research_location_compliance(
        city=city,
        state=state,
        county=county,
        categories=missing_categories,
        source_context=source_context,
        corrections_context=corrections_context,
        preemption_rules=preemption_rules,
        has_local_ordinance=has_local_ordinance,
        on_retry=on_retry,
        industry_context=industry_context,
    )
    refreshed_requirements = refreshed_requirements or []

    if not refreshed_requirements:
        return list(current_requirements)

    target_set = {_normalize_category(cat) or cat for cat in missing_categories}
    preserved = [
        req
        for req in current_requirements
        if (_normalize_category(req.get("category")) or req.get("category"))
        not in target_set
    ]
    merged_requirements = preserved + refreshed_requirements

    if has_local_ordinance is False:
        merged_requirements = _filter_city_level_requirements(
            merged_requirements, state
        )

    _normalize_requirement_categories(merged_requirements)
    merged_requirements = await _filter_with_preemption(
        conn, merged_requirements, state
    )
    await _upsert_jurisdiction_requirements_routed(conn, jurisdiction_id, merged_requirements, research_source="structured")

    for req in refreshed_requirements:
        source_url = req.get("source_url", "")
        if source_url:
            domain = extract_domain(source_url)
            if domain:
                await record_source(
                    conn,
                    jurisdiction_id,
                    domain,
                    req.get("source_name"),
                    req.get("category", ""),
                )

    return merged_requirements




async def research_jurisdiction_repo_only(
    jurisdiction_id: UUID,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Populate jurisdiction_requirements for the given jurisdiction via Gemini.

    Unlike run_compliance_check_stream(), this function writes ONLY to
    jurisdiction_requirements (the shared repo). It does NOT touch
    compliance_requirements, compliance_check_logs, or compliance_alerts for
    any tenant. Intended for the admin research queue.
    """
    from app.database import get_connection
    from app.core.services.gemini_compliance import get_gemini_compliance_service

    async with get_connection() as conn:
        j = await conn.fetchrow(
            "SELECT id, city, state, county FROM jurisdictions WHERE id = $1",
            jurisdiction_id,
        )
        if not j:
            yield {"type": "error", "message": "Jurisdiction not found"}
            return

        city = j["city"]
        state = j["state"]
        county = j.get("county")
        location_name = f"{city}, {state}"

        has_local_ordinance = await _lookup_has_local_ordinance(conn, city, state)

        yield {"type": "started", "location": location_name}

        service = get_gemini_compliance_service()

        existing_rows = await _load_jurisdiction_requirements(conn, jurisdiction_id)
        current_requirements = [_jurisdiction_row_to_dict(jr) for jr in existing_rows]
        missing_categories = _missing_required_categories(current_requirements)

        refresh_queue: asyncio.Queue = asyncio.Queue()

        def _on_retry(attempt: int, error: str) -> None:
            refresh_queue.put_nowait(
                {
                    "type": "retrying",
                    "message": f"Retrying research (attempt {attempt + 1})...",
                }
            )

        # --- Generic category research phase ---
        updated_requirements = list(current_requirements)
        if missing_categories:
            yield {
                "type": "repository_refresh",
                "jurisdiction_id": str(jurisdiction_id),
                "missing_categories": missing_categories,
                "message": (
                    f"Researching {len(missing_categories)} missing categories for "
                    f"{location_name} ({', '.join(missing_categories)})."
                ),
            }

            try:
                refresh_task = asyncio.create_task(
                    _refresh_repository_missing_categories(
                        conn,
                        service,
                        jurisdiction_id=jurisdiction_id,
                        city=city,
                        state=state,
                        county=county,
                        has_local_ordinance=has_local_ordinance,
                        current_requirements=current_requirements,
                        missing_categories=missing_categories,
                        on_retry=_on_retry,
                    )
                )
                async for evt in _heartbeat_while(refresh_task, queue=refresh_queue):
                    yield evt
                updated_requirements = refresh_task.result() or []
            except Exception as e:
                yield {"type": "error", "message": f"Research failed: {e}"}
                return

            missing_after = _missing_required_categories(updated_requirements)
            if missing_after:
                yield {
                    "type": "repository_only",
                    "jurisdiction_id": str(jurisdiction_id),
                    "missing_categories": missing_after,
                    "message": (
                        f"Repository still missing {', '.join(missing_after)} after research."
                    ),
                }

        # --- Industry-specific research phase ---
        # Call Gemini directly for industry variants and upsert additively
        # (don't use _refresh_repository_missing_categories which replaces categories).
        try:
            profiles = await conn.fetch("SELECT * FROM industry_compliance_profiles")
        except asyncpg.UndefinedTableError:
            profiles = []

        for profile in profiles:
            rate_types = profile.get("rate_types") or []
            relevant_rts = [rt for rt in rate_types if rt in _INDUSTRY_SPECIFIC_RATE_TYPES]
            if not relevant_rts:
                continue

            has_industry = await conn.fetchval(
                """SELECT EXISTS(
                    SELECT 1 FROM jurisdiction_requirements
                    WHERE jurisdiction_id = $1 AND rate_type = ANY($2::text[])
                )""",
                jurisdiction_id,
                relevant_rts,
            )
            if has_industry:
                continue

            focused = profile.get("focused_categories") or []
            if not focused:
                continue

            canonical = profile["name"].lower()
            ctx = _INDUSTRY_RESEARCH_CONTEXT.get(canonical, "")
            if not ctx:
                continue

            yield {
                "type": "repository_refresh",
                "message": f"Researching {canonical}-specific requirements for {location_name}...",
            }

            try:
                industry_task = asyncio.create_task(
                    service.research_location_compliance(
                        city=city,
                        state=state,
                        county=county,
                        categories=focused,
                        industry_context=ctx,
                        on_retry=_on_retry,
                    )
                )
                async for evt in _heartbeat_while(industry_task, queue=refresh_queue):
                    yield evt
                industry_reqs = industry_task.result() or []

                # Keep only industry-specific rows (rate_type matches)
                industry_only = [
                    r for r in industry_reqs
                    if _normalize_rate_type(r.get("rate_type")) in relevant_rts
                ]
                for req in industry_only:
                    _clamp_varchar_fields(req)
                    if not req.get("applicable_industries"):
                        req["applicable_industries"] = [canonical]

                if industry_only:
                    await _upsert_requirements_additive(
                        conn, jurisdiction_id, industry_only, research_source="gemini"
                    )
                    updated_requirements = updated_requirements + industry_only
                    yield {
                        "type": "repository_refresh",
                        "message": f"Added {len(industry_only)} {canonical}-specific requirements.",
                    }
                else:
                    yield {
                        "type": "repository_refresh",
                        "message": f"No {canonical}-specific requirements found for {location_name}.",
                    }
            except Exception as e:
                yield {
                    "type": "warning",
                    "message": f"Industry-specific research failed for {canonical}: {e}",
                }

        # --- Healthcare-specific research phase ---
        try:
            yield {
                "type": "repository_refresh",
                "message": f"Researching healthcare-specific compliance for {location_name}...",
            }
            healthcare_result = await _research_healthcare_requirements_for_jurisdiction(
                conn, jurisdiction_id
            )
            added_healthcare = healthcare_result.get("requirements") or []
            if added_healthcare:
                updated_requirements = updated_requirements + added_healthcare
            yield {
                "type": "repository_refresh",
                "message": (
                    f"Healthcare research completed for {location_name}: "
                    f"{healthcare_result.get('new', 0)} requirement(s) added."
                ),
            }
        except Exception as e:
            yield {
                "type": "warning",
                "message": f"Healthcare-specific research failed for {location_name}: {e}",
            }

        yield {
            "type": "complete",
            "location": location_name,
            "message": f"Research complete for {location_name}.",
            "new": len(updated_requirements),
            "updated": 0,
            "alerts": 0,
        }
