"""Baseline suite — score federal + CA-state against the enumerated labor master-list.

Every other suite measures the catalog against an *emergent* expectation (whatever
keys research produced). This one measures the two base-layer jurisdictions against a
*fixed, hand-cited* list (`baseline_masterlist.py`) — the only suite that can answer
"is federal labor actually done?" with a number instead of a vibe.

It scores each base jurisdiction's OWN rows (not the inherited chain union): the point
is whether the base layer itself exists, since every city inherits it. A master-list
key with no matching catalog row for that jurisdiction is a critical
`baseline_missing_key` finding carrying the citation to research next.

Read-only over the catalog. The diff (`diff_masterlist`) is pure and unit-tests
without a DB.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from .baseline_masterlist import (
    BASELINE_JURISDICTIONS,
    BaselineObligation,
    masterlist_keys,
)
from .golden import _rows_for
from .scoring import baseline_score

logger = logging.getLogger(__name__)


async def resolve_baseline_jid(conn, spec: Dict[str, Any]) -> Optional[Any]:
    """Resolve a baseline spec to a jurisdiction id — US-pinned.

    NOT golden._resolve_jurisdiction_id: that resolves federal as
    ``level IN ('federal','national') LIMIT 1``, which can return a foreign
    ``national`` row (UK/Mexico/Singapore all share that level). The baseline is US
    labor law, so federal must pin ``country_code='US'``.
    """
    if spec["level"] == "federal":
        row = await conn.fetchrow(
            "SELECT id FROM jurisdictions WHERE level::text = 'federal' "
            "AND COALESCE(country_code,'US') = 'US' LIMIT 1"
        )
    else:  # state
        row = await conn.fetchrow(
            "SELECT id FROM jurisdictions WHERE level::text = 'state' "
            "AND state = $1 AND COALESCE(country_code,'US') = 'US' LIMIT 1",
            spec.get("state"),
        )
    return row["id"] if row else None


def diff_masterlist(
    entries: List[BaselineObligation],
    present_keys: set,
) -> Tuple[List[BaselineObligation], List[BaselineObligation]]:
    """Split a master-list into (present, missing) against a jurisdiction's
    ``category:key`` set. Pure — ``present_keys`` is what the caller resolved from
    the catalog rows. Order-preserving."""
    present, missing = [], []
    for e in entries:
        (present if f"{e.category}:{e.key}" in present_keys else missing).append(e)
    return present, missing


async def run_baseline(conn) -> Dict:
    """Score the federal + CA-state jurisdictions against the labor master-list.

    Returns ``{results: {jid: {score, detail}}, findings, totals}``. Missing keys are
    ``critical`` findings and block the readiness gate through the runner's
    open-critical count — same path every suite uses.
    """
    findings: List[Dict] = []
    results: Dict = {}
    totals: Dict[str, int] = {}

    for spec in BASELINE_JURISDICTIONS:
        jid = await resolve_baseline_jid(conn, spec)
        if jid is None:
            logger.warning("baseline: jurisdiction not found for %s", spec["label"])
            continue

        # OWN rows only, indexed exactly like golden (category:normalized_key).
        catalog = await _rows_for(conn, jid)  # {f"{cat}:{normkey}": row}
        present_keys = set(catalog.keys())

        entries = spec["entries"]
        present, missing = diff_masterlist(entries, present_keys)

        label = spec["label"]
        totals[f"{label}_expected"] = len(entries)
        totals[f"{label}_present"] = len(present)

        for e in missing:
            findings.append({
                "suite": "baseline", "finding_type": "baseline_missing_key",
                "severity": "critical",
                "jurisdiction_id": jid, "requirement_key": e.key, "category": e.category,
                "expected": {"citation": e.citation, "authority_url": e.authority_url,
                             "applies_note": e.applies_note},
                "observed": {"present": False},
            })

        results[jid] = {
            "score": baseline_score(len(present), len(missing)),
            "detail": {"label": label, "expected": len(entries),
                       "present": len(present), "missing": len(missing),
                       "missing_keys": [f"{e.category}:{e.key}" for e in missing]},
        }

    return {"results": results, "findings": findings, "totals": totals}


def baseline_checklist(entries: List[BaselineObligation], present_keys: set) -> List[Dict]:
    """Per-entry present/missing list for the admin checklist endpoint. Pure."""
    return [
        {"category": e.category, "key": e.key, "citation": e.citation,
         "authority_url": e.authority_url, "applies_note": e.applies_note,
         "present": f"{e.category}:{e.key}" in present_keys}
        for e in entries
    ]
