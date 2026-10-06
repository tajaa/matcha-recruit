"""Refunds: full or partial, started here or in Stripe, all in one ledger.

An order used to carry one `refunded_cents` number and could only be refunded
in full. Every refund is now a row in `cappe_order_refunds` saying how much,
which units go back on the shelf, why, and where it came from.

The order of operations:

1. `start_refund` writes the row `pending`, with the owner's choice of what to
   restock, BEFORE Stripe is asked. One refund per order can be in flight (a
   partial unique index); a second one is refused until the first settles.
2. Stripe is called OUTSIDE any transaction, keyed by the row's id.
3. `apply_refund` marks the row `succeeded`, puts the chosen units back and
   moves the money on the order. Only a pending row can be applied, so the
   route and the `charge.refunded` webhook that echoes it can't both apply it.

The webhook (`sync_stripe_refunds`) is the other way in. It reads Stripe's
total refunded for the charge: a pending row it covers is applied with the
OWNER's restock choice (the webhook used to arrive first and guess); anything
beyond the ledger was refunded in the Stripe dashboard and is recorded here.

When the refunded total reaches the order total the order becomes `refunded`
and its booking slots are freed; a part refund leaves it paid or fulfilled.
Everything here takes the caller's connection and never talks to Stripe.
"""
from __future__ import annotations

import json
from typing import Any, Iterable, Optional
from uuid import UUID

import asyncpg
from fastapi import HTTPException, status

from .inventory import release_order_bookings, restock_order

REFUND_COLS = (
    "id, order_id, amount_cents, restock, lines, reason, status, source, "
    "stripe_refund_id, failure, created_at"
)

# A pending refund older than this is checked against Stripe before another
# is allowed: the request that wrote it most likely died mid-flight.
STALE_PENDING_SECONDS = 120


def order_total(order: Any) -> int:
    return int(order.get("total_cents") or order.get("subtotal_cents") or 0)


def refundable_left(order: Any) -> int:
    """What is still refundable on an order."""
    return max(0, order_total(order) - int(order.get("refunded_cents") or 0))


async def lock_order(conn, order_id: UUID, site_id: UUID):
    return await conn.fetchrow(
        """SELECT id, site_id, status, total_cents, subtotal_cents, refunded_cents, currency,
                  stripe_payment_intent, stripe_invoice_id
             FROM cappe_orders WHERE id = $1 AND site_id = $2 FOR UPDATE""",
        order_id, site_id,
    )


def decode_lines(value: Any) -> list[dict]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    return [dict(v) for v in (value or []) if isinstance(v, dict)]


async def plan_restock_lines(conn, order_id: UUID, requested: Iterable[Any]) -> list[dict]:
    """The units a part refund puts back: each requested physical line, capped
    at what is left on it. Unknown or non-physical lines are refused."""
    wanted: dict[str, int] = {}
    for line in requested:
        item_id, qty = str(line.item_id), int(line.quantity)
        if qty > 0:
            wanted[item_id] = wanted.get(item_id, 0) + qty
    if not wanted:
        return []
    rows = await conn.fetch(
        "SELECT id, title, quantity, restocked_quantity, fulfillment FROM cappe_order_items "
        "WHERE order_id = $1 AND id = ANY($2::uuid[])",
        order_id, list(wanted),
    )
    found = {str(r["id"]): r for r in rows}
    out = []
    for item_id, qty in wanted.items():
        row = found.get(item_id)
        if row is None or row["fulfillment"] != "physical":
            raise HTTPException(422, "Only this order's shipped goods can go back to stock")
        left = int(row["quantity"]) - int(row.get("restocked_quantity") or 0)
        if qty > left:
            raise HTTPException(
                422,
                f"Only {left} of “{row['title']}” can still go back to stock",
            )
        out.append({"item_id": item_id, "quantity": qty})
    return out


async def start_refund(
    conn, *, order, amount_cents: int, restock: bool, lines: list[dict],
    reason: Optional[str], source: str,
):
    """Write the pending ledger row. Caller holds the order lock."""
    try:
        return await conn.fetchrow(
            f"""INSERT INTO cappe_order_refunds
                    (order_id, site_id, amount_cents, restock, lines, reason, source)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7)
                RETURNING {REFUND_COLS}""",
            order["id"], order["site_id"], amount_cents, restock, json.dumps(lines),
            (reason or None) and reason[:500], source,
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "A refund for this order is still being processed. Try again in a minute.",
        )


async def fail_refund(conn, refund_id: UUID, failure: str) -> None:
    await conn.execute(
        "UPDATE cappe_order_refunds SET status = 'failed', failure = $2, updated_at = NOW() "
        "WHERE id = $1 AND status = 'pending'",
        refund_id, failure[:500],
    )


async def apply_refund(conn, *, refund_id: UUID, site_id: UUID, stripe_refund_id: Optional[str] = None):
    """Settle a pending refund: units back on the shelf, money on the order,
    and the order closed out when nothing is left to refund. Returns the
    settled row, or None when it was not pending (already applied, or failed).
    Caller holds a transaction."""
    refund = await conn.fetchrow(
        f"""UPDATE cappe_order_refunds
               SET status = 'succeeded', updated_at = NOW(),
                   stripe_refund_id = COALESCE($3, stripe_refund_id)
             WHERE id = $1 AND site_id = $2 AND status = 'pending'
         RETURNING {REFUND_COLS}""",
        refund_id, site_id, stripe_refund_id,
    )
    if refund is None:
        return None
    order = await lock_order(conn, refund["order_id"], site_id)
    if order is None:
        return refund
    lines = decode_lines(refund["lines"])
    if lines:
        await restock_order(
            conn, site_id=site_id, order_id=order["id"], reason="return",
            only={line["item_id"]: int(line["quantity"]) for line in lines},
        )
    refunded = int(order.get("refunded_cents") or 0) + int(refund["amount_cents"])
    if refunded >= order_total(order) and order["status"] in ("paid", "fulfilled"):
        await conn.execute(
            """UPDATE cappe_orders
                  SET status = 'refunded', refunded_at = NOW(), refunded_cents = $2,
                      stripe_refund_id = COALESCE($3, stripe_refund_id), updated_at = NOW()
                WHERE id = $1""",
            order["id"], order_total(order), refund["stripe_refund_id"],
        )
        if refund["restock"]:
            await restock_order(conn, site_id=site_id, order_id=order["id"], reason="return")
        await release_order_bookings(conn, order_id=order["id"])
    else:
        await conn.execute(
            "UPDATE cappe_orders SET refunded_cents = $2, stripe_refund_id = COALESCE($3, stripe_refund_id), "
            "updated_at = NOW() WHERE id = $1",
            order["id"], min(refunded, order_total(order)), refund["stripe_refund_id"],
        )
    return refund


async def record_refund(
    conn, *, order, amount_cents: int, source: str, restock: bool,
    stripe_refund_id: Optional[str] = None, reason: Optional[str] = None, lines: Optional[list] = None,
):
    """A refund that has already happened (a Stripe dashboard refund, a lost
    dispute, an order paid outside Stripe): written and applied in one go."""
    if stripe_refund_id and await conn.fetchval(
        "SELECT 1 FROM cappe_order_refunds WHERE stripe_refund_id = $1", stripe_refund_id,
    ):
        stripe_refund_id = None  # already in the ledger under another row
    row = await start_refund(
        conn, order=order, amount_cents=amount_cents, restock=restock, lines=lines or [],
        reason=reason, source=source,
    )
    return await apply_refund(conn, refund_id=row["id"], site_id=order["site_id"], stripe_refund_id=stripe_refund_id)


async def refund_in_full(
    conn, *, order_id: UUID, site_id: UUID, source: str, restock: bool,
    stripe_refund_id: Optional[str] = None,
):
    """Refund whatever is left on a paid or fulfilled order (a lost dispute,
    a full refund made in Stripe). None if the order holds no money."""
    order = await lock_order(conn, order_id, site_id)
    if order is None or order["status"] not in ("paid", "fulfilled"):
        return None
    left = refundable_left(order)
    if left <= 0:
        return None
    return await record_refund(
        conn, order=order, amount_cents=left, source=source, restock=restock,
        stripe_refund_id=stripe_refund_id,
    )


async def sync_stripe_refunds(
    conn, *, order_id: UUID, site_id: UUID, amount_refunded: int, stripe_refund_id: Optional[str],
) -> str:
    """Bring the ledger up to Stripe's total refunded for this order's charge.

    Pending rows the total covers are OURS, in flight: applied with the restock
    choice the owner made. Anything beyond is a refund made in the Stripe
    dashboard: recorded, with the goods restocked only on a full refund of an
    order that hadn't shipped. Caller holds a transaction."""
    order = await lock_order(conn, order_id, site_id)
    if order is None:
        return "unknown"
    ledger = await conn.fetch(
        "SELECT id, amount_cents, status FROM cappe_order_refunds "
        "WHERE order_id = $1 AND status IN ('pending', 'succeeded') ORDER BY created_at",
        order_id,
    )
    done = sum(int(r["amount_cents"]) for r in ledger if r["status"] == "succeeded")
    if not ledger:
        done = int(order.get("refunded_cents") or 0)
    for pending in (r for r in ledger if r["status"] == "pending"):
        if done + int(pending["amount_cents"]) <= amount_refunded:
            await apply_refund(conn, refund_id=pending["id"], site_id=site_id)
            done += int(pending["amount_cents"])
    extra = amount_refunded - done
    if extra > 0:
        order = await lock_order(conn, order_id, site_id)
        left = refundable_left(order)
        if order["status"] in ("paid", "fulfilled") and min(extra, left) > 0:
            await record_refund(
                conn, order=order, amount_cents=min(extra, left), source="stripe",
                restock=extra >= left and order["status"] != "fulfilled",
                stripe_refund_id=stripe_refund_id,
            )
    order = await lock_order(conn, order_id, site_id)
    return "refunded" if order["status"] == "refunded" else ("partially_refunded" if amount_refunded else "in_sync")


async def pending_refund(conn, order_id: UUID):
    """The order's in-flight refund and its age in seconds, if any."""
    return await conn.fetchrow(
        f"SELECT {REFUND_COLS}, EXTRACT(EPOCH FROM (NOW() - created_at)) AS age "
        "FROM cappe_order_refunds WHERE order_id = $1 AND status = 'pending'",
        order_id,
    )


async def list_refunds(conn, order_id: UUID) -> list[dict]:
    rows = await conn.fetch(
        f"SELECT {REFUND_COLS} FROM cappe_order_refunds WHERE order_id = $1 ORDER BY created_at",
        order_id,
    )
    return [{**dict(r), "lines": decode_lines(r["lines"])} for r in rows]
