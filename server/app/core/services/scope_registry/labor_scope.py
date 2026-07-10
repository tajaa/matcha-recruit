"""Per-jurisdiction labor scope — the authoritative "what must we fetch" view.

Jurisdiction-first and **industry-agnostic** (unlike the coordinate-driven
``resolve_scope`` and the manufacturing/healthcare-only ``core_checklist``): for
a (state, city) it answers, for a *generic* employer, which labor obligations
apply, split federal / state / city, and which are already codified in
``jurisdiction_requirements`` vs still on the fetch queue.

Exhaustiveness is honest per level (plan decision):
  * **federal** = exhaustive-by-enumeration — the eCFR parts are machine
    enumerable; ``us-flsa`` curates the statute the eCFR doesn't carry.
  * **state / city** = curated core only. ``curated_ca.py`` is load-bearing:
    ``unclassified_count = 0`` for a curated index means "the curated slice is
    fully classified", NEVER "all law at this level is scoped".

Not built on ``resolve_scope``: that path requires a category, writes a cache
row, and pulls non-labor indexes (40 CFR RCRA, ca-title-16). This reuses its
*pure* pieces — ``classification_matches`` and the key-precise requirement join —
under a labor-domain filter instead.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.core.services.compliance_evals.completeness import _bare_key
from app.core.services.compliance_evals.industry_keysets import CORE_LABOR_KEYS
from app.core.services.compliance_evals.keys import normalize_key

from .jurisdiction_chain import resolve_jurisdiction_chain
from .resolve import classification_matches

logger = logging.getLogger(__name__)

# Domain labels (authority_sources.domain_categories) that denote employment /
# workplace-safety law — i.e. labor. Positive membership keeps non-labor indexes
# (hazardous_waste_generators = 40 CFR; licensed_professions = ca-title-16) out.
LABOR_DOMAINS = {"all_industry", "general_industry", "all_ca_employers"}

# Most-local first — the governing level for a present obligation, and the order
# county folds toward city.
LEVEL_ORDER = ("city", "county", "state", "federal")

ENUMERATED_NOTE = (
    "Why exhaustive: each eCFR part below is ingested in full from the "
    "government's official eCFR structure API — every section is captured, none "
    "hand-picked. The FLSA wage-hour statute (29 U.S.C., not in eCFR) is curated "
    "separately. Bound: exhaustive within these parts; the part selection is the "
    "curated federal-labor backbone (safety, recordkeeping, leave, wage-hour)."
)
CURATED_NOTE = (
    "Why not exhaustive: no open, machine-readable index of this jurisdiction's "
    "full labor code exists, so these are hand-curated core provisions. A fully "
    "classified curated slice means only that the slice is complete — never that "
    "all law at this level is scoped."
)
NO_INDEX_NOTE = "no authority indexes ingested at this level"


def is_labor_index(slug: str, domain_categories: Optional[List[str]]) -> bool:
    """Is this authority index in the labor (employment/safety) domain? (pure)"""
    return bool(set(domain_categories or []) & LABOR_DOMAINS)


def _level_bucket(level: Optional[str]) -> str:
    """Map an authority/jurisdiction level onto federal / state / city."""
    lvl = (level or "").lower()
    if lvl == "federal":
        return "federal"
    if lvl in ("city", "county", "local", "special_district"):
        return "city"
    return "state"


def core_spine(req_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The 12-key industry-agnostic labor must-have checklist for a jurisdiction.

    ``req_rows`` are ``jurisdiction_requirements`` rows over the chain: each has
    ``category``, ``regulation_key``, ``requirement_key``, ``level``,
    ``country_code``. A key counts as present if the catalog holds it at any
    chain level; the governing level is the most-local one that holds it.
    """
    present_level: Dict[tuple, str] = {}
    for r in req_rows:
        bare = _bare_key(r.get("regulation_key"), r.get("requirement_key"))
        category = r.get("category")
        if not bare or not category:
            continue
        key = normalize_key(category, bare, r.get("level"), r.get("country_code") or "US")
        coord = (category, key)
        level = _level_bucket(r.get("level"))  # ∈ {city, state, federal}
        prior = present_level.get(coord)
        if prior is None or LEVEL_ORDER.index(level) < LEVEL_ORDER.index(prior):
            present_level[coord] = level

    items: List[Dict[str, Any]] = []
    present = 0
    for category, keys in CORE_LABOR_KEYS.items():
        for key in sorted(keys):
            level = present_level.get((category, key))
            if level is not None:
                present += 1
            items.append({"category": category, "key": key,
                          "present": level is not None, "level": level})
    total = len(items)
    return {"items": items, "present": present, "total": total, "complete": present == total}


def bucket_registry(
    applicable: List[Dict[str, Any]],
    requirements_by_key: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """Split matched labor classifications into codified/uncodified, by level.

    ``applicable`` rows are confirmed labor classifications that matched a generic
    employer (already ``classification_matches``-filtered); each carries ``level``,
    ``citation``, ``heading``, ``source_url``, ``index_slug``, ``disposition``,
    ``regulation_key``. ``requirements_by_key`` maps a codified key to its
    ``jurisdiction_requirements`` row.
    """
    levels: Dict[str, Dict[str, Any]] = {
        b: {"codified": [], "uncodified": []} for b in ("federal", "state", "city")
    }
    for row in applicable:
        bucket = _level_bucket(row.get("level"))
        entry = {
            "citation": row.get("citation"),
            "heading": row.get("heading"),
            "source_url": row.get("source_url"),
            "index": row.get("index_slug"),
            "disposition": row.get("disposition"),
        }
        key = row.get("regulation_key")
        if key and key in requirements_by_key:
            levels[bucket]["codified"].append(
                {**entry, "regulation_key": key, "requirement": requirements_by_key[key]}
            )
        else:
            levels[bucket]["uncodified"].append({**entry, "regulation_key": key})
    return levels


def build_exhaustiveness(index_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Per-level exhaustiveness basis from the labor authority indexes in scope.

    ``index_rows``: ``authority_indexes`` rows (labor-filtered) with ``slug``,
    ``name``, ``level``, ``enumerable``, ``item_count``, ``unclassified_count``.
    """
    out: Dict[str, Any] = {
        b: {"basis": "none", "indexes": [], "note": NO_INDEX_NOTE}
        for b in ("federal", "state", "city")
    }
    for r in index_rows:
        bucket = _level_bucket(r.get("level"))
        out[bucket]["indexes"].append({
            "slug": r.get("slug"), "name": r.get("name"),
            "source_type": r.get("source_type"),
            "enumerable": r.get("enumerable"),
            "item_count": r.get("item_count") or 0,
            "unclassified_count": r.get("unclassified_count") or 0,
        })
    for bucket, data in out.items():
        if not data["indexes"]:
            continue
        if any(ix.get("enumerable") for ix in data["indexes"]):
            data["basis"], data["note"] = "enumerated", ENUMERATED_NOTE
        else:
            data["basis"], data["note"] = "curated", CURATED_NOTE
        # Enumeration vs classification: the exhaustive claim is over enumerated
        # items, but only classified ones reach the fetch queue. Surface the gap
        # so "N to fetch" reads as a lower bound until classification finishes.
        total = sum(ix["item_count"] for ix in data["indexes"])
        unclassified = sum(ix["unclassified_count"] for ix in data["indexes"])
        data["enumeration"] = {
            "indexes": len(data["indexes"]),
            "enumerated": total,
            "classified": total - unclassified,
            "unclassified": unclassified,
        }
    return out


async def labor_scope(
    conn, *, state: Optional[str] = None, city: Optional[str] = None
) -> Dict[str, Any]:
    """Resolve the labor scope for a (state, city). See module docstring.

    ``state`` is optional: federal labor law is state-independent, so with no
    state the chain is federal-only and the federal column resolves fully while
    the state/city columns stay empty (prompt for a state).
    """
    if state and state.strip():
        jur = await resolve_jurisdiction_chain(conn, state.strip().upper(), city)
    else:
        federal = await conn.fetchval(
            "SELECT id FROM jurisdictions WHERE level::text = 'federal' LIMIT 1"
        )
        jur = {"ids": [federal] if federal else [], "state_found": False, "city_found": False}
    ids = jur["ids"]

    # ── core spine: present keys over the chain ────────────────────────────
    req_rows = [
        dict(r) for r in await conn.fetch(
            """
            SELECT jr.category, jr.regulation_key, jr.requirement_key,
                   j.level::text AS level, COALESCE(j.country_code, 'US') AS country_code
            FROM jurisdiction_requirements jr
            JOIN jurisdictions j ON j.id = jr.jurisdiction_id
            WHERE jr.jurisdiction_id = ANY($1::uuid[])
              AND COALESCE(jr.status, 'active') = 'active'
            """,
            ids,
        )
    ]
    core = core_spine(req_rows)

    # ── registry half: confirmed labor classifications in the chain ────────
    class_rows = [
        dict(r) for r in await conn.fetch(
            """
            SELECT c.item_id, c.disposition, c.applies_to_categories,
                   c.excludes_categories, c.entity_condition, c.regulation_key,
                   i.citation, i.heading, i.source_url,
                   ai.slug AS index_slug, ai.level, ai.domain_categories
            FROM authority_item_classifications c
            JOIN authority_index_items i ON i.id = c.item_id
            JOIN authority_indexes ai ON ai.id = i.authority_index_id
            WHERE c.status = 'confirmed'
              AND (ai.jurisdiction_id IS NULL OR ai.jurisdiction_id = ANY($1::uuid[]))
            """,
            ids,
        )
    ]
    labor_rows = [r for r in class_rows if is_labor_index(r["index_slug"], r["domain_categories"])]

    # Generic-employer semantics: empty category chain + empty attributes.
    # universal_in_domain matches; category_specific never; conditional only if
    # its trigger fires against no attributes (FMLA ≥50 won't).
    applicable: List[Dict[str, Any]] = []
    skipped = {"category_specific": 0, "conditional": 0}
    for row in labor_rows:
        if classification_matches(row, [], {}):
            applicable.append(row)
        elif row["disposition"] in skipped:
            skipped[row["disposition"]] += 1

    # Key-precise, most-local codified join (mirrors resolve.py) + provenance:
    # the stored value's own source/freshness and the codify-linkage timestamp,
    # so a codified obligation shows WHY it's codified inline.
    keys = sorted({r["regulation_key"] for r in applicable if r["regulation_key"]})
    requirements_by_key: Dict[str, Dict[str, Any]] = {}
    if keys:
        # scope_codifications may be absent on a DB without codify02 — degrade.
        have_links = await conn.fetchval("SELECT to_regclass('public.scope_codifications')")
        link_select = (
            "sc.codified_at, sc.source AS codify_source"
            if have_links else "NULL::timestamp AS codified_at, NULL::text AS codify_source"
        )
        link_join = (
            """LEFT JOIN LATERAL (
                   SELECT codified_at, source FROM scope_codifications s
                   WHERE s.jurisdiction_requirement_id = jr.id
                   ORDER BY codified_at DESC LIMIT 1
               ) sc ON TRUE"""
            if have_links else ""
        )
        for req in await conn.fetch(
            f"""
            SELECT jr.regulation_key, jr.key_definition_id, jr.title, jr.current_value,
                   jr.source_url, jr.source_name, jr.jurisdiction_level,
                   jr.jurisdiction_name, jr.last_verified_at, {link_select}
            FROM jurisdiction_requirements jr
            {link_join}
            WHERE jr.jurisdiction_id = ANY($1::uuid[])
              AND jr.regulation_key = ANY($2::text[])
              AND COALESCE(jr.status, 'active') = 'active'
            ORDER BY CASE LOWER(jr.jurisdiction_level)
                WHEN 'city' THEN 0 WHEN 'county' THEN 1
                WHEN 'state' THEN 2 ELSE 3 END
            """,
            ids, keys,
        ):
            requirements_by_key.setdefault(req["regulation_key"], dict(req))

    levels = bucket_registry(applicable, requirements_by_key)

    # Per-level provisional counts (labor authoring still in flight).
    prov_by_level = {"federal": 0, "state": 0, "city": 0}
    for r in await conn.fetch(
        """
        SELECT ai.level, ai.slug, ai.domain_categories, COUNT(*) AS n
        FROM authority_item_classifications c
        JOIN authority_index_items i ON i.id = c.item_id
        JOIN authority_indexes ai ON ai.id = i.authority_index_id
        WHERE c.status = 'provisional'
          AND (ai.jurisdiction_id IS NULL OR ai.jurisdiction_id = ANY($1::uuid[]))
        GROUP BY ai.level, ai.slug, ai.domain_categories
        """,
        ids,
    ):
        if is_labor_index(r["slug"], r["domain_categories"]):
            prov_by_level[_level_bucket(r["level"])] += int(r["n"])

    for bucket, data in levels.items():
        data["counts"] = {
            "codified": len(data["codified"]),
            "uncodified": len(data["uncodified"]),
            "provisional": prov_by_level[bucket],
        }

    # ── exhaustiveness: labor indexes in scope ─────────────────────────────
    index_rows = [
        dict(r) for r in await conn.fetch(
            """
            SELECT slug, name, level, source_type, enumerable, item_count,
                   unclassified_count, domain_categories
            FROM authority_indexes
            WHERE jurisdiction_id IS NULL OR jurisdiction_id = ANY($1::uuid[])
            """,
            ids,
        )
    ]
    labor_indexes = [r for r in index_rows if is_labor_index(r["slug"], r["domain_categories"])]
    exhaustiveness = build_exhaustiveness(labor_indexes)

    return {
        "coordinate": {
            "state": state.strip().upper() if state and state.strip() else None,
            "city": city,
            "state_found": jur["state_found"],
            "city_found": jur["city_found"],
            "jurisdiction_ids": [str(i) for i in ids],
        },
        "core": core,
        "registry": {"levels": levels, "skipped": skipped},
        "exhaustiveness": exhaustiveness,
    }
