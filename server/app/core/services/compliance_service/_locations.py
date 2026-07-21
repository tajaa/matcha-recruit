"""compliance_service.locations — J6 split of compliance_service.py."""
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
    parse_date,
)
from app.core.services.compliance_service._normalize import (
    _clamp_varchar_fields,
    _extract_numeric_value,
    _is_material_numeric_change,
    _is_material_text_change,
    _missing_required_categories,
    _normalize_category,
    _normalize_city_key,
    _normalize_requirement_categories,
    _validate_source_urls,
)
from app.core.services.compliance_service._jurisdictions import (
    _fill_missing_categories_from_parents,
    _get_or_create_jurisdiction,
    _jurisdiction_row_to_dict,
    _load_jurisdiction_legislation,
    _load_jurisdiction_requirements,
    _lookup_has_local_ordinance,
    _resolve_county_from_zip,
    _resolve_reference_city,
    _try_load_county_requirements,
    _try_load_state_requirements,
)
from app.core.services.compliance_service._hierarchy import (
    _filter_by_jurisdiction_priority,
    _filter_city_level_requirements,
    _filter_requirements_for_company,
    _filter_with_preemption,
    _project_chain_to_location,
    codified_gate_sql,
)
from app.core.services.compliance_service._catalog_writes import (
    _compute_requirement_key,
    _insert_catalog_requirement,
    _refresh_catalog_links,
    _snapshot_to_history,
    _update_requirement,
    _upsert_requirement,
)
from app.core.services.compliance_service._alerts import (
    _complete_check_log,
    _create_alert,
    _create_check_log,
    _log_policy_change,
)



async def _sync_requirements_to_location(
    conn,
    location_id: UUID,
    company_id: UUID,
    reqs: List[Dict],
    create_alerts: bool = True,
    service=None,
    validate_source_urls: bool = True,
) -> Dict[str, int]:
    """Sync a list of requirement dicts to a location's compliance_requirements.

    Runs the existing change-detection logic (upsert, history snapshot, alerts).
    Returns {"new": N, "updated": N, "alerts": N, "changes_to_verify": [...]}.

    ``validate_source_urls``: HEAD-checks every requirement's source_url for
    liveness (outbound HTTP to gov sites). That's catalog-quality maintenance —
    already done on the two research/write paths (``_upsert_requirements_additive``,
    ``_upsert_jurisdiction_requirements``) when a row is written. Repeating it
    per tenant, per sync, against the SAME urls every other tenant in the
    jurisdiction already validated is pure waste. Defaults True so existing
    callers are unaffected; the catalog-only projection path passes False.
    """
    # ── Data integrity pipeline ──
    for req in reqs:
        _clamp_varchar_fields(req)
        cat = _normalize_category(req.get("category"))
        if cat:
            req["category"] = cat
    if validate_source_urls:
        await _validate_source_urls(reqs)
    await _refresh_catalog_links(conn, reqs)

    new_count = 0
    updated_count = 0
    alert_count = 0

    existing_rows = await conn.fetch(
        "SELECT * FROM compliance_requirements WHERE location_id = $1",
        location_id,
    )
    existing_by_key = {}
    duplicates = []
    for row in existing_rows:
        row_dict = dict(row)
        key = _compute_requirement_key(row_dict)
        normalized_category = _normalize_category(
            row_dict.get("category")
        ) or row_dict.get("category")

        if key and (
            row_dict.get("requirement_key") != key
            or row_dict.get("category") != normalized_category
        ):
            await conn.execute(
                "UPDATE compliance_requirements SET requirement_key = $1, category = $2, updated_at = NOW() WHERE id = $3",
                key,
                normalized_category,
                row_dict["id"],
            )
            row_dict["requirement_key"] = key
            row_dict["category"] = normalized_category

        if not key:
            continue
        current = existing_by_key.get(key)
        if not current:
            existing_by_key[key] = row_dict
        else:
            current_updated = current.get("updated_at")
            row_updated = row_dict.get("updated_at")
            if current_updated and row_updated and row_updated > current_updated:
                duplicates.append(current)
                existing_by_key[key] = row_dict
            else:
                duplicates.append(row_dict)

    for dup in duplicates:
        await _snapshot_to_history(conn, dup, location_id)
        await conn.execute(
            "DELETE FROM compliance_requirements WHERE id = $1", dup["id"]
        )

    # Dismiss orphaned alerts
    await conn.execute(
        """
        UPDATE compliance_alerts SET status = 'dismissed', dismissed_at = NOW()
        WHERE location_id = $1 AND requirement_id IS NULL AND status IN ('unread', 'read')
        """,
        location_id,
    )

    new_requirement_keys = set()
    changes_to_verify = []

    for req in reqs:
        requirement_key = _compute_requirement_key(req)
        new_requirement_keys.add(requirement_key)
        existing = existing_by_key.get(requirement_key)

        # Fallback: match by category when the title-based key differs.
        # Only safe when exactly one unclaimed existing row shares the
        # category — multiple matches means we can't disambiguate and
        # must let the normal new-insert / stale-delete paths handle it.
        if not existing:
            norm_cat = _normalize_category(req.get("category"))
            if norm_cat:
                candidates = [
                    (ekey, erow)
                    for ekey, erow in existing_by_key.items()
                    if ekey.startswith(norm_cat + ":")
                    and ekey not in new_requirement_keys
                ]
                if len(candidates) == 1:
                    ekey, erow = candidates[0]
                    existing = erow
                    new_requirement_keys.add(ekey)  # prevent stale deletion

        if existing:
            old_value = existing.get("current_value")
            new_value = req.get("current_value")
            old_num = existing.get("numeric_value")
            new_num = req.get("numeric_value")
            if old_num is None:
                old_num = _extract_numeric_value(old_value)
            if new_num is None:
                new_num = _extract_numeric_value(new_value)

            # Minimum wages virtually never decrease — reject as likely
            # Gemini hallucination / stale data.  Use `continue` to skip
            # the entire update (including _update_requirement) so the
            # bad rate is never persisted.  The requirement_key is already
            # in new_requirement_keys so it won't be deleted.
            # Reject BEFORE dismissing alerts so existing alerts survive.
            if (
                _normalize_category(req.get("category")) == "minimum_wage"
                and old_num is not None
                and new_num is not None
                and (float(old_num) - float(new_num)) > 0.005
            ):
                print(
                    f"[Compliance] WARNING: Rejecting minimum wage decrease "
                    f"{old_num} → {new_num} for {req.get('jurisdiction_name')}"
                )
                continue

            # Dismiss stale alerts for this requirement (only reached
            # for non-rejected updates)
            await conn.execute(
                "UPDATE compliance_alerts SET status = 'dismissed', dismissed_at = NOW() WHERE requirement_id = $1 AND status IN ('unread', 'read')",
                existing["id"],
            )

            material_change = False
            if _is_material_numeric_change(old_num, new_num, req.get("category")):
                material_change = True
            elif old_num is None or new_num is None:
                # Only fall back to text comparison when we don't have
                # numeric values on both sides — avoids false alerts when
                # Gemini rephrases text but numeric value is unchanged.
                if _is_material_text_change(old_value, new_value, req.get("category")):
                    material_change = True
            # When numerics match for non-wage categories, trust the numeric comparison.
            # Text-only differences (after normalization) are usually just Gemini rephrasing
            # (e.g., "(unpaid)" annotations, word order changes). Don't flag as material.

            numeric_changed = (
                old_num is not None
                and new_num is not None
                and abs(float(old_num) - float(new_num)) > 0.001
            )
            text_changed = old_value != new_value
            metadata_changed = any(
                [
                    existing.get("title") != req.get("title"),
                    existing.get("description") != req.get("description"),
                    existing.get("source_url") != req.get("source_url"),
                    existing.get("source_name") != req.get("source_name"),
                    existing.get("effective_date")
                    != parse_date(req.get("effective_date")),
                    text_changed,
                    numeric_changed,
                ]
            )

            if metadata_changed:
                updated_count += 1
                await _snapshot_to_history(conn, existing, location_id)
                if material_change and create_alerts:
                    changes_to_verify.append(
                        {
                            "req": req,
                            "existing": existing,
                            "old_value": old_value,
                            "new_value": new_value,
                            "requirement_key": requirement_key,
                        }
                    )

            previous_value = existing.get("previous_value")
            last_changed_at = existing.get("last_changed_at")
            if material_change:
                previous_value = old_value
                last_changed_at = datetime.utcnow()
                # Log granular field changes to policy_change_log.
                #
                # requirement_id FKs jurisdiction_requirements (the CATALOG), but
                # `existing` is a compliance_requirements row — the per-location
                # projection. Passing existing["id"] here FK-violated every time,
                # killing the whole check. It stayed invisible because it only
                # fires when a value materially changes, and the sync used to die
                # earlier. An unlinked projection row has no catalog id to log
                # against, so it is skipped rather than faked.
                catalog_id = existing.get("jurisdiction_requirement_id")
                if catalog_id:
                    if old_value != new_value:
                        await _log_policy_change(
                            conn, catalog_id, "current_value",
                            old_value, new_value,
                        )
                    if old_num is not None and new_num is not None and abs(float(old_num) - float(new_num)) > 0.001:
                        await _log_policy_change(
                            conn, catalog_id, "numeric_value",
                            str(old_num), str(new_num),
                        )

            await _update_requirement(
                conn,
                existing["id"],
                requirement_key,
                req,
                previous_value,
                last_changed_at,
            )
            existing_by_key[requirement_key] = {**existing, "id": existing["id"]}
        else:
            # Guard: don't insert a min-wage decrease that bypassed the
            # matched-existing path due to key drift (title changed).
            # Only compare against entries with the SAME rate_type to avoid
            # rejecting legitimate lower variants (tipped, hotel, etc.).
            if _normalize_category(req.get("category")) == "minimum_wage":
                new_num_val = req.get("numeric_value") or _extract_numeric_value(
                    req.get("current_value")
                )
                new_rate_type = req.get("rate_type") or "general"
                if new_num_val is not None:
                    dominated = False
                    for ekey, erow in existing_by_key.items():
                        if not ekey.startswith("minimum_wage:"):
                            continue
                        # Only compare same rate_type (e.g., don't reject tipped $13.80 because general is $16.82)
                        existing_rate_type = erow.get("rate_type") or "general"
                        if existing_rate_type != new_rate_type:
                            continue
                        e_num = erow.get("numeric_value") or _extract_numeric_value(
                            erow.get("current_value")
                        )
                        if (
                            e_num is not None
                            and (float(e_num) - float(new_num_val)) > 0.005
                        ):
                            dominated = True
                            # Preserve old row from stale deletion
                            new_requirement_keys.add(ekey)
                            break
                    if dominated:
                        print(
                            f"[Compliance] WARNING: Rejecting min-wage insert "
                            f"{new_num_val} (lower than existing {e_num}) for "
                            f"{req.get('jurisdiction_name')} rate_type={new_rate_type}"
                        )
                        continue

            new_count += 1
            req_id = await _upsert_requirement(conn, location_id, requirement_key, req)

            if create_alerts:
                alert_count += 1
                await _create_alert(
                    conn,
                    location_id,
                    company_id,
                    req_id,
                    f"New Requirement: {req.get('title')}",
                    req.get("description") or "New compliance requirement identified.",
                    "info",
                    req.get("category"),
                    source_url=req.get("source_url"),
                    source_name=req.get("source_name"),
                    alert_type="new_requirement",
                    skip_email=True,  # bulk — caller sends one summary email
                )
            existing_by_key[requirement_key] = {"id": req_id}

    # Stale requirements cleanup
    stale_keys = set(existing_by_key.keys()) - new_requirement_keys
    for stale_key in stale_keys:
        stale = existing_by_key[stale_key]
        stale_id = stale.get("id")
        if stale_id:
            await _snapshot_to_history(conn, stale, location_id)
            await conn.execute(
                "DELETE FROM compliance_requirements WHERE id = $1", stale_id
            )

    return {
        "new": new_count,
        "updated": updated_count,
        "alerts": alert_count,
        "changes_to_verify": changes_to_verify,
        "existing_by_key": existing_by_key,
    }




async def project_location_from_catalog(
    conn,
    company_id: UUID,
    location_id: UUID,
    *,
    create_alerts: bool = False,
    check_type: str = "manual",
) -> Dict[str, int]:
    """Sync a location's tab from the shared catalog. NO Gemini, structurally.

    This is the tenant "Run check" button and the daily auto-sync's entry point,
    and the guarantee here is stronger than a flag: this function's only calls
    are ``_project_chain_to_location`` (read the catalog chain) and
    ``_sync_requirements_to_location(..., validate_source_urls=False)`` (write the
    projection). Neither imports ``get_gemini_compliance_service``, calls
    ``service.*``, or reaches ``_refresh_repository_missing_categories``. There is
    no code path from here to a Gemini call — not "Gemini is off because a flag
    says so," but "the call simply is not in this function's reachable graph."
    Research-capable checks (``run_compliance_check_stream`` /
    ``run_compliance_check_background``) are a deliberately separate,
    admin/onboarding-only surface.

    ``validate_source_urls=False`` on the sync call: liveness-checking every
    requirement's source_url is catalog-quality maintenance already done when a
    row is researched and written (the two write paths). Every tenant in a
    jurisdiction shares the same catalog rows, so re-validating the same URLs on
    every tenant's own sync is pure waste, not additional safety.

    Writes a ``compliance_check_log`` row and stamps
    ``business_locations.last_compliance_check`` like the full check does, so
    this is a full drop-in for both callers: the History tab shows the sync, and
    the daily dispatcher's ``ORDER BY last_compliance_check ASC NULLS FIRST``
    (``workers/tasks/compliance_checks.py``) still rotates correctly.

    Returns ``{"new": N, "updated": N, "alerts": N}``. Returns all-zero
    (no-op, no log written) if the location has no jurisdiction yet.

    Uses ONLY the passed ``conn`` — never ``get_location`` or any other pool
    accessor. The daily sweep runs in the pool-free Celery worker
    (``celery_app.py`` never calls ``init_pool``), where a pooled
    ``get_connection()`` raises "Database pool not initialized." Every helper
    below already takes ``conn``; this is the one spot that would otherwise reach
    for the pool. Same pattern as ``vertical_coverage.reproject_location``, which
    already runs pool-free in the vertical-coverage sweep worker.
    """
    row = await conn.fetchrow(
        "SELECT * FROM business_locations WHERE id = $1 AND company_id = $2",
        location_id, company_id,
    )
    if not row or not row["jurisdiction_id"]:
        return {"new": 0, "updated": 0, "alerts": 0}
    location = BusinessLocation(**dict(row))

    log_id = await _create_check_log(conn, location_id, company_id, check_type)

    requirements = await _project_chain_to_location(
        conn, company_id, location, location.jurisdiction_id
    )
    if not requirements:
        await conn.execute(
            "UPDATE business_locations SET last_compliance_check = NOW() WHERE id = $1",
            location_id,
        )
        await _complete_check_log(conn, log_id, 0, 0, 0)
        return {"new": 0, "updated": 0, "alerts": 0}

    sync_result = await _sync_requirements_to_location(
        conn,
        location_id,
        company_id,
        requirements,
        create_alerts=create_alerts,
        validate_source_urls=False,
    )
    await conn.execute(
        "UPDATE business_locations SET last_compliance_check = NOW() WHERE id = $1",
        location_id,
    )
    await _complete_check_log(
        conn, log_id, sync_result["new"], sync_result["updated"], sync_result["alerts"]
    )
    return {
        "new": sync_result["new"],
        "updated": sync_result["updated"],
        "alerts": sync_result["alerts"],
    }




async def ensure_location_for_employee(
    conn,
    company_id: UUID,
    work_city: Optional[str],
    work_state: str,
    background_tasks=None,
    work_zip: Optional[str] = None,
) -> Optional[UUID]:
    """Find or create a business_location for an employee's work address.

    Used during employee create/update to auto-derive compliance locations from
    employee addresses.  Works within the caller's connection (no
    ``get_connection()`` call).

    Returns the ``location_id`` (UUID) or None if ``work_state`` is falsy.
    """
    if not work_state:
        return None

    norm_state = work_state.upper().strip()
    norm_city = _normalize_city_key(work_city) if work_city else None

    # 1. Look for existing location matching (company_id, city, state)
    if norm_city:
        existing = await conn.fetchrow(
            """
            SELECT id, is_active FROM business_locations
            WHERE company_id = $1 AND LOWER(city) = $2 AND UPPER(state) = $3
            """,
            company_id, norm_city, norm_state,
        )
    else:
        # State-only: match locations with empty/null city
        existing = await conn.fetchrow(
            """
            SELECT id, is_active FROM business_locations
            WHERE company_id = $1 AND (city IS NULL OR city = '') AND UPPER(state) = $2
            """,
            company_id, norm_state,
        )

    # 2. Found + active → return id
    if existing and existing["is_active"]:
        return existing["id"]

    # 3. Found + inactive → reactivate
    if existing and not existing["is_active"]:
        await conn.execute(
            "UPDATE business_locations SET is_active = true, updated_at = NOW() WHERE id = $1",
            existing["id"],
        )
        return existing["id"]

    # 4. Not found → create
    # 4a. Check jurisdiction_reference for known jurisdiction
    is_known_jurisdiction = False
    ref_county = None
    if norm_city:
        resolved_city, ref_county = await _resolve_reference_city(conn, norm_city, norm_state)
        # Check if city was actually found in jurisdiction_reference
        # (vs. just returned as-is from _resolve_reference_city)
        try:
            ref_row = await conn.fetchrow(
                """
                SELECT city, county
                FROM jurisdiction_reference
                WHERE state = $2
                  AND (
                    city = $1
                    OR EXISTS (
                      SELECT 1
                      FROM unnest(COALESCE(aliases, ARRAY[]::text[])) AS alias
                      WHERE LOWER(alias) = $1
                    )
                  )
                LIMIT 1
                """,
                _normalize_city_key(norm_city),
                norm_state,
            )
            is_known_jurisdiction = ref_row is not None
            if ref_row and ref_row["county"]:
                ref_county = ref_row["county"]
        except asyncpg.UndefinedTableError:
            is_known_jurisdiction = False
    else:
        # State-only: always considered known (states are always covered)
        resolved_city = ""
        is_known_jurisdiction = True

    # Fall back to zip→county lookup if city-based resolution didn't find a county
    if not ref_county and work_zip:
        ref_county = await _resolve_county_from_zip(conn, work_zip, norm_state)

    # Determine source and coverage
    source = "employee_derived"
    coverage_status = "covered" if is_known_jurisdiction else "pending_review"
    display_city = work_city.strip() if work_city else ""

    # Insert the new location
    norm_zip = work_zip.strip() if work_zip else ""
    location_id = await conn.fetchval(
        """
        INSERT INTO business_locations
            (company_id, name, address, city, state, county, zipcode, source, coverage_status)
        VALUES ($1, $2, '', $3, $4, $5, $6, $7, $8)
        ON CONFLICT (company_id, LOWER(city), UPPER(state)) WHERE source = 'employee_derived' DO UPDATE
            SET is_active = true, updated_at = NOW(),
                zipcode = CASE WHEN business_locations.zipcode = '' OR business_locations.zipcode IS NULL
                               THEN EXCLUDED.zipcode ELSE business_locations.zipcode END
        RETURNING id
        """,
        company_id,
        f"{display_city}, {norm_state}" if display_city else norm_state,
        display_city,
        norm_state,
        ref_county,
        norm_zip,
        source,
        coverage_status,
    )

    # Resolve jurisdiction and link
    jurisdiction_id = await _get_or_create_jurisdiction(
        conn, display_city or norm_state, work_state, ref_county
    )
    await conn.execute(
        "UPDATE business_locations SET jurisdiction_id = $1 WHERE id = $2",
        jurisdiction_id, location_id,
    )

    if is_known_jurisdiction:
        # 4b. Known jurisdiction → clone repository data + trigger compliance check
        has_local_ordinance = await _lookup_has_local_ordinance(conn, display_city, norm_state)
        j_reqs = await _load_jurisdiction_requirements(conn, jurisdiction_id)
        req_dicts = None

        if j_reqs:
            req_dicts = [_jurisdiction_row_to_dict(jr) for jr in j_reqs]
            await _fill_missing_categories_from_parents(conn, jurisdiction_id, req_dicts, 7)
        elif not has_local_ordinance:
            # has_local_ordinance is False or None — try county/state fallback
            county_reqs = await _try_load_county_requirements(conn, jurisdiction_id, 7)
            if county_reqs:
                req_dicts = county_reqs
            else:
                state_reqs = await _try_load_state_requirements(conn, jurisdiction_id, 7)
                if state_reqs:
                    req_dicts = state_reqs
            if req_dicts:
                await _fill_missing_categories_from_parents(conn, jurisdiction_id, req_dicts, 7)

        if req_dicts:
            if not has_local_ordinance and display_city:
                req_dicts = _filter_city_level_requirements(req_dicts, norm_state)
            _normalize_requirement_categories(req_dicts)
            req_dicts = await _filter_requirements_for_company(conn, company_id, req_dicts)
            req_dicts = await _filter_with_preemption(conn, req_dicts, norm_state)
            for req in req_dicts:
                _clamp_varchar_fields(req)
            await _sync_requirements_to_location(
                conn, location_id, company_id, req_dicts, create_alerts=False,
            )

        if background_tasks is not None:
            async def _safe_compliance_bg(lid=location_id, cid=company_id):
                # Lazy import: _checks imports _locations, so importing it at
                # module top would be circular. Deferred to call time.
                from app.core.services.compliance_service._checks import (
                    run_compliance_check_background,
                )
                try:
                    await run_compliance_check_background(
                        lid, cid, check_type="auto_derive", allow_live_research=True,
                    )
                except Exception:
                    import traceback
                    print(f"[Compliance] Background compliance check failed for location {lid}: {traceback.format_exc()}")
            background_tasks.add_task(_safe_compliance_bg)
    else:
        # 4c. Unknown jurisdiction → queue for admin review, do NOT trigger check
        await conn.execute(
            """
            INSERT INTO jurisdiction_coverage_requests
                (city, state, county, requested_by_company_id, location_id, status)
            VALUES ($1, $2, $3, $4, $5, 'pending')
            ON CONFLICT (city, state) DO UPDATE
                SET location_id = COALESCE(jurisdiction_coverage_requests.location_id, EXCLUDED.location_id)
            """,
            display_city, norm_state, ref_county, company_id, location_id,
        )

    return location_id




async def create_location(company_id: UUID, data: LocationCreate) -> tuple:
    """Create a location, map it to a jurisdiction, and clone repository data if available.

    Returns (location, has_complete_repository_coverage) — callers should skip
    initial background research only when required labor categories are fully covered.
    """
    from app.database import get_connection

    async with get_connection() as conn:
        fa_json = json.dumps(data.facility_attributes) if data.facility_attributes else None
        location_id = await conn.fetchval(
            """
            INSERT INTO business_locations (company_id, name, address, city, state, county, zipcode, facility_attributes,
                                            ein, naics, max_employees, annual_avg_employees)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            RETURNING id
            """,
            company_id,
            data.name,
            data.address,
            data.city,
            data.state.upper(),
            data.county,
            data.zipcode or "",
            fa_json,
            data.ein,
            data.naics,
            data.max_employees,
            data.annual_avg_employees,
        )

        # Resolve county from zip if not provided
        resolved_county = data.county
        if not resolved_county and data.zipcode:
            resolved_county = await _resolve_county_from_zip(conn, data.zipcode, data.state)
            if resolved_county:
                await conn.execute(
                    "UPDATE business_locations SET county = $1 WHERE id = $2",
                    resolved_county, location_id,
                )

        # Map to jurisdiction
        jurisdiction_id = await _get_or_create_jurisdiction(
            conn, data.city, data.state, resolved_county
        )
        await conn.execute(
            "UPDATE business_locations SET jurisdiction_id = $1 WHERE id = $2",
            jurisdiction_id,
            location_id,
        )

        has_local_ordinance = await _lookup_has_local_ordinance(
            conn, data.city, data.state
        )

        # Check if jurisdiction already has requirements in the repository
        j_reqs = await _load_jurisdiction_requirements(conn, jurisdiction_id)
        has_repository_rows = len(j_reqs) > 0
        has_complete_repository_coverage = False

        # Try county data for cities without local ordinance (or unknown)
        req_dicts = None
        if has_repository_rows:
            req_dicts = [_jurisdiction_row_to_dict(jr) for jr in j_reqs]
            await _fill_missing_categories_from_parents(
                conn, jurisdiction_id, req_dicts, 7
            )
        else:
            if not has_local_ordinance:
                county_reqs = await _try_load_county_requirements(
                    conn, jurisdiction_id, 7
                )
                if county_reqs:
                    req_dicts = county_reqs
                else:
                    state_reqs = await _try_load_state_requirements(
                        conn, jurisdiction_id, 7
                    )
                    if state_reqs:
                        req_dicts = state_reqs

                # If we loaded from county or state, fill any remaining gaps from parents
                if req_dicts:
                    await _fill_missing_categories_from_parents(
                        conn, jurisdiction_id, req_dicts, 7
                    )

        if req_dicts:
            # Normalize and filter (with preemption awareness) before cloning.
            # This keeps create-location behavior consistent with the main
            # compliance check pipeline.
            if not has_local_ordinance:
                req_dicts = _filter_city_level_requirements(req_dicts, data.state)
            _normalize_requirement_categories(req_dicts)
            req_dicts = await _filter_requirements_for_company(conn, company_id, req_dicts)
            req_dicts = await _filter_with_preemption(conn, req_dicts, data.state)
            for req in req_dicts:
                _clamp_varchar_fields(req)
            missing_categories = _missing_required_categories(req_dicts)
            has_complete_repository_coverage = len(missing_categories) == 0
            if missing_categories:
                print(
                    "[Compliance] create_location: repository has partial coverage "
                    f"for {data.city}, {data.state}: {', '.join(missing_categories)}"
                )

        if req_dicts:
            # Clone requirements to location — no alerts for initial clone
            await _sync_requirements_to_location(
                conn,
                location_id,
                company_id,
                req_dicts,
                create_alerts=False,
            )

            # Clone legislation to location
            j_legs = await _load_jurisdiction_legislation(conn, jurisdiction_id)
            for item in j_legs:
                leg_key = item["legislation_key"]
                eff_date = item.get("expected_effective_date")
                confidence = (
                    float(item["confidence"])
                    if item.get("confidence") is not None
                    else None
                )
                await conn.execute(
                    """
                    INSERT INTO upcoming_legislation
                    (location_id, company_id, category, title, description, current_status,
                     expected_effective_date, impact_summary, source_url, source_name,
                     confidence, legislation_key)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                    ON CONFLICT (location_id, legislation_key) WHERE legislation_key IS NOT NULL DO NOTHING
                    """,
                    location_id,
                    company_id,
                    item.get("category"),
                    item["title"],
                    item.get("description"),
                    item.get("current_status", "proposed"),
                    eff_date,
                    item.get("impact_summary"),
                    item.get("source_url"),
                    item.get("source_name"),
                    confidence,
                    leg_key,
                )

            if has_complete_repository_coverage:
                # Mark as already checked only when core categories are fully covered.
                await conn.execute(
                    "UPDATE business_locations SET last_compliance_check = NOW() WHERE id = $1",
                    location_id,
                )

        row = await conn.fetchrow(
            "SELECT * FROM business_locations WHERE id = $1", location_id
        )
        location = BusinessLocation(**dict(row))
        return location, has_complete_repository_coverage




async def get_location_counts(location_id: UUID) -> dict:
    """Get requirements count and unread alerts count for a location."""
    from app.database import get_connection

    async with get_connection() as conn:
        loc = await conn.fetchrow(
            """SELECT bl.state, bl.company_id, jr.has_local_ordinance
               FROM business_locations bl
               LEFT JOIN jurisdiction_reference jr
                 ON LOWER(bl.city) = jr.city AND UPPER(bl.state) = jr.state
               WHERE bl.id = $1""",
            location_id,
        )
        state = (loc["state"] if loc else None) or ""
        company_id = loc["company_id"] if loc else None
        has_local_ordinance = loc["has_local_ordinance"] if loc else None

        rows = await conn.fetch(
            "SELECT r.category, r.jurisdiction_level, r.title, r.jurisdiction_name, r.rate_type "
            "FROM compliance_requirements r "
            "LEFT JOIN jurisdiction_requirements cat ON cat.id = r.jurisdiction_requirement_id "
            "WHERE r.location_id = $1"
            # This tile counts what the Requirements tab lists — the two must
            # agree or the count is just wrong on screen.
            + await codified_gate_sql("cat", conn=conn),
            location_id,
        )
        req_dicts = [dict(r) for r in rows]
        if has_local_ordinance is False:
            req_dicts = _filter_city_level_requirements(req_dicts, state)
        _normalize_requirement_categories(req_dicts)
        if company_id:
            req_dicts = await _filter_requirements_for_company(
                conn, company_id, req_dicts
            )
        filtered = (
            await _filter_with_preemption(conn, req_dicts, state)
            if state
            else _filter_by_jurisdiction_priority(req_dicts)
        )
        unread_alerts_count = await conn.fetchval(
            "SELECT COUNT(*) FROM compliance_alerts WHERE location_id = $1 AND status = 'unread'",
            location_id,
        )
        return {
            "requirements_count": len(filtered),
            "unread_alerts_count": unread_alerts_count or 0,
        }




async def get_locations(company_id: UUID) -> list[dict]:
    """Return locations with employee/requirements/alerts counts in a single query."""
    from app.database import get_connection

    async with get_connection() as conn:
        # `jurisdiction_repo_count` (jrc below) is deliberately NOT gated — it
        # reports what the shared catalog holds for this jurisdiction, which is
        # exactly the number an admin needs to see diverge from the tenant's.
        query = """SELECT bl.*, jr.has_local_ordinance,
                      COALESCE(ec.cnt, 0) AS employee_count,
                      COALESCE(en.names, ARRAY[]::text[]) AS employee_names,
                      COALESCE(rc.cnt, 0) AS requirements_count,
                      COALESCE(rall.cnt, 0) AS projected_count,
                      COALESCE(ac.cnt, 0) AS unread_alerts_count,
                      COALESCE(jrc.cnt, 0) AS jurisdiction_repo_count
               FROM business_locations bl
               LEFT JOIN jurisdiction_reference jr
                 ON LOWER(bl.city) = jr.city AND UPPER(bl.state) = jr.state
               LEFT JOIN LATERAL (
                   SELECT COUNT(*) AS cnt FROM employees e
                   WHERE e.termination_date IS NULL
                     AND (
                       e.work_location_id = bl.id
                       OR (
                         e.work_location_id IS NULL
                         AND LOWER(e.work_city) = LOWER(bl.city)
                         AND UPPER(e.work_state) = UPPER(bl.state)
                         AND e.org_id = bl.company_id
                       )
                     )
               ) ec ON true
               LEFT JOIN LATERAL (
                   SELECT ARRAY(
                       SELECT e.first_name || ' ' || e.last_name
                       FROM employees e
                       WHERE e.termination_date IS NULL
                         AND (
                           e.work_location_id = bl.id
                           OR (
                             e.work_location_id IS NULL
                             AND LOWER(e.work_city) = LOWER(bl.city)
                             AND UPPER(e.work_state) = UPPER(bl.state)
                             AND e.org_id = bl.company_id
                           )
                         )
                       LIMIT 5
                   ) AS names
               ) en ON true
               LEFT JOIN LATERAL (
                   SELECT COUNT(*) AS cnt FROM compliance_requirements cr
                   LEFT JOIN jurisdiction_requirements cat
                     ON cat.id = cr.jurisdiction_requirement_id
                   WHERE cr.location_id = bl.id
                   __CODIFIED_GATE__
               ) rc ON true
               LEFT JOIN LATERAL (
                   SELECT COUNT(*) AS cnt FROM compliance_requirements cr
                   WHERE cr.location_id = bl.id
               ) rall ON true
               LEFT JOIN LATERAL (
                   SELECT COUNT(*) AS cnt FROM compliance_alerts ca
                   WHERE ca.location_id = bl.id AND ca.status = 'unread'
               ) ac ON true
               LEFT JOIN LATERAL (
                   SELECT COUNT(*) AS cnt FROM jurisdiction_requirements jreq
                   WHERE jreq.jurisdiction_id = bl.jurisdiction_id
               ) jrc ON true
               WHERE bl.company_id = $1
               ORDER BY bl.created_at DESC"""
        query = query.replace(
            "__CODIFIED_GATE__", await codified_gate_sql("cat", conn=conn)
        )
        rows = await conn.fetch(query, company_id)
        result = []
        for row in rows:
            d = dict(row)
            # data_status answers "has this location been synced from the
            # catalog?" — a pipeline fact. It must read the UNGATED projection
            # count: a fully-synced location whose rows simply aren't codified
            # yet would otherwise report 'needs_research' and invite a pointless
            # (and billable) re-research of data we already hold.
            req_count = d.pop("projected_count", 0)
            repo_count = d.get("jurisdiction_repo_count", 0)
            if req_count > 0:
                d["data_status"] = "synced"
            elif repo_count > 0:
                d["data_status"] = "available"
            else:
                d["data_status"] = "needs_research"
            result.append(d)
        return result




async def verify_location_ownership(conn, location_id: UUID, company_id: UUID) -> bool:
    """Return True iff *location_id* belongs to *company_id*.

    Single source of truth for the ownership check that used to be inlined at
    three call sites (compliance.py's legislation-assign endpoint, and the two
    admin cherry-pick functions below) — future hardening (e.g. soft-delete
    awareness) lands once here instead of three times.
    """
    owns_location = await conn.fetchval(
        "SELECT 1 FROM business_locations WHERE id = $1 AND company_id = $2",
        location_id, company_id,
    )
    return bool(owns_location)




async def get_location(
    location_id: UUID, company_id: UUID
) -> Optional[BusinessLocation]:
    from app.database import get_connection

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """SELECT bl.*, jr.has_local_ordinance
               FROM business_locations bl
               LEFT JOIN jurisdiction_reference jr
                 ON LOWER(bl.city) = jr.city AND UPPER(bl.state) = jr.state
               WHERE bl.id = $1 AND bl.company_id = $2""",
            location_id,
            company_id,
        )
        if row:
            return BusinessLocation(**dict(row))
        return None




async def update_facility_attributes(
    location_id: UUID, company_id: UUID, attrs: dict
) -> Optional[dict]:
    """Merge new facility attributes into existing JSONB and return merged result."""
    from app.database import get_connection

    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT id, facility_attributes FROM business_locations WHERE id = $1 AND company_id = $2",
            location_id, company_id,
        )
        if not row:
            return None

        existing = row["facility_attributes"]
        if isinstance(existing, str):
            try:
                existing = json.loads(existing)
            except (json.JSONDecodeError, TypeError):
                existing = {}
        existing = existing or {}

        # Merge: new values overwrite, None values remove keys
        for k, v in attrs.items():
            if v is None:
                existing.pop(k, None)
            else:
                existing[k] = v

        await conn.execute(
            "UPDATE business_locations SET facility_attributes = $1, updated_at = NOW() WHERE id = $2",
            json.dumps(existing), location_id,
        )
        return existing




async def get_facility_attributes(
    location_id: UUID, company_id: UUID
) -> Optional[dict]:
    """Return facility_attributes for a location, or None if not found."""
    from app.database import get_connection

    async with get_connection() as conn:
        row = await conn.fetchrow(
            "SELECT facility_attributes FROM business_locations WHERE id = $1 AND company_id = $2",
            location_id, company_id,
        )
        if not row:
            return None
        fa = row["facility_attributes"]
        if isinstance(fa, str):
            try:
                return json.loads(fa)
            except (json.JSONDecodeError, TypeError):
                return {}
        return fa or {}




async def update_location(
    location_id: UUID, company_id: UUID, data: LocationUpdate
) -> Optional[BusinessLocation]:
    from app.database import get_connection
    from datetime import datetime

    async with get_connection() as conn:
        updates = []
        params = []
        param_idx = 3

        if data.name is not None:
            updates.append(f"name = ${param_idx}")
            params.append(data.name)
            param_idx += 1
        if data.address is not None:
            updates.append(f"address = ${param_idx}")
            params.append(data.address)
            param_idx += 1
        if data.city is not None:
            updates.append(f"city = ${param_idx}")
            params.append(data.city)
            param_idx += 1
        if data.state is not None:
            updates.append(f"state = ${param_idx}")
            params.append(data.state.upper())
            param_idx += 1
        if data.county is not None:
            updates.append(f"county = ${param_idx}")
            params.append(data.county)
            param_idx += 1
        if data.zipcode is not None:
            updates.append(f"zipcode = ${param_idx}")
            params.append(data.zipcode)
            param_idx += 1
        if data.is_active is not None:
            updates.append(f"is_active = ${param_idx}")
            params.append(data.is_active)
            param_idx += 1
        if data.ein is not None:
            updates.append(f"ein = ${param_idx}")
            params.append(data.ein)
            param_idx += 1
        if data.naics is not None:
            updates.append(f"naics = ${param_idx}")
            params.append(data.naics)
            param_idx += 1
        if data.max_employees is not None:
            updates.append(f"max_employees = ${param_idx}")
            params.append(data.max_employees)
            param_idx += 1
        if data.annual_avg_employees is not None:
            updates.append(f"annual_avg_employees = ${param_idx}")
            params.append(data.annual_avg_employees)
            param_idx += 1

        if not updates:
            return await get_location(location_id, company_id)

        updates.append("updated_at = NOW()")
        params.insert(0, location_id)
        params.insert(1, company_id)

        await conn.execute(
            f"UPDATE business_locations SET {', '.join(updates)} WHERE id = $1 AND company_id = $2",
            *params,
        )
        return await get_location(location_id, company_id)




async def delete_location(location_id: UUID, company_id: UUID) -> bool:
    from app.database import get_connection

    async with get_connection() as conn:
        # Protect locations with active employees
        active_count = await conn.fetchval(
            "SELECT COUNT(*) FROM employees WHERE work_location_id = $1 AND termination_date IS NULL",
            location_id,
        )
        if active_count and active_count > 0:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot delete: {active_count} active employee{'s' if active_count != 1 else ''} assigned to this location.",
            )

        result = await conn.execute(
            "DELETE FROM business_locations WHERE id = $1 AND company_id = $2",
            location_id,
            company_id,
        )
        return result == "DELETE 1"




async def admin_add_requirement_to_location(
    location_id: UUID, company_id: UUID, jurisdiction_requirement_id: UUID,
) -> dict:
    """Copy a single jurisdiction_requirements row into compliance_requirements
    for *location_id*, marking governance_source = 'admin_override'.

    Returns the inserted requirement dict, or raises if duplicate/not found.
    """
    from app.database import get_connection

    async with get_connection() as conn:
        if not await verify_location_ownership(conn, location_id, company_id):
            raise ValueError("Location does not belong to this company")

        # 1. Fetch the source row
        jr = await conn.fetchrow(
            "SELECT * FROM jurisdiction_requirements WHERE id = $1",
            jurisdiction_requirement_id,
        )
        if not jr:
            raise ValueError("Jurisdiction requirement not found")

        req_key = f"{jr['category']}:{jr['regulation_key'] or jr['title']}"

        # 2. Check for duplicate — by catalog FK (exact) OR legacy string key.
        exists = await conn.fetchval(
            """
            SELECT 1 FROM compliance_requirements
            WHERE location_id = $1
              AND (jurisdiction_requirement_id = $2 OR requirement_key = $3)
            """,
            location_id, jurisdiction_requirement_id, req_key,
        )
        if exists:
            raise ValueError("Requirement already exists for this location")

        # 3. Insert (stamps the catalog FK + provenance)
        return await _insert_catalog_requirement(
            conn, location_id, jr, "admin_override", on_conflict_nothing=False
        )




async def admin_add_requirements_to_location_batch(
    conn,
    location_id: UUID,
    company_id: UUID,
    jr_ids: list,
    governance_source: str = "onboarding_wizard",
) -> dict:
    """Project many jurisdiction_requirements rows into compliance_requirements
    for *location_id* on a shared connection (so callers can run inside their own
    transaction — e.g. onboarding finalize).

    Idempotent: a row already linked to a given catalog requirement at this
    location is skipped via the partial unique index. Returns
    ``{written, skipped_existing, missing_jr}``.

    Non-active rows (grounding-quarantined 'under_review', admin-rejected
    'repealed') are counted as ``missing_jr`` and never projected. This is an
    id-keyed path, so it bypasses the ``_load_jurisdiction_requirements`` choke
    point: a session whose resolved scope was computed BEFORE a row was
    quarantined would otherwise still serve it to the tenant at finalize.
    """
    if not await verify_location_ownership(conn, location_id, company_id):
        raise ValueError("Location does not belong to this company")

    written = skipped = missing = 0
    for jr_id in jr_ids:
        jr = await conn.fetchrow(
            "SELECT * FROM jurisdiction_requirements WHERE id = $1 "
            "AND COALESCE(status, 'active') = 'active'",
            jr_id,
        )
        if not jr:
            missing += 1
            continue
        row = await _insert_catalog_requirement(
            conn, location_id, jr, governance_source, on_conflict_nothing=True
        )
        if row is None:
            skipped += 1
        else:
            written += 1
    return {"written": written, "skipped_existing": skipped, "missing_jr": missing}
