"""Master-admin — configure Matcha Lite pricing (base price + optional sale price).

Single-row config table (matcha_lite_pricing); every change is recorded to
matcha_lite_pricing_history in the same transaction, since this directly sets
what customers are charged.
"""
import json
import logging
import math
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.database import get_connection
from app.core.dependencies import require_admin
from app.core.services.matcha_lite_pricing import (
    FLAT_PRODUCT_CODES,
    PRODUCT_CODES,
    SELECT_COLUMNS,
    get_matcha_lite_pricing,
    row_to_pricing,
)
from app.core.services.product_definitions import STRIPE_MIN_CHARGE_CENTS
from app.core.services.stripe_catalog import INCIDENT_PLANS, sync_after_save

router = APIRouter()
logger = logging.getLogger(__name__)


def _validate_product_code(product_code: str) -> str:
    if product_code not in PRODUCT_CODES:
        raise HTTPException(status_code=400, detail=f"Unknown product_code — must be one of {PRODUCT_CODES}")
    return product_code


class MatchaLitePricingConfig(BaseModel):
    price_per_block_cents: int
    block_size: int
    sale_price_per_block_cents: Optional[int] = None
    sale_active: bool
    min_headcount: int
    max_headcount: int
    updated_at: Optional[str] = None
    updated_by: Optional[str] = None


class MatchaLitePricingUpdate(BaseModel):
    price_per_block_cents: int = Field(gt=0)
    block_size: int = Field(gt=0)
    sale_price_per_block_cents: Optional[int] = Field(default=None, gt=0)
    sale_active: bool
    min_headcount: int = Field(gt=0)
    max_headcount: int = Field(gt=0)
    # The `updated_at` the editor loaded (null for a row not saved yet). When
    # sent, a save over a newer change is refused instead of silently undoing
    # it — the same row is editable from /admin/pricing and Signup Links.
    expected_updated_at: Optional[str] = None


@router.get("/matcha-lite-pricing", response_model=MatchaLitePricingConfig)
async def get_matcha_lite_pricing_admin(
    product_code: str = Query("matcha_lite"),
    current_user=Depends(require_admin),
):
    product_code = _validate_product_code(product_code)
    # No row yet (e.g. mlpricing04 hasn't seeded this add-on in this
    # environment) is not an error — product_code is already validated
    # against the known enum, so fall back to launch defaults rather than
    # 404ing the admin out of a config that's about to be created on save.
    async with get_connection() as conn:
        pricing = await get_matcha_lite_pricing(conn, product_code)
    return MatchaLitePricingConfig(**pricing.__dict__)


@router.put("/matcha-lite-pricing", response_model=MatchaLitePricingConfig)
async def update_matcha_lite_pricing(
    body: MatchaLitePricingUpdate,
    product_code: str = Query("matcha_lite"),
    current_user=Depends(require_admin),
):
    product_code = _validate_product_code(product_code)
    if product_code in FLAT_PRODUCT_CODES:
        # A flat plan is one unit; anything else here would only make the
        # checkout's headcount-of-1 price lookup refuse.
        body = body.model_copy(update={"block_size": 1, "min_headcount": 1, "max_headcount": 1})
    if body.min_headcount > body.max_headcount:
        raise HTTPException(status_code=400, detail="min_headcount cannot exceed max_headcount")
    if body.sale_active and body.sale_price_per_block_cents is None:
        raise HTTPException(status_code=400, detail="sale_price_per_block_cents is required when sale_active is true")
    # The cheapest checkout is the minimum headcount; Stripe refuses it under
    # $0.50, so a lower price would save and then 400 every checkout.
    min_blocks = math.ceil(body.min_headcount / body.block_size)
    for per_block in (body.price_per_block_cents, body.sale_price_per_block_cents if body.sale_active else None):
        if per_block is not None and min_blocks * per_block < STRIPE_MIN_CHARGE_CENTS:
            raise HTTPException(
                status_code=400,
                detail="Stripe can't charge less than $0.50 — raise the price so the smallest checkout reaches it",
            )
    new_values = body.model_dump(exclude={"expected_updated_at"})

    updated_by = getattr(current_user, "email", None) or str(getattr(current_user, "id", ""))

    async with get_connection() as conn:
        async with conn.transaction():
            old_row = await conn.fetchrow(
                """
                SELECT price_per_block_cents, block_size, sale_price_per_block_cents,
                       sale_active, min_headcount, max_headcount, updated_at
                FROM matcha_lite_pricing WHERE product_code = $1
                FOR UPDATE
                """,
                product_code,
            )
            if "expected_updated_at" in body.model_fields_set:
                current = old_row["updated_at"].isoformat() if old_row and old_row["updated_at"] else None
                if current != body.expected_updated_at:
                    raise HTTPException(
                        status_code=409,
                        detail="This price changed since you opened it. Reload to see the latest before saving.",
                    )

            # Upsert rather than requiring a pre-existing row: product_code is
            # already validated against the known PRODUCT_CODES enum, so a
            # missing row just means this environment's seed migration
            # (e.g. mlpricing04 for the add-ons) hasn't landed yet — the
            # admin's first save should create it, not 404.
            new_row = await conn.fetchrow(
                f"""
                INSERT INTO matcha_lite_pricing
                    (product_code, price_per_block_cents, block_size, sale_price_per_block_cents,
                     sale_active, min_headcount, max_headcount, updated_at, updated_by)
                VALUES ($1, $2, $3, $4, $5, $6, $7, now(), $8)
                ON CONFLICT (product_code) DO UPDATE SET
                    price_per_block_cents = EXCLUDED.price_per_block_cents,
                    block_size = EXCLUDED.block_size,
                    sale_price_per_block_cents = EXCLUDED.sale_price_per_block_cents,
                    sale_active = EXCLUDED.sale_active,
                    min_headcount = EXCLUDED.min_headcount,
                    max_headcount = EXCLUDED.max_headcount,
                    updated_at = now(),
                    updated_by = EXCLUDED.updated_by
                RETURNING {SELECT_COLUMNS}
                """,
                product_code,
                body.price_per_block_cents,
                body.block_size,
                body.sale_price_per_block_cents,
                body.sale_active,
                body.min_headcount,
                body.max_headcount,
                updated_by,
            )
            await conn.execute(
                """
                INSERT INTO matcha_lite_pricing_history (changed_by, old_values, new_values)
                VALUES ($1, $2::jsonb, $3::jsonb)
                """,
                updated_by,
                json.dumps({k: v for k, v in dict(old_row).items() if k != "updated_at"}) if old_row else "null",
                json.dumps({**new_values, "product_code": product_code}),
            )

    logger.info("Matcha Lite pricing (%s) updated by %s: %s", product_code, updated_by, new_values)
    if product_code in INCIDENT_PLANS:
        await sync_after_save("incidents", changed_by=updated_by)
    pricing = row_to_pricing(new_row)
    return MatchaLitePricingConfig(**pricing.__dict__)
