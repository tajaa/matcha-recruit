"""compliance_service.jurisdictions — J6 split of compliance_service.py."""
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
    _decode_jsonb,
)
from app.core.services.compliance_service._normalize import (
    _missing_required_categories,
    _normalize_category,
    _normalize_city_key,
)



_CITY_ALIAS_FALLBACKS = {
    ("NY", "new york city"): "new york",
    ("NY", "nyc"): "new york",
    ("UT", "salt lake"): "salt lake city",
}




async def _resolve_county_from_zip(conn, zipcode: str, state: str) -> Optional[str]:
    """Look up county from zip code. Returns None if zip not in reference."""
    if not zipcode:
        return None
    try:
        row = await conn.fetchrow(
            "SELECT county FROM zip_county_reference WHERE zipcode = $1 AND state = $2",
            zipcode.strip()[:5],
            state.upper(),
        )
        return row["county"] if row else None
    except asyncpg.UndefinedTableError:
        return None




async def _resolve_reference_city(
    conn,
    city: str,
    state: str,
) -> tuple[str, Optional[str]]:
    """Resolve input city to canonical jurisdiction_reference city + county."""
    norm_city = _normalize_city_key(city)
    norm_state = state.upper().strip()
    lookup_city = _CITY_ALIAS_FALLBACKS.get((norm_state, norm_city), norm_city)

    try:
        row = await conn.fetchrow(
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
            lookup_city,
            norm_state,
        )
    except asyncpg.UndefinedTableError:
        row = None

    if row:
        return row["city"], row["county"]

    return lookup_city, None




# ── Jurisdiction Repository Helpers ──────────────────────────────────────


async def _get_or_create_jurisdiction(
    conn, city: str, state: str, county: Optional[str] = None, zipcode: Optional[str] = None
) -> UUID:
    """Find or create a jurisdiction row with hierarchy resolution.

    Auto-resolves county from jurisdiction_reference when not provided; if
    that city-name match doesn't find one either and ``zipcode`` is given,
    falls back to `_resolve_county_from_zip` (D3.3 — zip was collected at
    onboarding but previously only used by one unrelated endpoint). Then
    links city -> county -> state via parent_id.
    """
    norm_state = state.upper().strip()

    # 1b. State-only shortcut — no city means we just need the state jurisdiction
    if not city or not city.strip():
        state_j = await conn.fetchrow(
            "SELECT id FROM jurisdictions WHERE COALESCE(city, '') = '' AND state = $1",
            norm_state,
        )
        if not state_j:
            await conn.execute(
                "INSERT INTO jurisdictions (city, state, display_name, level) VALUES ('', $1, $2, 'state') ON CONFLICT DO NOTHING",
                norm_state,
                norm_state,
            )
            state_j = await conn.fetchrow(
                "SELECT id FROM jurisdictions WHERE COALESCE(city, '') = '' AND state = $1",
                norm_state,
            )
        return state_j["id"]

    norm_city, ref_county = await _resolve_reference_city(conn, city, state)
    if not county and ref_county:
        county = ref_county
    if not county and zipcode:
        county = await _resolve_county_from_zip(conn, zipcode, norm_state)

    # 2. Get or create city jurisdiction
    city_display = f"{city.strip()}, {norm_state}"
    await conn.execute(
        """
        INSERT INTO jurisdictions (city, state, county, display_name, level)
        VALUES ($1, $2, $3, $4, 'city')
        ON CONFLICT DO NOTHING
        """,
        norm_city,
        norm_state,
        county,
        city_display,
    )
    city_row = await conn.fetchrow(
        "SELECT id, county, parent_id FROM jurisdictions WHERE city = $1 AND state = $2",
        norm_city,
        norm_state,
    )
    city_id = city_row["id"]

    # 3. Get or create state jurisdiction (uses empty-string city convention)
    state_j = await conn.fetchrow(
        "SELECT id FROM jurisdictions WHERE COALESCE(city, '') = '' AND state = $1",
        norm_state,
    )
    if not state_j:
        await conn.execute(
            "INSERT INTO jurisdictions (city, state, display_name, level) VALUES ('', $1, $2, 'state') ON CONFLICT DO NOTHING",
            norm_state,
            norm_state,
        )
        state_j = await conn.fetchrow(
            "SELECT id FROM jurisdictions WHERE COALESCE(city, '') = '' AND state = $1",
            norm_state,
        )
    state_id = state_j["id"]

    # 4. Link county -> state, city -> county (or city -> state if no county)
    if county:
        # Update city's county field if it was auto-resolved
        if not city_row["county"]:
            await conn.execute(
                "UPDATE jurisdictions SET county = $2 WHERE id = $1",
                city_id,
                county,
            )

        # Get or create county jurisdiction
        county_norm = county.lower().strip()
        county_j = await conn.fetchrow(
            "SELECT id FROM jurisdictions WHERE city = $1 AND state = $2",
            f"_county_{county_norm}",
            norm_state,
        )
        if not county_j:
            await conn.execute(
                """
                INSERT INTO jurisdictions (city, state, county, parent_id, display_name, level)
                VALUES ($1, $2, $3, $4, $5, 'county')
                ON CONFLICT DO NOTHING
                """,
                f"_county_{county_norm}",
                norm_state,
                county,
                state_id,
                f"{county}, {norm_state}",
            )
            county_j = await conn.fetchrow(
                "SELECT id FROM jurisdictions WHERE city = $1 AND state = $2",
                f"_county_{county_norm}",
                norm_state,
            )

        county_id = county_j["id"]

        # Ensure county -> state link
        await conn.execute(
            "UPDATE jurisdictions SET parent_id = $2 WHERE id = $1 AND parent_id IS NULL",
            county_id,
            state_id,
        )

        # Link city -> county (even if previously linked directly to state)
        if not city_row["parent_id"] or city_row["parent_id"] == state_id:
            await conn.execute(
                "UPDATE jurisdictions SET parent_id = $2 WHERE id = $1",
                city_id,
                county_id,
            )
    else:
        # No county: link city -> state directly
        if not city_row["parent_id"]:
            await conn.execute(
                "UPDATE jurisdictions SET parent_id = $2 WHERE id = $1",
                city_id,
                state_id,
            )

    return city_id




async def _lookup_has_local_ordinance(conn, city: str, state: str) -> Optional[bool]:
    """Check jurisdiction_reference for whether a city has its own local ordinance."""
    normalized_city = _normalize_city_key(city)
    normalized_state = state.upper().strip()
    lookup_city = _CITY_ALIAS_FALLBACKS.get(
        (normalized_state, normalized_city), normalized_city
    )

    try:
        ref = await conn.fetchrow(
            """
            SELECT has_local_ordinance
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
            lookup_city,
            normalized_state,
        )
        result = ref["has_local_ordinance"] if ref else None
        print(
            f"[Compliance] has_local_ordinance lookup: city={city!r}, state={state!r} → {result}"
        )
        return result
    except (asyncpg.UndefinedTableError, asyncpg.UndefinedColumnError):
        return None




async def _is_jurisdiction_fresh(
    conn, jurisdiction_id: UUID, threshold_days: int
) -> bool:
    """Check if jurisdiction data is trusted enough to skip Gemini.

    Library permanence (B5, settings.repository_ttl_enabled=False by default):
    once a jurisdiction has been verified at all, it stays "fresh" regardless
    of age — stored data is truth until a future diff-scheduler selectively
    re-checks it. Missing data (no last_verified_at) still returns False so
    gap-driven research (via _missing_required_categories) keeps firing. The
    age comparison is kept dormant here so re-enabling REPOSITORY_TTL_ENABLED
    restores selective re-checks without re-plumbing callers.
    """
    row = await conn.fetchrow(
        "SELECT last_verified_at FROM jurisdictions WHERE id = $1",
        jurisdiction_id,
    )
    if not row or not row["last_verified_at"]:
        return False

    from app.config import get_settings as _get_settings
    if not _get_settings().repository_ttl_enabled:
        return True
    age = datetime.utcnow() - row["last_verified_at"]
    return age < timedelta(days=threshold_days)




def _authority_label(level: Optional[str], display_name: Optional[str]) -> Optional[str]:
    """A display label for an issuing jurisdiction, from its `jurisdictions` row.

    `display_name` is authored inconsistently ("los angeles, CA" for the city,
    "Los Angeles, CA" for the county that contains it), so title-case the place
    while preserving a trailing 2-letter state code, and disambiguate a county
    from the identically-named city inside it.
    """
    if not display_name:
        return None
    name = display_name.strip()
    if not name:
        return None

    place, _, region = name.partition(",")
    place = place.strip()
    region = region.strip()
    # Only re-case an all-lower place; a name that already carries capitals may
    # hold something .title() would mangle ("City of Los Angeles" is fine, but
    # so is a hyphenated or apostrophed name).
    if place.islower():
        place = place.title()
    if level == "county" and "county" not in place.lower():
        place = f"{place} County"
    if not region:
        return place
    return f"{place}, {region.upper() if len(region) == 2 else region}"




def _basis_from_metadata(metadata: Any) -> Optional[List[Dict]]:
    """The floor relations recorded on a catalog row's metadata by codify.py.

    A row whose value is its OWN (CA's $70,304 threshold) carries no
    statute_citation for the federal reg it sits on top of — citing it would be
    false provenance — so the relation lives here instead. Surfacing it is what
    makes a demotion legible rather than a citation silently disappearing.
    """
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except (TypeError, ValueError):
            return None
    if not isinstance(metadata, dict):
        return None
    basis = metadata.get("jurisdictional_basis")
    return basis if isinstance(basis, list) else None




async def _load_jurisdiction_requirements(conn, jurisdiction_id: UUID) -> List[Dict]:
    """Read requirements from the jurisdiction repository.

    Excludes 'under_review' (grounding-quarantined), 'repealed' (an admin
    reviewed the quarantined value and confirmed it WRONG), and 'pending'
    (admin-queued research staged for review — not yet approved) rows — the
    single choke point every tenant-sync and gap-detection caller goes through.
    A quarantined row reads as a gap (triggers re-research, and a re-research
    that passes grounding promotes it back to active) rather than as
    served/covered — never silently surfaced to a tenant, never silently
    treated as permanently missing either. A rejected row must obviously never
    be served: it is a known-wrong value kept only as an audit trail. A pending
    row reads as a gap too, on purpose — it exists, but nobody approved it yet.
    """
    rows = await conn.fetch(
        "SELECT * FROM jurisdiction_requirements "
        "WHERE jurisdiction_id = $1 AND status NOT IN ('under_review', 'repealed', 'pending')",
        jurisdiction_id,
    )
    # Carry the catalog row id under an explicit key so the per-location sync can
    # stamp compliance_requirements.jurisdiction_requirement_id (the SSOT link /
    # dedup identity). `id` is already present from dict(r); the explicit alias is
    # unambiguous for the writers below.
    return [{**dict(r), "jurisdiction_requirement_id": r["id"]} for r in rows]




async def _load_chain_requirements(conn, leaf_jurisdiction_id: UUID) -> List[Dict]:
    """Every active requirement across a location's WHOLE jurisdiction chain.

    What a business is liable for is the union of city + county + state + federal
    law that reaches it — not whatever the last research pass happened to return.

    The check used to build a tenant's set from the LEAF jurisdiction's rows plus
    ``_fill_missing_categories_from_parents``, which only backfills categories the
    leaf lacks *entirely*. So a federal obligation never arrived if the leaf
    already held some row in the same category. That is how a Los Angeles dental
    practice was served no OSHA Bloodborne Pathogens standard, no infection
    control, no hazardous-waste generator rules and no radiation-machine
    registration — every one of them sitting in the catalog, in its chain, the
    whole time.

    Research fills gaps in the CATALOG. It does not decide what a tenant sees.
    Callers still apply the industry filter, facility triggers and preemption on
    top of this — this is the candidate set, not the final one.
    """
    rows = await conn.fetch(
        # `depth` bounds the recursion. The tree is at most city→county→state→
        # federal, but a parent_id cycle (a bad merge, a hand-edited row — the junk
        # `ca, CA` / `FL, FL` nodes are still live) would otherwise spin this CTE
        # forever, hanging the connection and every compliance check behind it.
        #
        # status = 'active' only. requirement_status_enum also has 'superseded' and
        # 'pending': a superseded row would be served next to the row that replaced
        # it (the same obligation twice, one with a stale value), and 'pending' is
        # the grounding-quarantine state — not something a tenant should be told
        # they are liable for.
        #
        # `status` is OUR state, not the law's. A row can be 'active' — researched,
        # cited, current in the catalog — and still not be in force, because the
        # catalog deliberately stores forward-looking law. Those are two different
        # time axes and both have to be read:
        #
        #   expired (expiration_date < today) — dropped. It isn't law; serving it
        #     tells a business it is liable for a repealed rule.
        #   future-effective (effective_date > today) — KEPT on purpose. Dropping
        #     it would hide "this hits you on 2027-07-01", which is the whole
        #     product value of storing it; the tab lanes it off `effective_date`.
        #     Whatever is done with it downstream, it must not read as current.
        #
        # NULL on either column means unknown, not false, so both predicates let
        # NULLs through — most of the catalog has no expiration_date, and a NULL
        # comparison would silently drop every one of those rows.
        """
        WITH RECURSIVE chain AS (
            SELECT id, parent_id, 0 AS depth FROM jurisdictions WHERE id = $1
            UNION ALL
            SELECT j.id, j.parent_id, c.depth + 1
            FROM jurisdictions j
            JOIN chain c ON j.id = c.parent_id
            WHERE c.depth < 8
        )
        SELECT r.* FROM jurisdiction_requirements r
        JOIN chain c ON c.id = r.jurisdiction_id
        WHERE r.status = 'active'
          AND (r.expiration_date IS NULL OR r.expiration_date >= CURRENT_DATE)
        """,
        leaf_jurisdiction_id,
    )
    return [{**dict(r), "jurisdiction_requirement_id": r["id"]} for r in rows]




def _is_no_rule_placeholder(req: Dict) -> bool:
    """Is this row here only to say that no rule applies?

    The research prompt deliberately asks for such a row rather than an empty list
    (an empty list reads downstream as a FAILED category), so they are load-bearing
    in the CATALOG — `skip_existing` callers use their presence as "this category
    was researched". They are pure noise on a TENANT'S TAB, whose whole job is
    answering "what am I responsible for".

    Keyed ONLY on the model's own `metadata.no_rule_applies` flag. There is no safe
    heuristic: `no_surprises_act` is the regulation_key of a real federal statute,
    and "Daily Overtime Threshold: this state has none" is a genuinely useful
    answer — guessing from titles or null values would hide real obligations.
    Rows written before the flag existed simply aren't matched, and are left alone.

    Reads BOTH shapes on purpose: a row loaded from the catalog carries the flag
    inside `metadata` (where _upsert_requirements_additive puts it), while a dict
    straight off a research pass still carries it top-level — and the research set
    is exactly what the stream syncs on its fallback path.
    """
    if req.get("no_rule_applies"):
        return True
    meta = _decode_jsonb(req.get("metadata"))
    return bool(meta.get("no_rule_applies")) if isinstance(meta, dict) else False




def _drop_no_rule_placeholders(reqs: List[Dict]) -> List[Dict]:
    kept = [r for r in reqs if not _is_no_rule_placeholder(r)]
    dropped = len(reqs) - len(kept)
    if dropped:
        logger.info("compliance: hid %d 'no rule applies' placeholder(s) from the tab", dropped)
    return kept




async def _load_jurisdiction_legislation(conn, jurisdiction_id: UUID) -> List[Dict]:
    """Read legislation from the jurisdiction repository."""
    rows = await conn.fetch(
        "SELECT * FROM jurisdiction_legislation WHERE jurisdiction_id = $1",
        jurisdiction_id,
    )
    return [dict(r) for r in rows]




def _jurisdiction_row_to_dict(jr: dict) -> dict:
    """Convert a jurisdiction_requirements row to a dict compatible with sync functions."""
    return {
        "jurisdiction_requirement_id": jr.get("id"),
        "category": jr["category"],
        "rate_type": jr.get("rate_type"),
        "jurisdiction_level": jr["jurisdiction_level"],
        "jurisdiction_name": jr["jurisdiction_name"],
        "title": jr["title"],
        "description": jr["description"],
        "current_value": jr["current_value"],
        "numeric_value": jr["numeric_value"],
        "source_url": jr["source_url"],
        "source_name": jr["source_name"],
        "effective_date": jr["effective_date"].isoformat()
        if jr.get("effective_date")
        else None,
        "expiration_date": jr["expiration_date"].isoformat()
        if jr.get("expiration_date")
        else None,
        "applicable_industries": jr.get("applicable_industries"),
        "trigger_conditions": jr.get("trigger_conditions"),
        "applicable_entity_types": jr.get("applicable_entity_types"),
    }




async def _try_load_county_requirements(
    conn, city_jurisdiction_id: UUID, threshold_days: int
) -> Optional[List[Dict]]:
    """Walk up parent_id to the county jurisdiction and load cached reqs if fresh."""
    row = await conn.fetchrow(
        "SELECT parent_id FROM jurisdictions WHERE id = $1", city_jurisdiction_id
    )
    if not row or not row["parent_id"]:
        return None
    county_id = row["parent_id"]

    # Verify it's actually a county (not state)
    county_row = await conn.fetchrow(
        "SELECT city FROM jurisdictions WHERE id = $1", county_id
    )
    if (
        not county_row
        or not county_row["city"]
        or not county_row["city"].startswith("_county_")
    ):
        return None

    if not await _is_jurisdiction_fresh(conn, county_id, threshold_days):
        return None

    j_reqs = await _load_jurisdiction_requirements(conn, county_id)
    if not j_reqs:
        return None

    print(
        f"[Compliance] Reusing county jurisdiction data ({len(j_reqs)} reqs) for city jurisdiction {city_jurisdiction_id}"
    )
    return [_jurisdiction_row_to_dict(jr) for jr in j_reqs]




async def _try_load_state_requirements(
    conn, jurisdiction_id: UUID, threshold_days: int
) -> Optional[List[Dict]]:
    """Walk up parent_id chain to the state jurisdiction and load cached reqs if fresh."""
    current_id = jurisdiction_id
    for _ in range(3):  # Walk up to 3 levels (city -> county -> state)
        row = await conn.fetchrow(
            "SELECT parent_id FROM jurisdictions WHERE id = $1", current_id
        )
        if not row or not row["parent_id"]:
            return None
        current_id = row["parent_id"]

        j_row = await conn.fetchrow(
            "SELECT id, city, state FROM jurisdictions WHERE id = $1", current_id
        )
        if j_row and j_row["city"] == "":  # State jurisdictions have empty city
            state_id = j_row["id"]
            if not await _is_jurisdiction_fresh(conn, state_id, threshold_days):
                return None

            j_reqs = await _load_jurisdiction_requirements(conn, state_id)
            if not j_reqs:
                return None

            print(
                f"[Compliance] Reusing state jurisdiction data ({len(j_reqs)} reqs) for jurisdiction {jurisdiction_id}"
            )
            return [_jurisdiction_row_to_dict(jr) for jr in j_reqs]
    return None




async def _fill_missing_categories_from_parents(
    conn, jurisdiction_id: UUID, requirements: List[Dict], threshold_days: int
) -> bool:
    """Attempt to fill missing categories from county or state caches. Returns True if any gaps were filled."""
    missing = _missing_required_categories(requirements)
    if not missing:
        return False

    filled_any = False

    # Try county — county ordinances change slowly, use lenient threshold
    county_reqs = await _try_load_county_requirements(
        conn, jurisdiction_id, max(threshold_days, 30)
    )
    if county_reqs:
        target_set = {_normalize_category(c) or c for c in missing}
        fill = [
            r
            for r in county_reqs
            if (_normalize_category(r.get("category")) or r.get("category"))
            in target_set
        ]
        if fill:
            requirements.extend(fill)
            filled_any = True
            missing = _missing_required_categories(requirements)
            if not missing:
                return True

    # Try state — state law changes slowly, use a much more lenient threshold
    state_reqs = await _try_load_state_requirements(
        conn, jurisdiction_id, max(threshold_days, 90)
    )
    if state_reqs:
        target_set = {_normalize_category(c) or c for c in missing}
        fill = [
            r
            for r in state_reqs
            if (_normalize_category(r.get("category")) or r.get("category"))
            in target_set
        ]
        if fill:
            requirements.extend(fill)
            filled_any = True

    return filled_any




async def _get_county_jurisdiction_id(
    conn, city_jurisdiction_id: UUID
) -> Optional[UUID]:
    """Get the county jurisdiction ID from parent_id chain."""
    row = await conn.fetchrow(
        "SELECT parent_id FROM jurisdictions WHERE id = $1", city_jurisdiction_id
    )
    if not row or not row["parent_id"]:
        return None
    county_row = await conn.fetchrow(
        "SELECT id, city FROM jurisdictions WHERE id = $1", row["parent_id"]
    )
    if county_row and county_row["city"] and county_row["city"].startswith("_county_"):
        return county_row["id"]
    return None




async def _get_state_jurisdiction_id(conn, jurisdiction_id: UUID) -> Optional[UUID]:
    """Walk the parent chain to the state node.

    Keys on ``level``, not on a city-string heuristic. The previous version
    tested ``city == ""`` — but 27 of 28 state rows carry city NULL, so the test
    was always false, this returned None, and the caller silently filed state law
    under the LEAF CITY. That single mismatch misparented 1,157 rows and is why a
    Los Angeles tenant was served no California minimum wage (migration jparent01).
    """
    current_id = jurisdiction_id
    for _ in range(4):  # city -> county -> state -> federal
        row = await conn.fetchrow(
            "SELECT id, level, parent_id FROM jurisdictions WHERE id = $1", current_id
        )
        if not row:
            return None
        if row["level"] == "state":
            return row["id"]
        if not row["parent_id"]:
            return None
        current_id = row["parent_id"]
    return None




async def _get_or_create_state_jurisdiction_id(
    conn, leaf_jurisdiction_id: UUID
) -> Optional[UUID]:
    """The state node for a leaf, creating it if the tree simply lacks one.

    Falling back to the leaf (what this code used to do) is never acceptable for
    a state-level obligation: it makes the row invisible to every other city in
    the same state. If the walk finds nothing, look the state up by code, and
    create the node as a last resort.
    """
    state_id = await _get_state_jurisdiction_id(conn, leaf_jurisdiction_id)
    if state_id:
        return state_id

    leaf = await conn.fetchrow(
        "SELECT state, country_code FROM jurisdictions WHERE id = $1", leaf_jurisdiction_id
    )
    if not leaf or not leaf["state"]:
        return None

    existing = await conn.fetchval(
        "SELECT id FROM jurisdictions WHERE level = 'state' AND state = $1 LIMIT 1",
        leaf["state"],
    )
    if existing:
        return existing

    federal_id = await conn.fetchval(
        "SELECT id FROM jurisdictions WHERE level = 'federal' AND state = 'US' LIMIT 1"
    )
    return await conn.fetchval(
        """
        INSERT INTO jurisdictions (display_name, level, state, country_code, parent_id, authority_type)
        VALUES ($1, 'state', $1, $2, $3, 'geographic')
        RETURNING id
        """,
        leaf["state"],
        leaf["country_code"] or "US",
        federal_id,
    )




async def _resolve_jurisdiction_id_for_level(
    conn, leaf_jurisdiction_id: UUID, jurisdiction_level: str
) -> Optional[UUID]:
    """Resolve the jurisdiction a requirement belongs on, from its stamped level.

    Returns None when the level is known but no home for it can be resolved.
    **Never falls back to the leaf.** That fallback is what corrupted 63% of the
    catalog (jparent01): chain resolution walks jurisdiction_id, so a state law
    filed under a city is invisible to every other city in that state — while
    still *displaying* as "California / state", so nothing looked wrong. Dropping
    the row is loud; misfiling it is silent. Callers park the None rows.
    """
    level = (jurisdiction_level or "").lower().strip()

    # If the node we were handed already IS the requested level, it is its own
    # home. The per-level helpers below assume a CITY leaf and walk the parent
    # chain — handed a county node, _get_county_jurisdiction_id inspects the
    # county's PARENT (the state) and returns None, so every county-stamped row
    # researched *at* a county node was silently skipped while the caller counted
    # it as written.
    own = await conn.fetchrow(
        "SELECT level FROM jurisdictions WHERE id = $1", leaf_jurisdiction_id
    )
    own_level = str(own["level"]) if own else None
    if own_level == level or (
        {own_level, level} <= {"federal", "national"} and own_level and level
    ):
        return leaf_jurisdiction_id

    if level == "city" or not level:
        return leaf_jurisdiction_id

    if level == "county":
        return await _get_county_jurisdiction_id(conn, leaf_jurisdiction_id)

    if level == "state":
        return await _get_or_create_state_jurisdiction_id(conn, leaf_jurisdiction_id)

    # 'national' is the same tier as 'federal' — a country's own law. It had no
    # case at all here, so it fell through to "unknown level, treat as city" and
    # 232 national rows were filed under cities.
    if level in ("federal", "national"):
        leaf = await conn.fetchrow(
            "SELECT country_code FROM jurisdictions WHERE id = $1", leaf_jurisdiction_id
        )
        country = (leaf["country_code"] if leaf else None) or "US"
        if country == "US":
            return await conn.fetchval(
                "SELECT id FROM jurisdictions WHERE level = 'federal' AND state = 'US' LIMIT 1"
            )
        return await conn.fetchval(
            "SELECT id FROM jurisdictions WHERE level = 'national' AND country_code = $1 LIMIT 1",
            country,
        )

    return None
