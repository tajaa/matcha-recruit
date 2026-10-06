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


_PHYSICAL_LINES = (
    "SELECT id, product_id, quantity, selected_option_ids, stock_decremented, decremented_option_ids "
    "FROM cappe_order_items WHERE order_id = $1 AND fulfillment = 'physical' ORDER BY id"
)


async def lock_stock_rows(conn, *, site_id: UUID, product_ids, option_ids=()) -> None:
    """Lock product rows, then option rows, each in id order.

    Every path that writes stock for more than one row — checkout, restock,
    re-take — takes its locks through here. Checkout used to lock in cart order
    and restock in line order, so carts [A, B] and [B, A] placed together, or a
    checkout racing a cancellation, could each hold the row the other wanted;
    Postgres resolves that by killing one of them with a 500. One global order
    means the second simply waits. Run inside the caller's transaction.
    """
    pids = sorted({p for p in product_ids if p is not None}, key=str)
    oids = sorted({o for o in option_ids if o is not None}, key=str)
    if pids:
        await conn.fetch(
            "SELECT id FROM cappe_products WHERE site_id = $1 AND id = ANY($2::uuid[]) "
            "ORDER BY id FOR UPDATE",
            site_id, pids,
        )
    if oids:
        await conn.fetch(
            "SELECT id FROM cappe_product_options WHERE site_id = $1 AND id = ANY($2::uuid[]) "
            "ORDER BY id FOR UPDATE",
            site_id, oids,
        )


def _line_option_ids(line) -> list:
    """The options a line's stock movement applies to. `decremented_option_ids`
    is what the sale actually took; NULL is a line from before that was
    recorded, where every selected option is the best that can be known."""
    recorded = line.get("decremented_option_ids")
    return list(recorded if recorded is not None else (line.get("selected_option_ids") or []))


async def restock_order(conn, *, site_id: UUID, order_id: UUID, reason: str) -> None:
    """Restock every physical line item of an order (product + selected
    variants), writing an audit row per adjustment. Shared by every order path
    that reverses a sale (owner decline, cancel, refund) — used to live only in
    the decline route, so cancelling/refunding an order permanently lost that
    stock. Run inside the caller's own transaction alongside the status write.

    Credits only what the sale took. A line records that at checkout
    (`stock_decremented`, `decremented_option_ids`); without it, a product sold
    while it was not tracking stock and switched to tracking afterwards gained
    units it never lost. Lines from before the record existed (NULL) fall back
    to "whatever tracks stock now"."""
    phys = await conn.fetch(_PHYSICAL_LINES, order_id)
    await lock_stock_rows(
        conn, site_id=site_id,
        product_ids=[it["product_id"] for it in phys],
        option_ids=[oid for it in phys for oid in _line_option_ids(it)],
    )
    for it in phys:
        pid, q = it["product_id"], it["quantity"]
        if pid is not None and it.get("stock_decremented") is not False:
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
        for oid in _line_option_ids(it):
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
    phys = await conn.fetch(_PHYSICAL_LINES, order_id)
    await lock_stock_rows(
        conn, site_id=site_id,
        product_ids=[it["product_id"] for it in phys],
        option_ids=[oid for it in phys for oid in _line_option_ids(it)],
    )
    for it in phys:
        pid, q = it["product_id"], it["quantity"]
        took_product, took_options = False, []
        if pid is not None and it.get("stock_decremented") is not False:
            bal = await conn.fetchval(
                "UPDATE cappe_products SET inventory = inventory - $1, updated_at = NOW() "
                "WHERE id = $2 AND site_id = $3 AND inventory IS NOT NULL RETURNING inventory",
                q, pid, site_id,
            )
            if bal is not None:
                took_product = True
                await log_adjustment(
                    conn, site_id=site_id, product_id=pid, delta=-q,
                    balance_after=bal, reason="sale",
                )
        for oid in _line_option_ids(it):
            obal = await conn.fetchval(
                "UPDATE cappe_product_options SET inventory = inventory - $1 "
                "WHERE id = $2 AND site_id = $3 AND inventory IS NOT NULL RETURNING inventory",
                q, oid, site_id,
            )
            if obal is not None:
                took_options.append(oid)
                if pid is not None:
                    await log_adjustment(
                        conn, site_id=site_id, product_id=pid, option_id=oid, delta=-q,
                        balance_after=obal, reason="sale",
                    )
        if it.get("stock_decremented") is None:
            # First time this line's stock is taken with a record (a renewal
            # order, or a line older than the record): write down what came off
            # the shelf so the eventual restock is its exact inverse.
            await conn.execute(
                "UPDATE cappe_order_items SET stock_decremented = $2, decremented_option_ids = $3::uuid[] "
                "WHERE id = $1",
                it["id"], took_product, took_options,
            )
