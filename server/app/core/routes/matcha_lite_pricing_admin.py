"""Master-admin — configure Matcha Lite pricing (base price + optional sale price).

Single-row config table (matcha_lite_pricing); every change is recorded to
matcha_lite_pricing_history in the same transaction, since this directly sets
what customers are charged.
"""
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ...database import get_connection
from ..dependencies import require_admin
from ..services.matcha_lite_pricing import (
    PRODUCT_CODES,
    SELECT_COLUMNS,
    get_matcha_lite_pricing,
    row_to_pricing,
)

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
    if body.min_headcount > body.max_headcount:
        raise HTTPException(status_code=400, detail="min_headcount cannot exceed max_headcount")
    if body.sale_active and body.sale_price_per_block_cents is None:
        raise HTTPException(status_code=400, detail="sale_price_per_block_cents is required when sale_active is true")

    updated_by = getattr(current_user, "email", None) or str(getattr(current_user, "id", ""))

    async with get_connection() as conn:
        async with conn.transaction():
            old_row = await conn.fetchrow(
                """
                SELECT price_per_block_cents, block_size, sale_price_per_block_cents,
                       sale_active, min_headcount, max_headcount
                FROM matcha_lite_pricing WHERE product_code = $1
                FOR UPDATE
                """,
                product_code,
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
                json.dumps(dict(old_row)) if old_row else "null",
                json.dumps({**body.model_dump(), "product_code": product_code}),
            )

    logger.info("Matcha Lite pricing (%s) updated by %s: %s", product_code, updated_by, body.model_dump())
    pricing = row_to_pricing(new_row)
    return MatchaLitePricingConfig(**pricing.__dict__)
