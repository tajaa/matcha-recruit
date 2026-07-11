"""Baseline suite — score federal + CA-state against the enumerated labor master-list.

Every other suite measures the catalog against an *emergent* expectation (whatever
keys research produced). This one measures the two base-layer jurisdictions against a
*fixed, hand-cited* list (`baseline_masterlist.py`) — the only suite that can answer
"is federal labor actually done?" with a number instead of a vibe.

It scores each base jurisdiction's OWN rows (not the inherited chain union): the point
is whether the base layer itself exists, since every city inherits it. A master-list
key with no matching catalog row for that jurisdiction is a critical
`baseline_missing_key` finding carrying the citation to research next.

Read-only over the catalog. The per-jurisdiction resolve→diff (`baseline_scorecard`)
is shared by the suite and the admin checklist endpoint so the two can never report a
different number for "is this base layer done?".
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from .baseline_masterlist import BASELINE_JURISDICTIONS, BaselineObligation
from .golden import GoldenJurisdiction, _resolve_jurisdiction_id, _rows_for
from .scoring import baseline_score

logger = logging.getLogger(__name__)


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


def _checklist_items(entries: List[BaselineObligation], present_keys: set) -> List[Dict]:
    return [
        {"category": e.category, "key": e.key, "citation": e.citation,
         "authority_url": e.authority_url, "applies_note": e.applies_note,
         "present": f"{e.category}:{e.key}" in present_keys}
        for e in entries
    ]


async def baseline_scorecard(conn) -> List[Dict[str, Any]]:
    """Resolve + score each base jurisdiction against the master-list — the single
    shared computation behind both the eval suite and the admin checklist endpoint.

    Returns one dict per spec: ``{spec, jid, entries, present, missing, expected,
    score, items}``. ``jid`` is None when the jurisdiction row doesn't exist.
    """
    out: List[Dict[str, Any]] = []
    for spec in BASELINE_JURISDICTIONS:
        gj = GoldenJurisdiction(level=spec["level"], state=spec.get("state"))
        jid = await _resolve_jurisdiction_id(conn, gj)
        entries = spec["entries"]
        present_keys = set((await _rows_for(conn, jid)).keys()) if jid is not None else set()
        present, missing = diff_masterlist(entries, present_keys)
        out.append({
            "spec": spec, "jid": jid, "entries": entries,
            "present": present, "missing": missing,
            "expected": len(entries),
            "score": baseline_score(len(present), len(missing)),
            "items": _checklist_items(entries, present_keys),
        })
    return out


async def run_baseline(conn) -> Dict:
    """Score the federal + CA-state jurisdictions against the labor master-list.

    Returns ``{results: {jid: {score, detail}}, findings, totals}``. Misses are
    ``critical`` findings, but baseline is a base-layer measure with its OWN
    scorecard — the runner deliberately does NOT fold baseline criticals into any
    per-(jurisdiction, industry) onboarding-readiness gate (that would let a base-layer
    gap flip a company's readiness; Step 1 is admin/data-side only).
    """
    findings: List[Dict] = []
    results: Dict = {}
    totals: Dict[str, int] = {}

    for card in await baseline_scorecard(conn):
        spec, jid = card["spec"], card["jid"]
        slug = spec["slug"]
        totals[f"{slug}_expected"] = card["expected"]
        totals[f"{slug}_present"] = len(card["present"])
        if jid is None:
            logger.warning("baseline: jurisdiction not found for %s", spec["label"])
            continue

        for e in card["missing"]:
            findings.append({
                "suite": "baseline", "finding_type": "baseline_missing_key",
                "severity": "critical",
                "jurisdiction_id": jid, "requirement_key": e.key, "category": e.category,
                "expected": {"citation": e.citation, "authority_url": e.authority_url,
                             "applies_note": e.applies_note},
                "observed": {"present": False},
            })

        results[jid] = {
            "score": card["score"],
            "detail": {"label": spec["label"], "slug": slug,
                       "expected": card["expected"], "present": len(card["present"]),
                       "missing": len(card["missing"]),
                       "missing_keys": [f"{e.category}:{e.key}" for e in card["missing"]]},
        }

    return {"results": results, "findings": findings, "totals": totals}
