"""compliance_service.catalog_writes — J6 split of compliance_service.py."""
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
    _as_jsonb,
    parse_date,
)
from app.core.services.compliance_service._normalize import (
    _base_title,
    _clamp_varchar_fields,
    _coerce_minimum_wage_rate_type,
    _match_title_to_canonical_key,
    _normalize_category,
    _normalize_rate_type,
    _normalize_title_key,
    _validate_source_urls,
)
from app.core.services.compliance_service._jurisdictions import (
    _resolve_jurisdiction_id_for_level,
)



async def _upsert_jurisdiction_requirements_routed(
    conn, leaf_jurisdiction_id: UUID, reqs: List[Dict], *, research_source: Optional[str] = None
) -> Dict[str, int]:
    """Route requirements to their proper jurisdiction level, then upsert.

    Instead of storing all requirements (federal, state, county, city) on
    the leaf city jurisdiction, this routes each requirement to the
    jurisdiction it actually belongs to. The resolve_jurisdiction_stack CTE
    already walks city→county→state→federal, so storing each requirement
    once at its source level eliminates duplication.
    """
    from collections import defaultdict

    # Group requirements by their jurisdiction level
    level_groups: Dict[str, List[Dict]] = defaultdict(list)
    for req in reqs:
        level = (req.get("jurisdiction_level") or "city").lower().strip()
        level_groups[level].append(req)

    # Resolve target jurisdiction for each level and upsert
    affected_jurisdictions: set = set()
    city_keys: set = set()  # Track city-level keys for cleanup

    unroutable = 0
    for level, group_reqs in level_groups.items():
        target_jid = await _resolve_jurisdiction_id_for_level(
            conn, leaf_jurisdiction_id, level
        )
        if target_jid is None:
            # No home for this level. Writing it to the leaf anyway is what broke
            # the catalog (jparent01) — the row would render as "state law" while
            # being reachable only from this one city. Skip and count it.
            unroutable += len(group_reqs)
            logger.warning(
                "compliance: cannot route %d %r-level requirement(s) from leaf %s — skipped",
                len(group_reqs), level, leaf_jurisdiction_id,
            )
            continue

        affected_jurisdictions.add(target_jid)

        await _upsert_requirements_additive(conn, target_jid, group_reqs, research_source=research_source)

        if target_jid == leaf_jurisdiction_id and level == "city":
            for req in group_reqs:
                city_keys.add(_compute_requirement_key(req))

    # Level-scoped cleanup: only delete stale CITY-level rows from the leaf
    # (preserves inherited requirements; only cleans up local ones).
    #
    # Scoped to `city` AND to this leaf on purpose. The sibling non-routed upsert
    # deletes any row of ANY level whose key this run didn't re-emit — against the
    # SHARED catalog, so one tenant's research pass can delete rows every other
    # tenant reads. See _upsert_jurisdiction_requirements.
    if city_keys:
        existing_rows = await conn.fetch(
            """SELECT id, requirement_key FROM jurisdiction_requirements
               WHERE jurisdiction_id = $1 AND jurisdiction_level = 'city'""",
            leaf_jurisdiction_id,
        )
        for row in existing_rows:
            if row["requirement_key"] not in city_keys:
                await conn.execute(
                    "DELETE FROM jurisdiction_requirements WHERE id = $1", row["id"]
                )

    # Update requirement_count + last_verified_at on all affected jurisdictions
    for jid in affected_jurisdictions:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM jurisdiction_requirements WHERE jurisdiction_id = $1",
            jid,
        )
        await conn.execute(
            "UPDATE jurisdictions SET last_verified_at = NOW(), requirement_count = $1, updated_at = NOW() WHERE id = $2",
            count,
            jid,
        )

    # Always touch last_verified_at on the leaf even if no city-level requirements
    if leaf_jurisdiction_id not in affected_jurisdictions:
        await conn.execute(
            "UPDATE jurisdictions SET last_verified_at = NOW(), updated_at = NOW() WHERE id = $1",
            leaf_jurisdiction_id,
        )

    return {
        "total": len(reqs),
        "levels_routed": {level: len(group) for level, group in level_groups.items()},
        "jurisdictions_affected": len(affected_jurisdictions),
    }




async def _upsert_requirements_routed_additive(
    conn, leaf_jurisdiction_id: UUID, reqs: List[Dict], *,
    research_source: Optional[str] = None, initial_status: str = "active",
) -> Dict[str, Dict[str, Any]]:
    """Route each requirement to the jurisdiction its stamped level belongs on.

    Like ``_upsert_jurisdiction_requirements_routed`` but with NO delete pass, so
    it is safe for a research run that covers only one slice of a jurisdiction
    (a single industry's categories). That sibling's city-cleanup deletes leaf
    city rows whose key the run didn't re-emit — for a dental-only pass that would
    delete every OTHER industry's city rows. It also deliberately does NOT stamp
    ``last_verified_at`` on the affected jurisdictions: a one-industry pass has
    not verified the jurisdiction, and stamping it would make
    ``_is_jurisdiction_fresh`` suppress the *generic* research the jurisdiction
    may still need.

    Without routing, a specialty pass writes state- and federal-stamped rows onto
    the LEAF CITY (this is what `_upsert_requirements_additive` does — it takes
    the jurisdiction it is handed). That is precisely the corruption migration
    jparent01 exists to undo: the row renders as "California / state" while being
    reachable only from the one city it was researched from, so no other city in
    the state can ever see it.

    Returns ``{level: {"jurisdiction_id": UUID|None, "written": int}}`` — what
    actually LANDED, per stamped level. Callers recording coverage must read this,
    not the input list: a row whose level cannot be routed is skipped, and a
    ledger that counts skipped rows as written marks a hole in the catalog as
    "covered", permanently.
    """
    from collections import defaultdict

    level_groups: Dict[str, List[Dict]] = defaultdict(list)
    for req in reqs:
        level = (req.get("jurisdiction_level") or "city").lower().strip()
        level_groups[level].append(req)

    outcome: Dict[str, Dict[str, Any]] = {}
    affected: set = set()
    for level, group_reqs in level_groups.items():
        target_jid = await _resolve_jurisdiction_id_for_level(
            conn, leaf_jurisdiction_id, level
        )
        if target_jid is None:
            logger.warning(
                "compliance: cannot route %d %r-level requirement(s) from %s — skipped",
                len(group_reqs), level, leaf_jurisdiction_id,
            )
            outcome[level] = {"jurisdiction_id": None, "written": 0}
            continue
        await _upsert_requirements_additive(
            conn, target_jid, group_reqs, research_source=research_source,
            initial_status=initial_status,
        )
        affected.add(target_jid)
        prev = outcome.get(level)
        outcome[level] = {
            "jurisdiction_id": target_jid,
            "written": (prev["written"] if prev else 0) + len(group_reqs),
        }

    for jid in affected:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM jurisdiction_requirements WHERE jurisdiction_id = $1", jid
        )
        await conn.execute(
            "UPDATE jurisdictions SET requirement_count = $1, updated_at = NOW() WHERE id = $2",
            count, jid,
        )
    return outcome




async def _upsert_requirements_additive(
    conn, jurisdiction_id: UUID, reqs: List[Dict], *, research_source: Optional[str] = None,
    source_tier: Optional[str] = None, initial_status: str = "active",
):
    """Upsert requirements to a jurisdiction without deleting existing rows.

    research_source: optional tag stored in metadata.research_source to track
    where data came from.  Known values:
        "gemini"       – Gemini AI research
        "official_api" – Government APIs (Federal Register, CMS, Congress.gov)
        "claude_skill" – Claude compliance skill
        "structured"   – Tier-1 structured data (CSV/scrape)
        "manual"       – Admin manual edit

    initial_status: status a brand-new row is INSERTed with — 'active' (default,
    every existing caller) or 'pending' (admin-queued research staged for
    review; invisible to tenants until POST /admin/research-review/approve).
    Only affects the INSERT branch. The ON CONFLICT UPDATE's status CASE is
    untouched: a staged write must never demote an already-active row, and a
    grounding failure still wins over staging (lands 'under_review', the
    existing quarantine surface) — simpler than a three-way state machine.
    """
    # ── Data integrity pipeline ──
    for req in reqs:
        _clamp_varchar_fields(req)
        cat = _normalize_category(req.get("category"))
        if cat:
            req["category"] = cat
    await _validate_source_urls(reqs)

    category_ids = {r["slug"]: r["id"] for r in await conn.fetch(
        "SELECT id, slug FROM compliance_categories"
    )}
    # Registry↔seed drift fallback: the code registry has repeatedly gained
    # categories before their compliance_categories seed migration landed
    # (baseline01, mfgcat01, catseed01 — each fixed a prior instance). A row
    # in such a category must still be WRITTEN (the `category` text column is
    # what nearly every read path filters on) — parked on `uncategorized`
    # rather than dropped, and never on an arbitrary row (the old LIMIT-1
    # bug). catseed01's backfill re-homes parked rows once the seed exists.
    uncategorized_id = category_ids.get("uncategorized")

    for req in reqs:
        category_id = category_ids.get(req.get("category"))
        if category_id is None:
            logger.warning(
                "compliance_service: category %r has no compliance_categories row "
                "(registry/seed drift) — parking %r on 'uncategorized' for "
                "jurisdiction %s (author a seed migration; see catseed01)",
                req.get("category"), req.get("title"), jurisdiction_id,
            )
            category_id = uncategorized_id
            if category_id is None:
                logger.error(
                    "compliance_service: no 'uncategorized' fallback row either — "
                    "dropping requirement %r", req.get("title"),
                )
                continue

        # Build per-requirement metadata (research_source + penalties if present)
        meta_dict: dict = {}
        # Carry any caller-set metadata (e.g. grounding marker from grounded
        # extraction) — but never let it override research_source below.
        req_meta = req.get("metadata")
        if isinstance(req_meta, dict):
            meta_dict.update(req_meta)
        if research_source:
            meta_dict["research_source"] = research_source
        # Sink-side guard for EVERY research path, mirroring the penalty guard
        # below: a caller that never validated against a grounded corpus (e.g.
        # the legacy specialty-research path) previously left this key absent
        # entirely, indistinguishable from pre-grounding-era rows. Default to
        # "ungrounded" so provenance is always queryable.
        meta_dict["grounding"] = req.get("grounding") or "ungrounded"
        if req.get("grounded_citations"):
            meta_dict["grounded_citations"] = req["grounded_citations"]
        # Candidate legal citation the model returned (primary-source prompt). Kept
        # in metadata only — the statute_citation COLUMN stays reconcile-owned; this
        # is the value the pilot's codify step confirms into that trio.
        rc = req.get("statute_citation")
        if rc and str(rc).strip():
            meta_dict["research_citation"] = str(rc).strip()[:500]
        # Sink-side penalty guard for EVERY research path (grounded or not): drop
        # the run-local cited_sources transport key and any insubstantive shell,
        # so ungrounded runs can't persist corpus-local S-ids or inflate the
        # penalty-coverage counter with an empty block.
        from app.core.services.scope_registry.grounded import sanitize_penalties_for_persist
        penalties = sanitize_penalties_for_persist(req.get("penalties"))
        if penalties is not None:
            meta_dict["penalties"] = penalties
        # "No rule applies here" placeholder — kept in the catalog (the research
        # prompt asks for one instead of an empty list, which downstream reads as a
        # FAILED category), but filtered out of the tenant's tab by
        # _project_chain_to_location. Only ever set from the model's own flag: no
        # text heuristic can tell these apart from real law (`no_surprises_act` is
        # a real statute; "Daily Overtime: none" is a real answer).
        if req.get("no_rule_applies"):
            meta_dict["no_rule_applies"] = True
        meta_fragment = json.dumps(meta_dict) if meta_dict else None

        requirement_key, regulation_key = _compute_key_parts(req)
        # RKD is keyed on the NORMALIZED category (same form as the bare key);
        # the raw req category may be cased/aliased ('Meal-Breaks').
        normalized_category = _normalize_category(req.get("category"))
        # _as_jsonb, not json.dumps: these values often come straight off a JSONB
        # read (asyncpg returns them as str), and dumps() would add another layer
        # of escaping on every research pass. See _as_jsonb.
        tc_json = _as_jsonb(req.get("trigger_conditions"))
        aet = _as_jsonb(req.get("applicable_entity_types"))
        steps_raw = req.get("implementation_steps")
        steps_json = json.dumps(steps_raw) if isinstance(steps_raw, list) and steps_raw else None
        # Grounding verdict → status intent (tri-state, consumed by the INSERT
        # VALUES and the ON CONFLICT status CASE below). req["grounded"] is an
        # explicit True/False ONLY when this req was actually checked against a
        # fetched corpus (validate_requirement_citations) — never set at all on
        # the legacy ungrounded-by-design research paths, which pass 'none' and
        # leave status alone. False ⇒ quarantine ('under_review'); True ⇒
        # 'promote' (un-quarantines a previously-failed row — without this,
        # under_review was terminal and the row looped on the research worklist
        # forever). Narrower than "any ungrounded row" by design.
        grounded = req.get("grounded")
        if grounded is False:
            req_status = "under_review"
        elif grounded is True:
            req_status = "promote"
        else:
            req_status = "none"
        await conn.execute(
            """
            INSERT INTO jurisdiction_requirements
                (jurisdiction_id, requirement_key, category, rate_type, jurisdiction_level, jurisdiction_name,
                 title, description, current_value, numeric_value, source_url, source_name,
                 effective_date, expiration_date, last_verified_at, requires_written_policy,
                 applicable_industries, trigger_conditions, applicable_entity_types,
                 implementation_steps, category_id, metadata, source_tier,
                 regulation_key, key_definition_id, source_url_status, source_checked_at, status)
            VALUES ($1, $2, $3::text, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, NOW(), $15, $16, $17, $18,
                    $22::jsonb,
                    $19,
                    CASE WHEN $20::text IS NOT NULL THEN $20::jsonb ELSE '{}'::jsonb END,
                    $21::source_tier_enum,
                    $23,
                    (SELECT id FROM regulation_key_definitions
                     WHERE key = $23::text AND category_slug = $24::text LIMIT 1),
                    COALESCE($25::text, 'unchecked'),
                    CASE WHEN $25::text IS NOT NULL THEN NOW() ELSE NULL END,
                    CASE WHEN $26::text = 'under_review'
                         THEN 'under_review'::requirement_status_enum
                         ELSE $28::requirement_status_enum END)
            ON CONFLICT (jurisdiction_id, requirement_key) DO UPDATE SET
                category = EXCLUDED.category,
                rate_type = EXCLUDED.rate_type,
                jurisdiction_level = EXCLUDED.jurisdiction_level,
                jurisdiction_name = EXCLUDED.jurisdiction_name,
                title = EXCLUDED.title,
                description = EXCLUDED.description,
                previous_value = LEFT(jurisdiction_requirements.current_value, 100),
                current_value = EXCLUDED.current_value,
                numeric_value = EXCLUDED.numeric_value,
                source_url = EXCLUDED.source_url,
                source_name = EXCLUDED.source_name,
                requires_written_policy = EXCLUDED.requires_written_policy,
                applicable_industries = (
                    SELECT array_agg(DISTINCT val) FROM unnest(
                        COALESCE(jurisdiction_requirements.applicable_industries, '{}')
                        || COALESCE(EXCLUDED.applicable_industries, '{}')
                    ) AS val
                ),
                trigger_conditions = EXCLUDED.trigger_conditions,
                applicable_entity_types = EXCLUDED.applicable_entity_types,
                effective_date = EXCLUDED.effective_date,
                expiration_date = EXCLUDED.expiration_date,
                last_verified_at = NOW(),
                last_changed_at = CASE
                    WHEN jurisdiction_requirements.current_value IS DISTINCT FROM EXCLUDED.current_value
                    THEN NOW() ELSE jurisdiction_requirements.last_changed_at END,
                implementation_steps = EXCLUDED.implementation_steps,
                -- A re-research pass IS "we re-read the law", so it clears a
                -- drift-raised needs_review: recompute the status from the value
                -- diff and drop the metadata.drift breadcrumb. Other statuses are
                -- left untouched (this upsert has never owned change_status).
                change_status = CASE
                    WHEN jurisdiction_requirements.change_status = 'needs_review'
                    THEN (CASE
                        WHEN jurisdiction_requirements.current_value IS DISTINCT FROM EXCLUDED.current_value
                        THEN 'changed' ELSE 'unchanged' END)
                    ELSE jurisdiction_requirements.change_status END,
                metadata = (
                    CASE
                        WHEN jurisdiction_requirements.change_status = 'needs_review'
                        THEN (COALESCE(jurisdiction_requirements.metadata, '{}'::jsonb) - 'drift') || EXCLUDED.metadata
                        ELSE COALESCE(jurisdiction_requirements.metadata, '{}'::jsonb) || EXCLUDED.metadata END
                    -- jsonb || is a SHALLOW merge, so a new penalties block would
                    -- wholesale-replace an existing one and drop keys the new block
                    -- omits (e.g. a skill-written source_url that grounded
                    -- re-research never sets). Deep-merge the penalties sub-object:
                    -- old penalties overlaid by new (new wins per key, old keys kept).
                    || CASE WHEN EXCLUDED.metadata ? 'penalties'
                        THEN jsonb_build_object('penalties',
                            COALESCE(jurisdiction_requirements.metadata->'penalties', '{}'::jsonb)
                            || (EXCLUDED.metadata->'penalties'))
                        ELSE '{}'::jsonb END
                ),
                source_tier = CASE
                    WHEN EXCLUDED.source_tier IS NOT NULL
                     AND (jurisdiction_requirements.source_tier IS NULL
                          OR EXCLUDED.source_tier < jurisdiction_requirements.source_tier)
                    THEN EXCLUDED.source_tier
                    ELSE jurisdiction_requirements.source_tier
                END,
                regulation_key = COALESCE(EXCLUDED.regulation_key, jurisdiction_requirements.regulation_key),
                key_definition_id = COALESCE(EXCLUDED.key_definition_id, jurisdiction_requirements.key_definition_id),
                -- Forward-repair: a re-research with a properly-resolved category
                -- corrects a historically mis-tagged row (the old LIMIT-1 bug).
                -- NULLIF keeps a drift-parked 'uncategorized' write ($27) from
                -- downgrading an already-correct tag.
                category_id = COALESCE(
                    NULLIF(EXCLUDED.category_id, $27::uuid),
                    jurisdiction_requirements.category_id),
                source_url_status = CASE
                    WHEN $25::text IS NOT NULL THEN $25::text
                    ELSE jurisdiction_requirements.source_url_status END,
                source_checked_at = CASE
                    WHEN $25::text IS NOT NULL THEN NOW()
                    ELSE jurisdiction_requirements.source_checked_at END,
                -- Grounding verdicts move status BOTH ways: a write that failed
                -- grounding quarantines the row; a write that PASSED grounding
                -- promotes a quarantined row back to active (without this,
                -- under_review was terminal — the row stayed off the served
                -- surface forever while staying ON the research worklist,
                -- re-burning Gemini every scheduled cycle). A write with no
                -- verdict (the ordinary ungrounded path) never touches status.
                status = CASE
                    WHEN $26::text = 'under_review' THEN 'under_review'::requirement_status_enum
                    WHEN $26::text = 'promote'
                         AND jurisdiction_requirements.status = 'under_review'
                    THEN 'active'::requirement_status_enum
                    ELSE jurisdiction_requirements.status END,
                updated_at = NOW()
            -- 'repealed' is an admin's explicit "this value is WRONG" verdict
            -- (POST /under-review/decide) and the row survives only as an audit
            -- trail. Re-research must not silently overwrite it back into
            -- existence — leave the row frozen until a human un-rejects it.
            WHERE jurisdiction_requirements.status <> 'repealed'
            """,
            jurisdiction_id,
            requirement_key,
            req.get("category"),
            req.get("rate_type"),
            req.get("jurisdiction_level"),
            req.get("jurisdiction_name"),
            req.get("title"),
            req.get("description"),
            req.get("current_value"),
            req.get("numeric_value"),
            req.get("source_url"),
            req.get("source_name"),
            parse_date(req.get("effective_date")),
            parse_date(req.get("expiration_date")),
            req.get("requires_written_policy"),
            req.get("applicable_industries"),
            tc_json,
            aet,
            category_id,           # $19: resolved above — never an arbitrary fallback row
            meta_fragment,         # $20: research_source metadata
            source_tier,           # $21: source_tier enum value
            steps_json,            # $22: implementation_steps JSONB
            regulation_key,        # $23: bare regulation_key (store↔scope join key)
            normalized_category,   # $24: normalized category for the RKD FK lookup
            req.get("source_url_status"),  # $25: liveness flag from _validate_source_urls
            req_status,             # $26: grounding verdict — 'under_review' | 'promote' | 'none'
            uncategorized_id,       # $27: drift-park sentinel — never downgrades an existing tag
            initial_status,         # $28: INSERT-only status for brand-new rows — 'active' | 'pending'
        )




async def _upsert_jurisdiction_requirements(
    conn, jurisdiction_id: UUID, reqs: List[Dict]
):
    """Write Gemini results into the jurisdiction repository. Remove stale rows."""
    # ── Data integrity pipeline ──
    for req in reqs:
        _clamp_varchar_fields(req)
        cat = _normalize_category(req.get("category"))
        if cat:
            req["category"] = cat
    await _validate_source_urls(reqs)

    category_ids = {r["slug"]: r["id"] for r in await conn.fetch(
        "SELECT id, slug FROM compliance_categories"
    )}
    # Registry↔seed drift fallback — park on 'uncategorized', never drop and
    # never an arbitrary row. See the twin comment in
    # _upsert_requirements_additive; catseed01's backfill re-homes these.
    uncategorized_id = category_ids.get("uncategorized")

    new_keys = set()
    for req in reqs:
        # Computed + retained in new_keys even on a category-resolution miss
        # below, so an unresolvable category doesn't ALSO purge whatever
        # this jurisdiction already has stored under the same key via the
        # stale-row cleanup at the bottom of this function.
        requirement_key = _compute_requirement_key(req)
        new_keys.add(requirement_key)

        category_id = category_ids.get(req.get("category"))
        if category_id is None:
            logger.warning(
                "compliance_service: category %r has no compliance_categories row "
                "(registry/seed drift) — parking %r on 'uncategorized' for "
                "jurisdiction %s (author a seed migration; see catseed01)",
                req.get("category"), req.get("title"), jurisdiction_id,
            )
            category_id = uncategorized_id
            if category_id is None:
                logger.error(
                    "compliance_service: no 'uncategorized' fallback row either — "
                    "dropping requirement %r", req.get("title"),
                )
                continue

        # _as_jsonb, not json.dumps: these values often come straight off a JSONB
        # read (asyncpg returns them as str), and dumps() would add another layer
        # of escaping on every research pass. See _as_jsonb.
        tc_json = _as_jsonb(req.get("trigger_conditions"))
        aet = _as_jsonb(req.get("applicable_entity_types"))
        await conn.execute(
            """
            INSERT INTO jurisdiction_requirements
                (jurisdiction_id, requirement_key, category, rate_type, jurisdiction_level, jurisdiction_name,
                 title, description, current_value, numeric_value, source_url, source_name,
                 effective_date, expiration_date, last_verified_at, requires_written_policy,
                 applicable_industries, trigger_conditions, applicable_entity_types,
                 category_id, source_url_status, source_checked_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, NOW(), $15, $16, $17, $18,
                    $19,
                    COALESCE($20::text, 'unchecked'),
                    CASE WHEN $20::text IS NOT NULL THEN NOW() ELSE NULL END)
            ON CONFLICT (jurisdiction_id, requirement_key) DO UPDATE SET
                category = EXCLUDED.category,
                rate_type = EXCLUDED.rate_type,
                jurisdiction_level = EXCLUDED.jurisdiction_level,
                jurisdiction_name = EXCLUDED.jurisdiction_name,
                title = EXCLUDED.title,
                description = EXCLUDED.description,
                previous_value = LEFT(jurisdiction_requirements.current_value, 100),
                current_value = EXCLUDED.current_value,
                numeric_value = EXCLUDED.numeric_value,
                source_url = EXCLUDED.source_url,
                source_name = EXCLUDED.source_name,
                requires_written_policy = EXCLUDED.requires_written_policy,
                applicable_industries = (
                    SELECT array_agg(DISTINCT val) FROM unnest(
                        COALESCE(jurisdiction_requirements.applicable_industries, '{}')
                        || COALESCE(EXCLUDED.applicable_industries, '{}')
                    ) AS val
                ),
                trigger_conditions = EXCLUDED.trigger_conditions,
                applicable_entity_types = EXCLUDED.applicable_entity_types,
                effective_date = EXCLUDED.effective_date,
                expiration_date = EXCLUDED.expiration_date,
                last_verified_at = NOW(),
                last_changed_at = CASE
                    WHEN jurisdiction_requirements.current_value IS DISTINCT FROM EXCLUDED.current_value
                    THEN NOW() ELSE jurisdiction_requirements.last_changed_at END,
                -- Forward-repair a historically mis-tagged category_id (the old
                -- LIMIT-1 bug); NULLIF keeps a drift-parked 'uncategorized'
                -- write ($21) from downgrading an already-correct tag.
                category_id = COALESCE(
                    NULLIF(EXCLUDED.category_id, $21::uuid),
                    jurisdiction_requirements.category_id),
                source_url_status = CASE
                    WHEN $20::text IS NOT NULL THEN $20::text
                    ELSE jurisdiction_requirements.source_url_status END,
                source_checked_at = CASE
                    WHEN $20::text IS NOT NULL THEN NOW()
                    ELSE jurisdiction_requirements.source_checked_at END,
                updated_at = NOW()
            """,
            jurisdiction_id,
            requirement_key,
            req.get("category"),
            req.get("rate_type"),
            req.get("jurisdiction_level"),
            req.get("jurisdiction_name"),
            req.get("title"),
            req.get("description"),
            req.get("current_value"),
            req.get("numeric_value"),
            req.get("source_url"),
            req.get("source_name"),
            parse_date(req.get("effective_date")),
            parse_date(req.get("expiration_date")),
            req.get("requires_written_policy"),
            req.get("applicable_industries"),
            tc_json,
            aet,
            category_id,           # $19: resolved above — never an arbitrary fallback row
            req.get("source_url_status"),  # $20: liveness flag from _validate_source_urls
            uncategorized_id,      # $21: drift-park sentinel — never downgrades an existing tag
        )

    # NO DELETE HERE — deliberately.
    #
    # This used to be: "Remove jurisdiction rows not in new result set" — every
    # row on this jurisdiction whose key THIS ONE RUN didn't re-emit was deleted.
    # jurisdiction_requirements is the SHARED catalog, so one tenant's research
    # pass (a single Gemini call, which returns a different slice every time)
    # deleted obligations every other tenant reads. It also destroyed rows whose
    # ids were still held by the caller's in-flight list, which then FK-aborted
    # the location sync mid-write (see _refresh_catalog_links).
    #
    # A row leaves the catalog by being *repealed* (status='repealed', which the
    # read path already excludes) or superseded — never by being absent from one
    # non-deterministic research result. Staleness is what last_verified_at and
    # the drift sweep are for.

    # Update jurisdiction counts and timestamp
    count = await conn.fetchval(
        "SELECT COUNT(*) FROM jurisdiction_requirements WHERE jurisdiction_id = $1",
        jurisdiction_id,
    )
    await conn.execute(
        "UPDATE jurisdictions SET last_verified_at = NOW(), requirement_count = $1, updated_at = NOW() WHERE id = $2",
        count,
        jurisdiction_id,
    )




async def _upsert_jurisdiction_legislation(
    conn, jurisdiction_id: UUID, items: List[Dict]
):
    """Write legislation results into the jurisdiction repository."""
    new_keys = set()
    for item in items:
        leg_key = item.get("legislation_key")
        if not leg_key:
            leg_key = _normalize_title_key(item.get("title", ""))
        if not leg_key:
            continue
        new_keys.add(leg_key)

        eff_date = parse_date(item.get("expected_effective_date"))
        confidence = item.get("confidence")
        if confidence is not None:
            confidence = float(confidence)

        await conn.execute(
            """
            INSERT INTO jurisdiction_legislation
                (jurisdiction_id, legislation_key, category, title, description,
                 current_status, expected_effective_date, impact_summary,
                 source_url, source_name, confidence, last_verified_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, NOW())
            ON CONFLICT (jurisdiction_id, legislation_key) DO UPDATE SET
                category = EXCLUDED.category,
                title = EXCLUDED.title,
                description = EXCLUDED.description,
                current_status = EXCLUDED.current_status,
                expected_effective_date = EXCLUDED.expected_effective_date,
                impact_summary = EXCLUDED.impact_summary,
                source_url = EXCLUDED.source_url,
                source_name = EXCLUDED.source_name,
                confidence = EXCLUDED.confidence,
                last_verified_at = NOW(),
                updated_at = NOW()
            """,
            jurisdiction_id,
            leg_key,
            item.get("category"),
            item.get("title"),
            item.get("description"),
            item.get("current_status", "proposed"),
            eff_date,
            item.get("impact_summary"),
            item.get("source_url"),
            item.get("source_name"),
            confidence,
        )

    # Update legislation count
    count = await conn.fetchval(
        "SELECT COUNT(*) FROM jurisdiction_legislation WHERE jurisdiction_id = $1",
        jurisdiction_id,
    )
    await conn.execute(
        "UPDATE jurisdictions SET legislation_count = $1, updated_at = NOW() WHERE id = $2",
        count,
        jurisdiction_id,
    )




async def _refresh_catalog_links(conn, reqs: List[Dict]) -> None:
    """Drop ``jurisdiction_requirement_id`` values the catalog no longer has.

    The in-flight requirement dicts are loaded from the catalog BEFORE the upsert
    runs (``_jurisdiction_row_to_dict`` stamps the id), and the upsert can delete
    or merge rows out from under them. The next call — this sync — then inserts a
    compliance_requirements row FK'd to a dead id and the whole location's sync
    aborts on ``compliance_requirements_jurisdiction_requirement_id_fkey``. That
    is what made a real onboarding build report "your compliance baseline is
    live" while having written only part of it.

    A stale link is dropped to NULL rather than raising: the requirement itself is
    still real and the tenant should see it. The FK is an enrichment link, not the
    row's identity.
    """
    ids = {
        req["jurisdiction_requirement_id"]
        for req in reqs
        if req.get("jurisdiction_requirement_id")
    }
    if not ids:
        return

    live = {
        row["id"]
        for row in await conn.fetch(
            "SELECT id FROM jurisdiction_requirements WHERE id = ANY($1::uuid[])",
            [UUID(str(i)) for i in ids],
        )
    }
    stale = {str(i) for i in ids} - {str(i) for i in live}
    if not stale:
        return

    for req in reqs:
        if str(req.get("jurisdiction_requirement_id") or "") in stale:
            req["jurisdiction_requirement_id"] = None
    logger.warning(
        "compliance: dropped %d stale catalog link(s) before location sync", len(stale)
    )




def _resolve_regulation_key(raw_key: str, category: str) -> Optional[str]:
    """Validate a Gemini-provided regulation_key against the canonical registry.

    Returns the matched canonical key if found, or None to signal fallback
    to title-based keying. Handles normalization and token-overlap matching
    so Gemini variants like 'california_paid_sick_leave' can resolve to
    'state_paid_sick_leave'.
    """
    from app.core.compliance_registry import EXPECTED_REGULATION_KEYS

    known_keys = EXPECTED_REGULATION_KEYS.get(category, frozenset())
    norm = _normalize_title_key(raw_key).strip().replace(" ", "_")
    if not norm:
        return None

    # Exact match
    if norm in known_keys:
        return norm

    # No known keys for this category — accept Gemini's key as-is
    if not known_keys:
        return norm

    # Token-overlap match: pick the known key with the highest Jaccard similarity
    norm_tokens = set(norm.split("_"))
    best_key = None
    best_score = 0.0
    for known in known_keys:
        known_tokens = set(known.split("_"))
        intersection = len(norm_tokens & known_tokens)
        union = len(norm_tokens | known_tokens)
        if union == 0:
            continue
        score = intersection / union
        if score > best_score:
            best_score = score
            best_key = known

    # Require >= 50% token overlap to accept the match
    if best_score >= 0.5 and best_key:
        return best_key

    # Gemini invented a key we can't match — accept it as-is so it's still
    # stable across runs (better than title-based), but it won't merge with
    # known keys.
    return norm




def _compute_key_parts(req) -> Tuple[str, Optional[str]]:
    """(composite requirement_key, bare regulation_key in registry vocab). Pure.

    The composite is the ON-CONFLICT identity and is byte-identical to the legacy
    ``_compute_requirement_key`` output. The bare key is the value for the
    ``regulation_key`` column — the store↔scope join key, in registry vocabulary
    (``normalize_key`` maps the minimum_wage rate_type dialect; it is identity for
    every other category, so a resolved regkey passes through unchanged).
    """
    from app.core.services.compliance_evals.keys import normalize_key

    cat = req.get("category") if isinstance(req, dict) else req.category
    title = req.get("title") if isinstance(req, dict) else req.title
    jname = (
        req.get("jurisdiction_name")
        if isinstance(req, dict)
        else getattr(req, "jurisdiction_name", None)
    )
    rate_type = (
        req.get("rate_type")
        if isinstance(req, dict)
        else getattr(req, "rate_type", None)
    )
    jlevel = (
        req.get("jurisdiction_level")
        if isinstance(req, dict)
        else getattr(req, "jurisdiction_level", None)
    )
    country = (
        (req.get("country_code") if isinstance(req, dict) else getattr(req, "country_code", None))
        or "US"
    )
    cat_key = _normalize_category(cat) or ""

    # Include rate_type in key for minimum_wage to allow multiple entries per jurisdiction.
    # This MUST run before the regulation_key path — minimum_wage uses rate_type as the
    # primary discriminator (general vs tipped vs healthcare vs exempt_salary, etc.).
    if cat_key == "minimum_wage":
        normalized_rate_type = (
            _coerce_minimum_wage_rate_type(req)
            if isinstance(req, dict)
            else (_normalize_rate_type(rate_type) or "general")
        )
        # ANTI-POLYMORPHY: the composite (the ON CONFLICT write identity) uses the
        # SAME registry key the column gets — not the rate_type dialect. The catalog
        # spoke two dialects for minimum_wage (keys.py), so a pass keying on
        # rate_type ('minimum_wage:exempt_salary') and one keying on the registry
        # vocabulary ('minimum_wage:exempt_salary_threshold') produced two composites
        # for ONE obligation, both survived ON CONFLICT, and the row forked. Keying
        # both on `bare` collapses the dialects to one identity, so a re-research
        # UPDATEs in place instead of minting a twin.
        bare = normalize_key("minimum_wage", normalized_rate_type, jlevel, country)
        return f"{cat_key}:{bare}", bare

    aet = req.get("applicable_entity_types") if isinstance(req, dict) else getattr(req, "applicable_entity_types", None)
    aet_prefix = f"{aet[0]}:" if aet and isinstance(aet, list) and len(aet) > 0 else ""

    # Prefer Gemini-provided regulation_key when present — but validate it
    # against the known canonical keys. If Gemini invents a key not in the
    # registry, try to match it; if no match, fall back to title-based key.
    reg_key = req.get("regulation_key") if isinstance(req, dict) else getattr(req, "regulation_key", None)
    if reg_key and isinstance(reg_key, str):
        resolved = _resolve_regulation_key(reg_key, cat_key)
        if resolved:
            return f"{aet_prefix}{cat_key}:{resolved}", resolved

    # Fallback: try to match title keywords to a canonical regulation key
    base_title = _base_title(title or "", jname)
    base_key = _normalize_title_key(base_title)

    canonical = _match_title_to_canonical_key(base_key, cat_key)
    if canonical:
        return f"{aet_prefix}{cat_key}:{canonical}", canonical

    # Final fallback: raw normalized title (no canonical match)
    return f"{aet_prefix}{cat_key}:{base_key}", base_key




def _compute_requirement_key(req) -> str:
    return _compute_key_parts(req)[0]




async def _upsert_requirement(
    conn, location_id: UUID, requirement_key: str, req: dict
) -> UUID:
    """Insert a new compliance requirement. Returns the new ID.

    ON CONFLICT on the (location_id, jurisdiction_requirement_id) partial unique
    index merges into the existing catalog-linked row instead of erroring. This
    matters because the scan's requirement_key (_compute_requirement_key) can
    differ from the projector's simple key for the same catalog requirement, so a
    key-miss could otherwise try to insert a second row for a jr already projected
    by the wizard at this location. Null-FK (Gemini-fresh) rows don't match the
    partial index, so they insert normally (string-key dedup as before).
    """
    return await conn.fetchval(
        """
        INSERT INTO compliance_requirements
        (location_id, requirement_key, category, rate_type, jurisdiction_level, jurisdiction_name, title, description,
         current_value, numeric_value, source_url, source_name, effective_date, applicable_industries,
         jurisdiction_requirement_id)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
        ON CONFLICT (location_id, jurisdiction_requirement_id)
            WHERE jurisdiction_requirement_id IS NOT NULL
        DO UPDATE SET
            requirement_key = EXCLUDED.requirement_key,
            category = EXCLUDED.category,
            rate_type = EXCLUDED.rate_type,
            jurisdiction_level = EXCLUDED.jurisdiction_level,
            jurisdiction_name = EXCLUDED.jurisdiction_name,
            title = EXCLUDED.title,
            description = EXCLUDED.description,
            current_value = EXCLUDED.current_value,
            numeric_value = EXCLUDED.numeric_value,
            source_url = EXCLUDED.source_url,
            source_name = EXCLUDED.source_name,
            effective_date = EXCLUDED.effective_date,
            applicable_industries = EXCLUDED.applicable_industries,
            updated_at = NOW()
        RETURNING id
        """,
        location_id,
        requirement_key,
        req.get("category"),
        req.get("rate_type"),
        req.get("jurisdiction_level"),
        req.get("jurisdiction_name"),
        req.get("title"),
        req.get("description"),
        req.get("current_value"),
        req.get("numeric_value"),
        req.get("source_url"),
        req.get("source_name"),
        parse_date(req.get("effective_date")),
        req.get("applicable_industries"),
        req.get("jurisdiction_requirement_id"),  # SSOT link; null for Gemini-fresh rows
    )




async def _update_requirement(
    conn,
    existing_id: UUID,
    requirement_key: str,
    req: dict,
    previous_value: Optional[str],
    last_changed_at: Optional[datetime],
):
    """Update an existing compliance requirement.

    Deliberately does NOT touch jurisdiction_requirement_id: this row was matched
    by requirement_key, and COALESCE-filling the FK here could collide with a
    different row at the same location that already holds that FK (e.g. a wizard
    projection), violating the (location_id, jurisdiction_requirement_id) unique
    index mid-scan. Go-forward rows get the FK stamped at INSERT time
    (_upsert_requirement); legacy null-FK rows keep string-key dedup.
    """
    await conn.execute(
        """
        UPDATE compliance_requirements
        SET requirement_key = $1, category = $2, rate_type = $3, jurisdiction_name = $4, title = $5,
            current_value = $6, numeric_value = $7, previous_value = $8, last_changed_at = $9,
            description = $10, source_url = $11, source_name = $12, effective_date = $13,
            applicable_industries = $14, updated_at = NOW()
        WHERE id = $15
        """,
        requirement_key,
        req.get("category"),
        req.get("rate_type"),
        req.get("jurisdiction_name"),
        req.get("title"),
        req.get("current_value"),
        req.get("numeric_value"),
        # previous_value is varchar(100) but holds a copy of current_value
        # (varchar 500) — clamp, same overflow as the catalog ON-CONFLICT paths.
        previous_value[:100] if previous_value else previous_value,
        last_changed_at,
        req.get("description"),
        req.get("source_url"),
        req.get("source_name"),
        parse_date(req.get("effective_date")),
        req.get("applicable_industries"),
        existing_id,
    )




async def _snapshot_to_history(conn, row_dict: dict, location_id: UUID):
    """Insert a snapshot of a requirement into the history table."""
    await conn.execute(
        """
        INSERT INTO compliance_requirement_history
        (requirement_id, location_id, category, rate_type, jurisdiction_level, jurisdiction_name,
         title, description, current_value, numeric_value, source_url, source_name, effective_date)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
        """,
        row_dict["id"],
        location_id,
        row_dict.get("category"),
        row_dict.get("rate_type"),
        row_dict.get("jurisdiction_level"),
        row_dict.get("jurisdiction_name"),
        row_dict.get("title"),
        row_dict.get("description"),
        row_dict.get("current_value"),
        row_dict.get("numeric_value"),
        row_dict.get("source_url"),
        row_dict.get("source_name"),
        row_dict.get("effective_date"),
    )




# ---------------------------------------------------------------------------
# Admin: cherry-pick a jurisdiction requirement into a company location
# ---------------------------------------------------------------------------


async def _insert_catalog_requirement(
    conn,
    location_id: UUID,
    jr: dict,
    governance_source: str,
    *,
    on_conflict_nothing: bool,
) -> Optional[dict]:
    """Project one ``jurisdiction_requirements`` row (``jr``) into
    ``compliance_requirements`` for *location_id*, stamping the catalog FK
    (``jurisdiction_requirement_id``) — the SSOT link / dedup identity — and the
    given ``governance_source``.

    When *on_conflict_nothing* is True, a row already linked to this
    (location_id, catalog requirement) is a no-op and returns ``None`` (via the
    ``uq_compliance_requirements_loc_jr`` partial unique index). The conflict
    clause is a static fragment — no user input is interpolated.
    """
    req_key = f"{jr['category']}:{jr['regulation_key'] or jr['title']}"
    conflict = (
        "ON CONFLICT (location_id, jurisdiction_requirement_id) "
        "WHERE jurisdiction_requirement_id IS NOT NULL DO NOTHING"
        if on_conflict_nothing
        else ""
    )
    row = await conn.fetchrow(
        f"""
        INSERT INTO compliance_requirements (
            location_id, category, jurisdiction_level, jurisdiction_name,
            title, description, current_value, numeric_value,
            source_url, source_name, effective_date,
            requirement_key, governance_source, jurisdiction_requirement_id
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
        {conflict}
        RETURNING id, category, jurisdiction_level, jurisdiction_name,
                  title, description, current_value, numeric_value,
                  source_url, source_name, effective_date,
                  requirement_key, governance_source, jurisdiction_requirement_id
        """,
        location_id,
        jr["category"],
        jr["jurisdiction_level"],
        jr["jurisdiction_name"],
        jr["title"],
        jr["description"],
        jr["current_value"],
        jr["numeric_value"],
        jr["source_url"],
        jr.get("source_name"),
        jr["effective_date"],
        req_key,
        governance_source,
        jr["id"],
    )
    if row is None:
        return None
    result = dict(row)
    result["id"] = str(result["id"])
    if result.get("jurisdiction_requirement_id") is not None:
        result["jurisdiction_requirement_id"] = str(result["jurisdiction_requirement_id"])
    return result
