"""Tenant-triggered vertical (industry sub-specialty) coverage.

A tenant on a mapped jurisdiction chain still sees nothing industry-specific
for a vertical nobody has researched yet — a dental office in Los Angeles gets
zero dental rows because "dental" was never scoped or researched, not because
the reachability machinery is broken (that was fixed separately: jparent01,
jsonfix01, the chain-union projection).

The catalog is tenant-independent: a company merely TRIGGERS a fill. The
result — categories in `compliance_categories`, requirements in
`jurisdiction_requirements`, both tagged with the industry_tag — is shared, so
every later company in that jurisdiction reads it with zero Gemini calls. This
module is the trigger + the memory that makes that convergence real:

  1. `resolve_vertical` — what sub-specialty does this company need scoped?
  2. `ensure_specialty` — does that specialty have categories yet? If not,
     discover + confirm them (`industry_specialties.py`, unmodified).
  3. `missing_cells` — which (jurisdiction, category) cells has nobody
     researched for this industry_tag yet, per the ledger?
  4. `fill` — research those cells (`research_specialization_for_jurisdiction`,
     unmodified) and record the ledger verdict.

The ledger (`jurisdiction_vertical_coverage`, migration vertcov01) exists
because `research_specialization_for_jurisdiction`'s own `skip_existing` check
infers coverage from "are there rows already" — which cannot distinguish
never-researched from researched-and-genuinely-empty, so an empty cell would
be re-researched forever. `empty` and `failed` are different ledger statuses
on purpose: an empty cell must never retry; a failed one should.
"""
from __future__ import annotations

import logging
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple
from uuid import UUID

from . import industry_specialties

logger = logging.getLogger(__name__)

# A single build must not accidentally kick off an unbounded research run —
# cap cells per trigger and report what was skipped rather than truncate
# silently. A "cell" is one (jurisdiction, category) pair.
MAX_CELLS_PER_FILL = 40


async def resolve_vertical(
    conn, company_id: UUID
) -> Optional[Tuple[str, str, str, str]]:
    """The vertical this company should be scoped against.

    Returns (parent_industry, slug, label, industry_tag), or None only when the
    company's industry can't be resolved at all.

    Three sources, most specific first:

    1. An explicit sub-specialty on the company (`healthcare:dental` — set at
       Matcha-X / Matcha Compliance signup, surfaced by
       `_get_company_industry_tags`).
    2. For healthcare with no specialty: the `facility_attributes.entity_type`
       the facility-inference pass in `run_compliance_check_stream` already
       detects and then drops on the floor. Persisted onto the company here so
       it becomes durable — and because `_filter_requirements_for_company` reads
       the company's own tag set, NOT facility_attributes, so without this write
       the rows we go on to research would be tagged `healthcare:dental` and
       then filtered right back out of the tenant's own tab.
    3. Otherwise the industry ITSELF is the vertical. A hospitality employer has
       no sub-specialty above hospitality; its industry-specific obligations are
       simply the hospitality ones. `industry_tag()` collapses
       (hospitality, hospitality) to the bare tag `hospitality`, which is what
       `_get_company_industry_tags` gives such a company.
    """
    from .compliance_service import _get_company_industry_tags, _resolve_industry

    tags = await _get_company_industry_tags(conn, company_id)
    specific = sorted(t for t in tags if ":" in t)
    if specific:
        tag = specific[0]
        parent, slug = tag.split(":", 1)
        return parent, slug, industry_specialties.label_from_slug(slug), tag

    canonical = _resolve_industry(
        await conn.fetchval("SELECT industry FROM companies WHERE id = $1", company_id) or ""
    )
    if not canonical:
        return None

    if canonical == "healthcare":
        from .compliance_service import _decode_jsonb

        fa_row = await conn.fetchrow(
            """
            SELECT facility_attributes FROM business_locations
            WHERE company_id = $1 AND facility_attributes IS NOT NULL
            ORDER BY updated_at DESC LIMIT 1
            """,
            company_id,
        )
        fa = _decode_jsonb(fa_row["facility_attributes"]) if fa_row else None
        entity_type = (fa or {}).get("entity_type")
        slug = industry_specialties.slugify(entity_type or "")
        if slug:
            await conn.execute(
                """
                UPDATE companies
                SET healthcare_specialties = array_append(
                    COALESCE(healthcare_specialties, ARRAY[]::text[]), $2
                )
                WHERE id = $1
                  AND NOT (COALESCE(healthcare_specialties, ARRAY[]::text[]) @> ARRAY[$2::text])
                """,
                company_id, slug,
            )
            return (
                "healthcare", slug,
                industry_specialties.label_from_slug(slug),
                industry_specialties.industry_tag("healthcare", slug),
            )

    return (
        canonical, canonical,
        industry_specialties.label_from_slug(canonical),
        industry_specialties.industry_tag(canonical, canonical),
    )


async def ensure_specialty(
    conn, parent_industry: str, slug: str, label: str
) -> Tuple[List[str], str]:
    """Categories + research context for this specialty, discovering them if new.

    Returns ([] , "") if discovery fails or yields nothing — callers must treat
    that as "nothing to research", not an error to surface mid-build.
    """
    tag = industry_specialties.industry_tag(parent_industry, slug)

    existing = await conn.fetch(
        "SELECT slug FROM compliance_categories WHERE industry_tag = $1", tag
    )
    if existing:
        context_row = await conn.fetchrow(
            "SELECT research_context FROM industry_specialties WHERE industry_tag = $1", tag
        )
        return (
            [r["slug"] for r in existing],
            (context_row["research_context"] if context_row else None) or "",
        )

    try:
        discovered = await industry_specialties.discover(parent_industry, label)
    except Exception:
        logger.exception("vertical_coverage: discovery failed for %s", tag)
        return [], ""

    if not discovered.get("categories"):
        return [], ""

    try:
        await industry_specialties.confirm(
            conn,
            parent_industry=parent_industry,
            slug=discovered["slug"],
            label=discovered["label"],
            research_context=discovered.get("research_context"),
            categories=discovered["categories"],
            admin_id=None,
        )
    except industry_specialties.SpecialtyTooLong:
        logger.warning("vertical_coverage: specialty tag too long for %s", tag)
        return [], ""

    keys = [c["key"] for c in discovered["categories"] if c.get("key")]
    return keys, discovered.get("research_context") or ""


async def missing_cells(
    conn, jurisdiction_ids: List[UUID], industry_tag: str, categories: List[str]
) -> List[Tuple[UUID, str]]:
    """(jurisdiction_id, category) pairs with no ledger verdict yet.

    `covered`, `empty`, and `in_progress` are all "not missing" — `in_progress`
    is excluded so a concurrent build doesn't double-research the same cell;
    it is not itself a terminal state, so a crashed fill just leaves it
    in_progress and a later build will not retry it either. That trade favors
    never double-billing a Gemini research call over self-healing a crash;
    the ledger row is small enough to reset by hand if that ever matters.
    """
    if not jurisdiction_ids or not categories:
        return []
    rows = await conn.fetch(
        """
        SELECT jurisdiction_id, category FROM jurisdiction_vertical_coverage
        WHERE jurisdiction_id = ANY($1::uuid[]) AND industry_tag = $2
          AND category = ANY($3::text[])
          AND status IN ('covered', 'empty', 'in_progress')
        """,
        jurisdiction_ids, industry_tag, categories,
    )
    resolved = {(r["jurisdiction_id"], r["category"]) for r in rows}
    cells = [
        (jid, cat)
        for jid in jurisdiction_ids
        for cat in categories
        if (jid, cat) not in resolved
    ]
    return cells[:MAX_CELLS_PER_FILL]


async def _mark(
    conn, jurisdiction_id: UUID, industry_tag: str, category: str,
    status: str, requested_by_company_id: UUID,
    requirements_written: int = 0, error: Optional[str] = None,
) -> None:
    await conn.execute(
        """
        INSERT INTO jurisdiction_vertical_coverage
            (jurisdiction_id, industry_tag, category, status,
             requirements_written, error, requested_by_company_id, updated_at)
        VALUES ($1,$2,$3,$4,$5,$6,$7, NOW())
        ON CONFLICT (jurisdiction_id, industry_tag, category) DO UPDATE SET
            status = EXCLUDED.status,
            requirements_written = EXCLUDED.requirements_written,
            error = EXCLUDED.error,
            requested_by_company_id = EXCLUDED.requested_by_company_id,
            updated_at = NOW()
        """,
        jurisdiction_id, industry_tag, category, status,
        requirements_written, error, requested_by_company_id,
    )


async def _category_briefs(conn, categories: List[str]) -> Dict[str, str]:
    """slug -> the description discovery wrote for it.

    The per-category research prompt is built from the category SLUG plus a
    `RESEARCH_PROMPTS` entry — and a runtime-discovered category has no entry
    there, so without this the model researches `dental_radiology_safety` off
    the words in the slug alone.
    """
    rows = await conn.fetch(
        """
        SELECT slug, name, description FROM compliance_categories
        WHERE slug = ANY($1::text[])
        """,
        categories,
    )
    return {
        r["slug"]: f"{r['name']}: {r['description']}" if r["description"] else r["name"]
        for r in rows
    }


async def _dedupe_by_regulation_key(conn, jurisdiction_id: UUID, industry_tag: str) -> int:
    """Collapse one obligation filed under two categories into one row.

    `requirement_key` is `<category>:<regulation_key>`, so the CATEGORY is part
    of an obligation's identity. A broad category researched alongside a narrow
    one therefore stores the same statute twice — the CA dental fill returned
    "Dental Sedation and Anesthesia Permit Requirements" under both
    `dental_sedation_anesthesia` and the catch-all `dental_practice_act_scope`,
    and the tenant saw each dental obligation listed twice on their tab.

    `regulation_key` is the stable identifier for the statute itself and is
    category-independent, so a collision on it inside one (jurisdiction,
    industry) IS the same obligation. Keep the oldest row (it is the one other
    tables may already reference) and drop the rest. FKs are ON DELETE CASCADE /
    SET NULL, and the tenant projection is rebuilt from the catalog immediately
    after, so nothing is stranded.

    Collapses on regulation_key OR on normalized title. Both are needed:
    `regulation_key` is MODEL-GENERATED, so a re-research of the same statute can
    name it `ca_dental_infection_control` one run and
    `ca_dental_infection_control_standard` the next — a key collision misses that,
    but the title is identical. Conversely two rows can share a key with different
    titles. Either match, inside one (jurisdiction, industry), is the same
    obligation.

    The prompt-side guard (sibling exclusion, below) is what should keep this
    from happening; this is the deterministic backstop for when the model
    ignores it.
    """
    dupes = await conn.fetch(
        """
        SELECT id FROM (
            SELECT id, ROW_NUMBER() OVER (
                PARTITION BY COALESCE(regulation_key, '~key~' || id::text)
                ORDER BY created_at, id
            ) AS rn_key,
            ROW_NUMBER() OVER (
                PARTITION BY lower(btrim(title)) ORDER BY created_at, id
            ) AS rn_title
            FROM jurisdiction_requirements
            WHERE jurisdiction_id = $1
              AND applicable_industries @> ARRAY[$2::text]
              AND status = 'active'
        ) ranked
        WHERE rn_key > 1 OR rn_title > 1
        """,
        jurisdiction_id, industry_tag,
    )
    if not dupes:
        return 0
    ids = [r["id"] for r in dupes]
    await conn.execute(
        "DELETE FROM compliance_requirements WHERE jurisdiction_requirement_id = ANY($1::uuid[])",
        ids,
    )
    await conn.execute(
        "DELETE FROM jurisdiction_requirements WHERE id = ANY($1::uuid[])", ids
    )
    logger.info(
        "vertical_coverage: deduped %d duplicate obligation(s) in %s/%s",
        len(ids), jurisdiction_id, industry_tag,
    )
    return len(ids)


async def fill(
    conn,
    company_id: UUID,
    cells: List[Tuple[UUID, str]],
    industry_tag: str,
    research_context: str,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Research each missing cell and record the ledger verdict.

    One cell = one (jurisdiction, category) research call, rather than one call
    per jurisdiction covering every category at once. That costs nothing extra —
    the underlying research is per-category-parallel either way — and buys two
    things a batched call cannot have: each category's prompt can name its OWN
    brief, and it can name its SIBLINGS so a broad category
    (`dental_practice_act_scope`) is told not to return the obligations a narrow
    one (`dental_sedation_anesthesia`) already owns.
    """
    from .compliance_service import research_specialization_for_jurisdiction
    from .scope_registry.research_loop import corpus_for_jurisdiction

    by_jurisdiction: Dict[UUID, List[str]] = {}
    for jid, cat in cells:
        by_jurisdiction.setdefault(jid, []).append(cat)

    briefs = await _category_briefs(conn, sorted({c for _, c in cells}))

    for jid, cats in by_jurisdiction.items():
        j_new = 0
        j_failed: List[str] = []

        for cat in cats:
            await _mark(conn, jid, industry_tag, cat, "in_progress", company_id)

            siblings = [c for c in cats if c != cat]
            context = research_context
            if briefs.get(cat):
                context += f"\n\nTHIS CATEGORY ({cat}) COVERS: {briefs[cat]}"
            if siblings:
                sib = "; ".join(f"{s} ({briefs.get(s, s)})" for s in siblings)
                context += (
                    f"\n\nSCOPE LIMIT — return ONLY obligations whose primary subject is "
                    f"'{cat}'. These sibling categories are researched by their own "
                    f"separate calls and their obligations MUST NOT be repeated here: {sib}."
                )

            try:
                corpus, citation_index = await corpus_for_jurisdiction(conn, jid, [cat])
            except Exception:
                logger.exception("vertical_coverage: corpus lookup failed for %s/%s", jid, cat)
                corpus, citation_index = "", {}

            try:
                result = await research_specialization_for_jurisdiction(
                    conn, jid, [cat], industry_tag,
                    industry_context=context,
                    skip_existing=False,
                    grounded_corpus=corpus,
                    citation_index=citation_index,
                )
            except Exception as exc:
                logger.exception("vertical_coverage: research failed for %s/%s", jid, cat)
                await _mark(conn, jid, industry_tag, cat, "failed", company_id, error=str(exc))
                j_failed.append(cat)
                continue

            if cat in set(result.get("failed") or []):
                await _mark(conn, jid, industry_tag, cat, "failed", company_id,
                            error="research pass errored")
                j_failed.append(cat)
                continue

            n = len(result.get("requirements") or [])
            j_new += n
            await _mark(conn, jid, industry_tag, cat,
                        "covered" if n > 0 else "empty", company_id,
                        requirements_written=n)

        deduped = await _dedupe_by_regulation_key(conn, jid, industry_tag)

        yield {
            "jurisdiction_id": str(jid),
            "categories": cats,
            "new": max(0, j_new - deduped),
            "deduped": deduped,
            "failed": sorted(j_failed),
        }


async def reproject_location(conn, company_id: UUID, location_id: UUID) -> int:
    """Re-sync a location's tab from the catalog after a vertical fill.

    Same projection `run_compliance_check_stream` runs after every research
    pass; called again here because the fill above wrote catalog rows after
    that location's own build already ran.
    """
    from .compliance_service import (
        _project_chain_to_location, _sync_requirements_to_location,
    )
    from ..models.compliance import BusinessLocation

    row = await conn.fetchrow(
        "SELECT * FROM business_locations WHERE id = $1 AND company_id = $2",
        location_id, company_id,
    )
    if not row or not row["jurisdiction_id"]:
        return 0

    location = BusinessLocation(**dict(row))
    requirements = await _project_chain_to_location(
        conn, company_id, location, row["jurisdiction_id"]
    )
    if not requirements:
        return 0
    sync_result = await _sync_requirements_to_location(
        conn, location_id, company_id, requirements
    )
    return sync_result.get("new", 0) + sync_result.get("updated", 0)
