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
from typing import Dict, List, Optional, Set, Tuple

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

    federal_id = None
    state_ids: Dict[str, object] = {}
    for j in jurs:
        if j["level"] in ("federal", "national"):
            federal_id = j["id"]
        elif j["level"] == "state" and j["state"]:
            state_ids[j["state"]] = j["id"]

    return {
        "jurisdictions": {j["id"]: dict(j) for j in jurs},
        "keys_by_jurisdiction": by_jur,
        "federal_id": federal_id,
        "state_ids": state_ids,
    }


def present_keys_for(graph: Dict, jurisdiction_id) -> Dict[str, Set[str]]:
    """Category → keys held at this jurisdiction ∪ its state ∪ federal."""
    jur = graph["jurisdictions"].get(jurisdiction_id)
    if not jur:
        return {}

    chain = [jurisdiction_id]
    if jur["level"] not in ("federal", "national"):
        state_id = graph["state_ids"].get(jur["state"])
        if state_id and state_id != jurisdiction_id:
            chain.append(state_id)
        if graph["federal_id"]:
            chain.append(graph["federal_id"])

    merged: Dict[str, Set[str]] = {}
    for jid in chain:
        for cat, keys in graph["keys_by_jurisdiction"].get(jid, {}).items():
            merged.setdefault(cat, set()).update(keys)
    return merged


async def evaluate_pair(
    conn,
    graph: Dict,
    jurisdiction_id,
    industry: Optional[str],
    weights_cache: Dict[str, Dict[str, float]],
) -> Tuple[Dict, List[Dict]]:
    """Score one (jurisdiction × industry) cell and emit its missing-key findings."""
    jur = graph["jurisdictions"][jurisdiction_id]
    country = jur.get("country_code") or "US"

    if industry not in weights_cache:
        weights_cache[industry or ""] = await iks.category_weights(conn, industry)
    weights = weights_cache.get(industry or "", {})

    expected = iks.expected_keys(industry, country_code=country)
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
    }
    return {"score": score, "detail": detail}, findings


async def run_completeness(
    conn,
    graph: Dict,
    jurisdiction_ids: List,
    industries: List[str],
) -> Dict:
    results: Dict = {}
    findings: List[Dict] = []
    weights_cache: Dict[str, Dict[str, float]] = {}

    for jid in jurisdiction_ids:
        for industry in industries:
            cell, cell_findings = await evaluate_pair(
                conn, graph, jid, industry, weights_cache
            )
            results[(jid, industry)] = cell
            findings.extend(cell_findings)

    return {"results": results, "findings": findings}
