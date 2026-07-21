"""compliance_service.checks — J6 split of compliance_service.py."""
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




async def get_employee_impact_for_location(
    location_id: UUID, company_id: UUID
) -> Dict[str, Any]:
    """Calculate employee impact for a compliance location.

    Returns total affected employees plus per-rate_type violation details.

    Primary path: query by work_location_id FK (fast, exact).
    Fallback: heuristic matching for employees with work_location_id IS NULL
    (legacy rows that predate the FK linkage).
    """
    from app.database import get_connection

    async with get_connection() as conn:
        # Get location state/city
        loc = await conn.fetchrow(
            "SELECT state, city FROM business_locations WHERE id = $1 AND company_id = $2",
            location_id, company_id,
        )
        if not loc:
            return {"total_affected": 0, "employee_names": [], "violations_by_rate_type": {}}

        loc_state = loc["state"]
        loc_city = loc["city"]

        # Primary path: employees linked via FK
        fk_employees = await conn.fetch(
            """
            SELECT id, first_name, last_name, pay_classification, pay_rate,
                   work_city, work_state
            FROM employees
            WHERE org_id = $1 AND work_location_id = $2 AND termination_date IS NULL
            """,
            company_id, location_id,
        )

        # Fallback: heuristic for legacy employees with work_location_id IS NULL
        if loc_city:
            heuristic_employees = await conn.fetch(
                """
                SELECT id, first_name, last_name, pay_classification, pay_rate,
                       work_city, work_state
                FROM employees
                WHERE org_id = $1
                  AND termination_date IS NULL
                  AND work_location_id IS NULL
                  AND (
                      (LOWER(work_city) = LOWER($2) AND UPPER(work_state) = UPPER($3))
                      OR (work_state IS NULL AND work_city IS NULL
                          AND address IS NOT NULL AND address ILIKE '%' || $2 || '%')
                  )
                """,
                company_id, loc_city, loc_state,
            )
        else:
            heuristic_employees = await conn.fetch(
                """
                SELECT id, first_name, last_name, pay_classification, pay_rate,
                       work_city, work_state
                FROM employees
                WHERE org_id = $1
                  AND termination_date IS NULL
                  AND work_location_id IS NULL
                  AND UPPER(work_state) = UPPER($2)
                  AND (work_city IS NULL OR work_city = '')
                """,
                company_id, loc_state,
            )

        # Deduplicate (in case FK and heuristic overlap during migration)
        seen_ids = {emp["id"] for emp in fk_employees}
        employees = list(fk_employees)
        for emp in heuristic_employees:
            if emp["id"] not in seen_ids:
                employees.append(emp)
                seen_ids.add(emp["id"])

        total_affected = len(employees)

        # Get minimum_wage requirements for this location to check violations
        wage_reqs = await conn.fetch(
            """
            SELECT rate_type, numeric_value, jurisdiction_level
            FROM compliance_requirements
            WHERE location_id = $1 AND category = 'minimum_wage' AND numeric_value IS NOT NULL
            ORDER BY
                CASE jurisdiction_level
                    WHEN 'city' THEN 1
                    WHEN 'county' THEN 2
                    WHEN 'state' THEN 3
                    WHEN 'federal' THEN 4
                    ELSE 5
                END
            """,
            location_id,
        )

        # Build rate_type -> threshold map (first match wins = highest priority jurisdiction)
        thresholds: Dict[str, float] = {}
        for wr in wage_reqs:
            rt = wr["rate_type"] or "general"
            if rt not in thresholds:
                thresholds[rt] = float(wr["numeric_value"])

        # Fallback: check jurisdiction_requirements for missing rate types
        missing_types = {"general", "exempt_salary"} - set(thresholds.keys())
        if missing_types:
            # Try via business_locations.jurisdiction_id first (city-level)
            jr_rows = await conn.fetch(
                """
                SELECT jr.rate_type, jr.numeric_value
                FROM business_locations bl
                JOIN jurisdiction_requirements jr ON jr.jurisdiction_id = bl.jurisdiction_id
                WHERE bl.id = $1
                  AND jr.category = 'minimum_wage'
                  AND jr.numeric_value IS NOT NULL
                  AND jr.rate_type = ANY($2::text[])
                ORDER BY jr.rate_type
                """,
                location_id, list(missing_types),
            )
            for jr in jr_rows:
                rt = jr["rate_type"] or "general"
                if rt not in thresholds:
                    thresholds[rt] = float(jr["numeric_value"])

            # State-level fallback for still-missing types (exempt salary is often state-level)
            still_missing = {"general", "exempt_salary"} - set(thresholds.keys())
            if still_missing and loc_state:
                state_rows = await conn.fetch(
                    """
                    SELECT jr.rate_type, jr.numeric_value
                    FROM jurisdictions j
                    JOIN jurisdiction_requirements jr ON jr.jurisdiction_id = j.id
                    WHERE UPPER(j.state) = UPPER($1)
                      AND (j.city IS NULL OR j.city = '' OR LOWER(j.city) = LOWER(j.state))
                      AND jr.category = 'minimum_wage'
                      AND jr.numeric_value IS NOT NULL
                      AND jr.rate_type = ANY($2::text[])
                    ORDER BY jr.numeric_value DESC
                    """,
                    loc_state, list(still_missing),
                )
                for sr in state_rows:
                    rt = sr["rate_type"] or "general"
                    if rt not in thresholds:
                        thresholds[rt] = float(sr["numeric_value"])

            # Final fallback: check compliance_requirements from other same-company
            # same-state locations at jurisdiction_level='state'. This catches exempt_salary
            # thresholds that the AI populated for a different location in the same state.
            still_missing = {"general", "exempt_salary"} - set(thresholds.keys())
            if still_missing and loc_state:
                peer_rows = await conn.fetch(
                    """
                    SELECT cr.rate_type, MAX(cr.numeric_value) AS numeric_value
                    FROM compliance_requirements cr
                    JOIN business_locations bl ON bl.id = cr.location_id
                    WHERE bl.company_id = $1
                      AND UPPER(bl.state) = UPPER($2)
                      AND bl.id != $3
                      AND cr.category = 'minimum_wage'
                      AND cr.jurisdiction_level = 'state'
                      AND cr.numeric_value IS NOT NULL
                      AND cr.rate_type = ANY($4::text[])
                    GROUP BY cr.rate_type
                    """,
                    company_id, loc_state, location_id, list(still_missing),
                )
                for pr in peer_rows:
                    rt = pr["rate_type"] or "general"
                    if rt not in thresholds:
                        thresholds[rt] = float(pr["numeric_value"])

        # Check each employee for wage violations, bucketed by rate_type
        violations_by_rate_type: Dict[str, list] = {}
        for emp in employees:
            if emp["pay_classification"] is None or emp["pay_rate"] is None:
                continue

            rate = float(emp["pay_rate"])
            classification = emp["pay_classification"]

            if classification == "hourly":
                rate_type_key = "general"
            elif classification == "exempt":
                rate_type_key = "exempt_salary"
            else:
                continue

            threshold = thresholds.get(rate_type_key)
            if threshold is not None and rate < threshold:
                violation = {
                    "employee_id": str(emp["id"]),
                    "employee_name": f"{emp['first_name']} {emp['last_name']}",
                    "pay_classification": classification,
                    "pay_rate": rate,
                    "threshold": threshold,
                    "shortfall": round(threshold - rate, 2),
                }
                violations_by_rate_type.setdefault(rate_type_key, []).append(violation)

        employee_names = [
            f"{e['first_name']} {e['last_name']}" for e in employees[:5]
        ]

        return {
            "total_affected": total_affected,
            "employee_names": employee_names,
            "violations_by_rate_type": violations_by_rate_type,
        }




async def get_location_requirements(
    location_id: UUID, company_id: UUID, category: Optional[str] = None
) -> List[RequirementResponse]:
    from app.database import get_connection

    async with get_connection() as conn:
        loc = await conn.fetchrow(
            """SELECT bl.state, jr.has_local_ordinance
               FROM business_locations bl
               LEFT JOIN jurisdiction_reference jr
                 ON LOWER(bl.city) = jr.city AND UPPER(bl.state) = jr.state
               WHERE bl.id = $1 AND bl.company_id = $2""",
            location_id,
            company_id,
        )
        if not loc:
            return []
        state = loc["state"]
        has_local_ordinance = loc["has_local_ordinance"]

        # source_url_status/statute_citation live on the catalog row
        # (jurisdiction_requirements) and are joined through the SSOT FK at
        # read time — never mirrored, so they can't go stale. Null-FK
        # (Gemini-fresh) rows read as NULL = unchecked / uncited.
        # `authority_*` is the issuing jurisdiction resolved through the catalog
        # FK — the trustworthy answer to "who imposes this?". It is deliberately
        # additive: r.jurisdiction_level / r.jurisdiction_name are free text and
        # several filters below still key on them, so this joins alongside rather
        # than overwriting them.
        query = """
            SELECT r.*, cat.source_url_status, cat.statute_citation, cat.citation_verified_at,
                   cat.metadata -> 'jurisdictional_basis' AS jurisdictional_basis,
                   j.level::text AS authority_level,
                   j.display_name AS authority_display_name
            FROM compliance_requirements r
            JOIN business_locations l ON r.location_id = l.id
            LEFT JOIN jurisdiction_requirements cat
              ON cat.id = r.jurisdiction_requirement_id
            LEFT JOIN jurisdictions j ON j.id = cat.jurisdiction_id
            WHERE l.id = $1 AND l.company_id = $2
        """
        query += await codified_gate_sql("cat", conn=conn)
        params = [location_id, company_id]

        if category:
            query += " AND r.category = $3"
            params.append(category)

        query += " ORDER BY r.category, r.jurisdiction_level"

        rows = await conn.fetch(query, *params)
        row_dicts = [dict(row) for row in rows]
        if has_local_ordinance is False:
            row_dicts = _filter_city_level_requirements(row_dicts, state)
        _normalize_requirement_categories(row_dicts)
        row_dicts = await _filter_requirements_for_company(
            conn, company_id, row_dicts
        )
        filtered = await _filter_with_preemption(conn, row_dicts, state)

        # Enrich with employee impact data
        try:
            impact = await get_employee_impact_for_location(location_id, company_id)
            total_affected = impact["total_affected"]
            employee_names = impact["employee_names"]
            violations_by_rt = impact["violations_by_rate_type"]
        except Exception:
            total_affected = None
            employee_names = []
            violations_by_rt = {}

        def _violation_count_for_row(row: dict) -> Optional[int]:
            if row["category"] != "minimum_wage":
                return None
            rt = row.get("rate_type") or "general"
            return len(violations_by_rt.get(rt, []))

        return [
            RequirementResponse(
                id=str(row["id"]),
                category=row["category"],
                rate_type=row.get("rate_type"),
                applicable_industries=sorted(_requirement_applicable_industries(row))
                or None,
                jurisdiction_level=row["jurisdiction_level"],
                jurisdiction_name=row["jurisdiction_name"],
                title=row["title"],
                description=row["description"],
                current_value=row["current_value"],
                numeric_value=float(row["numeric_value"])
                if row.get("numeric_value") is not None
                else None,
                source_url=row["source_url"],
                source_url_status=row.get("source_url_status"),
                statute_citation=row.get("statute_citation"),
                citation_verified_at=row["citation_verified_at"].isoformat()
                if row.get("citation_verified_at")
                else None,
                jurisdictional_basis=_parse_jsonb_list(row.get("jurisdictional_basis")),
                source_name=row["source_name"],
                effective_date=row["effective_date"].isoformat()
                if row["effective_date"]
                else None,
                previous_value=row["previous_value"],
                last_changed_at=row["last_changed_at"].isoformat()
                if row["last_changed_at"]
                else None,
                affected_employee_count=total_affected,
                affected_employee_names=employee_names or None,
                min_wage_violation_count=_violation_count_for_row(row),
                is_pinned=row.get("is_pinned", False),
                jurisdiction_requirement_id=str(row["jurisdiction_requirement_id"])
                if row.get("jurisdiction_requirement_id")
                else None,
                authority_level=row.get("authority_level"),
                authority_name=_authority_label(
                    row.get("authority_level"), row.get("authority_display_name")
                ),
            )
            for row in filtered
        ]




async def get_compliance_summary(company_id: UUID) -> ComplianceSummary:
    from app.database import get_connection

    async with get_connection() as conn:
        # Resolved once, outside the per-location loop below.
        gate = await codified_gate_sql("cat", conn=conn)
        locations = await conn.fetch(
            """SELECT bl.*, jr.has_local_ordinance
               FROM business_locations bl
               LEFT JOIN jurisdiction_reference jr
                 ON LOWER(bl.city) = jr.city AND UPPER(bl.state) = jr.state
               WHERE bl.company_id = $1""",
            company_id,
        )

        total_requirements = 0
        unread_alerts = 0
        critical_alerts = 0
        recent_changes = []
        auto_check_count = 0

        for loc in locations:
            if loc.get("auto_check_enabled", True):
                auto_check_count += 1

            reqs = await conn.fetch(
                "SELECT r.* FROM compliance_requirements r "
                "LEFT JOIN jurisdiction_requirements cat "
                "  ON cat.id = r.jurisdiction_requirement_id "
                "WHERE r.location_id = $1" + gate,
                loc["id"],
            )
            req_dicts = [dict(r) for r in reqs]
            if loc.get("has_local_ordinance") is False:
                req_dicts = _filter_city_level_requirements(req_dicts, loc["state"])
            _normalize_requirement_categories(req_dicts)
            req_dicts = await _filter_requirements_for_company(
                conn, loc["company_id"], req_dicts
            )
            filtered_reqs = await _filter_with_preemption(conn, req_dicts, loc["state"])
            total_requirements += len(filtered_reqs)

            for req in filtered_reqs:
                if req["last_changed_at"]:
                    recent_changes.append(
                        {
                            "location": loc["name"] or f"{loc['city']}, {loc['state']}",
                            "category": req["category"],
                            "title": req["title"],
                            "old_value": req["previous_value"],
                            "new_value": req["current_value"],
                            "changed_at": req["last_changed_at"].isoformat(),
                        }
                    )

            alerts = await conn.fetch(
                "SELECT * FROM compliance_alerts WHERE location_id = $1",
                loc["id"],
            )
            for alert in alerts:
                if alert["status"] == "unread":
                    unread_alerts += 1
                    if alert["severity"] == "critical":
                        critical_alerts += 1

        recent_changes.sort(key=lambda x: x["changed_at"], reverse=True)
        recent_changes = recent_changes[:10]

        # Get nearest upcoming deadlines
        upcoming_rows = await conn.fetch(
            """
            SELECT ul.title, ul.expected_effective_date, ul.current_status, ul.category,
                   bl.name AS location_name, bl.city, bl.state
            FROM upcoming_legislation ul
            JOIN business_locations bl ON ul.location_id = bl.id
            WHERE ul.company_id = $1
              AND ul.current_status NOT IN ('effective', 'dismissed')
              AND ul.expected_effective_date IS NOT NULL
              AND ul.expected_effective_date > CURRENT_DATE
            ORDER BY ul.expected_effective_date ASC
            LIMIT 3
            """,
            company_id,
        )
        upcoming_deadlines = []
        now = datetime.utcnow().date()
        for row in upcoming_rows:
            days = (row["expected_effective_date"] - now).days
            upcoming_deadlines.append(
                {
                    "title": row["title"],
                    "effective_date": row["expected_effective_date"].isoformat(),
                    "days_until": days,
                    "status": row["current_status"],
                    "category": row["category"],
                    "location": row["location_name"]
                    or f"{row['city']}, {row['state']}",
                }
            )

        return ComplianceSummary(
            total_locations=len(locations),
            total_requirements=total_requirements,
            unread_alerts=unread_alerts,
            critical_alerts=critical_alerts,
            recent_changes=recent_changes,
            auto_check_locations=auto_check_count,
            upcoming_deadlines=upcoming_deadlines,
        )




async def get_compliance_dashboard(company_id: UUID, horizon_days: int = 90) -> dict:
    """
    Return a compliance dashboard with actionable tasks for each upcoming change.
    """
    from app.database import get_connection

    def _parse_metadata(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, dict) else {}
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}

    def _parse_iso_date(value: Any) -> Optional[date]:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return None
            try:
                return date.fromisoformat(raw[:10])
            except ValueError:
                return None
        return None

    def _derive_sla_state(
        action_status: Optional[str],
        due_date: Optional[date],
        has_owner: bool,
        today: date,
    ) -> str:
        if action_status == "actioned":
            return "completed"
        if due_date and due_date < today:
            return "overdue"
        if due_date and (due_date - today).days <= 7:
            return "due_soon"
        if not has_owner:
            return "unassigned"
        return "on_track"

    default_playbooks = {
        "minimum_wage": "Audit pay bands and update payroll before the effective date.",
        "sick_leave": "Update sick leave policy language and accrual settings.",
        "overtime": "Review exempt/non-exempt classifications and overtime rules.",
        "pay_frequency": "Confirm payroll schedule and notice requirements.",
        "final_pay": "Align offboarding checklist with final pay timing rules.",
        "posting_requirements": "Refresh workplace posting packets and manager notices.",
    }

    async with get_connection() as conn:
        # ── 1. Fetch all company locations ──────────────────────────────────
        locations = await conn.fetch(
            """
            SELECT id, name, city, state, company_id
            FROM business_locations
            WHERE company_id = $1 AND is_active = true
            """,
            company_id,
        )
        location_map: dict[UUID, dict] = {row["id"]: dict(row) for row in locations}

        if not location_map:
            return {
                "kpis": {
                    "total_locations": 0,
                    "unread_alerts": 0,
                    "critical_alerts": 0,
                    "employees_at_risk": 0,
                    "overdue_actions": 0,
                    "assigned_actions": 0,
                    "unassigned_actions": 0,
                },
                "coming_up": [],
            }

        # ── 2. Fetch upcoming legislation within horizon ─────────────────────
        cutoff = datetime.utcnow().date() + timedelta(days=horizon_days)
        legislation_rows = await conn.fetch(
            """
            SELECT ul.id, ul.location_id, ul.title, ul.description, ul.category,
                   ul.current_status, ul.expected_effective_date, ul.impact_summary,
                   ul.source_url, ul.confidence, ul.created_at,
                   ca.id AS alert_id,
                   ca.severity,
                   ca.status AS alert_status,
                   ca.action_required,
                   ca.deadline AS alert_deadline,
                   ca.metadata AS alert_metadata
            FROM upcoming_legislation ul
            LEFT JOIN LATERAL (
                SELECT ca.id, ca.severity, ca.status, ca.action_required, ca.deadline, ca.metadata, ca.created_at
                FROM compliance_alerts ca
                WHERE ca.company_id = ul.company_id
                  AND ca.location_id = ul.location_id
                  AND ca.alert_type = 'upcoming_legislation'
                  AND ca.status <> 'dismissed'
                  AND ca.metadata->>'legislation_id' = ul.id::text
                ORDER BY
                    CASE ca.status
                        WHEN 'unread' THEN 0
                        WHEN 'read' THEN 1
                        WHEN 'actioned' THEN 2
                        ELSE 3
                    END,
                    CASE ca.severity
                        WHEN 'critical' THEN 0
                        WHEN 'warning' THEN 1
                        ELSE 2
                    END,
                    ca.created_at DESC
                LIMIT 1
            ) ca ON true
            WHERE ul.company_id = $1
              AND ul.current_status NOT IN ('effective', 'dismissed')
              AND (
                    ul.expected_effective_date IS NULL
                    OR ul.expected_effective_date <= $2
              )
            ORDER BY ul.expected_effective_date ASC NULLS LAST, ul.created_at DESC
            """,
            company_id,
            cutoff,
        )

        # ── 3. Fetch alert KPIs ──────────────────────────────────────────────
        alert_kpi_row = await conn.fetchrow(
            """
            SELECT
                COUNT(*) FILTER (WHERE status = 'unread') AS unread_alerts,
                COUNT(*) FILTER (WHERE status = 'unread' AND severity = 'critical') AS critical_alerts
            FROM compliance_alerts
            WHERE company_id = $1
            """,
            company_id,
        )
        unread_alerts = int(alert_kpi_row["unread_alerts"] or 0)
        critical_alerts = int(alert_kpi_row["critical_alerts"] or 0)

        # ── 4. Build state → employees mapping (state_estimate logic) ────────
        # We gather all active employees for the company grouped by work_state.
        employee_rows = await conn.fetch(
            """
            SELECT id, first_name, last_name, work_state
            FROM employees
            WHERE org_id = $1
              AND termination_date IS NULL
              AND work_state IS NOT NULL
            ORDER BY last_name, first_name
            """,
            company_id,
        )

        # state → list of {id, name}
        state_employee_map: dict[str, list[dict]] = {}
        for emp in employee_rows:
            st = (emp["work_state"] or "").upper().strip()
            if not st:
                continue
            state_employee_map.setdefault(st, []).append(
                {
                    "id": str(emp["id"]),
                    "name": f"{emp['first_name']} {emp['last_name']}",
                }
            )

        # Unique states covered by company locations
        location_states = {loc["state"].upper() for loc in locations}
        # Total employees whose state is a company location state
        employees_at_risk: set[str] = set()
        for st in location_states:
            for emp in state_employee_map.get(st, []):
                employees_at_risk.add(emp["id"])

        # Resolve action owner display names for any owner IDs carried in alert metadata.
        owner_ids: set[UUID] = set()
        for row in legislation_rows:
            metadata = _parse_metadata(row.get("alert_metadata"))
            owner_id_raw = metadata.get("action_owner_id")
            if isinstance(owner_id_raw, str) and owner_id_raw.strip():
                try:
                    owner_ids.add(UUID(owner_id_raw))
                except ValueError:
                    continue

        owner_name_map: dict[str, str] = {}
        if owner_ids:
            owner_rows = await conn.fetch(
                """
                SELECT u.id,
                       COALESCE(c.name, a.name, u.email) AS display_name
                FROM users u
                LEFT JOIN clients c ON c.user_id = u.id AND c.company_id = $2
                LEFT JOIN admins a ON a.user_id = u.id
                WHERE u.id = ANY($1::uuid[])
                """,
                list(owner_ids),
                company_id,
            )
            owner_name_map = {
                str(row["id"]): row["display_name"] for row in owner_rows if row["id"]
            }

        # ── 5. Deduplicate + enrich legislation items ────────────────────────
        now = datetime.utcnow().date()
        seen_leg_ids: set = set()
        coming_up = []

        for row in legislation_rows:
            leg_id = str(row["id"])
            if leg_id in seen_leg_ids:
                continue
            seen_leg_ids.add(leg_id)

            loc = location_map.get(row["location_id"])
            if not loc:
                continue

            loc_state = loc["state"].upper()
            affected = state_employee_map.get(loc_state, [])

            effective_date = row["expected_effective_date"]
            days_until = (effective_date - now).days if effective_date else None

            alert_metadata = _parse_metadata(row.get("alert_metadata"))
            owner_id_raw = alert_metadata.get("action_owner_id")
            owner_id = None
            if isinstance(owner_id_raw, str) and owner_id_raw.strip():
                try:
                    owner_id = str(UUID(owner_id_raw))
                except ValueError:
                    owner_id = None

            owner_name_raw = alert_metadata.get("action_owner_name")
            owner_name = (
                owner_name_raw.strip()
                if isinstance(owner_name_raw, str) and owner_name_raw.strip()
                else (owner_name_map.get(owner_id) if owner_id else None)
            )

            action_due_date = (
                _parse_iso_date(alert_metadata.get("action_due_date"))
                or row.get("alert_deadline")
                or effective_date
            )
            next_action = (
                (alert_metadata.get("next_action") or "").strip()
                if isinstance(alert_metadata.get("next_action"), str)
                else None
            ) or row.get("action_required")
            if not next_action:
                next_action = "Review legal impact and confirm operational changes."

            recommended_playbook = (
                (alert_metadata.get("recommended_playbook") or "").strip()
                if isinstance(alert_metadata.get("recommended_playbook"), str)
                else ""
            )
            if not recommended_playbook:
                recommended_playbook = default_playbooks.get(
                    row["category"], "Review impact, assign owner, and track completion."
                )

            estimated_financial_impact_raw = alert_metadata.get(
                "estimated_financial_impact"
            )
            estimated_financial_impact = None
            if isinstance(estimated_financial_impact_raw, (str, int, float)):
                estimated_financial_impact = str(estimated_financial_impact_raw).strip()
                if not estimated_financial_impact:
                    estimated_financial_impact = None

            action_status = row.get("alert_status") or "untracked"
            sla_state = _derive_sla_state(
                action_status=action_status,
                due_date=action_due_date,
                has_owner=owner_id is not None,
                today=now,
            )
            is_overdue = sla_state == "overdue"

            # Infer severity bucket if no linked alert found
            raw_severity = row["severity"]
            if not raw_severity:
                if days_until is not None and days_until <= 30:
                    raw_severity = "critical"
                elif days_until is not None and days_until <= 60:
                    raw_severity = "warning"
                else:
                    raw_severity = "info"

            coming_up.append(
                {
                    "legislation_id": leg_id,
                    "title": row["title"],
                    "description": row["description"] or row["impact_summary"],
                    "category": row["category"],
                    "severity": raw_severity,
                    "status": row["current_status"],
                    "effective_date": effective_date.isoformat()
                    if effective_date
                    else None,
                    "days_until": days_until,
                    "location_id": str(row["location_id"]),
                    "location_name": loc["name"] or f"{loc['city']}, {loc['state']}",
                    "location_state": loc_state,
                    "alert_id": str(row["alert_id"]) if row.get("alert_id") else None,
                    "action_status": action_status,
                    "next_action": next_action,
                    "action_owner_id": owner_id,
                    "action_owner_name": owner_name,
                    "action_due_date": action_due_date.isoformat()
                    if action_due_date
                    else None,
                    "is_overdue": is_overdue,
                    "sla_state": sla_state,
                    "recommended_playbook": recommended_playbook,
                    "estimated_financial_impact": estimated_financial_impact,
                    "affected_employee_count": len(affected),
                    "affected_employee_sample": [e["name"] for e in affected[:5]],
                    "impact_basis": "state_estimate",
                    "source_url": row["source_url"],
                }
            )

        overdue_actions = 0
        assigned_actions = 0
        unassigned_actions = 0
        for item in coming_up:
            if item.get("action_status") == "actioned":
                continue
            if item.get("is_overdue"):
                overdue_actions += 1
            if item.get("action_owner_id"):
                assigned_actions += 1
            else:
                unassigned_actions += 1

        return {
            "kpis": {
                "total_locations": len(location_map),
                "unread_alerts": unread_alerts,
                "critical_alerts": critical_alerts,
                "employees_at_risk": len(employees_at_risk),
                "overdue_actions": overdue_actions,
                "assigned_actions": assigned_actions,
                "unassigned_actions": unassigned_actions,
            },
            "coming_up": coming_up,
        }




async def update_auto_check_settings(
    location_id: UUID, company_id: UUID, settings: AutoCheckSettings
) -> Optional[BusinessLocation]:
    """Update auto-check settings for a location."""
    from app.database import get_connection

    async with get_connection() as conn:
        updates = []
        params = []
        param_idx = 3

        if settings.auto_check_enabled is not None:
            updates.append(f"auto_check_enabled = ${param_idx}")
            params.append(settings.auto_check_enabled)
            param_idx += 1
        if settings.auto_check_interval_days is not None:
            updates.append(f"auto_check_interval_days = ${param_idx}")
            params.append(settings.auto_check_interval_days)
            param_idx += 1

        if not updates:
            return await get_location(location_id, company_id)

        # Recompute next_auto_check
        if settings.auto_check_enabled is not None and not settings.auto_check_enabled:
            updates.append("next_auto_check = NULL")
        else:
            if settings.auto_check_interval_days is not None:
                interval = settings.auto_check_interval_days
            else:
                # Use the persisted interval so re-enabling doesn't reset to 7
                updates.append(
                    f"next_auto_check = NOW() + INTERVAL '1 day' * auto_check_interval_days"
                )
                interval = None
            if interval is not None:
                updates.append(
                    f"next_auto_check = NOW() + INTERVAL '1 day' * ${param_idx}"
                )
                params.append(interval)
                param_idx += 1

        updates.append("updated_at = NOW()")
        params.insert(0, location_id)
        params.insert(1, company_id)

        await conn.execute(
            f"UPDATE business_locations SET {', '.join(updates)} WHERE id = $1 AND company_id = $2",
            *params,
        )
        return await get_location(location_id, company_id)




async def get_check_log(
    location_id: UUID, company_id: UUID, limit: int = 20
) -> List[CheckLogEntry]:
    """Get compliance check history for a location."""
    from app.database import get_connection

    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM compliance_check_log
            WHERE location_id = $1 AND company_id = $2
            ORDER BY started_at DESC
            LIMIT $3
            """,
            location_id,
            company_id,
            limit,
        )
        return [
            CheckLogEntry(
                id=str(row["id"]),
                location_id=str(row["location_id"]),
                company_id=str(row["company_id"]),
                check_type=row["check_type"],
                status=row["status"],
                started_at=row["started_at"].isoformat(),
                completed_at=row["completed_at"].isoformat()
                if row["completed_at"]
                else None,
                new_count=row["new_count"] or 0,
                updated_count=row["updated_count"] or 0,
                alert_count=row["alert_count"] or 0,
                error_message=row["error_message"],
            )
            for row in rows
        ]




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




async def set_requirement_pinned(
    requirement_id: UUID, company_id: UUID, is_pinned: bool
) -> dict | None:
    from app.database import get_connection

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            UPDATE compliance_requirements cr
            SET is_pinned = $1
            FROM business_locations bl
            WHERE cr.id = $2
              AND cr.location_id = bl.id
              AND bl.company_id = $3
            RETURNING cr.id, cr.title, cr.is_pinned
            """,
            is_pinned,
            requirement_id,
            company_id,
        )
    if not row:
        return None
    return {"id": str(row["id"]), "title": row["title"], "is_pinned": row["is_pinned"]}




async def get_pinned_requirements(company_id: UUID) -> list[dict]:
    from app.database import get_connection

    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT cr.id, cr.category, cr.jurisdiction_level, cr.jurisdiction_name,
                   cr.title, cr.description, cr.current_value, cr.effective_date,
                   cr.source_url, cr.is_pinned,
                   bl.name AS location_name, bl.city, bl.state
            FROM compliance_requirements cr
            JOIN business_locations bl ON cr.location_id = bl.id
            LEFT JOIN jurisdiction_requirements cat
              ON cat.id = cr.jurisdiction_requirement_id
            WHERE bl.company_id = $1
              AND cr.is_pinned = true
              AND bl.is_active = true
            """
            # A pin is a bookmark into the tab. If the row isn't listed there
            # any more, a pin pointing at it is a dead link.
            + await codified_gate_sql("cat", conn=conn)
            + " ORDER BY cr.category, cr.jurisdiction_level",
            company_id,
        )
    return [
        {
            "id": str(row["id"]),
            "category": row["category"],
            "jurisdiction_level": row["jurisdiction_level"],
            "jurisdiction_name": row["jurisdiction_name"],
            "title": row["title"],
            "description": row["description"],
            "current_value": row["current_value"],
            "effective_date": row["effective_date"].isoformat()
            if row["effective_date"]
            else None,
            "source_url": row["source_url"],
            "is_pinned": row["is_pinned"],
            "location_name": row["location_name"],
            "city": row["city"],
            "state": row["state"],
        }
        for row in rows
    ]




async def get_hierarchical_requirements(
    location_id: UUID, company_id: UUID, category: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Fully resolve compliance requirements for a location using hierarchical precedence.

    This is the main entry point for the hierarchical view. It:
    1. Loads the location and its facility_attributes
    2. Resolves the jurisdiction stack via recursive CTE
    3. Groups by category
    4. Evaluates trigger conditions against facility attributes
    5. Determines governing requirement per category via precedence rules
    6. Returns a fully-resolved response dict — frontend just renders it

    Returns None if location not found.
    """
    from app.database import get_connection

    async with get_connection() as conn:
        # 1. Load location
        loc = await conn.fetchrow(
            """SELECT bl.id, bl.city, bl.state, bl.name,
                      bl.jurisdiction_id, bl.facility_attributes
               FROM business_locations bl
               WHERE bl.id = $1 AND bl.company_id = $2""",
            location_id,
            company_id,
        )
        if not loc:
            return None
        if not loc["jurisdiction_id"]:
            return None

        facility_attrs = loc["facility_attributes"]
        if isinstance(facility_attrs, str):
            try:
                facility_attrs = json.loads(facility_attrs)
            except (json.JSONDecodeError, TypeError):
                facility_attrs = None

        # 2. Resolve jurisdiction stack
        stack_rows = await resolve_jurisdiction_stack(conn, loc["jurisdiction_id"])

        # This view reads the catalog directly rather than the location's
        # projection, so the SQL gate on compliance_requirements never reaches
        # it — filter the rows themselves, or the hierarchical view becomes the
        # hole every uncodified row walks back through.
        from app.core.services.platform_settings import get_tenant_codified_only

        if await get_tenant_codified_only(conn=conn):
            stack_rows = [r for r in stack_rows if is_codified_row(r)]

        # 3. Group by category
        by_category: Dict[str, List[Dict[str, Any]]] = {}
        for row in stack_rows:
            cat = row["category"]
            if category and cat != category:
                continue
            by_category.setdefault(cat, []).append(row)

        # 4-5. Determine governing requirement per category
        resolved = determine_governing_requirement(by_category, facility_attrs)

        # 6. Look up category labels
        cat_labels = {}
        if resolved:
            cat_ids = [r["category_id"] for r in resolved if r.get("category_id")]
            if cat_ids:
                label_rows = await conn.fetch(
                    "SELECT id, slug, name, domain::text, \"group\" FROM compliance_categories WHERE id = ANY($1)",
                    cat_ids,
                )
                for lr in label_rows:
                    cat_labels[str(lr["id"])] = {
                        "name": lr["name"],
                        "domain": lr["domain"],
                        "group": lr["group"],
                        "slug": lr["slug"],
                    }

        # 7. Get employee impact
        try:
            impact = await get_employee_impact_for_location(location_id, company_id)
            total_affected = impact["total_affected"]
        except Exception:
            total_affected = None

        # 8. Build response
        categories_out = []
        total_requirements = 0
        for item in resolved:
            gov = item["governing_requirement"]
            cat_id_str = str(item.get("category_id", ""))
            cat_info = cat_labels.get(cat_id_str, {})

            all_levels = []
            for row in item["all_levels"]:
                all_levels.append({
                    "id": str(row["id"]),
                    "jurisdiction_level": row.get("jur_level") or row.get("jurisdiction_level", ""),
                    "jurisdiction_name": row.get("jur_display_name") or row.get("jurisdiction_name", ""),
                    "title": row.get("title", ""),
                    "description": row.get("description"),
                    "current_value": row.get("current_value"),
                    "previous_value": row.get("previous_value"),
                    "previous_description": row.get("previous_description"),
                    "change_status": row.get("change_status"),
                    "last_changed_at": row["last_changed_at"].isoformat() if row.get("last_changed_at") else None,
                    "numeric_value": float(row["numeric_value"]) if row.get("numeric_value") is not None else None,
                    "source_url": row.get("source_url"),
                    "source_url_status": row.get("source_url_status"),
                    "statute_citation": row.get("statute_citation"),
                    # A row demoted to a floor relation has NO statute_citation
                    # (citing the floor would be false provenance). Without the
                    # basis here the hierarchical view just loses the citation
                    # with nothing explaining why.
                    "jurisdictional_basis": _basis_from_metadata(row.get("metadata")),
                    "status": row.get("req_status", "active"),
                    "canonical_key": row.get("canonical_key"),
                    "triggered_by": _compute_triggered_by(row.get("trigger_conditions"), facility_attrs),
                })
                total_requirements += 1

            precedence = None
            if item.get("precedence_type"):
                precedence = {
                    "precedence_type": item["precedence_type"],
                    "reasoning_text": item.get("reasoning_text"),
                    "legal_citation": item.get("legal_citation"),
                    "trigger_condition": item.get("rule_trigger_condition"),
                }

            categories_out.append({
                "category": item["category"],
                "category_label": cat_info.get("name", item["category"]),
                "domain": cat_info.get("domain"),
                "authority_type": "geographic",  # v2: from jurisdiction row
                "governing_level": item.get("governing_level", ""),
                "governing_requirement": {
                    "id": str(gov["id"]),
                    "jurisdiction_level": gov.get("jur_level") or gov.get("jurisdiction_level", ""),
                    "jurisdiction_name": gov.get("jur_display_name") or gov.get("jurisdiction_name", ""),
                    "title": gov.get("title", ""),
                    "description": gov.get("description"),
                    "current_value": gov.get("current_value"),
                    "previous_value": gov.get("previous_value"),
                    "previous_description": gov.get("previous_description"),
                    "change_status": gov.get("change_status"),
                    "last_changed_at": gov["last_changed_at"].isoformat() if gov.get("last_changed_at") else None,
                    "numeric_value": float(gov["numeric_value"]) if gov.get("numeric_value") is not None else None,
                    "source_url": gov.get("source_url"),
                    "source_url_status": gov.get("source_url_status"),
                    "statute_citation": gov.get("statute_citation"),
                    "jurisdictional_basis": _basis_from_metadata(gov.get("metadata")),
                    "status": gov.get("req_status", "active"),
                    "canonical_key": gov.get("canonical_key"),
                    "triggered_by": _compute_triggered_by(gov.get("trigger_conditions"), facility_attrs),
                },
                "precedence": precedence,
                "all_levels": all_levels,
                "affected_employee_count": total_affected,
            })

        return {
            "location_id": str(loc["id"]),
            "location_name": loc["name"] or "",
            "city": loc["city"],
            "state": loc["state"],
            "facility_attributes": facility_attrs,
            "categories": categories_out,
            "total_categories": len(categories_out),
            "total_requirements": total_requirements,
        }




async def search_company_requirements(
    conn,
    company_id: UUID,
    query: str,
    location_id: UUID | None = None,
    limit: int = 50,
) -> list[dict]:
    """Full-text search across a company's compliance requirements."""
    pattern = f"%{query}%"
    rows = await conn.fetch(
        """
        SELECT cr.*, bl.city, bl.state, bl.name AS location_name
        FROM compliance_requirements cr
        JOIN business_locations bl ON cr.location_id = bl.id
        LEFT JOIN jurisdiction_requirements cat
          ON cat.id = cr.jurisdiction_requirement_id
        WHERE bl.company_id = $1
          AND ($2::uuid IS NULL OR bl.id = $2)
          AND (
            cr.title ILIKE $3 OR cr.description ILIKE $3
            OR cr.current_value ILIKE $3 OR cr.jurisdiction_name ILIKE $3
            OR cr.category ILIKE $3
          )
        """
        # Search must not be a back door to rows the tab won't show.
        + await codified_gate_sql("cat", conn=conn)
        + """
        ORDER BY
          CASE WHEN cr.title ILIKE $3 THEN 0
               WHEN cr.current_value ILIKE $3 THEN 1
               WHEN cr.category ILIKE $3 THEN 2
               ELSE 3
          END,
          cr.category, cr.jurisdiction_level
        LIMIT $4
        """,
        company_id,
        location_id,
        pattern,
        limit,
    )
    return [dict(row) for row in rows]
