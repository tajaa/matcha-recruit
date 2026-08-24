"""Shared inventory-count baseline query fragments.

An ``adjust`` movement is the last physical count for an item.  Both the audit
sheet and loss analysis need that exact definition; keeping it here prevents
their expected-on-hand windows from quietly diverging.
"""

BASELINES_CTE = """
    baselines AS (
        SELECT DISTINCT ON (item_id) item_id, created_at AS baseline_at,
               quantity AS baseline
        FROM inventory_movements
        WHERE company_id=$1 AND item_id=ANY($2::uuid[]) AND kind='adjust'
        ORDER BY item_id, created_at DESC, id DESC
    )
"""
