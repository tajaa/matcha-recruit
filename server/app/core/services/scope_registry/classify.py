"""Classify authority items against the business-category taxonomy.

The primitive act of the scope registry (SCOPE_REGISTRY_PLAN.md §3): every
enumerated authority item gets exactly one disposition —
``universal_in_domain`` / ``category_specific`` / ``conditional`` / ``excluded``.
Gemini pre-classifies at **subpart level** (sections inherit via
``inherits_from_item_id``); a human confirms per subpart; unconfirmed rows are
``provisional`` and count toward no resolved scope.

Hard gates (enforced by :func:`validate_proposal`, the pure testable core):
  * ``applies_to``/``excludes`` values must exist in the taxonomy (`CATEGORIES`)
  * a cited ``regulation_key`` must exist in `regulation_key_definitions` —
    otherwise it is stored NULL (applicable-but-uncodified, the fetch queue)
    with a warning. Keys are never invented.
  * ``entity_condition`` must be a shape ``evaluate_trigger_conditions`` accepts.
  * ``excluded`` requires an ``excluded_reason``.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import UUID

from .categories import CATEGORIES

logger = logging.getLogger(__name__)

DISPOSITIONS = ("universal_in_domain", "category_specific", "conditional", "excluded")

_LEAF_OPERATORS = {"exists", "eq", "neq", "gt", "gte", "lt", "lte", "in", "contains"}


def _condition_shape_error(node: Any) -> Optional[str]:
    """Validate an entity_condition against evaluate_trigger_conditions' shape.

    Compound: {"op": and|or|not, "conditions": [...]}. Leaf:
    {"type": "attribute", "key": str, "operator": op, "value": ...}.
    Returns an error string, or None when valid.
    """
    if not isinstance(node, dict):
        return "entity_condition must be an object"
    op = node.get("op")
    if op is not None:
        if op not in ("and", "or", "not"):
            return f"unknown op {op!r}"
        children = node.get("conditions")
        if not isinstance(children, list) or not children:
            return f"op {op!r} requires a non-empty conditions list"
        for child in children:
            err = _condition_shape_error(child)
            if err:
                return err
        return None
    if node.get("type") == "attribute":
        if not node.get("key") or not isinstance(node.get("key"), str):
            return "attribute condition requires a string key"
        if node.get("operator") not in _LEAF_OPERATORS:
            return f"unknown operator {node.get('operator')!r}"
        if node.get("operator") != "exists" and "value" not in node:
            return f"operator {node.get('operator')!r} requires a value"
        return None
    return "condition must be a compound {op, conditions} or an attribute leaf"


def validate_proposal(
    proposal: Dict[str, Any],
    rkd_keys_by_category: Dict[str, Set[str]],
) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """Normalize and gate one classification proposal (Gemini, seed, or admin).

    Returns ``(normalized, warnings)``. ``normalized is None`` means REJECTED —
    the proposal violated a hard gate and must not be stored. Warnings are
    non-fatal downgrades (an unknown regulation_key becomes NULL/uncodified).

    Pure function — the RKD keyset is passed in, no DB access.
    """
    warnings: List[str] = []

    disposition = proposal.get("disposition")
    if disposition not in DISPOSITIONS:
        return None, [f"unknown disposition {disposition!r}"]

    def _category_list(field: str) -> Optional[List[str]]:
        raw = proposal.get(field) or []
        if not isinstance(raw, list):
            return None
        slugs = []
        for entry in raw:
            slug = str(entry).strip().lower()
            if slug not in CATEGORIES:
                return None
            slugs.append(slug)
        return sorted(set(slugs))

    applies_to = _category_list("applies_to_categories")
    excludes = _category_list("excludes_categories")
    if applies_to is None:
        return None, [f"applies_to_categories contains a slug not in the taxonomy: "
                      f"{proposal.get('applies_to_categories')!r}"]
    if excludes is None:
        return None, [f"excludes_categories contains a slug not in the taxonomy: "
                      f"{proposal.get('excludes_categories')!r}"]

    if disposition == "category_specific" and not applies_to:
        return None, ["category_specific requires a non-empty applies_to_categories"]
    if disposition == "excluded" and not (proposal.get("excluded_reason") or "").strip():
        return None, ["excluded requires an excluded_reason"]

    entity_condition = proposal.get("entity_condition")
    if disposition == "conditional":
        err = _condition_shape_error(entity_condition)
        if err:
            return None, [f"conditional requires a valid entity_condition: {err}"]
    elif entity_condition is not None:
        # A condition on a non-conditional disposition is a modeling error.
        return None, [f"entity_condition is only valid on 'conditional' (got {disposition!r})"]

    regulation_key = (proposal.get("regulation_key") or "").strip() or None
    if regulation_key is not None:
        category_slug = (proposal.get("category_slug") or "").strip() or None
        known = (
            regulation_key in rkd_keys_by_category.get(category_slug, set())
            if category_slug
            else any(regulation_key in keys for keys in rkd_keys_by_category.values())
        )
        if not known:
            warnings.append(
                f"regulation_key {regulation_key!r} not in regulation_key_definitions"
                + (f" for category {category_slug!r}" if category_slug else "")
                + " — stored uncodified (NULL)"
            )
            regulation_key = None

    return (
        {
            "disposition": disposition,
            "applies_to_categories": applies_to,
            "excludes_categories": excludes,
            "entity_condition": entity_condition if disposition == "conditional" else None,
            "excluded_reason": (proposal.get("excluded_reason") or "").strip() or None,
            "regulation_key": regulation_key,
            "category_slug": (proposal.get("category_slug") or "").strip() or None,
        },
        warnings,
    )


async def fetch_rkd_keys_by_category(conn) -> Dict[str, Set[str]]:
    """category_slug → set of keys, from regulation_key_definitions."""
    rows = await conn.fetch("SELECT key, category_slug FROM regulation_key_definitions")
    out: Dict[str, Set[str]] = {}
    for r in rows:
        out.setdefault(r["category_slug"], set()).add(r["key"])
    return out


async def _upsert_classification(
    conn,
    item_id,
    normalized: Dict[str, Any],
    *,
    proposed_by: str,
    status: str = "provisional",
    inherits_from_item_id=None,
    confirmed_by=None,
) -> None:
    # key_definition_id resolves inline from the (validated) regulation_key so
    # the RKD FK is live, not dead weight. ORDER BY keeps the ambiguous case
    # (same key in two categories, no category hint) deterministic.
    await conn.execute(
        """
        INSERT INTO authority_item_classifications
            (item_id, disposition, applies_to_categories, excludes_categories,
             entity_condition, excluded_reason, regulation_key, key_definition_id,
             inherits_from_item_id, status, proposed_by, confirmed_by, confirmed_at)
        VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7,
                (SELECT id FROM regulation_key_definitions
                 WHERE key = $7 AND ($12::text IS NULL OR category_slug = $12)
                 ORDER BY category_slug LIMIT 1),
                $8, $9, $10, $11,
                CASE WHEN $9 = 'confirmed' THEN NOW() ELSE NULL END)
        ON CONFLICT (item_id) DO UPDATE SET
            disposition = EXCLUDED.disposition,
            applies_to_categories = EXCLUDED.applies_to_categories,
            excludes_categories = EXCLUDED.excludes_categories,
            entity_condition = EXCLUDED.entity_condition,
            excluded_reason = EXCLUDED.excluded_reason,
            regulation_key = EXCLUDED.regulation_key,
            key_definition_id = EXCLUDED.key_definition_id,
            inherits_from_item_id = EXCLUDED.inherits_from_item_id,
            status = EXCLUDED.status,
            proposed_by = EXCLUDED.proposed_by,
            confirmed_by = EXCLUDED.confirmed_by,
            confirmed_at = EXCLUDED.confirmed_at
        """,
        item_id,
        normalized["disposition"],
        normalized["applies_to_categories"],
        normalized["excludes_categories"],
        json.dumps(normalized["entity_condition"]) if normalized["entity_condition"] else None,
        normalized["excluded_reason"],
        normalized["regulation_key"],
        inherits_from_item_id,
        status,
        proposed_by,
        confirmed_by,
        normalized.get("category_slug"),
    )


async def _refresh_unclassified_count(conn, index_id) -> int:
    unclassified = await conn.fetchval(
        """
        SELECT COUNT(*) FROM authority_index_items i
        LEFT JOIN authority_item_classifications c ON c.item_id = i.id
        WHERE i.authority_index_id = $1 AND c.id IS NULL
        """,
        index_id,
    )
    await conn.execute(
        "UPDATE authority_indexes SET unclassified_count = $1 WHERE id = $2",
        unclassified, index_id,
    )
    return int(unclassified)


def child_classification_of(parent: Dict[str, Any]) -> Dict[str, Any]:
    """The content a child section inherits from its parent's classification.

    Everything copies except ``regulation_key`` — keys are per-obligation, not
    inherited (a subpart's key would wrongly claim every section codified).
    The set-based SQL in :func:`materialize_inherited_children` mirrors this
    mapping; keep the two in sync.
    """
    return {
        "disposition": parent["disposition"],
        "applies_to_categories": list(parent.get("applies_to_categories") or []),
        "excludes_categories": list(parent.get("excludes_categories") or []),
        "entity_condition": parent.get("entity_condition"),
        "excluded_reason": parent.get("excluded_reason"),
        "regulation_key": None,
        "category_slug": None,
    }


async def materialize_inherited_children(conn, index_id) -> int:
    """Materialize inheriting rows for unclassified children of classified parents.

    This is the NORMAL post-seed state, not an edge case: `apply_seed`
    classifies subparts while their ingested child sections stay unclassified.
    Without this sweep those children are unreachable — `classify_index` only
    targets unclassified items, so a child whose parent is already classified
    never gets a row and `unclassified_count` can never reach 0.

    Children copy the parent's content AND its status/proposed_by/confirmed_by:
    a confirmed parent's missing children must land confirmed, because the
    confirm cascade would have caught them had the rows existed. Content
    mapping mirrors :func:`child_classification_of`.
    """
    rows = await conn.fetch(
        """
        INSERT INTO authority_item_classifications
            (item_id, disposition, applies_to_categories, excludes_categories,
             entity_condition, excluded_reason, regulation_key, key_definition_id,
             inherits_from_item_id, status, proposed_by, confirmed_by, confirmed_at)
        SELECT child.id, pc.disposition, pc.applies_to_categories,
               pc.excludes_categories, pc.entity_condition, pc.excluded_reason,
               NULL, NULL,
               pc.item_id, pc.status, pc.proposed_by, pc.confirmed_by, pc.confirmed_at
        FROM authority_index_items child
        JOIN authority_item_classifications pc ON pc.item_id = child.parent_item_id
        LEFT JOIN authority_item_classifications cc ON cc.item_id = child.id
        WHERE child.authority_index_id = $1 AND cc.id IS NULL
        ON CONFLICT (item_id) DO NOTHING
        RETURNING id
        """,
        index_id,
    )
    return len(rows)


def _build_classify_prompt(
    index_row: Dict[str, Any],
    targets: List[Dict[str, Any]],
    children_by_target: Dict[str, List[str]],
) -> str:
    """The Gemini pre-classification prompt for one batch of targets."""
    taxonomy = ", ".join(sorted(CATEGORIES.keys()))
    lines = []
    for t in targets:
        kids = children_by_target.get(str(t["id"]), [])
        kid_note = f" (contains sections: {', '.join(kids[:12])}{'…' if len(kids) > 12 else ''})" if kids else ""
        lines.append(f'- "{t["citation"]}": {t.get("heading") or "(no heading)"}{kid_note}')
    items_block = "\n".join(lines)

    return f"""You are classifying legal authority items for an employment/business compliance scope registry.

AUTHORITY INDEX: {index_row['name']}
Index domain (who this index broadly applies to): {', '.join(index_row.get('domain_categories') or []) or 'unspecified'}
Index domain excludes: {', '.join(index_row.get('domain_excludes') or []) or 'none'}

BUSINESS CATEGORY TAXONOMY (the ONLY allowed values for applies_to_categories / excludes_categories):
{taxonomy}

For EACH item below, decide exactly one disposition:
- "universal_in_domain" — applies to every business the index's domain covers (e.g. lockout/tagout applies across general industry).
- "category_specific" — applies only to specific business categories; set applies_to_categories.
- "conditional" — applies only when an entity attribute crosses a threshold; set entity_condition as {{"type":"attribute","key":"<attr>","operator":"gte|eq|...","value":<v>}} (e.g. FMLA: employee_count gte 50).
- "excluded" — definitional/administrative text with no employer obligation; set excluded_reason.

ITEMS:
{items_block}

Return ONLY a JSON object: {{"classifications": [{{"citation": "...", "disposition": "...", "applies_to_categories": [], "excludes_categories": [], "entity_condition": null, "excluded_reason": null, "rationale": "one sentence"}}]}}
Every citation above must appear exactly once. Do not invent regulation keys — omit regulation_key entirely unless you are certain of an existing catalog key."""


async def classify_index(conn, slug: str, *, proposed_by: str = "gemini") -> Dict[str, Any]:
    """Gemini pre-classification of an index's unclassified subpart-level items.

    Subparts are the classification unit; their child sections get materialized
    inheriting rows (``inherits_from_item_id``) so ``unclassified_count`` is
    honest. Items that are neither subparts nor children of one (curated CA
    rows, part-direct sections) are classified individually.

    Everything lands ``provisional``. Returns counts + per-item warnings —
    nothing is silently dropped.
    """
    from app.core.services.gemini_compliance import get_gemini_compliance_service

    index_row = await conn.fetchrow(
        "SELECT id, slug, name, domain_categories, domain_excludes "
        "FROM authority_indexes WHERE slug = $1",
        slug,
    )
    if index_row is None:
        raise ValueError(f"unknown authority index slug: {slug!r}")
    index = dict(index_row)

    # Sweep first: children whose parents were classified in an earlier run
    # (or by the seed) inherit now — otherwise they'd be unreachable below,
    # which only targets unclassified items.
    inherited = await materialize_inherited_children(conn, index["id"])

    items = [
        dict(r)
        for r in await conn.fetch(
            """
            SELECT i.id, i.citation, i.heading, i.parent_item_id
            FROM authority_index_items i
            LEFT JOIN authority_item_classifications c ON c.item_id = i.id
            WHERE i.authority_index_id = $1 AND c.id IS NULL
            ORDER BY i.citation
            """,
            index["id"],
        )
    ]
    if not items:
        return {"slug": slug, "classified": 0, "inherited": inherited, "warnings": [],
                "unclassified_count": await _refresh_unclassified_count(conn, index["id"])}

    # Classification targets: items with no parent (subparts + flat/curated
    # rows). Children of a target inherit its classification.
    by_id = {str(i["id"]): i for i in items}
    targets = [i for i in items if i["parent_item_id"] is None]
    children_by_target: Dict[str, List[str]] = {}
    for i in items:
        pid = str(i["parent_item_id"]) if i["parent_item_id"] else None
        if pid and pid in by_id:
            children_by_target.setdefault(pid, []).append(i["citation"])

    if not targets:
        # Only children of still-unclassified parents remain — nothing Gemini
        # can act on directly; don't waste the model call.
        return {"slug": slug, "classified": 0, "inherited": inherited,
                "warnings": ["no unclassified subpart-level targets"],
                "unclassified_count": await _refresh_unclassified_count(conn, index["id"])}

    service = get_gemini_compliance_service()
    rkd = await fetch_rkd_keys_by_category(conn)

    def _validate(data: Any) -> Optional[str]:
        if not isinstance(data, dict) or not isinstance(data.get("classifications"), list):
            return "response must be {\"classifications\": [...]}"
        return None

    data = await service._call_with_retry(
        _build_classify_prompt(index, targets, children_by_target),
        response_key=None,
        max_retries=1,
        validate_fn=_validate,
        label=f"scope-registry classify {slug}",
    )

    proposals_by_citation = {
        str(p.get("citation", "")).strip(): p
        for p in data.get("classifications", [])
        if isinstance(p, dict)
    }

    classified = 0
    warnings: List[str] = []
    target_norm: Dict[str, Dict[str, Any]] = {}

    for t in targets:
        proposal = proposals_by_citation.get(t["citation"])
        if proposal is None:
            warnings.append(f"{t['citation']}: no proposal returned — left unclassified")
            continue
        normalized, item_warnings = validate_proposal(proposal, rkd)
        warnings.extend(f"{t['citation']}: {w}" for w in item_warnings)
        if normalized is None:
            warnings.append(f"{t['citation']}: proposal rejected — left unclassified")
            continue
        await _upsert_classification(
            conn, t["id"], normalized, proposed_by=proposed_by, status="provisional"
        )
        target_norm[str(t["id"])] = normalized
        classified += 1

    # Materialize inheriting rows for the classified targets' children.
    for i in items:
        pid = str(i["parent_item_id"]) if i["parent_item_id"] else None
        if pid and pid in target_norm:
            await _upsert_classification(
                conn, i["id"], child_classification_of(target_norm[pid]),
                proposed_by=proposed_by,
                status="provisional", inherits_from_item_id=UUID(pid),
            )
            inherited += 1

    unclassified = await _refresh_unclassified_count(conn, index["id"])
    return {
        "slug": slug,
        "classified": classified,
        "inherited": inherited,
        "warnings": warnings,
        "unclassified_count": unclassified,
    }


async def confirm_classifications(conn, item_ids: List[UUID], admin_id: UUID) -> Dict[str, Any]:
    """Confirm provisional classifications; cascades to inheriting sections.

    Confirming a subpart is confirming its sections — the human decision is
    made at subpart level (plan §3). Triggers a strata recompute.
    """
    from .strata import recompute_strata

    # One outer transaction so a recompute failure rolls the confirms back —
    # confirmed rows must never sit unmaterialized. recompute_strata's own
    # transaction nests as a savepoint.
    async with conn.transaction():
        result = await conn.fetch(
            """
            UPDATE authority_item_classifications
            SET status = 'confirmed', confirmed_by = $2, confirmed_at = NOW()
            WHERE (item_id = ANY($1::uuid[]) OR inherits_from_item_id = ANY($1::uuid[]))
              AND status = 'provisional'
            RETURNING id
            """,
            item_ids, admin_id,
        )
        strata = await recompute_strata(conn)
    return {"confirmed": len(result), "strata": strata}


async def override_classification(
    conn, item_id: UUID, proposal: Dict[str, Any], admin_id: UUID
) -> Dict[str, Any]:
    """Manual admin classification — gates still apply; lands confirmed.

    Propagates to rows that still INHERIT from this item, so a subpart
    override can't silently diverge from its sections. Deliberate per-section
    overrides are protected by construction: an admin override writes
    ``inherits_from_item_id = NULL`` (severing the link), so the propagation
    target `inherits_from_item_id = item_id` never touches them.
    """
    from .strata import recompute_strata

    rkd = await fetch_rkd_keys_by_category(conn)
    normalized, warnings = validate_proposal(proposal, rkd)
    if normalized is None:
        raise ValueError("; ".join(warnings) or "invalid classification")

    exists = await conn.fetchval(
        "SELECT 1 FROM authority_index_items WHERE id = $1", item_id
    )
    if not exists:
        raise ValueError(f"unknown authority item: {item_id}")

    async with conn.transaction():
        await _upsert_classification(
            conn, item_id, normalized,
            proposed_by="admin", status="confirmed", confirmed_by=admin_id,
        )
        # Re-materialize still-inheriting children from the new content
        # (mirrors child_classification_of: everything copies except the key).
        propagated = await conn.fetch(
            """
            UPDATE authority_item_classifications
            SET disposition = $2, applies_to_categories = $3,
                excludes_categories = $4, entity_condition = $5::jsonb,
                excluded_reason = $6, regulation_key = NULL,
                key_definition_id = NULL, status = 'confirmed',
                proposed_by = 'admin', confirmed_by = $7, confirmed_at = NOW()
            WHERE inherits_from_item_id = $1
            RETURNING id
            """,
            item_id,
            normalized["disposition"],
            normalized["applies_to_categories"],
            normalized["excludes_categories"],
            json.dumps(normalized["entity_condition"]) if normalized["entity_condition"] else None,
            normalized["excluded_reason"],
            admin_id,
        )
        index_id = await conn.fetchval(
            "SELECT authority_index_id FROM authority_index_items WHERE id = $1", item_id
        )
        await _refresh_unclassified_count(conn, index_id)
        strata = await recompute_strata(conn)
    return {
        "item_id": str(item_id),
        "propagated_to_children": len(propagated),
        "warnings": warnings,
        "strata": strata,
    }
