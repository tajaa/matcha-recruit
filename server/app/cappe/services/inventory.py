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


async def restock_order(conn, *, site_id: UUID, order_id: UUID, reason: str) -> None:
    """Restock every physical line item of an order (product + selected
    variants), writing an audit row per adjustment. Shared by every order path
    that reverses a sale (owner decline, cancel, refund) — used to live only in
    the decline route, so cancelling/refunding an order permanently lost that
    stock. Run inside the caller's own transaction alongside the status write."""
    phys = await conn.fetch(
        "SELECT product_id, quantity, selected_option_ids FROM cappe_order_items "
        "WHERE order_id = $1 AND fulfillment = 'physical'",
        order_id,
    )
    for it in phys:
        pid, q = it["product_id"], it["quantity"]
        if pid is not None:
            bal = await conn.fetchval(
                "UPDATE cappe_products SET inventory = inventory + $1, updated_at = NOW() "
                "WHERE id = $2 AND site_id = $3 AND inventory IS NOT NULL RETURNING inventory",
                q, pid, site_id,
            )
            if bal is not None:
                await log_adjustment(
                    conn, site_id=site_id, product_id=pid, delta=q,
                    balance_after=bal, reason=reason,
                )
        for oid in (it["selected_option_ids"] or []):
            obal = await conn.fetchval(
                "UPDATE cappe_product_options SET inventory = inventory + $1 "
                "WHERE id = $2 AND site_id = $3 AND inventory IS NOT NULL RETURNING inventory",
                q, oid, site_id,
            )
            if obal is not None and pid is not None:
                await log_adjustment(
                    conn, site_id=site_id, product_id=pid, option_id=oid, delta=q,
                    balance_after=obal, reason=reason,
                )
