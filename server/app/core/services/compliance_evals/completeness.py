"""Completeness suite — does (jurisdiction × industry) have the keys it needs?

Presence is inheritance-aware: a key counts for Los Angeles if it exists on the
Los Angeles row, on the California row, or on the federal row. That union is also
why no preemption filter is needed here. Preemption decides *which level governs*
a requirement, not whether we hold data for it — and when a state preempts local
minimum-wage ordinances, the state row is exactly where the key is supposed to
live, so the union already reflects the correct expectation.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from . import industry_keysets as iks
from .keys import normalize_key
from .scoring import completeness_score, missing_keys

logger = logging.getLogger(__name__)


def _bare_key(regulation_key: Optional[str], requirement_key: Optional[str]) -> Optional[str]:
    """The regulation key, tolerating rows written before `regulation_key` existed.

    `requirement_key` is the composite `category:regulation_key`; older rows only
    have that.
    """
    if regulation_key:
        return regulation_key
    if requirement_key and ":" in requirement_key:
        return requirement_key.rsplit(":", 1)[-1]
    return requirement_key or None


async def load_jurisdiction_graph(conn) -> Dict:
    """Everything the presence union needs, in two queries."""
    jurs = await conn.fetch("""
        SELECT id, city, state, country_code, level::text AS level, display_name
        FROM jurisdictions
    """)
    reqs = await conn.fetch("""
        SELECT jr.jurisdiction_id, jr.category, jr.regulation_key, jr.requirement_key,
               j.level::text AS level, COALESCE(j.country_code, 'US') AS country_code
        FROM jurisdiction_requirements jr
        JOIN jurisdictions j ON j.id = jr.jurisdiction_id
    """)

    by_jur: Dict = {}
    for r in reqs:
        key = _bare_key(r["regulation_key"], r["requirement_key"])
        if not key or not r["category"]:
            continue
        key = normalize_key(r["category"], key, r["level"], r["country_code"])
        by_jur.setdefault(r["jurisdiction_id"], {}).setdefault(r["category"], set()).add(key)

    # `federal` and `national` are NOT synonyms in this table: `federal` is the
    # single US row, while `national` rows are the country roots for the UK,
    # Mexico, and Singapore. Treating them as one bucket let a US city inherit
    # from the United Kingdom (and, since the UK row is empty, silently lose the
    # 50 real federal requirements — whichever row the query returned last won).
    federal_id = None
    national_ids: Dict[str, object] = {}
    state_ids: Dict[str, object] = {}
    for j in jurs:
        if j["level"] == "federal":
            federal_id = j["id"]
        elif j["level"] == "national":
            national_ids[j["country_code"] or "US"] = j["id"]
        elif j["level"] == "state" and j["state"]:
            state_ids[j["state"]] = j["id"]

    return {
        "jurisdictions": {j["id"]: dict(j) for j in jurs},
        "keys_by_jurisdiction": by_jur,
        "federal_id": federal_id,
        "national_ids": national_ids,
        "state_ids": state_ids,
    }


def chain_ids_for(graph: Dict, jurisdiction_id) -> List:
    """This jurisdiction ∪ its state ∪ its country root — the inheritance chain.

    The country root is the `federal` row for US jurisdictions and the matching
    `national` row otherwise — a US city must never inherit UK law, nor a UK one
    inherit the FLSA.
    """
    jur = graph["jurisdictions"].get(jurisdiction_id)
    if not jur:
        return []

    chain = [jurisdiction_id]
    if jur["level"] not in ("federal", "national"):
        state_id = graph["state_ids"].get(jur["state"])
        if state_id and state_id != jurisdiction_id:
            chain.append(state_id)

        country = jur.get("country_code") or "US"
        root = (
            graph.get("federal_id")
            if country == "US"
            else graph.get("national_ids", {}).get(country)
        )
        if root:
            chain.append(root)
    return chain


def present_keys_for(graph: Dict, jurisdiction_id) -> Dict[str, Set[str]]:
    """Category → keys held at this jurisdiction ∪ its state ∪ its country root."""
    merged: Dict[str, Set[str]] = {}
    for jid in chain_ids_for(graph, jurisdiction_id):
        for cat, keys in graph["keys_by_jurisdiction"].get(jid, {}).items():
            merged.setdefault(cat, set()).update(keys)
    return merged


async def registry_expected_keys(
    conn, chain_ids: List, industry: Optional[str]
) -> Optional[Dict[str, Set[str]]]:
    """Expected keys from the scope registry, when it covers this coordinate.

    The plan's denominator fix (§10): where confirmed strata exist for the
    industry's business-category in this jurisdiction's chain, the *expected*
    set is the registry's classified regulation keys — a grounded, cited
    worklist — instead of `industry_keysets`' registry category-groups (a
    taxonomy artifact that demands EU works-council rules of a machine shop).

    ``chain_ids`` is the jurisdiction inheritance chain (from
    :func:`chain_ids_for`), so a curated state index is matched even when a
    county sits between the city and the state. Returns ``None`` when no
    confirmed strata cover the coordinate, so the caller falls back to the
    current behavior unchanged — until classification happens on a
    jurisdiction, nothing here alters a single score.
    """
    try:
        from app.core.services.scope_registry.categories import ancestry, resolve_category
    except Exception:
        return None

    slug = resolve_category(industry) if industry else None
    chain = ancestry(slug) if slug else []
    if not chain:
        return None

    # Only trust the registry denominator when the covering indexes are
    # DEFINITIVELY scoped (plan §10: unclassified_count = 0). During partial
    # classification the resolved set is a subset of the true scope, so using
    # it as `expected` would shrink the denominator and inflate completeness.
    # Any unclassified item in a covering index ⇒ fall back to category-groups.
    #
    # This stays all-or-nothing ON PURPOSE, and it is not the gap the review
    # thought it was: an *unclassified* item has, by definition, no category
    # yet, so there is no sound way to say which categories it would or
    # wouldn't have added keys to. Any per-category relaxation here would be
    # guessing, and guessing low inflates completeness — the exact failure the
    # gate exists to prevent. What WAS wrong is that a partial registry made
    # the *overlay* go dark too; that's fixed in
    # registry_expected_keys_partial below, which is honest about its
    # confidence instead of silent.
    covering = await conn.fetch(
        "SELECT unclassified_count FROM authority_indexes "
        "WHERE jurisdiction_id IS NULL OR jurisdiction_id = ANY($1::uuid[])",
        list(chain_ids),
    )
    if not covering or any(c["unclassified_count"] > 0 for c in covering):
        return None

    # Confirmed classifications whose index covers this jurisdiction chain
    # (federal NULL always applies) and whose disposition selects the category.
    rows = await conn.fetch(
        """
        SELECT c.regulation_key, c.disposition, c.applies_to_categories,
               c.excludes_categories, kd.category_slug
        FROM authority_item_classifications c
        JOIN authority_index_items i ON i.id = c.item_id
        JOIN authority_indexes ai ON ai.id = i.authority_index_id
        LEFT JOIN regulation_key_definitions kd ON kd.id = c.key_definition_id
        WHERE c.status = 'confirmed'
          AND c.disposition <> 'excluded'
          AND c.regulation_key IS NOT NULL
          AND (ai.jurisdiction_id IS NULL OR ai.jurisdiction_id = ANY($1::uuid[]))
        """,
        list(chain_ids),
    )
    return _select_expected(rows, chain) or None


def _select_expected(rows, chain: List[str]) -> Dict[str, Set[str]]:
    """Confirmed classifications → {category: {regulation_key}} for this chain."""
    chain_set = set(chain)
    expected: Dict[str, Set[str]] = {}
    for r in rows:
        applies = set(r["applies_to_categories"] or [])
        excludes = set(r["excludes_categories"] or [])
        if excludes & chain_set:
            continue
        if r["disposition"] != "universal_in_domain" and applies and not (applies & chain_set):
            continue
        cat = r["category_slug"] or "uncategorized"
        expected.setdefault(cat, set()).add(r["regulation_key"])
    return expected


async def registry_expected_keys_partial(
    conn, chain_ids: List, industry: Optional[str],
) -> Dict[str, Any]:
    """Registry expected-keys WITHOUT the definitiveness gate, plus the
    confidence to render it honestly.

    Returns ``{"expected": {...}|None, "definitive": bool, "unclassified": int}``.

    ``definitive=True`` means every covering index is fully confirmed-classified
    — the expected set is the complete scope, and it's the same set
    :func:`registry_expected_keys` returns. ``definitive=False`` means it's a
    **floor**: these keys really are in scope (they're confirmed), but
    unclassified items may add more. A floor is still worth showing — "at least
    these N obligations, N unclassified items still to review" beats rendering
    nothing, which is what the all-or-nothing gate did to the whole engine
    overlay (COMPLIANCE_SYSTEM_GAP_REVIEW.md §4). It must never be used as a
    completeness *denominator*; see the note in registry_expected_keys.
    """
    try:
        from app.core.services.scope_registry.categories import ancestry, resolve_category
    except Exception:
        return {"expected": None, "definitive": False, "unclassified": 0}

    slug = resolve_category(industry) if industry else None
    chain = ancestry(slug) if slug else []
    if not chain:
        return {"expected": None, "definitive": False, "unclassified": 0}

    covering = await conn.fetch(
        "SELECT unclassified_count FROM authority_indexes "
        "WHERE jurisdiction_id IS NULL OR jurisdiction_id = ANY($1::uuid[])",
        list(chain_ids),
    )
    if not covering:
        return {"expected": None, "definitive": False, "unclassified": 0}
    unclassified = sum(c["unclassified_count"] or 0 for c in covering)

    rows = await conn.fetch(
        """
        SELECT c.regulation_key, c.disposition, c.applies_to_categories,
               c.excludes_categories, kd.category_slug
        FROM authority_item_classifications c
        JOIN authority_index_items i ON i.id = c.item_id
        JOIN authority_indexes ai ON ai.id = i.authority_index_id
        LEFT JOIN regulation_key_definitions kd ON kd.id = c.key_definition_id
        WHERE c.status = 'confirmed'
          AND c.disposition <> 'excluded'
          AND c.regulation_key IS NOT NULL
          AND (ai.jurisdiction_id IS NULL OR ai.jurisdiction_id = ANY($1::uuid[]))
        """,
        list(chain_ids),
    )
    expected = _select_expected(rows, chain)
    return {
        "expected": expected or None,
        "definitive": unclassified == 0,
        "unclassified": unclassified,
    }


async def registry_has_confirmed_classifications(conn) -> bool:
    """Cheap one-shot: is the scope registry live at all?

    Lets a full eval skip the per-(jurisdiction×industry) registry query when
    nothing is classified yet (the state everywhere until authoring happens),
    and degrades to False when `scoperg01` isn't applied — the completeness
    suite must run on a DB without the scope-registry tables.
    """
    try:
        return bool(await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM authority_item_classifications "
            "WHERE status = 'confirmed')"
        ))
    except Exception:
        return False


async def evaluate_pair(
    conn,
    graph: Dict,
    jurisdiction_id,
    industry: Optional[str],
    weights_cache: Dict[str, Dict[str, float]],
    *,
    registry_active: bool = True,
) -> Tuple[Dict, List[Dict]]:
    """Score one (jurisdiction × industry) cell and emit its missing-key findings.

    ``registry_active`` lets the caller skip the registry-expected lookup in bulk
    when no confirmed classifications exist (see run_completeness).
    """
    jur = graph["jurisdictions"][jurisdiction_id]
    country = jur.get("country_code") or "US"

    if industry not in weights_cache:
        weights_cache[industry or ""] = await iks.category_weights(conn, industry)
    weights = weights_cache.get(industry or "", {})

    # Prefer the registry's grounded scope where it covers this coordinate;
    # otherwise fall back to the category-group expectation (labeled honestly).
    registry_expected = (
        await registry_expected_keys(conn, chain_ids_for(graph, jurisdiction_id), industry)
        if registry_active
        else None
    )
    if registry_expected is not None:
        expected = registry_expected
        expectation_source = "registry"
    else:
        expected = iks.expected_keys(industry, country_code=country)
        expectation_source = "registry_groups"
    present = present_keys_for(graph, jurisdiction_id)
    focused = iks.focused_categories(industry, weights)

    score = completeness_score(present, expected, weights)
    gaps = missing_keys(present, expected)

    findings: List[Dict] = []
    for cat, keys in gaps.items():
        is_focused = cat in focused
        for key in keys:
            findings.append({
                "suite": "completeness",
                "finding_type": "missing_key",
                "severity": "critical" if is_focused else "warn",
                "jurisdiction_id": jurisdiction_id,
                "requirement_key": key,
                "category": cat,
                "industry": industry,
                "expected": {"regulation_key": key, "focused_category": is_focused},
                "observed": {"present": False},
            })

    focused_complete = all(cat not in gaps for cat in focused if cat in expected)

    detail = {
        "missing_keys": gaps,
        "expected_key_count": sum(len(v) for v in expected.values()),
        "present_key_count": sum(len(expected[c] & present.get(c, set())) for c in expected),
        "focused_categories": sorted(focused),
        "focused_keys_complete": focused_complete,
        "country_code": country,
        # 'registry' = grounded strata; 'registry_groups' = the taxonomy-artifact
        # fallback the plan flags as an unfounded denominator.
        "expectation_source": expectation_source,
    }
    return {"score": score, "detail": detail}, findings


def core_checklist(graph: Dict, jurisdiction_id, industry: str) -> Dict:
    """The ≤30-key must-have list as an explicit per-key verdict.

    Unlike the full-depth score (201 keys for manufacturing — unauditable by
    hand), this returns every key with its own present/missing flag so a human
    can read the whole thing and judge whether the *eval* is right, not just
    whether the data is. Every miss is critical by construction: the core set
    only contains keys whose absence is unambiguous.
    """
    present = present_keys_for(graph, jurisdiction_id)
    expected = iks.core_keys(industry)

    items: List[Dict] = []
    hits = 0
    for cat in sorted(expected):
        for key in sorted(expected[cat]):
            ok = key in present.get(cat, set())
            hits += ok
            items.append({"category": cat, "key": key, "present": ok})

    total = len(items)
    return {
        "score": round(100.0 * hits / total, 2) if total else 0.0,
        "present": hits,
        "total": total,
        "complete": hits == total,
        "items": items,
    }


async def run_completeness(
    conn,
    graph: Dict,
    jurisdiction_ids: List,
    industries: List[str],
) -> Dict:
    results: Dict = {}
    findings: List[Dict] = []
    weights_cache: Dict[str, Dict[str, float]] = {}
    registry_active = await registry_has_confirmed_classifications(conn)

    for jid in jurisdiction_ids:
        for industry in industries:
            cell, cell_findings = await evaluate_pair(
                conn, graph, jid, industry, weights_cache,
                registry_active=registry_active,
            )
            results[(jid, industry)] = cell
            findings.extend(cell_findings)

    return {"results": results, "findings": findings}
