"""Ingest authority indexes and their enumerated items into the scope registry.

Federal parts come from the official eCFR structure API (enumerable); California
slices come from the hand-curated `curated_ca` tables (not enumerable). Both
land in `authority_indexes` + `authority_index_items`; classification
(`authority_item_classifications`) is commit 4, so after ingest every item is
`unclassified` and `unclassified_count == item_count`.

Reuses `government_apis/ecfr.py` for the *fetch* (`_fetch_title_dates`,
`_fetch_part_structure`, `_fetch_part_versions`) and `authority_parse` for the
item-emitting walk (the ecfr module's own `_parse_structure` only counts).

Idempotent: items upsert on `UNIQUE(authority_index_id, citation)`; a re-run
updates headings/urls and re-links parents without duplicating. Orphan removal
(an item that vanishes upstream) is deferred to the commit-4 sync — deleting one
would cascade a classification that does not exist yet.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Dict, List, Optional

import httpx

from app.core.services.government_apis._base import _ECFR_BASE, _TIMEOUT
from app.core.services.government_apis.ecfr import (
    _fetch_part_structure,
    _fetch_part_versions,
    _fetch_title_dates,
)
from .authority_parse import parse_ecfr_items
from .authority_sources import (
    CURATED_INDEXES,
    FEDERAL_ECFR_PARTS,
    CuratedIndexSpec,
    FederalPart,
    curated_index_by_slug,
    federal_part_by_slug,
)
from .curated_ca import CURATED_ROWS
from .curated_us import CURATED_US_ROWS

# Curated rows live in two modules (CA + the US federal labor baseline). Merged here,
# at the single consumption point, so curated_us can import CuratedRow from curated_ca
# without an import cycle.
_ALL_CURATED_ROWS = {**CURATED_ROWS, **CURATED_US_ROWS}
from .models import IngestResult

logger = logging.getLogger(__name__)


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


async def _resolve_jurisdiction_id(conn, spec: Dict[str, str]) -> Optional[str]:
    """Resolve a curated index's jurisdiction spec to a jurisdictions.id.

    City rows store ``city`` lowercased (database.py). A missing row is an
    error for a *curated* index — it must attach somewhere — so raise rather
    than silently ingesting a stateless index.
    """
    level = spec.get("level")
    state = spec.get("state")
    city = spec.get("city")
    if city:
        row = await conn.fetchrow(
            "SELECT id FROM jurisdictions "
            "WHERE LOWER(city) = LOWER($1) AND state = $2 AND level = 'city' "
            "LIMIT 1",
            city, state,
        )
    else:
        # country_code tolerant of NULL: rows created before the country_code
        # migration may not be backfilled, and a US state row is US either way.
        row = await conn.fetchrow(
            "SELECT id FROM jurisdictions "
            "WHERE state = $1 AND level = $2 "
            "AND (country_code = 'US' OR country_code IS NULL) "
            "AND city IS NULL LIMIT 1",
            state, level,
        )
    if row is None:
        raise ValueError(
            f"no jurisdictions row for curated index spec {spec!r} — "
            "seed the jurisdiction before ingesting its authority index"
        )
    return str(row["id"])


async def _upsert_index(
    conn,
    *,
    slug: str,
    name: str,
    level: str,
    jurisdiction_id: Optional[str],
    source_type: str,
    domain_categories: List[str],
    domain_excludes: List[str],
    enumerable: bool,
) -> str:
    """Insert-or-update the authority_indexes row; return its id."""
    # last_ingested_at is deliberately NOT stamped here — it's the ingest's
    # commit marker, written by _recount as the final step so a torn run never
    # looks fresh (the scheduled sweep keys on it to decline re-crawls).
    row = await conn.fetchrow(
        """
        INSERT INTO authority_indexes
            (slug, name, level, jurisdiction_id, source_type,
             domain_categories, domain_excludes, enumerable)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        ON CONFLICT (slug) DO UPDATE SET
            name = EXCLUDED.name,
            level = EXCLUDED.level,
            jurisdiction_id = EXCLUDED.jurisdiction_id,
            source_type = EXCLUDED.source_type,
            domain_categories = EXCLUDED.domain_categories,
            domain_excludes = EXCLUDED.domain_excludes,
            enumerable = EXCLUDED.enumerable
        RETURNING id
        """,
        slug, name, level, jurisdiction_id, source_type,
        domain_categories, domain_excludes, enumerable,
    )
    return str(row["id"])


async def _upsert_items(conn, index_id: str, items: List[dict]) -> int:
    """Upsert items, then resolve parent_item_id from parent_citation.

    Two passes: rows first via executemany (so every parent exists before
    linking), then one set-based UPDATE maps each child's parent_citation to
    the parent's id within the same index. Returns the count upserted.
    """
    if not items:
        return 0

    await conn.executemany(
        """
        INSERT INTO authority_index_items
            (authority_index_id, citation, heading, hierarchy,
             source_url, amendment_date)
        VALUES ($1, $2, $3, $4::jsonb, $5, $6)
        ON CONFLICT (authority_index_id, citation) DO UPDATE SET
            heading = EXCLUDED.heading,
            hierarchy = EXCLUDED.hierarchy,
            source_url = EXCLUDED.source_url,
            amendment_date = EXCLUDED.amendment_date
        """,
        [
            (
                index_id,
                it["citation"],
                it.get("heading"),
                json.dumps(it.get("hierarchy") or {}),
                it.get("source_url"),
                it.get("amendment_date"),
            )
            for it in items
        ],
    )

    # parent_citation is a parse artifact, not a column — resolve it to
    # parent_item_id now that every row exists. One set-based UPDATE over the
    # (child, parent) citation pairs.
    pairs = [
        (it["citation"], it["parent_citation"])
        for it in items
        if it.get("parent_citation")
    ]
    if pairs:
        await conn.execute(
            """
            UPDATE authority_index_items child
            SET parent_item_id = parent.id
            FROM unnest($2::text[], $3::text[]) AS link(child_citation, parent_citation)
            JOIN authority_index_items parent
              ON parent.authority_index_id = $1
             AND parent.citation = link.parent_citation
            WHERE child.authority_index_id = $1
              AND child.citation = link.child_citation
            """,
            index_id,
            [p[0] for p in pairs],
            [p[1] for p in pairs],
        )
    return len(items)


def diff_authority_items(
    prior: List[dict], items: List[dict]
) -> List[tuple]:
    """Pure diff of freshly-parsed items against the prior snapshot.

    ``prior`` rows expose ``citation`` / ``heading`` / ``amendment_date`` (dict or
    asyncpg Record — both index by key). ``items`` are the parse dicts. Returns a
    list of ``(change_type, citation, heading, old_amendment_date,
    new_amendment_date)`` tuples:

      * new      — citation not previously present
      * amended  — citation present but its HEADING changed (a real per-section
                   structural signal)
      * removed  — citation previously present, absent from the new parse

    ``amendment_date`` is deliberately NOT an amended trigger: eCFR's versions API
    is part-granular, so the ingest stamps the SAME part-level date on every
    section — any part republish would then flag hundreds of unchanged sections as
    "amended" and drown the review queue. The old/new dates are still recorded on
    the row for context; they just don't, alone, constitute drift. (Section text
    changes aren't visible to a structure-based ingest regardless — that's what
    the statute-body layer is for.)

    An index's FIRST ingest has no baseline (``prior`` empty) — every item would
    read as "new", which is noise not drift — so an empty prior yields an empty
    diff. No I/O: unit-tested directly.
    """
    if not prior:
        return []

    prior_by_cite = {r["citation"]: r for r in prior}
    new_cites = {it["citation"] for it in items}

    drift: List[tuple] = []
    for it in items:
        cite = it["citation"]
        old = prior_by_cite.get(cite)
        if old is None:
            drift.append(("new", cite, it.get("heading"), None, it.get("amendment_date")))
            continue
        if (old["heading"] or "") != (it.get("heading") or ""):
            drift.append(
                ("amended", cite, it.get("heading"), old["amendment_date"], it.get("amendment_date"))
            )
    for cite, old in prior_by_cite.items():
        if cite not in new_cites:
            drift.append(("removed", cite, old["heading"], old["amendment_date"], None))
    return drift


async def _record_drift(conn, index_id: str, items: List[dict]) -> tuple[int, int, int]:
    """Diff freshly-parsed items against the index's prior state and log drift.

    Must run INSIDE the ingest transaction, BEFORE `_upsert_items` — it reads the
    pre-upsert `authority_index_items` snapshot as the baseline. Records one
    `authority_index_drift` row per change (a removed citation is recorded only —
    the item is NOT deleted; orphan removal stays deferred, matching
    `_upsert_items`' idempotent upsert). Returns (new, amended, removed).

    Because the orphaned item row persists, every LATER ingest would re-diff it
    as removed and re-log the same drift row forever ('new'/'amended' converge
    via the upsert; 'removed' alone doesn't). So a removal is only logged when
    the citation's LATEST drift row isn't already 'removed' — latest-row, not
    mere existence, so a remove → re-add ('new') → remove again still logs.
    """
    prior = await conn.fetch(
        "SELECT citation, heading, amendment_date "
        "FROM authority_index_items WHERE authority_index_id = $1",
        index_id,
    )
    drift_rows = diff_authority_items(prior, items)

    removed_cites = [row[1] for row in drift_rows if row[0] == "removed"]
    if removed_cites:
        latest = await conn.fetch(
            """
            SELECT DISTINCT ON (citation) citation, change_type
            FROM authority_index_drift
            WHERE authority_index_id = $1 AND citation = ANY($2::text[])
            ORDER BY citation, detected_at DESC
            """,
            index_id, removed_cites,
        )
        already_removed = {r["citation"] for r in latest if r["change_type"] == "removed"}
        if already_removed:
            drift_rows = [
                row for row in drift_rows
                if not (row[0] == "removed" and row[1] in already_removed)
            ]

    if drift_rows:
        await conn.executemany(
            """
            INSERT INTO authority_index_drift
                (authority_index_id, change_type, citation, heading,
                 old_amendment_date, new_amendment_date)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            [(index_id, ct, cite, heading, od, nd) for (ct, cite, heading, od, nd) in drift_rows],
        )

    counts = {"new": 0, "amended": 0, "removed": 0}
    for ct, *_ in drift_rows:
        counts[ct] += 1
    return (counts["new"], counts["amended"], counts["removed"])


async def _recount(conn, index_id: str) -> tuple[int, int]:
    """Persist (item_count, unclassified_count) and stamp last_ingested_at.

    The timestamp is the ingest's commit marker — it lands only when the counts
    do, so a run that dies mid-upsert never reads as fresh.
    """
    item_count = await conn.fetchval(
        "SELECT COUNT(*) FROM authority_index_items WHERE authority_index_id = $1",
        index_id,
    )
    # Predicate MUST match classify._refresh_unclassified_count (confirmed-only):
    # this runs on every ingest, so an any-row predicate here would silently
    # revert the confirmed-only semantics the completeness gate depends on.
    unclassified = await conn.fetchval(
        """
        SELECT COUNT(*) FROM authority_index_items i
        LEFT JOIN authority_item_classifications c
            ON c.item_id = i.id AND c.status = 'confirmed'
        WHERE i.authority_index_id = $1 AND c.id IS NULL
        """,
        index_id,
    )
    await conn.execute(
        "UPDATE authority_indexes SET item_count = $1, unclassified_count = $2, "
        "last_ingested_at = NOW() WHERE id = $3",
        item_count, unclassified, index_id,
    )
    return int(item_count), int(unclassified)


async def ingest_ecfr_index(
    conn, part: FederalPart, client: Optional[httpx.AsyncClient] = None
) -> IngestResult:
    """Fetch, parse, and upsert one federal eCFR part (jurisdiction_id NULL)."""
    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(timeout=_TIMEOUT)
    try:
        title_dates = await _fetch_title_dates(client)
        issue_date = title_dates.get(part.title)
        if not issue_date:
            raise ValueError(f"no eCFR issue date for title {part.title}")

        structure = await _fetch_part_structure(client, part.title, part.part, issue_date)
        if not structure:
            raise ValueError(
                f"eCFR structure fetch returned nothing for {part.title} CFR {part.part}"
            )
        amendment = _parse_date(await _fetch_part_versions(client, part.title, part.part))
    finally:
        if owns_client:
            await client.aclose()

    items = parse_ecfr_items(structure, part.title, part.part)
    for it in items:  # part-level amendment date (eCFR versions API is part-granular)
        it["amendment_date"] = amendment

    # All writes in one transaction: a mid-ingest failure rolls back rather
    # than leaving a torn index (fetch/parse stay outside — no locks held
    # while waiting on a .gov host).
    async with conn.transaction():
        index_id = await _upsert_index(
            conn,
            slug=part.slug,
            name=part.name,
            level=part.level,
            jurisdiction_id=None,
            source_type="ecfr",
            domain_categories=part.domain_categories,
            domain_excludes=part.domain_excludes,
            enumerable=True,
        )
        new_c, amended_c, removed_c = await _record_drift(conn, index_id, items)
        upserted = await _upsert_items(conn, index_id, items)
        item_count, unclassified = await _recount(conn, index_id)
    logger.info(
        "ingested %s: %d items (%d unclassified); drift +%d ~%d -%d",
        part.slug, item_count, unclassified, new_c, amended_c, removed_c,
    )
    return IngestResult(
        slug=part.slug, source_type="ecfr", items_upserted=upserted,
        item_count=item_count, unclassified_count=unclassified, enumerable=True,
        new_count=new_c, amended_count=amended_c, removed_count=removed_c,
    )


async def ingest_curated_index(conn, spec: CuratedIndexSpec) -> IngestResult:
    """Upsert a curated index and its hand-authored rows (enumerable=false).

    A curated index is usually state/local (resolves a jurisdiction row), but a
    federal curated index (e.g. the FLSA statute, which isn't in eCFR) has NULL
    jurisdiction — same as the federal eCFR parts.
    """
    rows = _ALL_CURATED_ROWS.get(spec.slug, [])
    jurisdiction_id = (
        None if spec.level == "federal"
        else await _resolve_jurisdiction_id(conn, spec.jurisdiction)
    )

    items = [
        {
            "citation": r["citation"],
            "heading": r["heading"],
            "hierarchy": r["hierarchy"],
            "parent_citation": None,  # curated rows are flat
            "source_url": r["source_url"],
            "amendment_date": None,
        }
        for r in rows
    ]
    async with conn.transaction():
        index_id = await _upsert_index(
            conn,
            slug=spec.slug,
            name=spec.name,
            level=spec.level,
            jurisdiction_id=jurisdiction_id,
            source_type="curated",
            domain_categories=spec.domain_categories,
            domain_excludes=spec.domain_excludes,
            enumerable=False,
        )
        new_c, amended_c, removed_c = await _record_drift(conn, index_id, items)
        upserted = await _upsert_items(conn, index_id, items)
        item_count, unclassified = await _recount(conn, index_id)
    logger.info(
        "ingested curated %s: %d items (%d unclassified); drift +%d ~%d -%d",
        spec.slug, item_count, unclassified, new_c, amended_c, removed_c,
    )
    return IngestResult(
        slug=spec.slug, source_type="curated", items_upserted=upserted,
        item_count=item_count, unclassified_count=unclassified, enumerable=False,
        new_count=new_c, amended_count=amended_c, removed_count=removed_c,
    )


async def ingest_by_slug(conn, slug: str) -> IngestResult:
    """Dispatch a single index by slug (federal or curated)."""
    fed = federal_part_by_slug(slug)
    if fed is not None:
        return await ingest_ecfr_index(conn, fed)
    cur = curated_index_by_slug(slug)
    if cur is not None:
        return await ingest_curated_index(conn, cur)
    raise ValueError(f"unknown authority index slug: {slug!r}")


async def ingest_all(conn) -> tuple[List[IngestResult], List[dict]]:
    """Ingest every catalog index. One shared httpx client for the federal parts.

    Returns ``(results, failures)`` — a failed index must surface in the task
    result, not just a server-side log line, or a partial sweep reads as
    "covered everything".
    """
    results: List[IngestResult] = []
    failures: List[dict] = []
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        for part in FEDERAL_ECFR_PARTS:
            try:
                results.append(await ingest_ecfr_index(conn, part, client=client))
            except Exception as exc:
                logger.warning("federal ingest failed for %s: %s", part.slug, exc)
                failures.append({"slug": part.slug, "error": str(exc)})
    for spec in CURATED_INDEXES:
        try:
            results.append(await ingest_curated_index(conn, spec))
        except Exception as exc:
            logger.warning("curated ingest failed for %s: %s", spec.slug, exc)
            failures.append({"slug": spec.slug, "error": str(exc)})
    return results, failures
