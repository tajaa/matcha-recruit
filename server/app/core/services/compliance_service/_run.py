"""compliance_service._run — check-runner twins (stream + background), split of _checks.py."""
from contextlib import asynccontextmanager
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
    MAX_VERIFICATIONS_PER_CHECK,
    _heartbeat_while,
    _parse_jsonb_list,
)
from app.core.services.compliance_service._normalize import (
    _missing_required_categories,
    _normalize_category,
    _normalize_requirement_categories,
)
from app.core.services.compliance_service._industry import (
    _get_industry_profile,
    _requirement_applicable_industries,
)
from app.core.services.compliance_service._verification import (
    format_corrections_for_prompt,
    get_recent_corrections,
    score_verification_confidence,
)
from app.core.services.compliance_service._jurisdictions import (
    _authority_label,
    _basis_from_metadata,
    _drop_no_rule_placeholders,
    _fill_missing_categories_from_parents,
    _get_or_create_jurisdiction,
    _is_jurisdiction_fresh,
    _jurisdiction_row_to_dict,
    _load_jurisdiction_requirements,
    _lookup_has_local_ordinance,
    _try_load_county_requirements,
    _try_load_state_requirements,
)
from app.core.services.compliance_service._hierarchy import (
    _compute_triggered_by,
    _filter_city_level_requirements,
    _filter_requirements_for_company,
    _filter_with_preemption,
    _project_chain_to_location,
    codified_gate_sql,
    determine_governing_requirement,
    is_codified_row,
    resolve_jurisdiction_stack,
)
from app.core.services.compliance_service._catalog_writes import (
    _compute_requirement_key,
    _upsert_jurisdiction_legislation,
    _upsert_jurisdiction_requirements_routed,
    _upsert_requirements_additive,
)
from app.core.services.compliance_service._alerts import (
    _complete_check_log,
    _create_alert,
    _create_check_log,
    _log_verification_outcome,
    _notify_company_admins_of_compliance_changes,
    _record_change_notification_item,
    _send_bulk_alert_email,
    escalate_upcoming_deadlines,
    process_upcoming_legislation,
)
from app.core.services.compliance_service._research import (
    _fill_from_state_fallback,
    _refresh_repository_missing_categories,
)
from app.core.services.compliance_service._locations import (
    _sync_requirements_to_location,
    get_location,
)




async def run_compliance_check_stream(
    location_id: UUID,
    company_id: UUID,
    allow_live_research: bool = True,
    categories: Optional[List[str]] = None,
    include_vertical_fill: bool = False,
    allow_repository_refresh: bool = True,
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Runs a compliance check for a specific location.
    Checks the jurisdiction repository first; only calls Gemini if stale/missing.

    ``include_vertical_fill``: after the check, research any industry-specific
    (vertical) compliance the shared catalog is still missing for this company —
    dental law for a dental office, hospitality law for a hotel.

    OFF by default, and that default is load-bearing. This generator has five
    callers: the tenant "Run check" route, the Matcha-X onboarding build's
    per-location loop, the roster-jurisdiction union, and two admin onboarding
    flows. An unconditional fill would fire three times in a single Matcha-X build
    (which already runs its own vertical phase, with the reproject-on-mint logic
    this level has no caller context for) and would silently add Gemini spend to
    the admin white-glove flows. Only the tenant-facing "Run check" opts in.
    Yields progress dicts as SSE-friendly events.

    ``categories`` optionally narrows the "required" set this run cares about
    (e.g. the Matcha-X self-serve onboarding finale passes
    ``MATCHA_X_LITE_CATEGORIES`` for a faster, cheaper basic-law sweep). When
    None — every existing caller — behaviour is identical to before.

    ``allow_repository_refresh``: ``allow_live_research=False`` was meant to mean
    "no Gemini, ever" for the tenant-facing route, but it only gated the
    per-company Tier-3 research block. The shared-jurisdiction gap-fill branch
    (search the catalog on miss, store forever) ran regardless — a "read-only"
    caller could still trigger a live research call. This flag closes that:
    False means the run is a pure projection from whatever the catalog already
    has, with zero Gemini calls, full stop. Defaults True so every existing
    caller (admin, onboarding) is unaffected; only the tenant route passes False.
    """
    from app.database import get_connection
    from app.core.services.gemini_compliance import get_gemini_compliance_service

    # ── Matcha-X lite scope ────────────────────────────────────────────────
    # When the caller passes a reduced ``categories`` set, shadow the
    # module-level ``_missing_required_categories`` with a local that treats
    # those as the required set. Every internal call below (which drives what
    # Tier-3 Gemini research fetches) then narrows automatically — no call-site
    # edits. With categories=None this shadow is identical to the module helper,
    # so the full (Pro) compliance check is byte-for-byte unaffected.
    _required_override = set(categories) if categories else None

    def _missing_required_categories(requirements: list[dict]) -> list[str]:
        present = {
            _normalize_category((req or {}).get("category"))
            for req in requirements
            if isinstance(req, dict) and (req or {}).get("category")
        }
        required = (
            _required_override
            if _required_override is not None
            else REQUIRED_LABOR_CATEGORIES
        )
        return sorted(cat for cat in required if cat not in present)

    location = await get_location(location_id, company_id)
    if not location:
        yield {"type": "error", "message": "Location not found"}
        return

    location_name = location.name or f"{location.city}, {location.state}"
    yield {"type": "started", "location": location_name}

    service = get_gemini_compliance_service()
    used_repository = False
    change_email_items: List[Dict[str, str]] = []
    requirements: List[Dict[str, Any]] = []
    cached_requirements_for_merge: List[Dict[str, Any]] = []
    research_categories: Optional[List[str]] = None
    industry_context: str = ""
    source_context: str = ""
    corrections_context: str = ""
    preemption_rules: Dict[str, bool] = {}
    new_count = 0
    updated_count = 0
    alert_count = 0

    async with get_connection() as conn:
        # Load industry profile for industry-aware research prompts
        industry_profile = await _get_industry_profile(conn, company_id)
        if industry_profile:
            industry_context = industry_profile.get("industry_context", "")

        log_id = await _create_check_log(conn, location_id, company_id, "manual")

        try:
            # Resolve jurisdiction
            jurisdiction_id = location.jurisdiction_id
            if not jurisdiction_id:
                jurisdiction_id = await _get_or_create_jurisdiction(
                    conn, location.city, location.state, location.county, location.zipcode
                )
                await conn.execute(
                    "UPDATE business_locations SET jurisdiction_id = $1 WHERE id = $2",
                    jurisdiction_id,
                    location_id,
                )

            # Look up whether this city has its own local ordinance
            has_local_ordinance = await _lookup_has_local_ordinance(
                conn, location.city, location.state
            )

            # ============================================================
            # FACILITY INFERENCE: Auto-populate facility_attributes for healthcare companies
            # ============================================================
            # A Gemini call, so it needs the same gate as the repository refresh
            # below — a projection-only run (tenant "Run check") must not spend
            # here either.
            canonical_industry = industry_profile.get("canonical_industry") if industry_profile else None
            if canonical_industry == "healthcare" and allow_repository_refresh:
                fa = location.facility_attributes
                if isinstance(fa, str):
                    try:
                        fa = json.loads(fa)
                    except (json.JSONDecodeError, TypeError):
                        fa = None
                has_entity_type = fa and fa.get("entity_type")
                if not has_entity_type:
                    try:
                        comp_row = await conn.fetchrow(
                            "SELECT name, industry, healthcare_specialties FROM companies WHERE id = $1",
                            company_id,
                        )
                        if comp_row:
                            inference = await service.infer_facility_profile(
                                company_name=comp_row["name"] or "",
                                industry=comp_row["industry"] or "",
                                healthcare_specialties=comp_row["healthcare_specialties"],
                                city=location.city,
                                state=location.state,
                            )
                            if inference and inference.get("confidence", 0) >= 0.5:
                                inferred_attrs = {
                                    "entity_type": inference["entity_type"],
                                    "payer_contracts": inference.get("likely_payer_contracts", []),
                                }
                                # Inline update to reuse existing connection
                                merged = (fa or {})
                                merged.update(inferred_attrs)
                                await conn.execute(
                                    "UPDATE business_locations SET facility_attributes = $1, updated_at = NOW() WHERE id = $2",
                                    json.dumps(merged), location_id,
                                )
                                # Reload location so Tier 4 sees the new attrs
                                row = await conn.fetchrow(
                                    "SELECT * FROM business_locations WHERE id = $1 AND company_id = $2",
                                    location_id, company_id,
                                )
                                if row:
                                    location = BusinessLocation(**dict(row))
                                yield {
                                    "type": "facility_inference",
                                    "message": f"Detected: {inference['entity_type']}",
                                }
                    except Exception as e:
                        print(f"[Facility Inference] Error during auto-inference: {e}")

            # ============================================================
            # TIER 1: Check for fresh structured data from authoritative sources
            # ============================================================
            from app.core.services.structured_data import StructuredDataService

            structured_service = StructuredDataService()

            tier1_data = await structured_service.get_tier1_data(
                conn,
                jurisdiction_id,
                city=location.city,
                state=location.state,
                county=location.county,
                categories=["minimum_wage"],
                freshness_hours=168,  # 7 days
                triggered_by="stream_check",
            )

            if tier1_data:
                yield {
                    "type": "tier1",
                    "message": f"Loading verified data for {location_name}...",
                }
                # Tier 1 only covers a subset of categories (minimum_wage).
                # Merge with repository data for other categories so the sync
                # doesn't delete requirements for categories Tier 1 didn't cover.
                tier1_categories = {
                    _normalize_category(r.get("category")) or r.get("category")
                    for r in tier1_data
                }
                j_reqs = await _load_jurisdiction_requirements(conn, jurisdiction_id)
                repo_reqs = [
                    _jurisdiction_row_to_dict(jr)
                    for jr in j_reqs
                    if (_normalize_category(jr.get("category")) or jr.get("category"))
                    not in tier1_categories
                ]
                requirements = tier1_data + repo_reqs
                missing_categories = _missing_required_categories(requirements)
                if missing_categories:
                    research_categories = missing_categories
                    cached_requirements_for_merge = list(requirements)
                    yield {
                        "type": "researching",
                        "message": f"Expanding coverage for {location_name}: missing {', '.join(missing_categories)}.",
                    }
                else:
                    used_repository = True  # Skip Gemini and fresh-data logic

            # ============================================================
            # TIER 2: Check if jurisdiction repository is fresh enough
            # ============================================================
            # Use the location's auto_check_interval_days as the freshness threshold
            elif await _is_jurisdiction_fresh(
                conn, jurisdiction_id, location.auto_check_interval_days or 7
            ):
                # Load from repository — skip Gemini
                yield {
                    "type": "repository",
                    "message": f"Loading compliance data for {location_name}...",
                }
                j_reqs = await _load_jurisdiction_requirements(conn, jurisdiction_id)
                requirements = [_jurisdiction_row_to_dict(jr) for jr in j_reqs]

                # Fill any gaps from state or county, even if the city has its own local ordinances
                filled = await _fill_missing_categories_from_parents(
                    conn,
                    jurisdiction_id,
                    requirements,
                    location.auto_check_interval_days or 7,
                )
                if filled:
                    yield {
                        "type": "repository",
                        "message": f"Filled missing categories from state/county data...",
                    }

                missing_categories = _missing_required_categories(requirements)
                if missing_categories:
                    research_categories = missing_categories
                    cached_requirements_for_merge = list(requirements)
                    yield {
                        "type": "researching",
                        "message": f"Coverage gap detected ({', '.join(missing_categories)}). Running live research...",
                    }
                else:
                    used_repository = True

            # If repo is fresh but the company has an industry profile (e.g.
            # healthcare), check whether industry-specific requirements
            # (rate_type='healthcare') are already in the company's compliance
            # data.  If not, force Gemini research for the industry's focused
            # categories so the company gets SB 525, nurse-overtime, etc.
            if used_repository and industry_context and industry_profile:
                focused = industry_profile.get("focused_categories") or []
                industry_rt = industry_profile.get("rate_types") or []
                if focused and industry_rt:
                    has_industry_data = await conn.fetchval(
                        """SELECT EXISTS(
                            SELECT 1 FROM compliance_requirements
                            WHERE location_id = $1 AND rate_type = ANY($2::text[])
                        )""",
                        location_id,
                        industry_rt,
                    )
                    if not has_industry_data:
                        # Need to research industry-specific variants
                        used_repository = False
                        research_categories = focused
                        cached_requirements_for_merge = list(requirements)
                        yield {
                            "type": "researching",
                            "message": f"Researching industry-specific requirements for {location_name}...",
                        }

            # ============================================================
            # TIER 2.5: County/State data reuse for no-local-ordinance cities
            # ============================================================
            if not used_repository and has_local_ordinance is False:
                county_reqs = await _try_load_county_requirements(
                    conn, jurisdiction_id, location.auto_check_interval_days or 7
                )
                if county_reqs:
                    yield {
                        "type": "repository",
                        "message": f"Using {location.county or 'county'} data for {location.city}...",
                    }
                    requirements = county_reqs

                    filled = await _fill_missing_categories_from_parents(
                        conn,
                        jurisdiction_id,
                        requirements,
                        location.auto_check_interval_days or 7,
                    )
                    if filled:
                        yield {
                            "type": "repository",
                            "message": f"Filled missing categories from state data...",
                        }

                    missing_categories = _missing_required_categories(requirements)
                    if missing_categories:
                        research_categories = missing_categories
                        cached_requirements_for_merge = list(requirements)
                        yield {
                            "type": "researching",
                            "message": f"Cache missing {', '.join(missing_categories)}. Running live research...",
                        }
                    else:
                        used_repository = True
                else:
                    state_reqs = await _try_load_state_requirements(
                        conn, jurisdiction_id, location.auto_check_interval_days or 7
                    )
                    if state_reqs:
                        yield {
                            "type": "repository",
                            "message": f"Using state data for {location.city}...",
                        }
                        requirements = state_reqs

                        filled = await _fill_missing_categories_from_parents(
                            conn,
                            jurisdiction_id,
                            requirements,
                            location.auto_check_interval_days or 7,
                        )

                        missing_categories = _missing_required_categories(requirements)
                        if missing_categories:
                            research_categories = missing_categories
                            cached_requirements_for_merge = list(requirements)
                            yield {
                                "type": "researching",
                                "message": f"State cache missing {', '.join(missing_categories)}. Running live research...",
                            }
                        else:
                            used_repository = True

            # ============================================================
            # TIER 3: Research with Gemini (stale or missing data)
            # ============================================================
            if not used_repository and allow_live_research:
                # Stale or missing — call Gemini
                # First, get known sources for this jurisdiction (or discover them)
                known_sources = await get_known_sources(conn, jurisdiction_id)

                if not known_sources:
                    # Bootstrap: discover sources for new jurisdiction
                    yield {
                        "type": "discovering_sources",
                        "message": f"Learning about {location_name}...",
                    }
                    discovered = await service.discover_jurisdiction_sources(
                        city=location.city,
                        state=location.state,
                        county=location.county,
                    )
                    for src in discovered:
                        domain = (src.get("domain") or "").lower()
                        if domain:
                            for cat in src.get("categories", []):
                                await record_source(
                                    conn, jurisdiction_id, domain, src.get("name"), cat
                                )
                    known_sources = await get_known_sources(conn, jurisdiction_id)

                # Build context for research prompt
                source_context = build_context_prompt(known_sources)

                # Phase 3.1: Get recent corrections to avoid repeating false positives
                corrections = await get_recent_corrections(jurisdiction_id)
                corrections_context = format_corrections_for_prompt(corrections)

                # Load preemption rules for this state to guide Gemini prompts
                try:
                    preemption_rows = await conn.fetch(
                        "SELECT category, allows_local_override FROM state_preemption_rules WHERE state = $1",
                        location.state.upper(),
                    )
                    preemption_rules = {
                        row["category"]: row["allows_local_override"]
                        for row in preemption_rows
                    }
                except asyncpg.UndefinedTableError:
                    preemption_rules = {}

                yield {
                    "type": "researching",
                    "message": f"Researching requirements for {location_name}...",
                }

                # Inform the client when a city has no local ordinance
                if has_local_ordinance is False:
                    parent = f"{location.county} County / " if location.county else ""
                    yield {
                        "type": "jurisdiction_info",
                        "message": f"{location.city} does not have its own local ordinances. Using {parent}{location.state} rules.",
                    }

                research_queue = asyncio.Queue()

                def _on_research_retry(attempt: int, error: str):
                    research_queue.put_nowait(
                        {
                            "type": "retrying",
                            "message": f"Retrying research (attempt {attempt + 1})...",
                        }
                    )

                research_task = asyncio.create_task(
                    service.research_location_compliance(
                        city=location.city,
                        state=location.state,
                        county=location.county,
                        categories=research_categories,
                        source_context=source_context,
                        corrections_context=corrections_context,
                        preemption_rules=preemption_rules,
                        has_local_ordinance=has_local_ordinance,
                        on_retry=_on_research_retry,
                        industry_context=industry_context,
                    )
                )
                async for evt in _heartbeat_while(research_task, queue=research_queue):
                    yield evt
                researched_requirements = research_task.result() or []
                if research_categories and cached_requirements_for_merge:
                    target_set = {
                        _normalize_category(cat) or cat for cat in research_categories
                    }
                    preserved = [
                        req
                        for req in cached_requirements_for_merge
                        if (
                            _normalize_category(req.get("category"))
                            or req.get("category")
                        )
                        not in target_set
                    ]
                    requirements = preserved + researched_requirements
                else:
                    requirements = researched_requirements

                # After Tier 3: if some research categories are still missing, fall back to
                # state-level data (e.g., final_pay / minor_work_permit governed by state law).
                still_missing = [
                    cat
                    for cat in (research_categories or [])
                    if cat
                    not in {
                        _normalize_category(r.get("category")) for r in requirements
                    }
                ]
                if still_missing:
                    requirements = await _fill_from_state_fallback(
                        conn,
                        service,
                        jurisdiction_id,
                        location.city,
                        location.state,
                        location.county,
                        has_local_ordinance,
                        requirements,
                        still_missing,
                        threshold_days=max(location.auto_check_interval_days or 7, 90),
                    )
            # Repository-only mode: allow_live_research=False forbids per-company
            # live research, but gap-driven refresh of the SHARED jurisdiction
            # source-of-truth is intentional — it fires only for categories never
            # researched in this jurisdiction and upserts into the shared library
            # (library-permanence model: search on miss, store forever).
            #
            # That refresh is itself a Gemini call, so it needs its own gate.
            # allow_repository_refresh=False (the tenant-facing route) means this
            # run must be a pure projection with ZERO Gemini spend — a customer's
            # button click must never research, even indirectly via "the shared
            # library happened to have a gap." Catalog freshness is our job, on
            # our schedule (legislation_watch / structured_data_fetch / admin
            # refresh); a tenant only ever reads what we've already stored.
            elif not used_repository and not allow_live_research and not allow_repository_refresh:
                # Real gaps only. The tier stages above build `requirements` from
                # a leaf-only or freshness-windowed slice, so a category the FULL
                # chain covers can look "missing" here (false gap → false queue).
                # Recompute against the exact set the tab projects
                # (`_project_chain_to_location`, whole chain, no freshness limit)
                # so we only ever queue jurisdictions we genuinely lack.
                chain_reqs = await _project_chain_to_location(
                    conn, company_id, location, jurisdiction_id
                )
                missing_categories = _missing_required_categories(chain_reqs)
                used_repository = True
                if missing_categories:
                    yield {
                        "type": "repository_only",
                        "jurisdiction_id": str(jurisdiction_id),
                        "missing_categories": missing_categories,
                        "message": (
                            "Some categories aren't in the library yet for "
                            f"{location_name} ({', '.join(missing_categories)}). "
                            "An admin can refresh jurisdiction data to add them."
                        ),
                    }

            elif not used_repository and not allow_live_research and allow_repository_refresh:
                missing_categories = _missing_required_categories(requirements)
                used_repository = True
                if missing_categories:
                    yield {
                        "type": "repository_refresh",
                        "jurisdiction_id": str(jurisdiction_id),
                        "missing_categories": missing_categories,
                        "message": (
                            "Repository coverage is incomplete. Triggering source-of-truth refresh for "
                            f"{location_name} ({', '.join(missing_categories)})."
                        ),
                    }
                    refresh_queue = asyncio.Queue()

                    def _on_refresh_retry(attempt: int, error: str):
                        refresh_queue.put_nowait(
                            {
                                "type": "retrying",
                                "message": f"Retrying repository refresh (attempt {attempt + 1})...",
                            }
                        )

                    refresh_task = asyncio.create_task(
                        _refresh_repository_missing_categories(
                            conn,
                            service,
                            jurisdiction_id=jurisdiction_id,
                            city=location.city,
                            state=location.state,
                            county=location.county,
                            has_local_ordinance=has_local_ordinance,
                            current_requirements=requirements,
                            missing_categories=missing_categories,
                            on_retry=_on_refresh_retry,
                        )
                    )
                    try:
                        async for evt in _heartbeat_while(
                            refresh_task, queue=refresh_queue
                        ):
                            yield evt
                        requirements = refresh_task.result() or requirements
                    except Exception as refresh_error:
                        print(
                            "[Compliance] Repository refresh failed for "
                            f"{location.city}, {location.state}: {refresh_error}"
                        )

                    missing_after_refresh = _missing_required_categories(requirements)
                    if missing_after_refresh:
                        yield {
                            "type": "repository_only",
                            "jurisdiction_id": str(jurisdiction_id),
                            "missing_categories": missing_after_refresh,
                            "message": (
                                "Jurisdiction repository is still missing "
                                f"{', '.join(missing_after_refresh)} after refresh. "
                                "Run Admin > Jurisdictions research refresh for this city."
                            ),
                        }
                    else:
                        yield {
                            "type": "repository_refreshed",
                            "jurisdiction_id": str(jurisdiction_id),
                            "message": (
                                f"Source-of-truth refreshed for {location_name}. Re-syncing from repository."
                            ),
                        }

                    if not requirements:
                        stale_repo_rows = await _load_jurisdiction_requirements(
                            conn, jurisdiction_id
                        )
                        if stale_repo_rows:
                            requirements = [
                                _jurisdiction_row_to_dict(jr) for jr in stale_repo_rows
                            ]
                            yield {
                                "type": "fallback",
                                "message": "Using existing repository data while coverage refresh completes.",
                            }

            # Stale-data fallback: if Gemini returned nothing, try cached data.
            # Set used_repository = True to skip fresh-data logic (upserts, alerts, verification).
            if not requirements and not used_repository:
                j_reqs = await _load_jurisdiction_requirements(conn, jurisdiction_id)
                if j_reqs:
                    requirements = [_jurisdiction_row_to_dict(jr) for jr in j_reqs]
                    used_repository = True
                    print(
                        f"[Compliance] Falling back to stale repository data ({len(requirements)} cached requirements)"
                    )
                    yield {
                        "type": "fallback",
                        "message": "Using cached data (live research unavailable)",
                    }

            # ============================================================
            # TIER 4: Triggered research based on facility attributes
            # ============================================================
            from app.core.compliance_registry import get_activated_profiles as _get_activated_profiles

            fa = location.facility_attributes
            if isinstance(fa, str):
                try:
                    fa = json.loads(fa)
                except (json.JSONDecodeError, TypeError):
                    fa = None
            activated_profiles = _get_activated_profiles(fa) if fa else []
            failed_profile_keys: set = set()
            if activated_profiles:
                # Lazy-init Gemini context if Tier 3 didn't run
                if not source_context:
                    known_sources = await get_known_sources(conn, jurisdiction_id)
                    source_context = build_context_prompt(known_sources)

                for profile in activated_profiles:
                    # Check if jurisdiction already has triggered requirements for this profile
                    existing_triggered = await conn.fetchval(
                        """SELECT COUNT(*) FROM jurisdiction_requirements
                           WHERE jurisdiction_id = $1
                             AND applicable_entity_types @> $2::jsonb""",
                        jurisdiction_id,
                        json.dumps([profile.key]),
                    )
                    if existing_triggered and existing_triggered > 0:
                        # Load existing triggered requirements and add to results
                        triggered_rows = await conn.fetch(
                            """SELECT * FROM jurisdiction_requirements
                               WHERE jurisdiction_id = $1
                                 AND applicable_entity_types @> $2::jsonb""",
                            jurisdiction_id,
                            json.dumps([profile.key]),
                        )
                        for tr in triggered_rows:
                            requirements.append(_jurisdiction_row_to_dict(dict(tr)))
                        continue

                    yield {
                        "type": "trigger_research",
                        "message": f"Researching {profile.label}-specific requirements...",
                    }
                    try:
                        trigger_cats = list(profile.applicable_categories)
                        triggered_reqs = await service.research_triggered_requirements(
                            city=location.city,
                            state=location.state,
                            county=location.county,
                            profile_key=profile.key,
                            profile_label=profile.label,
                            trigger_condition=profile.trigger_condition,
                            research_instruction=profile.research_instruction,
                            categories=trigger_cats,
                            source_context=source_context,
                        )
                        if triggered_reqs:
                            await _upsert_requirements_additive(
                                conn, jurisdiction_id, triggered_reqs, research_source="gemini"
                            )
                            requirements.extend(triggered_reqs)
                    except Exception as e:
                        failed_profile_keys.add(profile.key)
                        print(f"[Tier 4] Error researching {profile.key}: {e}")

            # ── Gap detection: flag missing specialty policies for admin ──
            if activated_profiles:
                req_categories = {
                    r.get("category") for r in requirements if r.get("category")
                }
                for profile in activated_profiles:
                    if profile.key in failed_profile_keys:
                        continue
                    for cat in profile.applicable_categories:
                        if cat not in req_categories:
                            # Deduplicate: skip if a missing_specialty alert already exists
                            existing_alert = await conn.fetchval(
                                """SELECT id FROM compliance_alerts
                                   WHERE location_id = $1 AND alert_type = 'missing_specialty'
                                     AND category = $2 AND metadata->>'trigger_profile' = $3
                                     AND status != 'dismissed'""",
                                location_id, cat, profile.key,
                            )
                            if existing_alert:
                                continue
                            try:
                                cat_label = cat.replace("_", " ").title()
                                await _create_alert(
                                    conn,
                                    location_id,
                                    company_id,
                                    None,
                                    f"Missing {cat_label} policies for {profile.label}",
                                    (
                                        f"Facility profile indicates {profile.label} requirements apply "
                                        f"but no {cat_label} policies found. Admin review recommended."
                                    ),
                                    "info",
                                    cat,
                                    alert_type="missing_specialty",
                                    metadata={
                                        "inferred_profile": profile.key,
                                        "missing_category": cat,
                                        "trigger_profile": profile.key,
                                        "source": "gemini_inference",
                                    },
                                )
                            except Exception as e:
                                print(f"[Gap Detection] Error creating alert for {cat}/{profile.key}: {e}")

            if not requirements:
                await conn.execute(
                    "UPDATE business_locations SET last_compliance_check = NOW() WHERE id = $1",
                    location_id,
                )
                await _complete_check_log(conn, log_id, 0, 0, 0)
                yield {
                    "type": "completed",
                    "location": location_name,
                    "new": 0,
                    "updated": 0,
                    "alerts": 0,
                }
                return

            # Post-filter: handle city-level results for cities with no local ordinance.
            # Instead of stripping all city-level entries (which can lose entire categories
            # like minimum_wage), promote orphaned city-level entries to state-level.
            if has_local_ordinance is False:
                requirements = _filter_city_level_requirements(
                    requirements, location.state
                )
                # Annotate remaining reqs with inheritance note
                parent = f"{location.county} County / " if location.county else ""
                note = (
                    f" [Note: {location.city} does not have its own local ordinance; "
                    f"this requirement applies via {parent}{location.state} state law.]"
                )
                for r in requirements:
                    desc = r.get("description") or ""
                    if note not in desc:
                        r["description"] = desc + note

            # Normalize and filter (with preemption awareness)
            _normalize_requirement_categories(requirements)
            requirements = await _filter_requirements_for_company(
                conn, company_id, requirements
            )
            requirements = await _filter_with_preemption(
                conn, requirements, location.state
            )

            yield {
                "type": "processing",
                "message": f"Processing {len(requirements)} requirements...",
            }

            # If Gemini was called, contribute results to jurisdiction repository.
            if not used_repository:
                await _upsert_jurisdiction_requirements_routed(
                    conn, jurisdiction_id, requirements, research_source="gemini"
                )

                # Learn from successful research: record any new sources seen
                for req in requirements:
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

            # Re-project from the CATALOG over the location's whole jurisdiction
            # chain, now that this run's research has been contributed to it.
            #
            # `requirements` up to here is one research pass's result set — the
            # deltas. What the tenant is liable for is the union of every active
            # obligation in its city/county/state/federal chain. Syncing the
            # research result instead of the chain is why an LA dental practice
            # saw no OSHA Bloodborne Pathogens standard, no infection control and
            # no hazardous-waste rules: all three were in the catalog, in its
            # chain, and simply never made it into the projection.
            #
            # Falls back to the research set if the chain projection comes back
            # empty — an empty sync would wipe the tenant's tab.
            chain_requirements = await _project_chain_to_location(
                conn, company_id, location, jurisdiction_id
            )
            if chain_requirements:
                yield {
                    "type": "processing",
                    "message": (
                        f"Applying {len(chain_requirements)} requirements across "
                        f"{location_name}'s full jurisdiction stack..."
                    ),
                }
                requirements = chain_requirements
            else:
                # Fallback path: syncing this run's raw research set. It has NOT
                # been through _project_chain_to_location, so the placeholder
                # filter has to be applied here too — otherwise "no rule applies"
                # rows reach the tab by the one route that skips the projection.
                requirements = _drop_no_rule_placeholders(requirements)

            # Sync requirements to location (change detection, alerts, history)
            # Only create alerts for fresh Gemini data — repository data is cached
            # and shouldn't re-alert on every check.
            sync_result = await _sync_requirements_to_location(
                conn,
                location_id,
                company_id,
                requirements,
                create_alerts=not used_repository,
            )
            new_count = sync_result["new"]
            updated_count = sync_result["updated"]
            alert_count = sync_result["alerts"]
            changes_to_verify = sync_result["changes_to_verify"]
            existing_by_key = sync_result["existing_by_key"]

            # Send ONE summary email for all new requirement alerts (not per-alert)
            if alert_count > 0:
                try:
                    await _send_bulk_alert_email(company_id, location_id, alert_count)
                except Exception as e:
                    print(f"[Compliance] Bulk alert email error: {e}")

            # Auto-embed new/updated jurisdiction requirements for RAG Q&A
            try:
                from app.core.services.compliance_embedding_pipeline import embed_updated_requirements
                asyncio.create_task(embed_updated_requirements(conn, jurisdiction_id))
            except Exception as e:
                print(f"[Compliance] Embedding update error: {e}")

            # Yield per-requirement status events
            new_keys = {_compute_requirement_key(r) for r in requirements}
            for req in requirements:
                req_title = req.get("title", "")
                rk = _compute_requirement_key(req)
                existing_entry = existing_by_key.get(rk)
                if existing_entry and existing_entry.get("id"):
                    # Could be updated or unchanged — emit generic result
                    yield {"type": "result", "status": "existing", "message": req_title}
                else:
                    yield {"type": "result", "status": "new", "message": req_title}

            # Collect (alert_id, change_info) for batch impact summary generation
            alert_changes_for_summary: list[tuple] = []

            # Verify material changes with Gemini (skip verification when using cached repository data)
            # Phase 2.3: Use batched verification for efficiency
            if changes_to_verify and not used_repository:
                verify_total = min(len(changes_to_verify), MAX_VERIFICATIONS_PER_CHECK)
                yield {
                    "type": "verifying",
                    "message": f"Verifying {verify_total} change(s) in batch...",
                }
                verification_count = 0

                # Prepare batch of changes for verification
                changes_batch = []
                for change_info in changes_to_verify[:MAX_VERIFICATIONS_PER_CHECK]:
                    req = change_info["req"]
                    changes_batch.append(
                        {
                            "category": req.get("category", ""),
                            "title": req.get("title", ""),
                            "old_value": change_info["old_value"],
                            "new_value": change_info["new_value"],
                        }
                    )

                # Get jurisdiction name from first change (all same jurisdiction)
                jurisdiction_name = changes_to_verify[0]["req"].get(
                    "jurisdiction_name", f"{location.city}, {location.state}"
                )

                try:
                    yield {
                        "type": "verifying_item",
                        "message": f"Batch verifying {verify_total} changes...",
                        "current": 1,
                        "total": 1,
                    }
                    verify_task = asyncio.create_task(
                        service.verify_compliance_changes_batch(
                            changes=changes_batch,
                            jurisdiction_name=jurisdiction_name,
                        )
                    )
                    async for evt in _heartbeat_while(verify_task):
                        yield evt
                    verification_results = verify_task.result()
                except Exception as e:
                    print(f"[Compliance] Batch verification failed: {e}")
                    verification_results = [
                        VerificationResult(
                            confirmed=False,
                            confidence=0.5,
                            sources=[],
                            explanation="Batch verification unavailable",
                        )
                    ] * len(changes_batch)

                # Process each verification result
                for idx, (change_info, verification) in enumerate(
                    zip(
                        changes_to_verify[:MAX_VERIFICATIONS_PER_CHECK],
                        verification_results,
                    )
                ):
                    req = change_info["req"]
                    existing = change_info["existing"]

                    confidence = score_verification_confidence(verification.sources)
                    confidence = max(confidence, verification.confidence)

                    change_msg = f"Value changed from {change_info['old_value']} to {change_info['new_value']}."
                    description = req.get("description")
                    if description:
                        change_msg += f" {description}"

                    # Compute requirement key for logging
                    req_key = _compute_requirement_key(req)

                    if confidence >= 0.6:
                        alert_count += 1
                        alert_id = await _create_alert(
                            conn,
                            location_id,
                            company_id,
                            existing["id"],
                            f"Compliance Change: {req.get('title')}",
                            change_msg,
                            "warning",
                            req.get("category"),
                            source_url=req.get("source_url"),
                            source_name=req.get("source_name"),
                            alert_type="change",
                            confidence_score=round(confidence, 2),
                            verification_sources=verification.sources,
                            metadata={
                                "verification_explanation": verification.explanation
                            },
                        )
                        alert_changes_for_summary.append((alert_id, change_info))
                        # Log verification outcome for calibration
                        await _log_verification_outcome(
                            conn,
                            jurisdiction_id,
                            alert_id,
                            req_key,
                            req.get("category"),
                            confidence,
                            predicted_is_change=True,
                            verification_sources=verification.sources,
                        )
                        _record_change_notification_item(
                            change_email_items, req, change_info
                        )
                        verification_count += 1
                    elif confidence >= 0.3:
                        alert_count += 1
                        alert_id = await _create_alert(
                            conn,
                            location_id,
                            company_id,
                            existing["id"],
                            f"Unverified: {req.get('title')}",
                            change_msg,
                            "info",
                            req.get("category"),
                            source_url=req.get("source_url"),
                            source_name=req.get("source_name"),
                            alert_type="change",
                            confidence_score=round(confidence, 2),
                            verification_sources=verification.sources,
                            metadata={
                                "verification_explanation": verification.explanation,
                                "unverified": True,
                            },
                        )
                        alert_changes_for_summary.append((alert_id, change_info))
                        # Log verification outcome for calibration
                        await _log_verification_outcome(
                            conn,
                            jurisdiction_id,
                            alert_id,
                            req_key,
                            req.get("category"),
                            confidence,
                            predicted_is_change=True,
                            verification_sources=verification.sources,
                        )
                        _record_change_notification_item(
                            change_email_items, req, change_info
                        )
                        verification_count += 1
                    else:
                        # Log low-confidence rejections too for calibration
                        await _log_verification_outcome(
                            conn,
                            jurisdiction_id,
                            None,
                            req_key,
                            req.get("category"),
                            confidence,
                            predicted_is_change=False,
                            verification_sources=verification.sources,
                        )
                        print(
                            f"[Compliance] Low confidence ({confidence:.2f}) for change: {req.get('title')}, skipping alert"
                        )

                # Handle overflow changes without verification
                for change_info in changes_to_verify[MAX_VERIFICATIONS_PER_CHECK:]:
                    req = change_info["req"]
                    existing = change_info["existing"]
                    change_msg = f"Value changed from {change_info['old_value']} to {change_info['new_value']}."
                    if req.get("description"):
                        change_msg += f" {req['description']}"
                    alert_count += 1
                    overflow_alert_id = await _create_alert(
                        conn,
                        location_id,
                        company_id,
                        existing["id"],
                        f"Compliance Change: {req.get('title')}",
                        change_msg,
                        "warning",
                        req.get("category"),
                        source_url=req.get("source_url"),
                        source_name=req.get("source_name"),
                        alert_type="change",
                    )
                    alert_changes_for_summary.append((overflow_alert_id, change_info))
                    _record_change_notification_item(
                        change_email_items, req, change_info
                    )

                if verification_count > 0:
                    yield {
                        "type": "verified",
                        "message": f"Verified {verification_count} change(s)",
                    }

            # Legislation scan — only via Gemini when not using repository
            if not used_repository:
                yield {
                    "type": "scanning",
                    "message": "Scanning for upcoming legislation...",
                }
                try:
                    current_reqs = [
                        dict(r) for r in existing_by_key.values() if r.get("id")
                    ]
                    leg_task = asyncio.create_task(
                        service.scan_upcoming_legislation(
                            city=location.city,
                            state=location.state,
                            county=location.county,
                            current_requirements=current_reqs,
                        )
                    )
                    async for evt in _heartbeat_while(leg_task):
                        yield evt
                    legislation_items = leg_task.result()
                    # Contribute to jurisdiction repository
                    await _upsert_jurisdiction_legislation(
                        conn, jurisdiction_id, legislation_items
                    )
                    leg_count = await process_upcoming_legislation(
                        conn, location_id, company_id, legislation_items
                    )
                    if leg_count > 0:
                        alert_count += leg_count
                        yield {
                            "type": "legislation",
                            "message": f"Found {leg_count} upcoming legislative change(s)",
                        }
                except Exception as e:
                    print(f"[Compliance] Legislation scan error: {e}")

            # Deadline escalation
            try:
                escalated = await escalate_upcoming_deadlines(conn, company_id)
                if escalated > 0:
                    yield {
                        "type": "escalation",
                        "message": f"Escalated {escalated} deadline(s)",
                    }
            except Exception as e:
                print(f"[Compliance] Deadline escalation error: {e}")

            # Generate plain-English impact summaries for change alerts
            if alert_changes_for_summary:
                yield {
                    "type": "progress",
                    "message": f"Generating impact summaries for {len(alert_changes_for_summary)} alert(s)...",
                }
                try:
                    from app.core.services.impact_summary import batch_generate_impact_summaries

                    loc_dict = {
                        "id": location_id,
                        "name": getattr(location, "name", None) or location_name,
                        "city": location.city,
                        "state": location.state,
                    }
                    company_row = await conn.fetchrow(
                        "SELECT name, industry FROM companies WHERE id = $1",
                        company_id,
                    )
                    company_ctx = {
                        "company_name": company_row["name"] if company_row else "",
                        "industry": company_row["industry"] if company_row else "",
                    }
                    await batch_generate_impact_summaries(
                        alert_changes_for_summary, loc_dict, company_ctx, conn
                    )
                except Exception as e:
                    print(f"[Compliance] Impact summary generation error: {e}")

            await conn.execute(
                "UPDATE business_locations SET last_compliance_check = NOW() WHERE id = $1",
                location_id,
            )
            await _complete_check_log(
                conn, log_id, new_count, updated_count, alert_count
            )
        except Exception as e:
            await _complete_check_log(
                conn, log_id, new_count, updated_count, alert_count, error=str(e)
            )
            raise

    # Vertical (industry-specific) coverage — research what the shared catalog is
    # still missing for this company's industry, then re-project.
    #
    # Placed HERE, after the `async with get_connection()` block above has exited,
    # on purpose: that block holds ONE pool connection for the entire check, and a
    # fill is many sequential Gemini calls. Splicing it inside would pin that
    # connection for minutes. `vertical_coverage.fill` takes a connection FACTORY
    # for exactly this reason.
    vertical_new = 0
    if include_vertical_fill:
        from app.database import get_connection as _get_conn
        from app.core.services import vertical_coverage

        try:
            async with _get_conn() as vconn:
                resolved = await vertical_coverage.resolve_vertical(vconn, company_id)
                if resolved:
                    v_parent, v_slug, v_label, v_tag, v_minted = resolved
                    v_categories, v_context = await vertical_coverage.ensure_specialty(
                        vconn, v_parent, v_slug, v_label
                    )
                    chains = await vertical_coverage.chains_for_leaves(
                        vconn, [jurisdiction_id]
                    )
                    nodes = sorted({j for c in chains.values() for j, _ in c})
                    await vertical_coverage.backfill_ledger(
                        vconn, nodes, v_tag, v_categories
                    )
                    plan, v_deferred = await vertical_coverage.plan_fill(
                        vconn, chains, v_tag, v_categories
                    )
                else:
                    plan, v_deferred, v_minted, v_label = [], 0, False, None

            if resolved and (plan or v_minted):
                if plan:
                    yield {
                        "type": "vertical_researching",
                        "vertical": v_label,
                        "cells": len(plan),
                        "deferred": v_deferred,
                        "message": f"Researching {v_label}-specific requirements…",
                    }
                v_deduped = 0
                async for vev in vertical_coverage.fill(
                    _get_conn, company_id, plan, v_tag, v_context
                ):
                    vertical_new += vev.get("new", 0)
                    v_deduped += vev.get("deduped", 0)

                # Re-project on ANY catalog change, and always when the specialty
                # tag was just minted: every projection before that write filtered
                # this vertical's rows out (the industry filter reads the company's
                # own tag set), so a fully-covered ledger still leaves the tab bare.
                if vertical_new or v_deduped or v_minted:
                    async with _get_conn() as vconn:
                        await vertical_coverage.reproject_location(
                            vconn, company_id, location_id
                        )
                    yield {
                        "type": "vertical_complete",
                        "vertical": v_label,
                        "requirements_added": vertical_new,
                        "message": f"{v_label}: {vertical_new} requirement(s) added.",
                    }
        except Exception as e:
            # Vertical scoping is additive — never fail a check over it.
            print(f"[Compliance] Vertical fill failed for {location_name}: {e}")
            yield {"type": "warning", "message": f"Vertical scoping incomplete: {e}"}

    from app.config import get_settings as _get_settings
    if _get_settings().compliance_emails_enabled:
        try:
            await _notify_company_admins_of_compliance_changes(
                company_id=company_id,
                location=location,
                change_items=change_email_items,
            )
        except Exception as e:
            print(f"[Compliance] Error notifying admins about compliance changes: {e}")

    yield {
        "type": "completed",
        "location": location_name,
        "new": new_count + vertical_new,
        "updated": updated_count,
        "alerts": alert_count,
    }






async def run_compliance_check_background(
    location_id: UUID,
    company_id: UUID,
    check_type: str = "scheduled",
    allow_live_research: bool = True,
    allow_repository_refresh: bool = True,
) -> Dict[str, Any]:
    """Non-streaming compliance check for Celery tasks.
    Checks the jurisdiction repository first; only calls Gemini if stale/missing.
    Returns summary dict.

    ``allow_repository_refresh=False`` makes this call a pure projection from
    whatever the shared catalog already has — zero Gemini calls, including the
    facility-inference call and the shared-jurisdiction gap-fill (see the
    matching flag on ``run_compliance_check_stream`` for why that gap-fill
    needed its own gate separate from ``allow_live_research``). The daily
    per-tenant sweep (``workers/tasks/compliance_checks.py``) passes False:
    catalog freshness is our job on our own schedule, not a side effect of a
    scheduled tenant sync.
    """
    from app.database import get_connection
    from app.core.services.gemini_compliance import get_gemini_compliance_service

    location = await get_location(location_id, company_id)
    if not location:
        return {"error": "Location not found", "new": 0, "updated": 0, "alerts": 0}

    service = get_gemini_compliance_service()
    used_repository = False
    change_email_items: List[Dict[str, str]] = []
    requirements: List[Dict[str, Any]] = []
    cached_requirements_for_merge: List[Dict[str, Any]] = []
    research_categories: Optional[List[str]] = None
    industry_context: str = ""
    source_context: str = ""
    corrections_context: str = ""
    preemption_rules: Dict[str, bool] = {}
    new_count = 0
    updated_count = 0
    alert_count = 0

    async with get_connection() as conn:
        # Load industry profile for industry-aware research prompts
        industry_profile = await _get_industry_profile(conn, company_id)
        if industry_profile:
            industry_context = industry_profile.get("industry_context", "")

        log_id = await _create_check_log(conn, location_id, company_id, check_type)

        try:
            # Resolve jurisdiction
            jurisdiction_id = location.jurisdiction_id
            if not jurisdiction_id:
                jurisdiction_id = await _get_or_create_jurisdiction(
                    conn, location.city, location.state, location.county, location.zipcode
                )
                await conn.execute(
                    "UPDATE business_locations SET jurisdiction_id = $1 WHERE id = $2",
                    jurisdiction_id,
                    location_id,
                )

            # Look up whether this city has its own local ordinance
            has_local_ordinance = await _lookup_has_local_ordinance(
                conn, location.city, location.state
            )

            # ── Facility Inference for healthcare companies ──
            # This is itself a Gemini call, gated the same as the repository
            # refresh below: a projection-only run must not spend here either.
            canonical_industry = industry_profile.get("canonical_industry") if industry_profile else None
            if canonical_industry == "healthcare" and allow_repository_refresh:
                fa = location.facility_attributes
                if isinstance(fa, str):
                    try:
                        fa = json.loads(fa)
                    except (json.JSONDecodeError, TypeError):
                        fa = None
                has_entity_type = fa and fa.get("entity_type")
                if not has_entity_type:
                    try:
                        comp_row = await conn.fetchrow(
                            "SELECT name, industry, healthcare_specialties FROM companies WHERE id = $1",
                            company_id,
                        )
                        if comp_row:
                            inference = await service.infer_facility_profile(
                                company_name=comp_row["name"] or "",
                                industry=comp_row["industry"] or "",
                                healthcare_specialties=comp_row["healthcare_specialties"],
                                city=location.city,
                                state=location.state,
                            )
                            if inference and inference.get("confidence", 0) >= 0.5:
                                inferred_attrs = {
                                    "entity_type": inference["entity_type"],
                                    "payer_contracts": inference.get("likely_payer_contracts", []),
                                }
                                merged = (fa or {})
                                merged.update(inferred_attrs)
                                await conn.execute(
                                    "UPDATE business_locations SET facility_attributes = $1, updated_at = NOW() WHERE id = $2",
                                    json.dumps(merged), location_id,
                                )
                                row = await conn.fetchrow(
                                    "SELECT * FROM business_locations WHERE id = $1 AND company_id = $2",
                                    location_id, company_id,
                                )
                                if row:
                                    location = BusinessLocation(**dict(row))
                                print(
                                    f"[Facility Inference] Auto-set {inference['entity_type']} "
                                    f"for {location.name or location.city}"
                                )
                    except Exception as e:
                        print(f"[Facility Inference] Error during auto-inference: {e}")

            # TIER 1: Check for fresh structured data from authoritative sources
            from app.core.services.structured_data import StructuredDataService

            structured_service = StructuredDataService()

            tier1_data = await structured_service.get_tier1_data(
                conn,
                jurisdiction_id,
                city=location.city,
                state=location.state,
                county=location.county,
                categories=["minimum_wage"],
                freshness_hours=168,
                triggered_by="background_check",
            )

            # Check repository freshness threshold
            threshold = location.auto_check_interval_days or 7

            if tier1_data:
                # Tier 1 only covers a subset of categories (minimum_wage).
                # Merge with repository data for other categories.
                tier1_categories = {
                    _normalize_category(r.get("category")) or r.get("category")
                    for r in tier1_data
                }
                j_reqs = await _load_jurisdiction_requirements(conn, jurisdiction_id)
                repo_reqs = [
                    _jurisdiction_row_to_dict(jr)
                    for jr in j_reqs
                    if (_normalize_category(jr.get("category")) or jr.get("category"))
                    not in tier1_categories
                ]
                requirements = tier1_data + repo_reqs
                missing_categories = _missing_required_categories(requirements)
                if missing_categories:
                    research_categories = missing_categories
                    cached_requirements_for_merge = list(requirements)
                    print(
                        f"[Compliance] Coverage gap for {location.city}, {location.state} "
                        f"({', '.join(missing_categories)}); running live research."
                    )
                else:
                    used_repository = True
            elif await _is_jurisdiction_fresh(conn, jurisdiction_id, threshold):
                j_reqs = await _load_jurisdiction_requirements(conn, jurisdiction_id)
                requirements = [_jurisdiction_row_to_dict(jr) for jr in j_reqs]

                await _fill_missing_categories_from_parents(
                    conn, jurisdiction_id, requirements, threshold
                )

                missing_categories = _missing_required_categories(requirements)
                if missing_categories:
                    research_categories = missing_categories
                    cached_requirements_for_merge = list(requirements)
                    print(
                        f"[Compliance] Fresh cache missing categories for {location.city}, {location.state}: "
                        f"{', '.join(missing_categories)}. Running live research."
                    )
                else:
                    used_repository = True

            # Industry-specific check (same logic as streaming path)
            if used_repository and industry_context and industry_profile:
                focused = industry_profile.get("focused_categories") or []
                industry_rt = industry_profile.get("rate_types") or []
                if focused and industry_rt:
                    has_industry_data = await conn.fetchval(
                        """SELECT EXISTS(
                            SELECT 1 FROM compliance_requirements
                            WHERE location_id = $1 AND rate_type = ANY($2::text[])
                        )""",
                        location_id,
                        industry_rt,
                    )
                    if not has_industry_data:
                        used_repository = False
                        research_categories = focused
                        cached_requirements_for_merge = list(requirements)
                        print(
                            f"[Compliance] Researching industry-specific requirements for "
                            f"{location.city}, {location.state}"
                        )

            # TIER 2.5: County/State data reuse for no-local-ordinance cities
            if not used_repository and has_local_ordinance is False:
                county_reqs = await _try_load_county_requirements(
                    conn, jurisdiction_id, threshold
                )
                if county_reqs:
                    requirements = county_reqs

                    await _fill_missing_categories_from_parents(
                        conn, jurisdiction_id, requirements, threshold
                    )

                    missing_categories = _missing_required_categories(requirements)
                    if missing_categories:
                        research_categories = missing_categories
                        cached_requirements_for_merge = list(requirements)
                        print(
                            f"[Compliance] Cache missing categories for {location.city}, {location.state}: "
                            f"{', '.join(missing_categories)}. Running live research."
                        )
                    else:
                        used_repository = True
                else:
                    state_reqs = await _try_load_state_requirements(
                        conn, jurisdiction_id, threshold
                    )
                    if state_reqs:
                        requirements = state_reqs

                        await _fill_missing_categories_from_parents(
                            conn, jurisdiction_id, requirements, threshold
                        )

                        missing_categories = _missing_required_categories(requirements)
                        if missing_categories:
                            research_categories = missing_categories
                            cached_requirements_for_merge = list(requirements)
                            print(
                                f"[Compliance] State cache missing categories for {location.city}, {location.state}: "
                                f"{', '.join(missing_categories)}. Running live research."
                            )
                        else:
                            used_repository = True

            # TIER 3: Research with Gemini (stale or missing data)
            if not used_repository and allow_live_research:
                # Get known sources for this jurisdiction (or discover them)
                known_sources = await get_known_sources(conn, jurisdiction_id)

                if not known_sources:
                    # Bootstrap: discover sources for new jurisdiction
                    discovered = await service.discover_jurisdiction_sources(
                        city=location.city,
                        state=location.state,
                        county=location.county,
                    )
                    for src in discovered:
                        domain = (src.get("domain") or "").lower()
                        if domain:
                            for cat in src.get("categories", []):
                                await record_source(
                                    conn, jurisdiction_id, domain, src.get("name"), cat
                                )
                    known_sources = await get_known_sources(conn, jurisdiction_id)

                # Build context for research prompt
                source_context = build_context_prompt(known_sources)

                # Phase 3.1: Get recent corrections to avoid repeating false positives
                corrections = await get_recent_corrections(jurisdiction_id)
                corrections_context = format_corrections_for_prompt(corrections)

                # Load preemption rules for this state
                try:
                    preemption_rows = await conn.fetch(
                        "SELECT category, allows_local_override FROM state_preemption_rules WHERE state = $1",
                        location.state.upper(),
                    )
                    preemption_rules = {
                        row["category"]: row["allows_local_override"]
                        for row in preemption_rows
                    }
                except asyncpg.UndefinedTableError:
                    preemption_rules = {}

                requirements = await service.research_location_compliance(
                    city=location.city,
                    state=location.state,
                    county=location.county,
                    categories=research_categories,
                    source_context=source_context,
                    corrections_context=corrections_context,
                    preemption_rules=preemption_rules,
                    has_local_ordinance=has_local_ordinance,
                    industry_context=industry_context,
                )
                if research_categories and cached_requirements_for_merge:
                    target_set = {
                        _normalize_category(cat) or cat for cat in research_categories
                    }
                    preserved = [
                        req
                        for req in cached_requirements_for_merge
                        if (
                            _normalize_category(req.get("category"))
                            or req.get("category")
                        )
                        not in target_set
                    ]
                    requirements = preserved + requirements
            # Repository-only, no catalog refresh: a pure projection from whatever
            # the shared catalog already has. This is the daily tenant sweep's
            # path (allow_repository_refresh=False) — catalog freshness is our
            # job on our own schedule, never a side effect of syncing a tenant.
            elif not used_repository and not allow_live_research and not allow_repository_refresh:
                # Real gaps only — recompute against the full chain the tab
                # projects, not the tier-stage slice (see the stream twin).
                chain_reqs = await _project_chain_to_location(
                    conn, company_id, location, jurisdiction_id
                )
                missing_categories = _missing_required_categories(chain_reqs)
                used_repository = True
                if missing_categories:
                    print(
                        f"[Compliance] Projection-only: missing categories for {location.city}, {location.state}: "
                        f"{', '.join(missing_categories)}. Not refreshing (allow_repository_refresh=False)."
                    )

            # Repository-only mode — see the twin branch in run_compliance_check_stream for semantics.
            elif not used_repository and not allow_live_research and allow_repository_refresh:
                missing_categories = _missing_required_categories(requirements)
                used_repository = True
                if missing_categories:
                    print(
                        f"[Compliance] Repository-only mode: missing categories for {location.city}, {location.state}: "
                        f"{', '.join(missing_categories)}. Triggering source-of-truth refresh "
                        f"(jurisdiction_id={jurisdiction_id})."
                    )
                    try:
                        requirements = await _refresh_repository_missing_categories(
                            conn,
                            service,
                            jurisdiction_id=jurisdiction_id,
                            city=location.city,
                            state=location.state,
                            county=location.county,
                            has_local_ordinance=has_local_ordinance,
                            current_requirements=requirements,
                            missing_categories=missing_categories,
                        )
                    except Exception as refresh_error:
                        print(
                            f"[Compliance] Source-of-truth refresh failed for {location.city}, {location.state}: "
                            f"{refresh_error}"
                        )

                    missing_after_refresh = _missing_required_categories(requirements)
                    if missing_after_refresh:
                        print(
                            f"[Compliance] Repository still missing categories for {location.city}, {location.state}: "
                            f"{', '.join(missing_after_refresh)} after refresh."
                        )
                    else:
                        print(
                            f"[Compliance] Repository refresh completed for {location.city}, {location.state}."
                        )

                    if not requirements:
                        stale_repo_rows = await _load_jurisdiction_requirements(
                            conn, jurisdiction_id
                        )
                        if stale_repo_rows:
                            requirements = [
                                _jurisdiction_row_to_dict(jr) for jr in stale_repo_rows
                            ]
                            print(
                                f"[Compliance] Using stale repository fallback for {location.city}, {location.state} "
                                f"({len(requirements)} requirement(s))."
                            )

            # Stale-data fallback: if Gemini returned nothing, try cached data.
            # Set used_repository = True to skip fresh-data logic (upserts, alerts, verification).
            if not requirements and not used_repository:
                j_reqs = await _load_jurisdiction_requirements(conn, jurisdiction_id)
                if j_reqs:
                    requirements = [_jurisdiction_row_to_dict(jr) for jr in j_reqs]
                    used_repository = True
                    print(
                        f"[Compliance] Background: falling back to stale repository data ({len(requirements)} cached requirements)"
                    )

            # ── TIER 4: Triggered research based on facility attributes ──
            from app.core.compliance_registry import get_activated_profiles as _get_activated_profiles_bg

            fa_bg = location.facility_attributes
            if isinstance(fa_bg, str):
                try:
                    fa_bg = json.loads(fa_bg)
                except (json.JSONDecodeError, TypeError):
                    fa_bg = None
            activated_profiles_bg = _get_activated_profiles_bg(fa_bg) if fa_bg else []
            failed_profile_keys_bg: set = set()
            if activated_profiles_bg:
                if not source_context:
                    known_sources = await get_known_sources(conn, jurisdiction_id)
                    source_context = build_context_prompt(known_sources)

                for profile in activated_profiles_bg:
                    existing_triggered = await conn.fetchval(
                        """SELECT COUNT(*) FROM jurisdiction_requirements
                           WHERE jurisdiction_id = $1
                             AND applicable_entity_types @> $2::jsonb""",
                        jurisdiction_id,
                        json.dumps([profile.key]),
                    )
                    if existing_triggered and existing_triggered > 0:
                        triggered_rows = await conn.fetch(
                            """SELECT * FROM jurisdiction_requirements
                               WHERE jurisdiction_id = $1
                                 AND applicable_entity_types @> $2::jsonb""",
                            jurisdiction_id,
                            json.dumps([profile.key]),
                        )
                        for tr in triggered_rows:
                            requirements.append(_jurisdiction_row_to_dict(dict(tr)))
                        continue

                    print(f"[Tier 4] Researching {profile.label}-specific requirements...")
                    try:
                        trigger_cats = list(profile.applicable_categories)
                        triggered_reqs = await service.research_triggered_requirements(
                            city=location.city,
                            state=location.state,
                            county=location.county,
                            profile_key=profile.key,
                            profile_label=profile.label,
                            trigger_condition=profile.trigger_condition,
                            research_instruction=profile.research_instruction,
                            categories=trigger_cats,
                            source_context=source_context,
                        )
                        if triggered_reqs:
                            await _upsert_requirements_additive(
                                conn, jurisdiction_id, triggered_reqs, research_source="gemini"
                            )
                            requirements.extend(triggered_reqs)
                    except Exception as e:
                        failed_profile_keys_bg.add(profile.key)
                        print(f"[Tier 4] Error researching {profile.key}: {e}")

            # ── Gap detection: flag missing specialty policies for admin ──
            if activated_profiles_bg:
                req_categories = {
                    r.get("category") for r in requirements if r.get("category")
                }
                for profile in activated_profiles_bg:
                    if profile.key in failed_profile_keys_bg:
                        continue
                    for cat in profile.applicable_categories:
                        if cat not in req_categories:
                            existing_alert = await conn.fetchval(
                                """SELECT id FROM compliance_alerts
                                   WHERE location_id = $1 AND alert_type = 'missing_specialty'
                                     AND category = $2 AND metadata->>'trigger_profile' = $3
                                     AND status != 'dismissed'""",
                                location_id, cat, profile.key,
                            )
                            if existing_alert:
                                continue
                            try:
                                cat_label = cat.replace("_", " ").title()
                                await _create_alert(
                                    conn,
                                    location_id,
                                    company_id,
                                    None,
                                    f"Missing {cat_label} policies for {profile.label}",
                                    (
                                        f"Facility profile indicates {profile.label} requirements apply "
                                        f"but no {cat_label} policies found. Admin review recommended."
                                    ),
                                    "info",
                                    cat,
                                    alert_type="missing_specialty",
                                    metadata={
                                        "inferred_profile": profile.key,
                                        "missing_category": cat,
                                        "trigger_profile": profile.key,
                                        "source": "gemini_inference",
                                    },
                                )
                            except Exception as e:
                                print(f"[Gap Detection] Error creating alert for {cat}/{profile.key}: {e}")

            if not requirements:
                await conn.execute(
                    "UPDATE business_locations SET last_compliance_check = NOW() WHERE id = $1",
                    location_id,
                )
                await _complete_check_log(conn, log_id, 0, 0, 0)
                return {"new": 0, "updated": 0, "alerts": 0}

            # Post-filter: handle city-level results for cities with no local ordinance
            if has_local_ordinance is False:
                requirements = _filter_city_level_requirements(
                    requirements, location.state
                )
                # Annotate remaining reqs with inheritance note
                parent = f"{location.county} County / " if location.county else ""
                note = (
                    f" [Note: {location.city} does not have its own local ordinance; "
                    f"this requirement applies via {parent}{location.state} state law.]"
                )
                for r in requirements:
                    desc = r.get("description") or ""
                    if note not in desc:
                        r["description"] = desc + note

            _normalize_requirement_categories(requirements)
            requirements = await _filter_requirements_for_company(
                conn, company_id, requirements
            )
            requirements = await _filter_with_preemption(
                conn, requirements, location.state
            )

            # Contribute to repository after Gemini call.
            if not used_repository:
                await _upsert_jurisdiction_requirements_routed(
                    conn, jurisdiction_id, requirements, research_source="gemini"
                )

                # Learn from successful research: record any new sources seen
                for req in requirements:
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

            # Sync to location
            sync_result = await _sync_requirements_to_location(
                conn,
                location_id,
                company_id,
                requirements,
                create_alerts=True,
            )
            new_count = sync_result["new"]
            updated_count = sync_result["updated"]
            alert_count = sync_result["alerts"]
            changes_to_verify = sync_result["changes_to_verify"]
            existing_by_key = sync_result["existing_by_key"]

            # Send ONE summary email for all new requirement alerts
            if alert_count > 0:
                try:
                    await _send_bulk_alert_email(company_id, location_id, alert_count)
                except Exception as e:
                    print(f"[Compliance] Bulk alert email error: {e}")

            # Collect (alert_id, change_info) for batch impact summary generation
            bg_alert_changes: list[tuple] = []

            # Verify changes (skip when using cached repository data)
            if not used_repository:
                for change_info in changes_to_verify[:MAX_VERIFICATIONS_PER_CHECK]:
                    req = change_info["req"]
                    existing = change_info["existing"]
                    try:
                        verification = await service.verify_compliance_change_adaptive(
                            category=req.get("category", ""),
                            title=req.get("title", ""),
                            jurisdiction_name=req.get("jurisdiction_name", ""),
                            old_value=change_info["old_value"],
                            new_value=change_info["new_value"],
                        )
                        confidence = max(
                            score_verification_confidence(verification.sources),
                            verification.confidence,
                        )
                    except Exception:
                        confidence = 0.5
                        verification = VerificationResult(
                            confirmed=False,
                            confidence=0.0,
                            sources=[],
                            explanation="Verification unavailable",
                        )

                    change_msg = f"Value changed from {change_info['old_value']} to {change_info['new_value']}."
                    if req.get("description"):
                        change_msg += f" {req['description']}"

                    if confidence >= 0.6:
                        alert_count += 1
                        bg_aid = await _create_alert(
                            conn,
                            location_id,
                            company_id,
                            existing["id"],
                            f"Compliance Change: {req.get('title')}",
                            change_msg,
                            "warning",
                            req.get("category"),
                            source_url=req.get("source_url"),
                            source_name=req.get("source_name"),
                            alert_type="change",
                            confidence_score=round(confidence, 2),
                            verification_sources=verification.sources,
                            metadata={
                                "verification_explanation": verification.explanation
                            },
                        )
                        bg_alert_changes.append((bg_aid, change_info))
                        _record_change_notification_item(
                            change_email_items, req, change_info
                        )
                    elif confidence >= 0.3:
                        alert_count += 1
                        bg_aid = await _create_alert(
                            conn,
                            location_id,
                            company_id,
                            existing["id"],
                            f"Unverified: {req.get('title')}",
                            change_msg,
                            "info",
                            req.get("category"),
                            source_url=req.get("source_url"),
                            source_name=req.get("source_name"),
                            alert_type="change",
                            confidence_score=round(confidence, 2),
                            verification_sources=verification.sources,
                            metadata={
                                "verification_explanation": verification.explanation,
                                "unverified": True,
                            },
                        )
                        bg_alert_changes.append((bg_aid, change_info))
                        _record_change_notification_item(
                            change_email_items, req, change_info
                        )

                for change_info in changes_to_verify[MAX_VERIFICATIONS_PER_CHECK:]:
                    req = change_info["req"]
                    existing = change_info["existing"]
                    change_msg = f"Value changed from {change_info['old_value']} to {change_info['new_value']}."
                    if req.get("description"):
                        change_msg += f" {req['description']}"
                    alert_count += 1
                    bg_oid = await _create_alert(
                        conn,
                        location_id,
                        company_id,
                        existing["id"],
                        f"Compliance Change: {req.get('title')}",
                        change_msg,
                        "warning",
                        req.get("category"),
                        source_url=req.get("source_url"),
                        source_name=req.get("source_name"),
                        alert_type="change",
                    )
                    bg_alert_changes.append((bg_oid, change_info))
                    _record_change_notification_item(
                        change_email_items, req, change_info
                    )

            # Legislation scan — only via Gemini when not using repository
            if not used_repository:
                try:
                    current_reqs = [
                        dict(r) for r in existing_by_key.values() if r.get("id")
                    ]
                    legislation_items = await service.scan_upcoming_legislation(
                        city=location.city,
                        state=location.state,
                        county=location.county,
                        current_requirements=current_reqs,
                    )
                    await _upsert_jurisdiction_legislation(
                        conn, jurisdiction_id, legislation_items
                    )
                    leg_count = await process_upcoming_legislation(
                        conn, location_id, company_id, legislation_items
                    )
                    alert_count += leg_count
                except Exception as e:
                    print(f"[Compliance] Background legislation scan error: {e}")

            # Deadline escalation
            try:
                await escalate_upcoming_deadlines(conn, company_id)
            except Exception as e:
                print(f"[Compliance] Background escalation error: {e}")

            # Generate impact summaries for change alerts (background)
            if bg_alert_changes:
                try:
                    from app.core.services.impact_summary import batch_generate_impact_summaries

                    loc_dict = {
                        "id": location_id,
                        "name": getattr(location, "name", None),
                        "city": location.city,
                        "state": location.state,
                    }
                    company_row = await conn.fetchrow(
                        "SELECT name, industry FROM companies WHERE id = $1",
                        company_id,
                    )
                    company_ctx = {
                        "company_name": company_row["name"] if company_row else "",
                        "industry": company_row["industry"] if company_row else "",
                    }
                    await batch_generate_impact_summaries(
                        bg_alert_changes, loc_dict, company_ctx, conn
                    )
                except Exception as e:
                    print(f"[Compliance] Background impact summary error: {e}")

            await conn.execute(
                "UPDATE business_locations SET last_compliance_check = NOW() WHERE id = $1",
                location_id,
            )
            await _complete_check_log(
                conn, log_id, new_count, updated_count, alert_count
            )

        except Exception as e:
            await _complete_check_log(
                conn, log_id, new_count, updated_count, alert_count, error=str(e)
            )
            raise

    from app.config import get_settings as _get_settings
    if _get_settings().compliance_emails_enabled:
        try:
            await _notify_company_admins_of_compliance_changes(
                company_id=company_id,
                location=location,
                change_items=change_email_items,
            )
        except Exception as e:
            print(f"[Compliance] Error notifying admins about compliance changes: {e}")

    return {"new": new_count, "updated": updated_count, "alerts": alert_count}




