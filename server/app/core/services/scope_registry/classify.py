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


from .resolve import SCOPE_LEVELS

# Phrasings Gemini/statutes use that the jurisdictions table does NOT store: it
# holds bare names ("Los Angeles", "Cook"), so strip the level word to match.
# Suffix stripping is county-only — a trailing "City" is part of many real city
# names (Kansas City, Salt Lake City) and must be kept.
_SCOPE_PREFIXES = {
    "county": ("county of ", "parish of ", "borough of "),
    "city": ("city of ", "town of ", "village of "),
}
_SCOPE_SUFFIXES = {
    "county": (" county", " parish", " borough"),
    "city": (),
}


def _jurisdiction_scope_shape_error(node: Any) -> Optional[str]:
    """Validate a jurisdiction_scope against ``{"level","names"}``. Pure.

    Shape: ``{"level": "county"|"city", "names": [non-empty str, ...]}``. Level is
    matched case-insensitively (the read-side matcher lowercases too, so the gate
    must not reject "County"). Returns an error string, or None when valid.
    """
    if not isinstance(node, dict):
        return "jurisdiction_scope must be an object"
    level = (node.get("level") or "").lower() if isinstance(node.get("level"), str) else node.get("level")
    if level not in SCOPE_LEVELS:
        return f"jurisdiction_scope level must be one of {SCOPE_LEVELS}, got {node.get('level')!r}"
    names = node.get("names")
    if not isinstance(names, list) or not names:
        return "jurisdiction_scope requires a non-empty names list"
    for n in names:
        if not isinstance(n, str) or not n.strip():
            return "jurisdiction_scope names must be non-empty strings"
    return None


def _canonicalize_scope_name(name: str, level: str) -> str:
    """Strip the level word so a name matches the jurisdictions table's bare form.

    'County of Los Angeles' / 'Los Angeles County' → 'Los Angeles'; 'City of
    Oakland' → 'Oakland'. Leaves an already-bare name and a genuine trailing word
    (Kansas City) alone. Display casing of the remainder is preserved.
    """
    s = name.strip()
    low = s.lower()
    for pre in _SCOPE_PREFIXES.get(level, ()):
        if low.startswith(pre):
            s = s[len(pre):].strip()
            low = s.lower()
            break
    for suf in _SCOPE_SUFFIXES.get(level, ()):
        if low.endswith(suf):
            s = s[: len(s) - len(suf)].strip()
            break
    return s


def _normalize_jurisdiction_scope(node: Dict[str, Any]) -> Dict[str, Any]:
    """Lowercase the level; canonicalize + trim/dedupe/sort names (display casing
    preserved). Assumes shape-valid."""
    level = node["level"].lower()
    seen: Dict[str, str] = {}
    for n in node["names"]:
        canon = _canonicalize_scope_name(n, level)
        if canon:
            seen.setdefault(canon.lower(), canon)
    return {"level": level, "names": [seen[k] for k in sorted(seen)]}


def resolve_regulation_key(
    raw_key: Any,
    raw_category: Any,
    rkd_keys_by_category: Dict[str, Set[str]],
) -> Tuple[Optional[str], List[str]]:
    """Gate one proposed regulation_key against the RKD. Never invents.

    An unknown key is a non-fatal DOWNGRADE to NULL (applicable-but-uncodified,
    which is the fetch queue's whole purpose), not a rejection — the rest of the
    proposal may be perfectly good.

    Shared by :func:`validate_proposal` (the disposition pass) and
    :func:`propose_keys_for_index` (the key pass) so the two cannot drift into
    disagreeing about what counts as a real key.
    """
    warnings: List[str] = []
    regulation_key = (str(raw_key).strip() if raw_key else "") or None
    if regulation_key is None:
        return None, warnings

    category_slug = (str(raw_category).strip() if raw_category else "") or None
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
        return None, warnings
    return regulation_key, warnings


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

    # Sub-index jurisdiction scope (optional; narrows the item's own reach).
    # A bad scope is a non-fatal DOWNGRADE, not a rejection: it's an optional
    # annotation, so discarding it (with a warning) preserves the otherwise-valid
    # disposition — the same policy as an unknown regulation_key above. Rejecting
    # the whole proposal would leave a correctly-classified item unclassified.
    jurisdiction_scope = proposal.get("jurisdiction_scope")
    if jurisdiction_scope is not None:
        if disposition == "excluded":
            # An excluded item applies to no one — a scope on it is meaningless,
            # not a value worth keeping. Drop it silently.
            jurisdiction_scope = None
        else:
            err = _jurisdiction_scope_shape_error(jurisdiction_scope)
            if err:
                warnings.append(f"{err} — dropped (item stored without a sub-jurisdiction scope)")
                jurisdiction_scope = None
            else:
                jurisdiction_scope = _normalize_jurisdiction_scope(jurisdiction_scope)

    regulation_key, key_warnings = resolve_regulation_key(
        proposal.get("regulation_key"),
        proposal.get("category_slug"),
        rkd_keys_by_category,
    )
    warnings.extend(key_warnings)

    return (
        {
            "disposition": disposition,
            "applies_to_categories": applies_to,
            "excludes_categories": excludes,
            "entity_condition": entity_condition if disposition == "conditional" else None,
            "excluded_reason": (proposal.get("excluded_reason") or "").strip() or None,
            "regulation_key": regulation_key,
            "category_slug": (proposal.get("category_slug") or "").strip() or None,
            "jurisdiction_scope": jurisdiction_scope,
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
             inherits_from_item_id, status, proposed_by, confirmed_by, confirmed_at,
             jurisdiction_scope)
        VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7,
                (SELECT id FROM regulation_key_definitions
                 WHERE key = $7 AND ($12::text IS NULL OR category_slug = $12)
                 ORDER BY category_slug LIMIT 1),
                $8, $9::text, $10, $11,
                CASE WHEN $9::text = 'confirmed' THEN NOW() ELSE NULL END,
                $13::jsonb)
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
            confirmed_at = EXCLUDED.confirmed_at,
            jurisdiction_scope = EXCLUDED.jurisdiction_scope
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
        json.dumps(normalized["jurisdiction_scope"]) if normalized.get("jurisdiction_scope") else None,
    )


async def _refresh_unclassified_count(conn, index_id) -> int:
    # Must match registry_expected_keys' own denominator (confirmed-only,
    # completeness.py) — counting "has any classification row" instead of
    # "has a CONFIRMED classification row" lets a classified-but-unconfirmed
    # index read unclassified_count=0, opening the completeness gate while
    # the expected-keys query then silently serves a shrunken confirmed-only
    # set as if it were the full registry (completeness reads inflated).
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
        # A subpart scoped to named counties/cities scopes its sections too.
        "jurisdiction_scope": parent.get("jurisdiction_scope"),
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
             inherits_from_item_id, status, proposed_by, confirmed_by, confirmed_at,
             jurisdiction_scope)
        SELECT child.id, pc.disposition, pc.applies_to_categories,
               pc.excludes_categories, pc.entity_condition, pc.excluded_reason,
               NULL, NULL,
               pc.item_id, pc.status, pc.proposed_by, pc.confirmed_by, pc.confirmed_at,
               pc.jurisdiction_scope
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

If — and ONLY if — an item's own citation or heading limits it to specific named counties or cities (not the whole index's jurisdiction), set "jurisdiction_scope" to {{"level":"county"|"city","names":["Exact Name",...]}}. Otherwise use null. Do not infer a narrowing that the text does not state — null (whole-index reach) is the safe default.

ITEMS:
{items_block}

Return ONLY a JSON object: {{"classifications": [{{"citation": "...", "disposition": "...", "applies_to_categories": [], "excludes_categories": [], "entity_condition": null, "excluded_reason": null, "jurisdiction_scope": null, "rationale": "one sentence"}}]}}
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

    from .authority_sources import is_penalty_schedule

    if is_penalty_schedule(slug):
        # A penalty schedule imposes no employer duty — there is nothing to give
        # a disposition to. Every section would land `excluded`, and the index
        # would then sit in the unclassified queue forever.
        return {"slug": slug, "classified": 0, "inherited": 0,
                "warnings": ["penalty-schedule index — not classifiable"],
                "unclassified_count": 0}

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


async def fetch_rkd_catalog(conn) -> List[Dict[str, Any]]:
    """The RKD vocabulary as prompt material: key, category, human name."""
    rows = await conn.fetch(
        "SELECT key, category_slug, name FROM regulation_key_definitions "
        "ORDER BY category_slug, key"
    )
    return [dict(r) for r in rows]


def _build_key_prompt(
    index_row: Dict[str, Any],
    items: List[Dict[str, Any]],
    rkd_rows: List[Dict[str, Any]],
) -> str:
    """Prompt for the key pass: map each authority section to ONE registry key.

    Deliberately a different question from `_build_classify_prompt`, which asks
    *who* an item applies to. This asks *which obligation it is* — and that is a
    per-section fact, so unlike disposition it cannot be inherited from a
    subpart (29 CFR 1910 Subpart J holds both lockout/tagout and confined
    spaces; one key across both would be a lie).
    """
    by_cat: Dict[str, List[str]] = {}
    for r in rkd_rows:
        by_cat.setdefault(r["category_slug"], []).append(f'{r["key"]} ({r["name"]})')
    vocab = "\n".join(
        f"  {cat}:\n" + "\n".join(f"    - {k}" for k in keys)
        for cat, keys in sorted(by_cat.items())
    )
    items_block = "\n".join(
        f'- "{i["citation"]}": {i.get("heading") or "(no heading)"}' for i in items
    )
    return f"""You are mapping legal authority sections to a compliance registry's obligation keys.

AUTHORITY INDEX: {index_row['name']}

REGISTRY VOCABULARY — the ONLY keys that exist, grouped by category_slug:
{vocab}

For EACH authority section below, decide which SINGLE registry key it is the legal authority for.

Rules:
- The key must be copied EXACTLY from the vocabulary above, together with the category_slug it is listed under.
- Most sections map to NOTHING. Definitions, scope/purpose text, appendices, recordkeeping minutiae and
  administrative provisions have no key — return null. A wrong mapping cites the wrong statute at a
  business, which is worse than no mapping at all.
- Map a section only when it is the PRIMARY authority for that obligation, not merely related to it.
  Example: 29 CFR 1910.147 is the primary authority for lockout_tagout; 29 CFR 1910.333 mentions
  the same practice but is not its primary authority — return null for the latter.
- AT MOST ONE section per key. Where several sections elaborate the same obligation, give the key to the
  single most authoritative one and null to the rest. Example: for injury_illness_recordkeeping across
  29 CFR 1904, the key belongs on the general recording-criteria section, NOT on each narrow
  case-type section (hearing loss, needlesticks, tuberculosis) that merely applies it.
- Never invent a key. If nothing in the vocabulary fits, return null.

SECTIONS:
{items_block}

Return ONLY a JSON object:
{{"keys": [{{"citation": "...", "regulation_key": "..." or null, "category_slug": "..." or null, "confidence": "high"|"medium"|"low", "rationale": "one short sentence"}}]}}
Every citation above must appear exactly once."""


def dedupe_key_claims(
    accepted: List[Dict[str, Any]],
    already: Set[str],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """One key, one section. Pick the single winner per key. Pure.

    The prompt asks the model for this, but a model that ignores it would hand
    :func:`select_primary_citation` a pile of same-key candidates and let a
    lexicographic tie-break choose the citation a business reads — which is how
    "29 CFR 1904.10" (hearing-loss recording) ends up cited as the authority for
    all injury recordkeeping.

    Precedence:
      1. confidence (the model's own judgement first)
      2. **section over subpart** — the obligation-bearing unit is the section
         (29 CFR 1910.212), not the subpart that contains it (Subpart O).
         Citation order alone gets this exactly backwards: a space sorts before
         a period, so ``"29 CFR 1910 Subpart O" < "29 CFR 1910.212"`` and the
         coarser item wins — the opposite of `select_primary_citation`'s
         deepest-hierarchy rule.
      3. citation, so the outcome is deterministic across runs.

    ``already`` is the set of keys this index carries from an EARLIER run. It
    makes the pass idempotent: without it a second run hands the same key to a
    second section (29 CFR 1904.4 *and* 1904.7 both claiming
    injury_illness_recordkeeping), the very pile-up the dedupe exists to stop.
    Note this is one-way — a key already parked on a subpart is not re-opened
    by a later run, so fixing a bad winner means clearing the key first.
    """
    rank = {"high": 0, "medium": 1, "low": 2}
    warnings: List[str] = []
    best_by_key: Dict[str, Dict[str, Any]] = {}

    for a in sorted(
        accepted,
        key=lambda x: (rank.get(x["confidence"], 3), not x.get("is_section"), x["citation"]),
    ):
        if a["key"] in already:
            warnings.append(
                f"{a['citation']}: {a['key']!r} already held by another section "
                f"in this index — skipped"
            )
            continue
        if a["key"] in best_by_key:
            warnings.append(
                f"{a['citation']}: {a['key']!r} already claimed by "
                f"{best_by_key[a['key']]['citation']} — skipped"
            )
            continue
        best_by_key[a["key"]] = a

    return list(best_by_key.values()), warnings


async def propose_keys_for_index(
    conn,
    slug: str,
    *,
    batch_size: int = 40,
    min_confidence: str = "medium",
) -> Dict[str, Any]:
    """Second classification pass: fill ``regulation_key`` on an index's items.

    Why this exists: the disposition pass classifies **subparts** and lets
    sections inherit, but `child_classification_of` deliberately drops the key
    on inheritance (keys are per-obligation). The result was that no
    Gemini-classified section ever carried a key — 353 classifications, zero
    keys — and `match_codifications` skips NULL-key rows, so nothing the AI
    touched could ever codify. Every key in the database had been hand-seeded.

    Runs over targets AND children, since the obligation-bearing unit is
    usually the section (29 CFR 1910.147), not the subpart that contains it.
    Skips ``excluded`` items — an item with no employer obligation has no key
    by definition.

    Lands keys on rows that stay ``provisional``: this proposes, a human still
    confirms. Unknown keys are downgraded to NULL by the shared RKD gate.
    """
    from app.core.services.gemini_compliance import get_gemini_compliance_service

    from .authority_sources import is_penalty_schedule

    if is_penalty_schedule(slug):
        # Keys name obligations. A penalty schedule is the authority for what a
        # breach COSTS, never for the obligation itself — it binds via
        # penalty_item_id, not regulation_key.
        return {"slug": slug, "considered": 0, "proposed": 0, "keyed": 0,
                "warnings": ["penalty-schedule index — carries no obligation keys"]}

    index_row = await conn.fetchrow(
        "SELECT id, slug, name FROM authority_indexes WHERE slug = $1", slug
    )
    if index_row is None:
        raise ValueError(f"unknown authority index slug: {slug!r}")
    index = dict(index_row)

    items = [
        dict(r)
        for r in await conn.fetch(
            """
            SELECT i.id, i.citation, i.heading,
                   i.parent_item_id IS NOT NULL AS is_section
            FROM authority_index_items i
            JOIN authority_item_classifications c ON c.item_id = i.id
            WHERE i.authority_index_id = $1
              AND c.regulation_key IS NULL
              AND c.disposition <> 'excluded'
            ORDER BY i.citation
            """,
            index["id"],
        )
    ]
    if not items:
        return {"slug": slug, "considered": 0, "proposed": 0, "keyed": 0, "warnings": []}

    rkd_rows = await fetch_rkd_catalog(conn)
    rkd = await fetch_rkd_keys_by_category(conn)
    service = get_gemini_compliance_service()

    def _validate(data: Any) -> Optional[str]:
        if not isinstance(data, dict) or not isinstance(data.get("keys"), list):
            return 'response must be {"keys": [...]}'
        return None

    allowed_confidence = {
        "high": {"high"},
        "medium": {"high", "medium"},
        "low": {"high", "medium", "low"},
    }.get(min_confidence, {"high", "medium"})
    warnings: List[str] = []
    accepted: List[Dict[str, Any]] = []

    # Collect every batch BEFORE writing: the one-section-per-key rule can only
    # be enforced with the whole index in hand, and batching splits it.
    for start in range(0, len(items), batch_size):
        batch = items[start:start + batch_size]
        by_citation = {i["citation"]: i for i in batch}
        try:
            data = await service._call_with_retry(
                _build_key_prompt(index, batch, rkd_rows),
                response_key=None,
                max_retries=1,
                validate_fn=_validate,
                label=f"scope-registry keys {slug} [{start}:{start + len(batch)}]",
            )
        except Exception as exc:  # noqa: BLE001 — one bad batch must not lose the rest
            warnings.append(f"batch {start}: {type(exc).__name__}: {exc}")
            continue

        for prop in data.get("keys", []):
            if not isinstance(prop, dict):
                continue
            citation = str(prop.get("citation", "")).strip()
            item = by_citation.get(citation)
            if item is None:
                # A citation we did not send. Never trust a model-authored
                # citation onto a row — that is how a key lands on the wrong law.
                warnings.append(f"{citation!r}: not in this batch — ignored")
                continue
            if prop.get("regulation_key") is None:
                continue
            confidence = str(prop.get("confidence", "")).lower()
            if confidence not in allowed_confidence:
                warnings.append(
                    f"{citation}: {prop.get('regulation_key')!r} dropped "
                    f"(confidence {prop.get('confidence')!r})"
                )
                continue
            key, key_warnings = resolve_regulation_key(
                prop.get("regulation_key"), prop.get("category_slug"), rkd
            )
            warnings.extend(f"{citation}: {w}" for w in key_warnings)
            if key is None:
                continue
            accepted.append({
                "item_id": item["id"], "citation": citation, "key": key,
                "category_slug": (prop.get("category_slug") or "").strip() or None,
                "confidence": confidence,
                "is_section": item["is_section"],
            })

    already: Set[str] = {
        r["regulation_key"]
        for r in await conn.fetch(
            """
            SELECT DISTINCT c.regulation_key
            FROM authority_item_classifications c
            JOIN authority_index_items i ON i.id = c.item_id
            WHERE i.authority_index_id = $1 AND c.regulation_key IS NOT NULL
            """,
            index["id"],
        )
    }
    winners, dedupe_warnings = dedupe_key_claims(accepted, already)
    warnings.extend(dedupe_warnings)

    keyed = 0
    for a in winners:
        # key_definition_id resolves from (key, category) so the category guard
        # in match_codifications has something live to check.
        updated = await conn.fetchval(
            """
            UPDATE authority_item_classifications
            SET regulation_key = $2,
                key_definition_id = (
                    SELECT id FROM regulation_key_definitions
                    WHERE key = $2 AND ($3::text IS NULL OR category_slug = $3)
                    ORDER BY category_slug LIMIT 1
                )
            WHERE item_id = $1 AND regulation_key IS NULL
            RETURNING id
            """,
            a["item_id"], a["key"], a["category_slug"],
        )
        if updated:
            keyed += 1

    return {
        "slug": slug, "considered": len(items), "proposed": len(accepted),
        "keyed": keyed, "warnings": warnings,
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
    from .resolve import parse_jsonb

    # PATCH semantics: an override that doesn't mention jurisdiction_scope or
    # entity_condition keeps the existing one, rather than defaulting it to None.
    # An explicit null still clears.
    #
    # jurisdiction_scope: defaulting to None would WIDEN a narrowed
    # classification to whole-index reach.
    #
    # entity_condition: defaulting to None is worse. `conditional` is REJECTED
    # by validate_proposal without a valid condition, so an editor that can't
    # re-supply it simply cannot save a conditional item at all — and the
    # tempting workaround (flip the disposition to universal_in_domain just to
    # get a key stored) silently WIPES the trigger and serves e.g. the PSM
    # standard to every company. That is exactly the over-scope the §9
    # acceptance test exists to prevent.
    missing = [
        f for f in ("jurisdiction_scope", "entity_condition") if f not in proposal
    ]
    if missing:
        row = await conn.fetchrow(
            "SELECT jurisdiction_scope, entity_condition "
            "FROM authority_item_classifications WHERE item_id = $1",
            item_id,
        )
        proposal = {
            **proposal,
            **{f: parse_jsonb(row[f]) if row else None for f in missing},
        }

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
                proposed_by = 'admin', confirmed_by = $7, confirmed_at = NOW(),
                jurisdiction_scope = $8::jsonb
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
            json.dumps(normalized["jurisdiction_scope"]) if normalized.get("jurisdiction_scope") else None,
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
