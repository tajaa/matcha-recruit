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
    for link in links:
        row = await conn.fetchrow(
            """
            INSERT INTO scope_codifications
                (classification_id, jurisdiction_requirement_id, regulation_key,
                 jurisdiction_id, source, run_info)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb)
            ON CONFLICT (classification_id, jurisdiction_requirement_id) DO UPDATE SET
                codified_at = NOW(), source = EXCLUDED.source, run_info = EXCLUDED.run_info
            RETURNING (xmax = 0) AS inserted
            """,
            link["classification_id"], link["jurisdiction_requirement_id"],
            link["regulation_key"], link["jurisdiction_id"], source, run_info_json,
        )
        if row and row["inserted"]:
            inserted += 1
        else:
            updated += 1

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
