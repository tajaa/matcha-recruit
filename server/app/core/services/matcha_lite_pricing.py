"""Matcha Lite pricing — DB-backed, admin-configurable via /admin/matcha-lite-pricing.

Price is a step function: ceil(headcount / block_size) * price_per_block, with
an optional sale override. Supersedes stripe_service.matcha_lite_price_cents
for the actual checkout path — that function stays in place since
matcha_compliance_price_cents still calls it as its headcount component
(Matcha-X / Matcha Compliance pricing is unchanged, still a hardcoded stub).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from ...database import get_connection

SELECT_COLUMNS = """
    price_per_block_cents, block_size, sale_price_per_block_cents,
    sale_active, min_headcount, max_headcount, updated_at, updated_by
"""


@dataclass
class MatchaLitePricing:
    price_per_block_cents: int
    block_size: int
    sale_price_per_block_cents: Optional[int]
    sale_active: bool
    min_headcount: int
    max_headcount: int
    updated_at: Optional[str]
    updated_by: Optional[str]

    @property
    def effective_price_per_block_cents(self) -> int:
        if self.sale_active and self.sale_price_per_block_cents is not None:
            return self.sale_price_per_block_cents
        return self.price_per_block_cents


def row_to_pricing(row) -> MatchaLitePricing:
    return MatchaLitePricing(
        price_per_block_cents=row["price_per_block_cents"],
        block_size=row["block_size"],
        sale_price_per_block_cents=row["sale_price_per_block_cents"],
        sale_active=row["sale_active"],
        min_headcount=row["min_headcount"],
        max_headcount=row["max_headcount"],
        updated_at=row["updated_at"].isoformat() if row["updated_at"] else None,
        updated_by=row["updated_by"],
    )


async def get_matcha_lite_pricing(conn=None) -> MatchaLitePricing:
    """Fetch the live Matcha Lite pricing config.

    Pass an existing `conn` to reuse a connection already held by the caller
    (e.g. the checkout endpoint, which also reads headcount in the same
    request); otherwise a short-lived connection is opened.
    """
    query = f"SELECT {SELECT_COLUMNS} FROM matcha_lite_pricing WHERE product_code = 'matcha_lite'"

    if conn is not None:
        row = await conn.fetchrow(query)
    else:
        async with get_connection() as c:
            row = await c.fetchrow(query)

    if row is None:
        # Defensive fallback if the seed row was somehow deleted — matches
        # the launch default (migration mlpricing01).
        return MatchaLitePricing(
            price_per_block_cents=5000,
            block_size=10,
            sale_price_per_block_cents=None,
            sale_active=False,
            min_headcount=1,
            max_headcount=300,
            updated_at=None,
            updated_by=None,
        )
    return row_to_pricing(row)


def compute_matcha_lite_price_cents(pricing: MatchaLitePricing, headcount: int) -> Optional[int]:
    """Monthly price in cents for `headcount` under `pricing`, or None if out of range."""
    if headcount < pricing.min_headcount or headcount > pricing.max_headcount:
        return None
    blocks = math.ceil(headcount / pricing.block_size)
    return blocks * pricing.effective_price_per_block_cents
