"""The codify layer — the explicit link between SCOPE and STORE.

`resolve_scope`/`labor_scope` call an obligation "codified" by matching the
scope classification's `regulation_key` against a `jurisdiction_requirements`
row — a string join recomputed on every read. This module records that match as
a stored fact (`scope_codifications`) with provenance, and (commit 3) drives the
fetch queue into research so the loop closes.

`match_codifications` is the pure core (key equality + a category guard);
`reconcile_codifications` fetches, matches, and upserts the linkage.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from .jurisdiction_chain import resolve_jurisdiction_chain

logger = logging.getLogger(__name__)


def match_codifications(
    classifications: List[Dict[str, Any]],
    requirement_rows: List[Dict[str, Any]],
    rkd_category_by_id: Optional[Dict[Any, str]] = None,
) -> List[Dict[str, Any]]:
    """Key-equality join between confirmed classifications and catalog rows (pure).

    One linkage per (classification × requirement) sharing a non-NULL
    ``regulation_key``. When the classification carries a ``key_definition_id``,
    the requirement's ``category`` must also equal that key's RKD ``category_slug``
    — guards the same key living in two categories (e.g. ``exempt_salary_threshold``
    under both minimum_wage and overtime).

    ``classifications``: rows with ``id``, ``regulation_key``, ``key_definition_id``.
    ``requirement_rows``: rows with ``id``, ``regulation_key``, ``jurisdiction_id``,
    ``category``.
    """
    rkd_category_by_id = rkd_category_by_id or {}

    reqs_by_key: Dict[str, List[Dict[str, Any]]] = {}
    for r in requirement_rows:
        key = r.get("regulation_key")
        if key:
            reqs_by_key.setdefault(key, []).append(r)

    links: List[Dict[str, Any]] = []
    for c in classifications:
        key = c.get("regulation_key")
        if not key:
            continue  # NULL-key classifications can never codify
        want_category = rkd_category_by_id.get(c.get("key_definition_id"))
        for r in reqs_by_key.get(key, []):
            if want_category is not None and r.get("category") != want_category:
                continue
            links.append({
                "classification_id": c["id"],
                "jurisdiction_requirement_id": r["id"],
                "regulation_key": key,
                "jurisdiction_id": r.get("jurisdiction_id"),
            })
    return links


async def chain_uncodified(
    conn, *, state: Optional[str] = None, city: Optional[str] = None,
    labor_only: bool = True,
) -> Dict[str, Any]:
    """The chain's research worklist: confirmed applicable classifications with no
    codified value in the chain, split into ``keyed`` (researchable — has a
    regulation_key to codify against) and ``unkeyed`` (NULL key — needs a key
    minted before research can codify it).

    ``state`` optional: federal-only chain when absent (mirrors labor_scope).
    ``labor_only`` restricts to labor-domain indexes so the worklist matches
    what the Labor scope panel shows (the surface that triggers research).

    Returns ``{chain, keyed: [...], unkeyed: [...]}``. Each keyed item carries
    ``classification_id``, ``regulation_key``, ``category_slug`` (RKD), ``level``,
    ``citation``, ``heading``.
    """
    from .resolve import classification_matches
    from .labor_scope import is_labor_index

    if state and state.strip():
        jur = await resolve_jurisdiction_chain(conn, state.strip().upper(), city)
    else:
        federal = await conn.fetchval(
            "SELECT id FROM jurisdictions WHERE level::text = 'federal' LIMIT 1"
        )
        jur = {"ids": [federal] if federal else [], "state_found": False,
               "city_found": False, "federal_id": federal, "state_id": None, "city_id": None}
    ids = jur["ids"]

    rows = [
        dict(r) for r in await conn.fetch(
            """
            SELECT c.id AS classification_id, c.disposition, c.applies_to_categories,
                   c.excludes_categories, c.entity_condition, c.regulation_key,
                   c.key_definition_id, rkd.category_slug,
                   i.citation, i.heading, ai.level, ai.slug AS index_slug,
                   ai.domain_categories
            FROM authority_item_classifications c
            JOIN authority_index_items i ON i.id = c.item_id
            JOIN authority_indexes ai ON ai.id = i.authority_index_id
            LEFT JOIN regulation_key_definitions rkd ON rkd.id = c.key_definition_id
            WHERE c.status = 'confirmed' AND c.disposition <> 'excluded'
              AND (ai.jurisdiction_id IS NULL OR ai.jurisdiction_id = ANY($1::uuid[]))
            """,
            ids,
        )
    ]
    if labor_only:
        rows = [r for r in rows if is_labor_index(r["index_slug"], r["domain_categories"])]

    # Generic-employer applicability (empty chain + attrs): universal matches,
    # category_specific/conditional don't — the same set the panel shows.
    applicable = [r for r in rows if classification_matches(r, [], {})]

    # Codified keys already present in the chain.
    codified_keys = set(await conn.fetchval(
        """
        SELECT COALESCE(array_agg(DISTINCT regulation_key), '{}')
        FROM jurisdiction_requirements
        WHERE jurisdiction_id = ANY($1::uuid[])
          AND regulation_key IS NOT NULL
          AND COALESCE(status, 'active') = 'active'
        """,
        ids,
    ) or [])

    keyed, unkeyed = [], []
    for r in applicable:
        item = {
            "classification_id": r["classification_id"],
            "regulation_key": r["regulation_key"],
            "category_slug": r["category_slug"],
            "level": r["level"],
            "citation": r["citation"],
            "heading": r["heading"],
        }
        if not r["regulation_key"]:
            unkeyed.append(item)
        elif r["regulation_key"] not in codified_keys:
            keyed.append(item)
    return {
        "chain": {"federal_id": jur["federal_id"], "state_id": jur["state_id"],
                  "city_id": jur["city_id"], "state_found": jur["state_found"],
                  "city_found": jur["city_found"]},
        "keyed": keyed,
        "unkeyed": unkeyed,
    }


def build_research_context(items: List[Dict[str, Any]]) -> str:
    """Target the specific missed obligations in the Gemini research prompt."""
    lines = []
    for it in items:
        cite = it.get("citation") or ""
        heading = it.get("heading") or ""
        key = it.get("regulation_key") or ""
        lines.append(f"- {key} ({cite}{' — ' + heading if heading else ''})")
    return (
        "Target these specific obligations that are in scope but not yet codified "
        "for this jurisdiction:\n" + "\n".join(lines)
    )


def group_research_units(
    keyed_items: List[Dict[str, Any]],
    *,
    federal_id: Any,
    state_id: Any,
    city_id: Any,
) -> List[Dict[str, Any]]:
    """Group keyed worklist items into (target jurisdiction × category) research
    units. Level → target: federal→federal_id, state→state_id, city/county/local→
    city_id (falls back to state_id when there's no city row). Items whose target
    jurisdiction can't be resolved are dropped (reported by the caller). Pure."""
    def target(level: str) -> Any:
        lvl = (level or "").lower()
        if lvl == "federal":
            return federal_id
        if lvl in ("city", "county", "local", "special_district"):
            return city_id or state_id
        return state_id

    by_jur: Dict[Any, Dict[str, Any]] = {}
    for it in keyed_items:
        jid = target(it["level"])
        if not jid or not it.get("category_slug"):
            continue  # no target jurisdiction row, or no RKD category to research
        unit = by_jur.setdefault(jid, {"jurisdiction_id": jid, "categories": set(),
                                       "keys": [], "items": []})
        unit["categories"].add(it["category_slug"])
        unit["keys"].append(it["regulation_key"])
        unit["items"].append(it)

    units = []
    for unit in by_jur.values():
        units.append({
            "jurisdiction_id": unit["jurisdiction_id"],
            "categories": sorted(unit["categories"]),
            "keys": unit["keys"],
            "items": unit["items"],
            "context": build_research_context(unit["items"]),
        })
    return units


async def reconcile_codifications(
    conn,
    *,
    state: Optional[str] = None,
    city: Optional[str] = None,
    source: str = "reconcile",
    run_info: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Match confirmed keyed classifications against keyed catalog rows and
    persist the linkage. Chain-scoped when ``state`` is given, else registry-wide.

    Returns counts: ``classifications_checked``, ``matched`` (link pairs),
    ``inserted``, ``updated``, ``unmatched_keys`` (keyed classifications with no
    catalog match — vocabulary drift / genuinely uncodified).
    """
    if state and state.strip():
        jur = await resolve_jurisdiction_chain(conn, state.strip().upper(), city)
        chain_ids = jur["ids"]
    else:
        chain_ids = None

    # Confirmed, non-excluded, keyed classifications (chain-filtered on the
    # authority index's jurisdiction; federal/global indexes always included).
    class_where = ["c.status = 'confirmed'", "c.disposition <> 'excluded'",
                   "c.regulation_key IS NOT NULL"]
    class_params: List[Any] = []
    if chain_ids is not None:
        class_params.append(chain_ids)
        class_where.append(
            f"(ai.jurisdiction_id IS NULL OR ai.jurisdiction_id = ANY(${len(class_params)}::uuid[]))"
        )
    classifications = [
        dict(r) for r in await conn.fetch(
            f"""
            SELECT c.id, c.regulation_key, c.key_definition_id
            FROM authority_item_classifications c
            JOIN authority_index_items i ON i.id = c.item_id
            JOIN authority_indexes ai ON ai.id = i.authority_index_id
            WHERE {' AND '.join(class_where)}
            """,
            *class_params,
        )
    ]

    # Active keyed catalog rows (chain-filtered on the requirement's jurisdiction).
    req_where = ["regulation_key IS NOT NULL", "COALESCE(status, 'active') = 'active'"]
    req_params: List[Any] = []
    if chain_ids is not None:
        req_params.append(chain_ids)
        req_where.append(f"jurisdiction_id = ANY(${len(req_params)}::uuid[])")
    requirement_rows = [
        dict(r) for r in await conn.fetch(
            f"""
            SELECT id, regulation_key, jurisdiction_id, category
            FROM jurisdiction_requirements
            WHERE {' AND '.join(req_where)}
            """,
            *req_params,
        )
    ]

    # RKD category per key_definition_id, so the matcher can enforce the guard.
    kd_ids = sorted({c["key_definition_id"] for c in classifications if c.get("key_definition_id")})
    rkd_category_by_id: Dict[Any, str] = {}
    if kd_ids:
        for r in await conn.fetch(
            "SELECT id, category_slug FROM regulation_key_definitions WHERE id = ANY($1::uuid[])",
            kd_ids,
        ):
            rkd_category_by_id[r["id"]] = r["category_slug"]

    links = match_codifications(classifications, requirement_rows, rkd_category_by_id)

    inserted = updated = 0
    run_info_json = json.dumps(run_info) if run_info else None
    if links:
        # One set-based upsert (unnest) instead of N round trips.
        result = await conn.fetch(
            """
            INSERT INTO scope_codifications
                (classification_id, jurisdiction_requirement_id, regulation_key,
                 jurisdiction_id, source, run_info)
            SELECT * FROM unnest(
                $1::uuid[], $2::uuid[], $3::text[], $4::uuid[]
            ) AS t(classification_id, jurisdiction_requirement_id, regulation_key, jurisdiction_id),
            LATERAL (SELECT $5::varchar AS source, $6::jsonb AS run_info) s
            ON CONFLICT (classification_id, jurisdiction_requirement_id) DO UPDATE SET
                codified_at = NOW(), source = EXCLUDED.source, run_info = EXCLUDED.run_info
            RETURNING (xmax = 0) AS inserted
            """,
            [link["classification_id"] for link in links],
            [link["jurisdiction_requirement_id"] for link in links],
            [link["regulation_key"] for link in links],
            [link["jurisdiction_id"] for link in links],
            source, run_info_json,
        )
        inserted = sum(1 for r in result if r["inserted"])
        updated = len(result) - inserted

    matched_classification_ids = {link["classification_id"] for link in links}
    unmatched_keys = sorted({
        c["regulation_key"] for c in classifications
        if c["id"] not in matched_classification_ids
    })

    return {
        "classifications_checked": len(classifications),
        "matched": len(links),
        "inserted": inserted,
        "updated": updated,
        "unmatched_keys": unmatched_keys,
    }
