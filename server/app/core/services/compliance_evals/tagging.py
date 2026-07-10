"""Tagging / organization suite — is the catalog filed correctly?

Two deterministic checks and one labeled-sample measurement:

  1. **Integrity** — categories and regulation keys that are not in the registry.
     A key nobody expects is a key no coverage report will ever notice is missing.

  2. **Structural industry tags** — the load-bearing one. ``_filter_requirements_for_company``
     passes any row with an empty ``applicable_industries`` through to *every*
     company. So a row in an industry-specific category (``lockout_tagout`` under
     ``machine_safety``) that carries no tag is not merely untidy: a restaurant
     receives it. Today the catalog has zero manufacturing tags, so every
     manufacturing row is in exactly this state.

  3. **Labeled precision/recall** — against a hand-labeled fixture, because the
     structural check can only see tags that are *absent*, never tags that are
     *wrong*.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.core.compliance_registry import CATEGORY_KEYS, EXPECTED_REGULATION_KEYS

from . import industry_keysets as iks
from .completeness import _bare_key
from .keys import normalize_key
from .scoring import tagging_score

logger = logging.getLogger(__name__)

LABELS_PATH = Path(__file__).parent / "fixtures" / "tagging_labels.json"


def _root(industry: str) -> str:
    """`healthcare:oncology` → `healthcare`. Tag matching happens at the root."""
    return industry.split(":", 1)[0]


def tag_satisfies(tags: List[str], industry: str) -> bool:
    """Does any tag place this row inside `industry`'s tenant set?

    Root-level matching, because `_filter_requirements_for_company` intersects a
    company's tag set (which contains both `healthcare` and `healthcare:oncology`
    for an oncology practice) against the row's. A `healthcare` tag on an oncology
    row is loose but not leaky; no tag at all is leaky.
    """
    if not tags:
        return False
    root = _root(industry)
    return any(_root(t) == root for t in tags if t)


def load_labels() -> List[Dict]:
    if not LABELS_PATH.exists():
        return []
    try:
        with LABELS_PATH.open() as fh:
            data = json.load(fh)
        return data.get("labels", [])
    except (ValueError, OSError):
        logger.warning("tagging_labels.json unreadable; skipping labeled metrics", exc_info=True)
        return []


def _label_key(state: Optional[str], city: Optional[str], requirement_key: str) -> str:
    return f"{(state or '').upper()}|{(city or '').lower()}|{requirement_key}"


def label_metrics(
    labeled: List[Dict], observed: Dict[str, List[str]]
) -> Tuple[Optional[float], Optional[float], List[Dict]]:
    """Micro-averaged precision/recall of `applicable_industries` against labels."""
    if not labeled:
        return None, None, []

    tp = fp = fn = 0
    errors: List[Dict] = []
    for lab in labeled:
        key = _label_key(lab.get("state"), lab.get("city"), lab["requirement_key"])
        if key not in observed:
            continue
        expected = set(lab.get("expected_industries") or [])
        actual = set(observed[key])
        tp += len(expected & actual)
        fp += len(actual - expected)
        fn += len(expected - actual)
        if expected != actual:
            errors.append({
                "requirement_key": lab["requirement_key"],
                "state": lab.get("state"),
                "city": lab.get("city"),
                "expected": sorted(expected),
                "observed": sorted(actual),
            })

    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    return precision, recall, errors


async def run_tagging(conn, jurisdiction_ids: Optional[List] = None) -> Dict:
    sql = """
        SELECT jr.id, jr.jurisdiction_id, jr.category, jr.regulation_key,
               jr.requirement_key, jr.applicable_industries,
               j.state, j.city, j.level::text AS level,
               COALESCE(j.country_code, 'US') AS country_code
        FROM jurisdiction_requirements jr
        JOIN jurisdictions j ON j.id = jr.jurisdiction_id
    """
    params: List = []
    if jurisdiction_ids:
        sql += " WHERE jr.jurisdiction_id = ANY($1::uuid[])"
        params.append(jurisdiction_ids)
    rows = await conn.fetch(sql, *params)

    findings: List[Dict] = []
    per_jur: Dict = {}
    observed_tags: Dict[str, List[str]] = {}

    for r in rows:
        jid = r["jurisdiction_id"]
        stats = per_jur.setdefault(jid, {"total": 0, "structural": 0, "integrity": 0})
        stats["total"] += 1

        category = r["category"]
        raw_key = _bare_key(r["regulation_key"], r["requirement_key"])
        tags = list(r["applicable_industries"] or [])

        # Normalize before both the integrity check and the label lookup. A
        # minimum-wage row stored under rate_type `general` is a legitimate
        # product of the pipeline; comparing it raw against the registry would
        # brand hundreds of correct rows `invalid_key` and bury the real ones.
        key = normalize_key(category, raw_key, r["level"], r["country_code"])

        if key:
            observed_tags[_label_key(r["state"], r["city"], key)] = tags

        # 1. Integrity
        if category not in CATEGORY_KEYS:
            stats["integrity"] += 1
            findings.append({
                "suite": "tagging",
                "finding_type": "invalid_category",
                "severity": "warn",
                "jurisdiction_id": jid,
                "requirement_id": r["id"],
                "requirement_key": r["requirement_key"],
                "category": category,
                "observed": {"category": category},
            })
        elif key and key not in EXPECTED_REGULATION_KEYS.get(category, frozenset()):
            stats["integrity"] += 1
            findings.append({
                "suite": "tagging",
                "finding_type": "invalid_key",
                "severity": "info",
                "jurisdiction_id": jid,
                "requirement_id": r["id"],
                "requirement_key": r["requirement_key"],
                "category": category,
                "expected": {"known_keys_in_category": sorted(
                    EXPECTED_REGULATION_KEYS.get(category, frozenset())
                )[:12]},
                "observed": {"regulation_key": raw_key, "normalized": key},
            })

        # 2. Structural industry tag
        owner = iks.industry_specific_category(category) if category else None
        if owner and not tag_satisfies(tags, owner):
            stats["structural"] += 1
            findings.append({
                "suite": "tagging",
                "finding_type": "industry_tag_missing",
                "severity": "critical",
                "jurisdiction_id": jid,
                "requirement_id": r["id"],
                "requirement_key": r["requirement_key"],
                "category": category,
                "industry": owner,
                "expected": {"applicable_industries_contains": _root(owner)},
                "observed": {
                    "applicable_industries": tags,
                    "consequence": "row is served to companies in every industry",
                },
            })

    precision, recall, label_errors = label_metrics(load_labels(), observed_tags)
    for err in label_errors:
        findings.append({
            "suite": "tagging",
            "finding_type": "tag_precision_error",
            "severity": "warn",
            "requirement_key": err["requirement_key"],
            "expected": {"applicable_industries": err["expected"]},
            "observed": {"applicable_industries": err["observed"]},
        })

    results = {
        jid: {
            "score": tagging_score(
                s["total"], s["structural"], s["integrity"], precision, recall
            ),
            "detail": {
                **s,
                "label_precision": precision,
                "label_recall": recall,
            },
        }
        for jid, s in per_jur.items()
    }
    return {"results": results, "findings": findings}
