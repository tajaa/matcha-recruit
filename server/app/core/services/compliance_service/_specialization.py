"""compliance_service.specialization — J6 split of compliance_service.py."""
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

from app.core.services.compliance_service._normalize import (
    _clamp_varchar_fields,
)
from app.core.services.compliance_service._verification import (
    format_corrections_for_prompt,
    get_recent_corrections,
)
from app.core.services.compliance_service._jurisdictions import (
    _lookup_has_local_ordinance,
)
from app.core.services.compliance_service._catalog_writes import (
    _upsert_requirements_additive,
    _upsert_requirements_routed_additive,
)



# Reduced category set for the Matcha-X self-serve onboarding finale: basic
# federal + labor + common state-specific law. Passed as ``categories`` to
# run_compliance_check_stream so the live build researches ~9 categories instead
# of the full required-labor sweep — faster and cheaper for self-serve. All keys
# are valid entries in compliance_registry.
MATCHA_X_LITE_CATEGORIES: List[str] = [
    "minimum_wage",
    "overtime",
    "sick_leave",
    "meal_breaks",
    "pay_frequency",
    "final_pay",
    "anti_discrimination",
    "workplace_safety",
    "i9_everify",
]




# ──────────────────────────────────────────────────────────────────────────────
# Specialization Research Wizard
# ──────────────────────────────────────────────────────────────────────────────


async def discover_specialization_categories(
    specialization: str,
    parent_industry: str = "healthcare",
) -> Dict[str, Any]:
    """Use Gemini to discover regulatory categories for a given specialization."""
    from app.core.services.gemini_compliance import get_gemini_compliance_service
    from app.core.compliance_registry import CATEGORY_KEYS

    service = get_gemini_compliance_service()
    slug = specialization.lower().replace(" ", "_")
    # The vertical can BE the industry (a hospitality employer has no
    # sub-specialty above hospitality). Then there is no "parent baseline" to
    # research beyond, and the specialization prompt below would be asking the
    # model to exclude the very categories we want.
    top_level = slug == parent_industry
    industry_tag = parent_industry if top_level else f"{parent_industry}:{slug}"

    if top_level:
        prompt = (
            f"You are a compliance expert. For a business operating in the **{specialization}** "
            f"industry in the United States, identify the regulatory compliance categories that "
            f"are SPECIFIC TO THIS INDUSTRY — the obligations a {specialization} employer has that "
            f"a generic employer in another industry does NOT.\n\n"
            f"Return a JSON object with two keys:\n"
            f"1. \"categories\": an array of objects, each with:\n"
            f"   - \"key\": a snake_case slug (e.g., \"food_handler_certification\")\n"
            f"   - \"label\": a human-readable name\n"
            f"   - \"description\": what specific regulations/standards to research for this category\n"
            f"   - \"authority_sources\": array of authoritative domains (e.g., [\"fda.gov\", \"osha.gov\"])\n"
            f"2. \"research_context\": a paragraph describing the key regulatory bodies, federal statutes, "
            f"and common state-level variations for {specialization} compliance. This will be used as "
            f"context for subsequent research calls.\n\n"
            f"Do NOT include generic employment-law categories that apply to EVERY employer regardless "
            f"of industry (minimum wage, overtime, anti-discrimination, I-9, workers' comp, final pay) — "
            f"those are already researched separately. Aim for 5-15 categories."
        )
    else:
        prompt = (
            f"You are a compliance expert. For a **{specialization}** practice under the "
            f"**{parent_industry}** industry, identify the regulatory compliance categories that "
            f"require specific research beyond the general {parent_industry} baseline.\n\n"
            f"Return a JSON object with two keys:\n"
            f"1. \"categories\": an array of objects, each with:\n"
            f"   - \"key\": a snake_case slug (e.g., \"cardiac_catheterization_safety\")\n"
            f"   - \"label\": a human-readable name\n"
            f"   - \"description\": what specific regulations/standards to research for this category\n"
            f"   - \"authority_sources\": array of authoritative domains (e.g., [\"cms.gov\", \"acc.org\"])\n"
            f"2. \"research_context\": a paragraph describing the key regulatory bodies, federal statutes, "
            f"and common state-level variations for {specialization} compliance. This will be used as "
            f"context for subsequent research calls.\n\n"
            f"Focus on categories unique to {specialization} — do NOT include general {parent_industry} "
            f"categories like HIPAA, billing integrity, or clinical safety unless {specialization} has "
            f"specific sub-requirements. Aim for 5-15 categories."
        )

    result = await service._call_with_retry(
        prompt,
        response_key=None,
        max_retries=1,
        label=f"discover_{specialization}_categories",
    )

    categories = result.get("categories", [])
    for cat in categories:
        cat["is_existing"] = cat.get("key", "") in CATEGORY_KEYS

    industry_context = (
        f"\n\nINDUSTRY CONTEXT -- {specialization.upper()} ({parent_industry.upper()}):\n"
        + result.get("research_context", "")
        + f"\n\nTag each requirement with 'applicable_industries': ['{industry_tag}']."
    )

    return {
        "specialization": specialization,
        "industry_tag": industry_tag,
        "categories": categories,
        "industry_context": industry_context,
    }




async def research_specialization_for_jurisdiction(
    conn,
    jurisdiction_id: UUID,
    categories: List[str],
    industry_tag: str,
    industry_context: str = "",
    batch_size: int = 4,
    progress_callback: Optional[Callable] = None,
    *,
    skip_existing: bool = True,
    grounded_corpus: str = "",
    citation_index: Optional[Dict[str, Any]] = None,
    route_by_level: bool = False,
    only_levels: Optional[set] = None,
    initial_status: str = "active",
) -> Dict[str, Any]:
    """Research specialization-specific categories for a jurisdiction.

    Generalized version of _research_healthcare/_oncology/_medical_compliance functions.

    ``skip_existing=False`` researches every requested category even if the
    jurisdiction already has rows in it — the fetch-queue case, where the
    category exists but a specific key was missed (the missing key is targeted
    via ``industry_context``).

    ``route_by_level=True`` files each returned row on the jurisdiction its
    STAMPED level belongs to, instead of writing everything to the jurisdiction
    passed in. Without it, researching a city hands back federal and state
    obligations and writes them onto the city — the misparenting jparent01 had to
    migrate away. Off by default so the admin specialization flow keeps its
    existing behavior; the vertical-coverage path turns it on. Adds
    ``jurisdictions_written`` and ``written_by_level`` to the result.

    TODO(known-debt): the default-False means the admin specialization flow and
    the scope-registry research paths still write leaf-misparented rows — the
    writer jparent01 migrated the damage of is alive on those paths. Flipping the
    default needs those three flows re-verified (their skip_existing checks read
    per-jurisdiction state that routing relocates); do it as its own change.

    ``only_levels``: keep ONLY rows whose stamped jurisdiction_level is in this
    set, dropping the rest before they are written. Researching a category at every
    node of a chain (which is how the vertical ledger earns its per-state reuse)
    otherwise collects the same state obligation up to four times — the city, county,
    state and federal passes each volunteer California's amalgam rule, and the model
    names it differently every time, so no deterministic key/title dedupe can
    collapse them. Giving each cell sole ownership of ONE level removes the
    duplication at the source: a row this cell doesn't own is not dropped from the
    catalog, it is simply left to the cell that does own it.

    ``grounded_corpus`` (+ ``citation_index``): fetched official statute text the
    model must extract values FROM and cite (see grounded.py). When present, each
    returned req is gated by ``validate_requirement_citations`` — reqs that cite a
    real corpus id upsert as ``research_source='gemini_grounded'``; ungrounded
    ones stay ``'gemini'`` + ``metadata.grounding='ungrounded'``.
    """
    from app.core.services.scope_registry.grounded import validate_requirement_citations, validate_penalty_citations
    from app.core.services.gemini_compliance import get_gemini_compliance_service, refresh_dynamic_categories
    from app.core.services.jurisdiction_context import get_known_sources, build_context_prompt, get_global_authority_sources

    # A specialty's categories are confirmed into `compliance_categories` at
    # runtime, but the model-output validator gates on a frozen constant compiled
    # from compliance_registry. Without this refresh every dental/hospitality/etc
    # category reads as "invalid", the requested set empties, and the research call
    # silently falls back to the generic labor default — returning wage law that
    # then gets force-tagged with this industry_tag below.
    await refresh_dynamic_categories(conn)

    j = await conn.fetchrow(
        "SELECT id, city, state, county FROM jurisdictions WHERE id = $1",
        jurisdiction_id,
    )
    if not j:
        return {"error": "Jurisdiction not found", "new": 0, "categories": [], "failed": []}

    city = j["city"]
    state = j["state"]
    county = j.get("county")
    # County nodes store their name in `city` under an internal sentinel
    # ('_county_los angeles'). Passed through raw, the Gemini prompt is asked
    # about a city literally named '_county_los angeles' — degraded or nonsense
    # research whose empty result then gets recorded as a terminal 'empty'
    # verdict. Present it as the county it is.
    if city and city.startswith("_county_"):
        county = county or city[len("_county_"):]
        city = ""
        location_name = f"{county.title()} County, {state}"
    else:
        location_name = f"{city}, {state}" if city else state
    # Federal target = the U.S. national baseline itself (state 'US', no city). The
    # research prompt otherwise treats the jurisdiction as a state/local layer ABOVE
    # federal and returns a null "no additional rule" row — degenerate for federal.
    is_federal = (state == "US" and not city)

    has_local_ordinance = await _lookup_has_local_ordinance(conn, city, state)
    known_sources = await get_known_sources(conn, jurisdiction_id)
    source_context = build_context_prompt(known_sources)
    source_context += get_global_authority_sources(categories)
    # Pass `conn` — this function is reachable from the Celery vertical-coverage
    # sweep, and workers have no pool (get_connection() raises there).
    corrections = await get_recent_corrections(jurisdiction_id, conn=conn)
    corrections_context = format_corrections_for_prompt(corrections)

    try:
        preemption_rows = await conn.fetch(
            "SELECT category, allows_local_override FROM state_preemption_rules WHERE state = $1",
            state.upper(),
        )
        preemption_rules = {row["category"]: row["allows_local_override"] for row in preemption_rows}
    except asyncpg.UndefinedTableError:
        preemption_rules = {}
    except Exception as e:
        logger.warning(f"preemption rules lookup failed: {e}")
        preemption_rules = {}

    # Check which categories this specialization has already researched.
    # If an industry_tag is provided, only skip categories where requirements
    # tagged with this specific specialization already exist — so cardiology
    # and neurology can both research billing_integrity independently.
    existing_cats: set = set()
    if skip_existing:
        if industry_tag:
            existing = await conn.fetch(
                """SELECT DISTINCT category FROM jurisdiction_requirements
                   WHERE jurisdiction_id = $1
                     AND applicable_industries @> ARRAY[$2::text]""",
                jurisdiction_id,
                industry_tag,
            )
        else:
            existing = await conn.fetch(
                "SELECT DISTINCT category FROM jurisdiction_requirements WHERE jurisdiction_id = $1",
                jurisdiction_id,
            )
        existing_cats = {r["category"] for r in existing}
    missing = sorted(cat for cat in categories if cat not in existing_cats)

    if not missing:
        return {"new": 0, "location": location_name, "categories": [], "failed": [], "requirements": [], "skipped": True}

    service = get_gemini_compliance_service()
    total_new = 0
    penalties_stripped = 0  # ungrounded penalty blocks dropped in grounded runs
    failed_categories: List[str] = []
    added_requirements: List[Dict[str, Any]] = []
    jurisdictions_written: set = set()
    # level -> rows that actually LANDED (routing can skip a level it can't
    # place). Coverage decisions must read this, never the pre-write count.
    written_by_level: Dict[str, int] = {}

    async def _write(rows: List[Dict[str, Any]], *, research_source: str) -> None:
        if route_by_level:
            outcome = await _upsert_requirements_routed_additive(
                conn, jurisdiction_id, rows, research_source=research_source,
                initial_status=initial_status,
            )
            for level, info in outcome.items():
                written_by_level[level] = written_by_level.get(level, 0) + info["written"]
                if info["jurisdiction_id"]:
                    jurisdictions_written.add(info["jurisdiction_id"])
        else:
            await _upsert_requirements_additive(
                conn, jurisdiction_id, rows, research_source=research_source,
                initial_status=initial_status,
            )
            jurisdictions_written.add(jurisdiction_id)
            for r in rows:
                level = (r.get("jurisdiction_level") or "city").lower().strip()
                written_by_level[level] = written_by_level.get(level, 0) + 1

    # Batch categories
    batches = [missing[i:i + batch_size] for i in range(0, len(missing), batch_size)]
    progress_idx = 0

    for batch in batches:
        batch_label = ", ".join(c.replace("_", " ") for c in batch)
        progress_idx += len(batch)
        if progress_callback:
            progress_callback(progress_idx, len(missing), f"Researching {batch_label} for {location_name}...")

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
                industry_context=industry_context,
                is_federal=is_federal,
                grounded_corpus=grounded_corpus,
            )
            reqs = reqs or []

            if only_levels:
                kept = [
                    r for r in reqs
                    if (r.get("jurisdiction_level") or "city").lower().strip() in only_levels
                ]
                if len(kept) != len(reqs):
                    logger.info(
                        "specialization: %s/%s — dropped %d row(s) outside this cell's level %s "
                        "(owned by another cell in the chain)",
                        location_name, ",".join(batch), len(reqs) - len(kept), sorted(only_levels),
                    )
                reqs = kept

            for req in reqs:
                _clamp_varchar_fields(req)
                if industry_tag and not req.get("applicable_industries"):
                    req["applicable_industries"] = [industry_tag]

            if reqs:
                if grounded_corpus:
                    # Gate on the corpus the model was given. Grounded reqs
                    # (cited a real statute excerpt) upsert as gemini_grounded;
                    # the rest stay gemini + a metadata.grounding marker.
                    validate_requirement_citations(reqs, citation_index)
                    # Penalties are values too: gate them on the same corpus,
                    # independently of the req-level verdict (penalty text often
                    # lives in a different section). Any penalty block that isn't
                    # grounded in the fetched statute is dropped rather than
                    # persisted from recall — the locator invariant — which also
                    # keeps a recall pass from clobbering skill-written penalties
                    # (real source_url/verified_date) via the metadata merge.
                    validate_penalty_citations(
                        reqs, citation_index, verified_date=date.today().isoformat())
                    for r in reqs:
                        p = r.get("penalties")
                        if isinstance(p, dict) and p.get("grounding") != "grounded":
                            r["penalties"] = None
                            penalties_stripped += 1
                    grounded = [r for r in reqs if r.get("grounded")]
                    ungrounded = [r for r in reqs if not r.get("grounded")]
                    for r in grounded:
                        r["grounding"] = "grounded"
                    for r in ungrounded:
                        r["grounding"] = "ungrounded"
                    if grounded:
                        await _write(grounded, research_source="gemini_grounded")
                    if ungrounded:
                        await _write(ungrounded, research_source="gemini")
                else:
                    await _write(reqs, research_source="gemini")
                total_new += len(reqs)
                added_requirements.extend(reqs)
        except Exception as e:
            failed_categories.extend(batch)
            print(f"[Specialization Research] Error researching {batch_label} for {location_name}: {e}")

    if penalties_stripped:
        # Grounded runs drop penalty blocks not backed by the fetched corpus; the
        # corpus is the requirement's own sections, so enforcement-subpart penalties
        # are routinely stripped. Surface it so a coverage dip reads as expected,
        # not as a regression.
        print(f"[Specialization Research] {location_name}: dropped {penalties_stripped} "
              f"ungrounded penalty block(s) (not in the fetched corpus)")

    return {
        "new": total_new,
        "location": location_name,
        "categories": [c for c in missing if c not in failed_categories],
        "failed": failed_categories,
        "requirements": added_requirements,
        "penalties_stripped": penalties_stripped,
        "jurisdictions_written": jurisdictions_written,
        "written_by_level": written_by_level,
    }




async def get_specialization_completeness(
    conn,
    industry_tag: str,
    expected_categories: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Get completeness data for a specialization across jurisdictions."""
    rows = await conn.fetch(
        """
        SELECT j.state, j.city,
               COUNT(DISTINCT jr.category) AS categories_covered,
               COUNT(*) AS total_requirements
        FROM jurisdiction_requirements jr
        JOIN jurisdictions j ON j.id = jr.jurisdiction_id
        WHERE jr.applicable_industries @> ARRAY[$1::text]
        GROUP BY j.state, j.city
        ORDER BY j.state, j.city
        """,
        industry_tag,
    )
    result = []
    for r in rows:
        entry = {
            "state": r["state"],
            "city": r["city"] or "",
            "categories_covered": r["categories_covered"],
            "total_requirements": r["total_requirements"],
        }
        if expected_categories:
            entry["coverage_pct"] = round(r["categories_covered"] / len(expected_categories) * 100, 1)
        result.append(entry)
    return result
