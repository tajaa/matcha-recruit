"""Matcha Lite pricing — DB-backed, admin-configurable via /admin/matcha-lite-pricing.

Price is a step function: ceil(headcount / block_size) * price_per_block, with
an optional sale override. Supersedes stripe_service.matcha_lite_price_cents
for the actual checkout path — that function stays in place for Matcha-X,
which is unchanged, still a hardcoded stub.

Matcha Compliance also uses this table (product_code='matcha_compliance'),
seeded flat at $8/head (block_size=1) — see migration mlpricing03.
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

# signup_source values priced via this table: the two Lite variants (share the
# /lite/signup page + /checkout/lite endpoint) plus standalone Matcha Compliance
# (/compliance/signup + /checkout/compliance) — each its own row.
PRODUCT_CODES = ("matcha_lite", "matcha_lite_essentials", "matcha_compliance")

_FALLBACK_DEFAULTS = {
    "matcha_lite": dict(price_per_block_cents=5000, block_size=10, min_headcount=1, max_headcount=300),
    "matcha_lite_essentials": dict(price_per_block_cents=4000, block_size=10, min_headcount=1, max_headcount=300),
    "matcha_compliance": dict(price_per_block_cents=800, block_size=1, min_headcount=1, max_headcount=300),
}


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


async def get_matcha_lite_pricing(conn=None, product_code: str = "matcha_lite") -> MatchaLitePricing:
    """Fetch the live pricing config for `product_code` ('matcha_lite' or
    'matcha_lite_essentials' — see PRODUCT_CODES).

    Pass an existing `conn` to reuse a connection already held by the caller
    (e.g. the checkout endpoint, which also reads headcount in the same
    request); otherwise a short-lived connection is opened.
    """
    query = f"SELECT {SELECT_COLUMNS} FROM matcha_lite_pricing WHERE product_code = $1"

    if conn is not None:
        row = await conn.fetchrow(query, product_code)
    else:
        async with get_connection() as c:
            row = await c.fetchrow(query, product_code)

    if row is None:
        # Defensive fallback if the seed row was somehow deleted — matches
        # the launch defaults (migrations mlpricing01/mlpricing02).
        defaults = _FALLBACK_DEFAULTS.get(product_code, _FALLBACK_DEFAULTS["matcha_lite"])
        return MatchaLitePricing(
            sale_price_per_block_cents=None,
            sale_active=False,
            updated_at=None,
            updated_by=None,
            **defaults,
        )
    return row_to_pricing(row)


def compute_matcha_lite_price_cents(pricing: MatchaLitePricing, headcount: int) -> Optional[int]:
    """Monthly price in cents for `headcount` under `pricing`, or None if out of range."""
    if headcount < pricing.min_headcount or headcount > pricing.max_headcount:
        return None
    blocks = math.ceil(headcount / pricing.block_size)
    return blocks * pricing.effective_price_per_block_cents
