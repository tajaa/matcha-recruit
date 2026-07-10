"""Scope eval suite — measures the scope-registry's classification coverage.

The fifth suite (SCOPE_REGISTRY_PLAN.md §7). Non-network, inline. Read-only over
the `scope_registry` tables — like the rest of `compliance_evals`, it records
findings and never mutates what it measures.

Findings (per authority index, jurisdiction-attributed where the index has one):
  * ``unclassified_authority_item`` — items with no classification. **Critical
    for an enumerable index** (eCFR: "every section classified or excluded" is a
    checkable claim, so a gap is a hard defect), **warn for a curated index**
    (the list is explicitly "curated, not exhaustive").
  * ``provisional_classification`` — classifications awaiting human confirmation.
    Critical: provisional counts toward no resolved scope, so unconfirmed work
    means the registry is not yet authoritative for that index.
  * ``scope_without_value`` — a confirmed, applicable classification with no
    codified catalog value (regulation_key NULL, or a key with no active
    `jurisdiction_requirements` row anywhere). The fetch queue surfaced as a
    finding — critical, because the obligation is scoped but unanswerable.
  * ``ungated_conditional`` — a conditional classification whose gating
    attribute is not one the platform ever supplies, so it can never fire.
    Under-scoping made visible rather than silent (warn).

`requirement_id` on findings stays NULL — it is a `jurisdiction_requirements`
FK, and these findings are about `authority_index_items`; the item id and
citation ride in ``observed`` instead.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

# Facility attributes the platform actually injects at resolve time. A
# conditional keyed on anything else is dead — see matcha_work_node (roster
# injection) + facility_attributes JSONB, and the scope_registry seed's
# documented psm_covered_chemicals.
KNOWN_FACILITY_ATTRS = frozenset({
    "employee_count", "employee_count_state", "entity_type",
    "payer_contracts", "psm_covered_chemicals",
})


def _condition_attr_keys(condition: Any) -> List[str]:
    """Every attribute key referenced anywhere in an entity_condition tree."""
    if isinstance(condition, str):
        try:
            condition = json.loads(condition)
        except (TypeError, ValueError):
            return []
    if not isinstance(condition, dict):
        return []
    if condition.get("type") == "attribute" and condition.get("key"):
        return [condition["key"]]
    keys: List[str] = []
    for child in condition.get("conditions") or []:
        keys.extend(_condition_attr_keys(child))
    return keys


async def run_scope(conn, jurisdiction_ids: Optional[List] = None) -> Dict:
    """Emit scope-coverage findings. Findings-only (no scorecard subscore).

    Authority indexes are registry-global; an index attributes its findings to
    its own ``jurisdiction_id`` (NULL for federal). ``jurisdiction_ids`` filters
    curated indexes to the eval's targets; federal (NULL) is always included.
    """
    findings: List[Dict] = []
    totals = {
        "scope_indexes": 0,
        "scope_unclassified": 0,
        "scope_provisional": 0,
        "scope_without_value": 0,
        "scope_ungated_conditional": 0,
    }

    indexes = await conn.fetch(
        """
        SELECT id, slug, name, jurisdiction_id, enumerable, source_type,
               item_count, unclassified_count
        FROM authority_indexes
        ORDER BY slug
        """
    )
    jur_filter = set(jurisdiction_ids or [])

    for idx in indexes:
        jid = idx["jurisdiction_id"]
        if jur_filter and jid is not None and jid not in jur_filter:
            continue
        totals["scope_indexes"] += 1

        # 1. Unclassified items — the definitive remaining-work counter.
        if idx["unclassified_count"]:
            totals["scope_unclassified"] += idx["unclassified_count"]
            sample = await conn.fetch(
                """
                SELECT i.citation FROM authority_index_items i
                LEFT JOIN authority_item_classifications c ON c.item_id = i.id
                WHERE i.authority_index_id = $1 AND c.id IS NULL
                ORDER BY i.citation LIMIT 10
                """,
                idx["id"],
            )
            findings.append({
                "suite": "scope",
                "finding_type": "unclassified_authority_item",
                "severity": "critical" if idx["enumerable"] else "warn",
                "jurisdiction_id": jid,
                "requirement_key": None,
                "category": None,
                "industry": None,
                "expected": {"index": idx["slug"], "enumerable": idx["enumerable"]},
                "observed": {
                    "unclassified_count": idx["unclassified_count"],
                    "sample_citations": [r["citation"] for r in sample],
                },
            })

        # 2. Provisional classifications — not yet authoritative.
        provisional = await conn.fetchval(
            """
            SELECT COUNT(*) FROM authority_item_classifications c
            JOIN authority_index_items i ON i.id = c.item_id
            WHERE i.authority_index_id = $1 AND c.status = 'provisional'
            """,
            idx["id"],
        )
        if provisional:
            totals["scope_provisional"] += provisional
            findings.append({
                "suite": "scope",
                "finding_type": "provisional_classification",
                "severity": "critical",
                "jurisdiction_id": jid,
                "requirement_key": None,
                "category": None,
                "industry": None,
                "expected": {"index": idx["slug"]},
                "observed": {"provisional_count": provisional},
            })

        # 3. scope_without_value — confirmed applicable, no codified value.
        without_value = await conn.fetch(
            """
            SELECT i.citation, c.regulation_key
            FROM authority_item_classifications c
            JOIN authority_index_items i ON i.id = c.item_id
            WHERE i.authority_index_id = $1
              AND c.status = 'confirmed'
              AND c.disposition <> 'excluded'
              AND (c.regulation_key IS NULL OR NOT EXISTS (
                    SELECT 1 FROM jurisdiction_requirements jr
                    WHERE jr.regulation_key = c.regulation_key
                      AND COALESCE(jr.status, 'active') = 'active'))
            ORDER BY i.citation
            """,
            idx["id"],
        )
        if without_value:
            totals["scope_without_value"] += len(without_value)
            findings.append({
                "suite": "scope",
                "finding_type": "scope_without_value",
                "severity": "critical",
                "jurisdiction_id": jid,
                "requirement_key": None,
                "category": None,
                "industry": None,
                "expected": {"index": idx["slug"]},
                "observed": {
                    "count": len(without_value),
                    "sample": [
                        {"citation": r["citation"], "regulation_key": r["regulation_key"]}
                        for r in without_value[:10]
                    ],
                },
            })

        # 4. ungated_conditional — conditional keyed on an attribute nothing supplies.
        conditionals = await conn.fetch(
            """
            SELECT i.citation, c.entity_condition
            FROM authority_item_classifications c
            JOIN authority_index_items i ON i.id = c.item_id
            WHERE i.authority_index_id = $1
              AND c.disposition = 'conditional'
              AND c.entity_condition IS NOT NULL
            """,
            idx["id"],
        )
        for row in conditionals:
            attrs = _condition_attr_keys(row["entity_condition"])
            unknown = [a for a in attrs if a not in KNOWN_FACILITY_ATTRS]
            if unknown:
                totals["scope_ungated_conditional"] += 1
                findings.append({
                    "suite": "scope",
                    "finding_type": "ungated_conditional",
                    "severity": "warn",
                    "jurisdiction_id": jid,
                    "requirement_key": None,
                    "category": None,
                    "industry": None,
                    "expected": {
                        "index": idx["slug"],
                        "known_attributes": sorted(KNOWN_FACILITY_ATTRS),
                    },
                    "observed": {
                        "citation": row["citation"],
                        "unknown_attributes": unknown,
                    },
                })

    return {"findings": findings, "totals": totals}
