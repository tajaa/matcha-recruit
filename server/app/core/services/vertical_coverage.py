"""Tenant-triggered vertical (industry) coverage.

A tenant on a mapped jurisdiction chain still sees nothing industry-specific for
a vertical nobody has researched yet — a dental office in Los Angeles gets zero
dental rows because "dental" was never scoped or researched, not because the
reachability machinery is broken (that was fixed separately: jparent01,
jsonfix01, the chain-union projection).

The catalog is tenant-independent: a company merely TRIGGERS a fill. The result —
categories in `compliance_categories`, requirements in `jurisdiction_requirements`,
both tagged with the industry_tag — is shared, so every later company in that
jurisdiction reads it with zero Gemini calls. This module is the trigger + the
memory that makes that convergence real:

  1. `resolve_vertical`   — which vertical does this company need scoped?
  2. `ensure_specialty`   — does it have categories yet? If not, discover + confirm.
  3. `chains_for_leaves`  — each location's chain, federal → state → county → city.
  4. `backfill_ledger`    — mark cells the catalog ALREADY covers as covered.
  5. `plan_fill`          — one research CALL per (leaf, category), covering every
                            missing chain cell that call can reach.
  6. `fill`               — run the plan, route writes by stamped level, record
                            each cell's verdict from what actually LANDED.

THE SHAPE OF A CELL, and why the calls don't mirror it: the ledger cell is
(chain node, category) — the federal node, the state node — never the tenant's
leaf. Keyed on the leaf, federal law would be re-researched once per city, and a
San Francisco dental office could never read the California rows Los Angeles
paid for (the chain walk only finds rows on its own ancestors). But the research
CALL is per (leaf, category): one call returns the federal, state, county and
city obligations together, `route_by_level` files each row on the node its
stamped level belongs to, and every reachable cell is marked from the outcome.
One call per category also can't disagree with itself — the four-calls-per-
category variant had each level's pass re-volunteering the same state statute
under a different title, which no deterministic dedupe could collapse.

THE LEDGER RECORDS WHAT LANDED, NOT WHAT WAS RETURNED. Routing can skip a row it
cannot place; counting skipped rows as written marks a hole in the catalog as
"covered" — a terminal status, so the hole would be permanent and invisible.
Verdicts are read from `written_by_level`.

`empty` and `failed` are deliberately different statuses: an empty cell (we
researched, there is genuinely nothing) must never retry; a failed one should.
That distinction is what `research_specialization_for_jurisdiction`'s own
`skip_existing` check — which infers coverage from "are there rows already" —
structurally cannot express.

Honest limitation: each research call pins one pool connection for its full
duration (the research function reads context and writes results on it), so a
cold fill occupies a pool slot for most of its wall-clock. The per-call
connection scope bounds that pinning per call and lets other work interleave
between calls; it does not eliminate it.
"""
from __future__ import annotations

import logging
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple
from uuid import UUID

from . import industry_specialties

logger = logging.getLogger(__name__)

# One build must not kick off an unbounded research run. The cap is on research
# CALLS (one per (leaf, category) with missing cells); what doesn't fit is
# REPORTED, never silently dropped, and is picked up by the next build (the
# ledger has no verdict for a deferred cell).
MAX_CALLS_PER_FILL = 12

# The levels a chain node OWNS in the ledger. 'federal' and 'national' are one
# tier (a country's own law) under two names.
_LEVELS_OWNED_BY: Dict[str, set] = {
    "federal": {"federal", "national"},
    "national": {"federal", "national"},
    "state": {"state"},
    "county": {"county"},
    "city": {"city"},
}

# Facility inference (`infer_facility_profile`) constrains entity_type to a
# CLOSED ENUM — this maps each enum value to the specialty slug it corresponds
# to, or None when the value is a facility SHAPE rather than a vertical
# (hospital, clinic, fqhc — those are what TRIGGER_PROFILES and trigger
# conditions are for, not industry scoping). Free-text or unknown values map to
# nothing: inference must never MINT a specialty — a hallucinated or
# company-name-shaped entity_type would create a whole disjoint ledger
# namespace and a Gemini discovery run for a vertical that doesn't exist.
# Signup is the only place a new specialty enters the vocabulary.
_ENTITY_TYPE_SPECIALTY: Dict[str, Optional[str]] = {
    "dental": "dental",
    "pharmacy": "pharmacy",
    "behavioral_health": "behavioral_health",
    "home_health": "home_health",
    "hospice": "hospice",
    "dialysis_center": "dialysis",
    "hospital": None,
    "critical_access_hospital": None,
    "clinic": None,
    "fqhc": None,
    "nursing_facility": None,
    "ambulatory_surgery_center": None,
    "lab": None,
    "other": None,
}


def _specialty_from_entity_type(entity_type: Optional[str]) -> Optional[str]:
    slug = industry_specialties.slugify(entity_type or "")
    if not slug:
        return None
    return _ENTITY_TYPE_SPECIALTY.get(slug)


async def resolve_vertical(
    conn, company_id: UUID
) -> Optional[Tuple[str, str, str, str, bool]]:
    """The vertical this company should be scoped against.

    Returns (parent_industry, slug, label, industry_tag, minted_now), or None
    only when the company's industry can't be resolved at all. ``minted_now`` is
    True when this call just persisted an inferred specialty onto the company —
    the caller must reproject the company's locations even if the ledger says
    everything is covered, because every projection made BEFORE this write
    filtered the vertical's rows out (the industry filter reads the company's
    own tag set).

    Three sources, most specific first:

    1. An explicit sub-specialty on the company (`healthcare:dental` — set at
       Matcha-X / Matcha Compliance signup, surfaced by
       `_get_company_industry_tags`).
    2. For healthcare with no specialty: the `facility_attributes.entity_type`
       the facility-inference pass in `run_compliance_check_stream` already
       detects and then drops on the floor — mapped through the closed
       `_ENTITY_TYPE_SPECIALTY` vocabulary, never slugified free text.
       Persisted onto the company so it becomes durable and so
       `_filter_requirements_for_company` can match the rows this module goes
       on to research.
    3. Otherwise the industry ITSELF is the vertical. A hospitality employer has
       no sub-specialty above hospitality; `industry_tag()` collapses
       (hospitality, hospitality) to the bare tag `hospitality`, which is what
       `_get_company_industry_tags` gives such a company.
    """
    from .compliance_service import _get_company_industry_tags, _resolve_industry

    tags = await _get_company_industry_tags(conn, company_id)
    specific = sorted(t for t in tags if ":" in t)
    if specific:
        tag = specific[0]
        parent, slug = tag.split(":", 1)
        return parent, slug, industry_specialties.label_from_slug(slug), tag, False

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
        entity_type = (fa or {}).get("entity_type") if isinstance(fa, dict) else None
        slug = _specialty_from_entity_type(entity_type)
        if slug:
            result = await conn.execute(
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
            minted = result == "UPDATE 1"
            return (
                "healthcare", slug,
                industry_specialties.label_from_slug(slug),
                industry_specialties.industry_tag("healthcare", slug),
                minted,
            )

    return (
        canonical, canonical,
        industry_specialties.label_from_slug(canonical),
        industry_specialties.industry_tag(canonical, canonical),
        False,
    )


async def ensure_specialty(
    conn, parent_industry: str, slug: str, label: str
) -> Tuple[List[str], str]:
    """Categories + research context for this vertical, discovering them if new.

    Returns ([], "") if discovery fails or yields nothing — callers must treat
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


async def chains_for_leaves(
    conn, leaf_ids: List[UUID]
) -> Dict[UUID, List[Tuple[UUID, str]]]:
    """leaf id -> its chain nodes as (jurisdiction_id, level), broadest first.

    The ledger's cells live on chain nodes, so a fill must know which nodes each
    leaf's research call can reach. Broadest-first, so shared cells (federal,
    state) are claimed by the first leaf and later leaves only pay for their own
    county/city delta.
    """
    if not leaf_ids:
        return {}
    rows = await conn.fetch(
        """
        WITH RECURSIVE chain AS (
            SELECT id AS leaf_id, id, parent_id, 0 AS depth
            FROM jurisdictions WHERE id = ANY($1::uuid[])
            UNION ALL
            SELECT c.leaf_id, j.id, j.parent_id, c.depth + 1
            FROM jurisdictions j
            JOIN chain c ON j.id = c.parent_id
            WHERE c.depth < 8
        )
        SELECT DISTINCT c.leaf_id, j.id, j.level
        FROM jurisdictions j JOIN chain c ON c.id = j.id
        """,
        leaf_ids,
    )
    order = {"federal": 0, "national": 0, "state": 1, "county": 2, "city": 3}
    chains: Dict[UUID, List[Tuple[UUID, str]]] = {}
    for r in sorted(rows, key=lambda r: order.get(r["level"], 9)):
        if r["level"] in _LEVELS_OWNED_BY:
            chains.setdefault(r["leaf_id"], []).append((r["id"], r["level"]))
    return chains


async def backfill_ledger(
    conn, jurisdiction_ids: List[UUID], industry_tag: str, categories: List[str],
) -> int:
    """Mark cells the catalog ALREADY covers as covered, before anything is researched.

    Without this the ledger starts cold over verticals that are already populated.
    `healthcare` alone has seeded categories and 300+ rows — the next
    plain-healthcare tenant to onboard would re-research every one of them
    synchronously (`skip_existing=False`), paying for law the catalog already
    holds and minting duplicates wherever the model's regulation_key drifted.

    Coverage is judged on CATEGORY membership alone, not on the row's
    `applicable_industries` tag: the categories passed in are this vertical's own
    (selected from `compliance_categories` by industry_tag), so any active row in
    one of them covers the cell — including seeded rows that predate industry
    tagging, which a tag-containment check would miss and re-research.

    Only writes rows that do not exist: a real verdict from a previous fill
    (`empty`, `failed`) is never overwritten by an inferred one.
    """
    if not jurisdiction_ids or not categories:
        return 0
    result = await conn.execute(
        """
        INSERT INTO jurisdiction_vertical_coverage
            (jurisdiction_id, industry_tag, category, status, requirements_written)
        SELECT r.jurisdiction_id, $2, r.category, 'covered', COUNT(*)
        FROM jurisdiction_requirements r
        WHERE r.jurisdiction_id = ANY($1::uuid[])
          AND r.category = ANY($3::text[])
          AND r.status = 'active'
        GROUP BY r.jurisdiction_id, r.category
        ON CONFLICT (jurisdiction_id, industry_tag, category) DO NOTHING
        """,
        jurisdiction_ids, industry_tag, categories,
    )
    try:
        return int(str(result).split()[-1])
    except (ValueError, IndexError):
        return 0


async def plan_fill(
    conn,
    leaf_chains: Dict[UUID, List[Tuple[UUID, str]]],
    industry_tag: str,
    categories: List[str],
) -> Tuple[List[Tuple[UUID, str, List[Tuple[UUID, str]]]], int]:
    """(research calls to make, how many the cap deferred).

    Each entry is (leaf_id, category, [(node_id, level), ...]) — one research
    call at the leaf, covering that category's missing cells across the leaf's
    chain. A shared node (federal, state) is claimed by the first leaf that
    reaches it, so a two-city tenant pays federal and state once.

    `covered`, `empty` and `in_progress` cells are all "not missing".
    `in_progress` is excluded so a concurrent build doesn't double-research the
    same cell; a crashed fill therefore leaves the cell wedged rather than
    retried, which trades self-healing for never double-billing a research call
    (see the sweeper note in VERTICAL_COVERAGE_PLAN.md).

    The overflow count is RETURNED, not swallowed. Truncating silently reads to
    the caller as "we covered everything"; the deferred cells are picked up by
    the next build because the ledger has no verdict for them.
    """
    if not leaf_chains or not categories:
        return [], 0

    all_nodes = sorted({jid for chain in leaf_chains.values() for jid, _ in chain})
    rows = await conn.fetch(
        """
        SELECT jurisdiction_id, category FROM jurisdiction_vertical_coverage
        WHERE jurisdiction_id = ANY($1::uuid[]) AND industry_tag = $2
          AND category = ANY($3::text[])
          AND status IN ('covered', 'empty', 'in_progress')
        """,
        all_nodes, industry_tag, categories,
    )
    resolved = {(r["jurisdiction_id"], r["category"]) for r in rows}

    claimed: set = set()
    plan: List[Tuple[UUID, str, List[Tuple[UUID, str]]]] = []
    for leaf_id, chain in leaf_chains.items():
        for cat in categories:
            nodes = [
                (jid, level)
                for jid, level in chain
                if (jid, cat) not in resolved and (jid, cat) not in claimed
            ]
            if not nodes:
                continue
            claimed.update((jid, cat) for jid, _ in nodes)
            plan.append((leaf_id, cat, nodes))

    deferred = max(0, len(plan) - MAX_CALLS_PER_FILL)
    if deferred:
        logger.info(
            "vertical_coverage: %d research call(s) over the %d-call cap for %s — "
            "deferred to the next build (their cells hold no verdict, so they are picked up)",
            deferred, MAX_CALLS_PER_FILL, industry_tag,
        )
    return plan[:MAX_CALLS_PER_FILL], deferred


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
    there, so without this the model researches `dental_radiology_safety` off the
    words in the slug alone.
    """
    rows = await conn.fetch(
        "SELECT slug, name, description FROM compliance_categories WHERE slug = ANY($1::text[])",
        categories,
    )
    return {
        r["slug"]: f"{r['name']}: {r['description']}" if r["description"] else r["name"]
        for r in rows
    }


async def _dedupe_fill_rows(
    conn, jurisdiction_id: UUID, industry_tag: str, categories: List[str], cutoff,
) -> int:
    """Collapse duplicates THIS FILL introduced against what already existed.

    `requirement_key` is `<category>:<regulation_key>`, so the CATEGORY is part
    of an obligation's identity — a statute the model returns under two
    categories stores twice, and a re-research whose model-generated
    `regulation_key` drifted stores next to the original under a new key but the
    same title.

    Two match rules, deliberately different scopes:
      * same `regulation_key` ACROSS categories — the key is statute-derived, so
        a collision is the same obligation filed twice;
      * same normalized title WITHIN one category — across categories a generic
        title ("Recordkeeping Requirements") legitimately names distinct
        obligations, and collapsing those would delete real law.

    Only rows created at/after ``cutoff`` (the fill's start, read from the DB
    clock) are ever DELETED. The partition ranks against everything — so a new
    duplicate of an old row loses to it — but pre-existing rows are never
    removed: deleting catalog rows other tenants already project, from inside an
    unrelated tenant's onboarding, is how a shared catalog gets corrupted.
    Membership is by category, not tag containment, so an untagged legacy twin
    still wins over this fill's re-write of it.
    """
    dupes = await conn.fetch(
        """
        SELECT id FROM (
            SELECT id, created_at, ROW_NUMBER() OVER (
                PARTITION BY COALESCE(regulation_key, '~key~' || id::text)
                ORDER BY created_at, id
            ) AS rn_key,
            ROW_NUMBER() OVER (
                PARTITION BY category, lower(btrim(title)) ORDER BY created_at, id
            ) AS rn_title
            FROM jurisdiction_requirements
            WHERE jurisdiction_id = $1
              AND status = 'active'
              AND (applicable_industries @> ARRAY[$2::text] OR category = ANY($3::text[]))
        ) ranked
        WHERE (rn_key > 1 OR rn_title > 1) AND created_at >= $4
        """,
        jurisdiction_id, industry_tag, categories, cutoff,
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
    get_conn,
    company_id: UUID,
    plan: List[Tuple[UUID, str, List[Tuple[UUID, str]]]],
    industry_tag: str,
    research_context: str,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Run the research plan and record each cell's verdict.

    One research call per plan entry — the call happens AT THE LEAF so the
    prompt has a real place to research, `only_levels` is the union of the
    missing cells' levels, and `route_by_level=True` files each returned row on
    the node its stamped level belongs to. Cell verdicts come from
    ``written_by_level`` — what actually landed, never the pre-route count.

    Yields one event per plan entry: {leaf_id, category, nodes, new, deduped,
    failed}.
    """
    from .compliance_service import research_specialization_for_jurisdiction
    from .scope_registry.research_loop import corpus_for_jurisdiction

    all_categories = sorted({cat for _, cat, _ in plan})
    async with get_conn() as conn:
        briefs = await _category_briefs(conn, all_categories)
        # LOCALTIMESTAMP, not now(): jurisdiction_requirements.created_at is
        # `timestamp WITHOUT time zone`, and comparing it against a tz-aware
        # value raises "can't subtract offset-naive and offset-aware datetimes"
        # — which killed the whole dedupe pass. Read the clock from the DB (not
        # the app host) so the cutoff is in the same frame as the rows.
        fill_started_at = await conn.fetchval("SELECT LOCALTIMESTAMP")

    touched: set = set()

    for leaf_id, cat, nodes in plan:
        siblings = [c for c in all_categories if c != cat]
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

        owned_levels: set = set()
        for _, level in nodes:
            owned_levels |= _LEVELS_OWNED_BY.get(level, {level})

        new_count = 0
        failed = False
        try:
            async with get_conn() as conn:
                for jid, _ in nodes:
                    await _mark(conn, jid, industry_tag, cat, "in_progress", company_id)
                try:
                    corpus, citation_index = await corpus_for_jurisdiction(conn, leaf_id, [cat])
                except Exception:
                    logger.exception(
                        "vertical_coverage: corpus lookup failed for %s/%s", leaf_id, cat)
                    corpus, citation_index = "", {}

                result = await research_specialization_for_jurisdiction(
                    conn, leaf_id, [cat], industry_tag,
                    industry_context=context,
                    skip_existing=False,
                    grounded_corpus=corpus,
                    citation_index=citation_index,
                    route_by_level=True,
                    only_levels=owned_levels,
                )

                # Verdicts on the SAME connection, immediately: a fresh acquire
                # here could fail (pool pressure) after a paid, successful
                # research call, stranding the cells at in_progress — which is
                # terminal-by-policy and has no sweeper.
                if cat in set(result.get("failed") or []):
                    failed = True
                    for jid, _ in nodes:
                        await _mark(conn, jid, industry_tag, cat, "failed", company_id,
                                    error="research pass errored")
                else:
                    written = result.get("written_by_level") or {}
                    for jid, level in nodes:
                        n = sum(written.get(lv, 0) for lv in _LEVELS_OWNED_BY.get(level, {level}))
                        new_count += n
                        await _mark(conn, jid, industry_tag, cat,
                                    "covered" if n > 0 else "empty", company_id,
                                    requirements_written=n)
                    touched.update(result.get("jurisdictions_written") or set())
        except Exception as exc:
            logger.exception("vertical_coverage: research failed for %s/%s", leaf_id, cat)
            failed = True
            try:
                async with get_conn() as conn:
                    for jid, _ in nodes:
                        await _mark(conn, jid, industry_tag, cat, "failed", company_id,
                                    error=str(exc))
            except Exception:
                logger.exception(
                    "vertical_coverage: could not record failure for %s/%s — cells "
                    "remain in_progress", leaf_id, cat)

        yield {
            "leaf_id": str(leaf_id),
            "category": cat,
            "nodes": len(nodes),
            "new": new_count,
            "deduped": 0,
            "failed": [cat] if failed else [],
        }

    # Dedupe is cleanup that runs AFTER the rows are written and the ledger is
    # recorded. It must never take the fill down with it: a failure here would
    # otherwise discard a completed, paid-for research pass and skip the
    # tenant's reprojection.
    deduped_total = 0
    if touched:
        try:
            async with get_conn() as conn:
                for jid in touched:
                    deduped_total += await _dedupe_fill_rows(
                        conn, jid, industry_tag, all_categories, fill_started_at
                    )
        except Exception:
            logger.exception(
                "vertical_coverage: dedupe pass failed for %s — rows are written and "
                "the ledger is recorded; duplicates may remain", industry_tag)
    if deduped_total:
        yield {"leaf_id": None, "category": None, "nodes": 0,
               "new": -deduped_total, "deduped": deduped_total, "failed": []}


async def reproject_location(conn, company_id: UUID, location_id: UUID) -> int:
    """Re-sync a location's tab from the catalog after a vertical fill.

    Same projection `run_compliance_check_stream` runs after every research pass;
    called again here because the fill above wrote catalog rows after that
    location's own build already ran.
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
