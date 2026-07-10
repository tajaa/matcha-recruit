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
        row = await conn.fetchrow(
            "SELECT id FROM jurisdictions "
            "WHERE state = $1 AND level = $2 AND country_code = 'US' "
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
    row = await conn.fetchrow(
        """
        INSERT INTO authority_indexes
            (slug, name, level, jurisdiction_id, source_type,
             domain_categories, domain_excludes, enumerable, last_ingested_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
        ON CONFLICT (slug) DO UPDATE SET
            name = EXCLUDED.name,
            level = EXCLUDED.level,
            jurisdiction_id = EXCLUDED.jurisdiction_id,
            source_type = EXCLUDED.source_type,
            domain_categories = EXCLUDED.domain_categories,
            domain_excludes = EXCLUDED.domain_excludes,
            enumerable = EXCLUDED.enumerable,
            last_ingested_at = NOW()
        RETURNING id
        """,
        slug, name, level, jurisdiction_id, source_type,
        domain_categories, domain_excludes, enumerable,
    )
    return str(row["id"])


async def _upsert_items(conn, index_id: str, items: List[dict]) -> int:
    """Upsert items, then resolve parent_item_id from parent_citation.

    Two passes: rows first (so every parent exists before linking), then a
    single UPDATE join maps each child's parent_citation to the parent's id
    within the same index. Returns the count upserted.
    """
    if not items:
        return 0

    for it in items:
        await conn.execute(
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
            index_id,
            it["citation"],
            it.get("heading"),
            json.dumps(it.get("hierarchy") or {}),
            it.get("source_url"),
            it.get("amendment_date"),
        )

    # parent_citation is a parse artifact, not a column — resolve it to
    # parent_item_id now that every row exists.
    await _link_parents(conn, index_id, items)
    return len(items)


async def _link_parents(conn, index_id: str, items: List[dict]) -> None:
    """Resolve parent_item_id for items whose parse carried a parent_citation."""
    id_by_citation = {
        r["citation"]: r["id"]
        for r in await conn.fetch(
            "SELECT id, citation FROM authority_index_items WHERE authority_index_id = $1",
            index_id,
        )
    }
    for it in items:
        parent_citation = it.get("parent_citation")
        if not parent_citation:
            continue
        parent_id = id_by_citation.get(parent_citation)
        if parent_id is None:
            continue
        await conn.execute(
            "UPDATE authority_index_items SET parent_item_id = $1 "
            "WHERE authority_index_id = $2 AND citation = $3",
            parent_id, index_id, it["citation"],
        )


async def _recount(conn, index_id: str) -> tuple[int, int]:
    """Return (item_count, unclassified_count) and persist them on the index."""
    item_count = await conn.fetchval(
        "SELECT COUNT(*) FROM authority_index_items WHERE authority_index_id = $1",
        index_id,
    )
    unclassified = await conn.fetchval(
        """
        SELECT COUNT(*) FROM authority_index_items i
        LEFT JOIN authority_item_classifications c ON c.item_id = i.id
        WHERE i.authority_index_id = $1 AND c.id IS NULL
        """,
        index_id,
    )
    await conn.execute(
        "UPDATE authority_indexes SET item_count = $1, unclassified_count = $2 "
        "WHERE id = $3",
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
    upserted = await _upsert_items(conn, index_id, items)
    item_count, unclassified = await _recount(conn, index_id)
    logger.info(
        "ingested %s: %d items (%d unclassified)", part.slug, item_count, unclassified
    )
    return IngestResult(
        slug=part.slug, source_type="ecfr", items_upserted=upserted,
        item_count=item_count, unclassified_count=unclassified, enumerable=True,
    )


async def ingest_curated_index(conn, spec: CuratedIndexSpec) -> IngestResult:
    """Upsert a curated CA index and its hand-authored rows (enumerable=false)."""
    rows = CURATED_ROWS.get(spec.slug, [])
    jurisdiction_id = await _resolve_jurisdiction_id(conn, spec.jurisdiction)

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
    upserted = await _upsert_items(conn, index_id, items)
    item_count, unclassified = await _recount(conn, index_id)
    logger.info(
        "ingested curated %s: %d items (%d unclassified)", spec.slug, item_count, unclassified
    )
    return IngestResult(
        slug=spec.slug, source_type="curated", items_upserted=upserted,
        item_count=item_count, unclassified_count=unclassified, enumerable=False,
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


async def ingest_all(conn) -> List[IngestResult]:
    """Ingest every catalog index. One shared httpx client for the federal parts."""
    results: List[IngestResult] = []
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        for part in FEDERAL_ECFR_PARTS:
            try:
                results.append(await ingest_ecfr_index(conn, part, client=client))
            except Exception as exc:
                logger.warning("federal ingest failed for %s: %s", part.slug, exc)
    for spec in CURATED_INDEXES:
        try:
            results.append(await ingest_curated_index(conn, spec))
        except Exception as exc:
            logger.warning("curated ingest failed for %s: %s", spec.slug, exc)
    return results
