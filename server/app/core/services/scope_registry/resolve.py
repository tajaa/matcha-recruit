"""Resolve a business coordinate to its scope — pure SQL + deterministic triggers.

``resolve_scope`` is the registry's read path: given a business category (or
NAICS, or a company), a jurisdiction chain, and facility attributes, return the
classified obligations that apply — split into **codified** keys (joined
key-precisely to `jurisdiction_requirements`) and the **uncodified fetch queue**
(applicable items with no catalog value yet).

No AI at read time, ever (plan §3): the SQL selects confirmed classifications;
conditional rows are filtered by the existing deterministic
``evaluate_trigger_conditions``. Provisional classifications count toward no
resolved scope — they are surfaced as a count, nothing more.

Results cache into ``scope_resolutions`` by coordinate hash — the "second
identical warehouse = zero work" table. The cache is invalidated by comparing
its ``computed_at`` against the newest strata refresh.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Dict, List, Optional

from .categories import ancestry, categories_for_naics, resolve_category
from .jurisdiction_chain import resolve_jurisdiction_chain

logger = logging.getLogger(__name__)


def parse_jsonb(value: Any) -> Any:
    """asyncpg returns JSONB as str on this pool — normalize to objects.

    (workers/utils has an equivalent, but a core service importing from the
    workers layer is the wrong direction.)
    """
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return None
    return value


def coordinate_hash(
    category_chain: List[str],
    jurisdiction_ids: List[Any],
    facility_attributes: Optional[Dict[str, Any]],
) -> str:
    """Stable hash of a resolution coordinate (attr order must not matter)."""
    payload = json.dumps(
        {
            "categories": sorted(category_chain),
            "jurisdictions": sorted(str(j) for j in jurisdiction_ids),
            "attributes": dict(sorted((facility_attributes or {}).items())),
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def classification_matches(
    row: Dict[str, Any],
    category_chain: List[str],
    facility_attributes: Optional[Dict[str, Any]],
) -> bool:
    """Does one confirmed classification apply to this coordinate? (pure)

    * excluded            → never
    * excludes ∩ ancestry → never (an exclude anywhere in the chain wins)
    * universal_in_domain → yes
    * category_specific   → applies_to ∩ ancestry
    * conditional         → (applies_to empty or ∩ ancestry) AND the trigger
                            fires against facility_attributes (deterministic)
    """
    from app.core.services.compliance_service import evaluate_trigger_conditions

    disposition = row["disposition"]
    if disposition == "excluded":
        return False
    chain = set(category_chain)
    if set(row.get("excludes_categories") or []) & chain:
        return False
    if disposition == "universal_in_domain":
        return True

    applies = set(row.get("applies_to_categories") or [])
    if disposition == "category_specific":
        return bool(applies & chain)
    if disposition == "conditional":
        if applies and not (applies & chain):
            return False
        condition = parse_jsonb(row.get("entity_condition"))
        if condition is None and row.get("entity_condition") is not None:
            return False  # unparseable stored condition never silently applies
        return evaluate_trigger_conditions(condition, facility_attributes or {})
    return False


async def resolve_scope(
    conn,
    *,
    category: Optional[str] = None,
    naics: Optional[str] = None,
    state: Optional[str] = None,
    city: Optional[str] = None,
    facility_attributes: Optional[Dict[str, Any]] = None,
    use_cache: bool = True,
) -> Dict[str, Any]:
    """Resolve one (category × jurisdiction × attributes) coordinate.

    Returns::

        {
          "coordinate": {category_chain, jurisdiction_ids, state_found, city_found},
          "codified":   [ {citation, heading, regulation_key, requirement: {...}|None} ],
          "uncodified": [ {citation, heading, disposition, applies_to} ],   # fetch queue
          "counts":     {applicable, codified, uncodified, provisional, conditional_skipped},
          "unmodeled_coordinates": [ ... ],
          "cache": "hit"|"miss",
        }

    ``provisional`` is deliberately chain-wide, not coordinate-filtered: it is
    an authoring-work-remains signal for the preview, and filtering it to the
    queried category would hide pending work from the admin.

    Company-wide resolution (per-location union off `business_locations` +
    roster-injected facility attributes) arrives with the commit-5 shadow.
    """
    unmodeled: List[Dict[str, Any]] = []

    slug = resolve_category(category) if category else None
    chain_slugs: List[str] = ancestry(slug) if slug else []
    if not chain_slugs and naics:
        chain_slugs = categories_for_naics(naics)
    if not chain_slugs:
        unmodeled.append({
            "kind": "category",
            "value": category or naics,
            "note": "no taxonomy category resolves this input",
        })

    if not state:
        raise ValueError("resolve_scope requires a state")
    jur = await resolve_jurisdiction_chain(conn, state.upper(), city)
    if not jur["state_found"]:
        unmodeled.append({
            "kind": "state",
            "value": state.upper(),
            "note": "no state jurisdiction row — coverage degrades to federal only",
        })
    if city and not jur["city_found"]:
        unmodeled.append({
            "kind": "city",
            "value": city,
            "note": "unknown city — coverage degrades to state ∪ federal",
        })

    coord_hash = coordinate_hash(chain_slugs, jur["ids"], facility_attributes)

    cache_state = "miss"
    if use_cache:
        cached = await conn.fetchrow(
            """
            SELECT r.computed_at, r.key_count, r.uncodified_count, r.provisional_count
            FROM scope_resolutions r
            WHERE r.coordinate_hash = $1
              AND r.computed_at >= COALESCE(
                    (SELECT MAX(refreshed_at) FROM scope_strata), 'epoch'::timestamp)
            """,
            coord_hash,
        )
        cache_state = "hit" if cached else "miss"
        # Cached counts prove reuse ("second warehouse = zero work"), but the
        # full item detail is cheap SQL — recompute the payload either way.
        # stratum_ids tracking (serving wholly from cache) lands with the
        # commit-5/6 read path.

    # One pass over confirmed classifications in the chain. Disposition and
    # exclude logic runs in Python (classification_matches) so the conditional
    # branch shares evaluate_trigger_conditions with the rest of the platform.
    rows = [
        dict(r)
        for r in await conn.fetch(
            """
            SELECT c.item_id, c.disposition, c.applies_to_categories,
                   c.excludes_categories, c.entity_condition, c.regulation_key,
                   i.citation, i.heading, i.source_url, (i.body_text IS NOT NULL) AS has_body,
                   ai.slug AS index_slug, ai.level, ai.jurisdiction_id
            FROM authority_item_classifications c
            JOIN authority_index_items i ON i.id = c.item_id
            JOIN authority_indexes ai ON ai.id = i.authority_index_id
            WHERE c.status = 'confirmed'
              AND (ai.jurisdiction_id IS NULL OR ai.jurisdiction_id = ANY($1::uuid[]))
            """,
            jur["ids"],
        )
    ]
    provisional_count = await conn.fetchval(
        """
        SELECT COUNT(*)
        FROM authority_item_classifications c
        JOIN authority_index_items i ON i.id = c.item_id
        JOIN authority_indexes ai ON ai.id = i.authority_index_id
        WHERE c.status = 'provisional'
          AND (ai.jurisdiction_id IS NULL OR ai.jurisdiction_id = ANY($1::uuid[]))
        """,
        jur["ids"],
    )

    applicable: List[Dict[str, Any]] = []
    conditional_skipped = 0
    for row in rows:
        if classification_matches(row, chain_slugs, facility_attributes):
            applicable.append(row)
        elif row["disposition"] == "conditional":
            conditional_skipped += 1

    # Key-precise catalog join for the codified half (NOT a category grab).
    keys = sorted({r["regulation_key"] for r in applicable if r["regulation_key"]})
    requirements_by_key: Dict[str, Dict[str, Any]] = {}
    if keys:
        # Most-local row per key (city > county > state > federal) for the
        # preview. TRUE preemption (which level legally wins, incl.
        # allows_local_override) stays with determine_governing_requirement —
        # this is a display pick, deterministic so previews don't flap.
        for req in await conn.fetch(
            """
            SELECT regulation_key, title, current_value, source_url,
                   jurisdiction_level, jurisdiction_name
            FROM jurisdiction_requirements
            WHERE jurisdiction_id = ANY($1::uuid[])
              AND regulation_key = ANY($2::text[])
              AND COALESCE(status, 'active') = 'active'
            ORDER BY CASE LOWER(jurisdiction_level)
                WHEN 'city' THEN 0 WHEN 'county' THEN 1
                WHEN 'state' THEN 2 ELSE 3 END
            """,
            jur["ids"], keys,
        ):
            requirements_by_key.setdefault(req["regulation_key"], dict(req))

    codified = []
    uncodified = []
    for row in applicable:
        entry = {
            "item_id": str(row["item_id"]) if row.get("item_id") else None,
            "has_body": bool(row.get("has_body")),
            "citation": row["citation"],
            "heading": row["heading"],
            "source_url": row["source_url"],
            "index": row["index_slug"],
            "level": row["level"],
            "disposition": row["disposition"],
            "applies_to": row["applies_to_categories"],
        }
        key = row["regulation_key"]
        if key and key in requirements_by_key:
            codified.append({**entry, "regulation_key": key,
                             "requirement": requirements_by_key[key]})
        elif key:
            # Key named but no catalog row in this chain — still the fetch queue.
            uncodified.append({**entry, "regulation_key": key})
        else:
            uncodified.append({**entry, "regulation_key": None})

    result = {
        "coordinate": {
            "category_chain": chain_slugs,
            "jurisdiction_ids": [str(j) for j in jur["ids"]],
            "state_found": jur["state_found"],
            "city_found": jur["city_found"],
            "coordinate_hash": coord_hash,
        },
        "codified": codified,
        "uncodified": uncodified,
        "counts": {
            "applicable": len(applicable),
            "codified": len(codified),
            "uncodified": len(uncodified),
            "provisional": int(provisional_count),
            "conditional_skipped": conditional_skipped,
        },
        "unmodeled_coordinates": unmodeled,
        "cache": cache_state,
    }

    if use_cache:
        await conn.execute(
            """
            INSERT INTO scope_resolutions
                (coordinate_hash, stratum_ids, key_count, uncodified_count,
                 provisional_count, computed_at)
            VALUES ($1, '{}', $2, $3, $4, NOW())
            ON CONFLICT (coordinate_hash) DO UPDATE SET
                key_count = EXCLUDED.key_count,
                uncodified_count = EXCLUDED.uncodified_count,
                provisional_count = EXCLUDED.provisional_count,
                computed_at = NOW()
            """,
            coord_hash, len(codified), len(uncodified), int(provisional_count),
        )

    return result


async def fetch_queue(
    conn, *, category: Optional[str] = None, state: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Applicable-classified items with no codified catalog value — the direct
    input to the research pipeline (plan §6).

    Unlike resolve_scope this is a registry-wide worklist view: confirmed,
    non-excluded classifications whose regulation_key is NULL, optionally
    narrowed to a category (ancestry-aware) or a state's chain.
    """
    params: List[Any] = []
    # "No codified value" is BOTH a NULL key (never minted) and a named key
    # with no catalog row anywhere — either way the research pipeline owes it
    # a value.
    where = [
        "c.status = 'confirmed'",
        "c.disposition <> 'excluded'",
        "(c.regulation_key IS NULL OR NOT EXISTS ("
        "   SELECT 1 FROM jurisdiction_requirements jr"
        "   WHERE jr.regulation_key = c.regulation_key"
        "     AND COALESCE(jr.status, 'active') = 'active'))",
    ]

    if state:
        jur = await resolve_jurisdiction_chain(conn, state.upper(), None)
        params.append(jur["ids"])
        where.append(f"(ai.jurisdiction_id IS NULL OR ai.jurisdiction_id = ANY(${len(params)}::uuid[]))")

    rows = [
        {**dict(r), "entity_condition": parse_jsonb(r["entity_condition"])}
        for r in await conn.fetch(
            f"""
            SELECT c.item_id, c.disposition, c.applies_to_categories,
                   c.excludes_categories, c.entity_condition, c.regulation_key,
                   i.citation, i.heading, i.source_url,
                   ai.slug AS index_slug, ai.level
            FROM authority_item_classifications c
            JOIN authority_index_items i ON i.id = c.item_id
            JOIN authority_indexes ai ON ai.id = i.authority_index_id
            WHERE {' AND '.join(where)}
            ORDER BY ai.slug, i.citation
            """,
            *params,
        )
    ]

    if category:
        slug = resolve_category(category)
        chain = set(ancestry(slug)) if slug else set()
        rows = [
            r for r in rows
            if not (set(r.get("excludes_categories") or []) & chain)
            and (
                r["disposition"] == "universal_in_domain"
                or not r.get("applies_to_categories")
                or (set(r["applies_to_categories"]) & chain)
            )
        ]
    return rows
