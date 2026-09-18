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


async def release_order_bookings(conn, *, order_id: UUID) -> int:
    """Free the appointment slots an order's booking lines were holding.

    A booking line reserves its slot when the order is created (the
    double-book index covers `pending` and `confirmed`), so an order that is
    released without this keeps the slot off the calendar for nobody. Only
    still-live bookings are touched — a completed or already-declined one is
    history, not a hold. Run in the caller's transaction beside the status
    write and `restock_order`. Returns the number of slots freed.
    """
    rows = await conn.fetch(
        """UPDATE cappe_bookings SET status = 'cancelled', updated_at = NOW()
            WHERE id IN (SELECT booking_id FROM cappe_order_items
                          WHERE order_id = $1 AND booking_id IS NOT NULL)
              AND status IN ('pending', 'confirmed')
        RETURNING id""",
        order_id,
    )
    return len(rows)


async def retake_order_stock(conn, *, site_id: UUID, order_id: UUID) -> None:
    """Take an order's physical stock back out — the inverse of `restock_order`.

    Used when money arrives for an order that had already been released (its
    stock handed back at cancel/decline time) and the order is restored to
    `paid`. `paid` is a decremented state: a later refund restocks it, so
    restoring the status without re-taking the stock credits the shelf twice.

    Deliberately NOT guarded on `inventory >= qty`: the buyer has been charged,
    so the unit is owed whether or not it was resold in the meantime. A negative
    balance is the honest record of that oversell, and it blocks further sales
    (`create_public_order` requires `inventory >= qty`) until a human resolves
    it. Run in the caller's transaction beside the status write.
    """
    phys = await conn.fetch(
        "SELECT product_id, quantity, selected_option_ids FROM cappe_order_items "
        "WHERE order_id = $1 AND fulfillment = 'physical'",
        order_id,
    )
    for it in phys:
        pid, q = it["product_id"], it["quantity"]
        if pid is not None:
            bal = await conn.fetchval(
                "UPDATE cappe_products SET inventory = inventory - $1, updated_at = NOW() "
                "WHERE id = $2 AND site_id = $3 AND inventory IS NOT NULL RETURNING inventory",
                q, pid, site_id,
            )
            if bal is not None:
                await log_adjustment(
                    conn, site_id=site_id, product_id=pid, delta=-q,
                    balance_after=bal, reason="sale",
                )
        for oid in (it["selected_option_ids"] or []):
            obal = await conn.fetchval(
                "UPDATE cappe_product_options SET inventory = inventory - $1 "
                "WHERE id = $2 AND site_id = $3 AND inventory IS NOT NULL RETURNING inventory",
                q, oid, site_id,
            )
            if obal is not None and pid is not None:
                await log_adjustment(
                    conn, site_id=site_id, product_id=pid, option_id=oid, delta=-q,
                    balance_after=obal, reason="sale",
                )
