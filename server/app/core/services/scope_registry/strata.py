"""Materialize scope strata from confirmed classifications.

A stratum is a reusable coordinate ``(level, jurisdiction, category|ALL,
entity_condition|base)`` with counts. Strata are **derived** — rebuilt wholesale
from confirmed classifications, never hand-edited (plan §3: "Strata are derived
from classifications, never hand-authored").

Strata carry coordinates + counts, not item lists: resolution re-queries the
classifications for the actual items/keys, which is also where
``excludes_categories`` is enforced (a coordinate row can't express per-item
excludes).

Only **confirmed** classifications materialize — provisional counts toward no
resolved scope (the confirm-before-verdict invariant).
"""
from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


async def recompute_strata(conn) -> Dict[str, Any]:
    """Full rebuild of scope_strata inside one transaction.

    Coordinate derivation from confirmed classifications × items × indexes:
      * universal_in_domain          → (level, jurisdiction, NULL, NULL)
      * category_specific / conditional → one stratum per applies_to slug,
        conditional rows carrying their entity_condition
      * excluded                     → no stratum
    ``key_count`` counts DISTINCT codified regulation_keys in the coordinate;
    ``item_count`` counts classified items. Also refreshes every index's
    ``unclassified_count`` (items with no classification row at any status).
    """
    async with conn.transaction():
        await conn.execute("DELETE FROM scope_strata")

        # Universal strata: one per (level, jurisdiction) with universal items.
        await conn.execute(
            """
            INSERT INTO scope_strata
                (level, jurisdiction_id, category_slug, entity_condition,
                 label, status, item_count, key_count, refreshed_at)
            SELECT
                ai.level,
                ai.jurisdiction_id,
                NULL,
                NULL,
                ai.level || ' × ALL',
                'active',
                COUNT(*),
                COUNT(DISTINCT c.regulation_key) FILTER (WHERE c.regulation_key IS NOT NULL),
                NOW()
            FROM authority_item_classifications c
            JOIN authority_index_items i ON i.id = c.item_id
            JOIN authority_indexes ai ON ai.id = i.authority_index_id
            WHERE c.status = 'confirmed'
              AND c.disposition = 'universal_in_domain'
            GROUP BY ai.level, ai.jurisdiction_id
            """
        )

        # Category strata: unnest applies_to; conditional rows group by their
        # condition as well (coordinate uniqueness includes md5(condition)).
        await conn.execute(
            """
            INSERT INTO scope_strata
                (level, jurisdiction_id, category_slug, entity_condition,
                 label, status, item_count, key_count, refreshed_at)
            SELECT
                ai.level,
                ai.jurisdiction_id,
                cat.slug,
                c.entity_condition,
                ai.level || ' × ' || cat.slug
                    || CASE WHEN c.entity_condition IS NOT NULL THEN ' (conditional)' ELSE '' END,
                'active',
                COUNT(*),
                COUNT(DISTINCT c.regulation_key) FILTER (WHERE c.regulation_key IS NOT NULL),
                NOW()
            FROM authority_item_classifications c
            JOIN authority_index_items i ON i.id = c.item_id
            JOIN authority_indexes ai ON ai.id = i.authority_index_id
            CROSS JOIN LATERAL unnest(c.applies_to_categories) AS cat(slug)
            WHERE c.status = 'confirmed'
              AND c.disposition IN ('category_specific', 'conditional')
            GROUP BY ai.level, ai.jurisdiction_id, cat.slug, c.entity_condition
            """
        )

        # Conditional universal rows (conditional with empty applies_to =
        # "applies to everyone in the domain, when the condition fires" — FMLA).
        await conn.execute(
            """
            INSERT INTO scope_strata
                (level, jurisdiction_id, category_slug, entity_condition,
                 label, status, item_count, key_count, refreshed_at)
            SELECT
                ai.level,
                ai.jurisdiction_id,
                NULL,
                c.entity_condition,
                ai.level || ' × ALL (conditional)',
                'active',
                COUNT(*),
                COUNT(DISTINCT c.regulation_key) FILTER (WHERE c.regulation_key IS NOT NULL),
                NOW()
            FROM authority_item_classifications c
            JOIN authority_index_items i ON i.id = c.item_id
            JOIN authority_indexes ai ON ai.id = i.authority_index_id
            WHERE c.status = 'confirmed'
              AND c.disposition = 'conditional'
              AND COALESCE(array_length(c.applies_to_categories, 1), 0) = 0
            GROUP BY ai.level, ai.jurisdiction_id, c.entity_condition
            """
        )

        # Refresh every index's unclassified_count in the same transaction.
        await conn.execute(
            """
            UPDATE authority_indexes ai
            SET unclassified_count = sub.cnt
            FROM (
                SELECT i.authority_index_id, COUNT(*) FILTER (WHERE c.id IS NULL) AS cnt
                FROM authority_index_items i
                LEFT JOIN authority_item_classifications c ON c.item_id = i.id
                GROUP BY i.authority_index_id
            ) sub
            WHERE sub.authority_index_id = ai.id
            """
        )

        totals = await conn.fetchrow(
            "SELECT COUNT(*) AS strata, COALESCE(SUM(item_count), 0) AS items, "
            "COALESCE(SUM(key_count), 0) AS keys FROM scope_strata"
        )

    result = {
        "strata": int(totals["strata"]),
        "items": int(totals["items"]),
        "keys": int(totals["keys"]),
    }
    logger.info("recomputed scope strata: %s", result)
    return result
