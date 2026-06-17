"""Cappe inventory helpers — append-only stock audit log.

Every stock mutation (sale at checkout, restock on decline, manual adjustment,
damage/return) writes a `cappe_inventory_adjustments` row recording the signed
delta, the resulting balance, and why. Keep these calls inside the caller's
transaction so the log can never drift from the actual stock.
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

VALID_REASONS = {"sale", "manual", "restock", "decline_restock", "damage", "return", "adjustment"}


async def log_adjustment(
    conn,
    *,
    site_id: UUID,
    product_id: UUID,
    delta: int,
    balance_after: Optional[int],
    reason: str = "manual",
    option_id: Optional[UUID] = None,
    note: Optional[str] = None,
) -> None:
    """Record one stock change. `reason` is coerced to a valid value."""
    if reason not in VALID_REASONS:
        reason = "manual"
    await conn.execute(
        """INSERT INTO cappe_inventory_adjustments
               (site_id, product_id, option_id, delta, balance_after, reason, note)
           VALUES ($1, $2, $3, $4, $5, $6, $7)""",
        site_id, product_id, option_id, delta, balance_after, reason,
        (note or None) if note is None else note[:1000],
    )
