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
from ..services.matcha_lite_pricing import PRODUCT_CODES, SELECT_COLUMNS, row_to_pricing

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
    async with get_connection() as conn:
        row = await conn.fetchrow(f"SELECT {SELECT_COLUMNS} FROM matcha_lite_pricing WHERE product_code = $1", product_code)
    if not row:
        raise HTTPException(status_code=404, detail="Pricing config not found")
    pricing = row_to_pricing(row)
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
            if not old_row:
                raise HTTPException(status_code=404, detail="Pricing config not found")

            new_row = await conn.fetchrow(
                f"""
                UPDATE matcha_lite_pricing
                SET price_per_block_cents = $1, block_size = $2, sale_price_per_block_cents = $3,
                    sale_active = $4, min_headcount = $5, max_headcount = $6,
                    updated_at = now(), updated_by = $7
                WHERE product_code = $8
                RETURNING {SELECT_COLUMNS}
                """,
                body.price_per_block_cents,
                body.block_size,
                body.sale_price_per_block_cents,
                body.sale_active,
                body.min_headcount,
                body.max_headcount,
                updated_by,
                product_code,
            )
            await conn.execute(
                """
                INSERT INTO matcha_lite_pricing_history (changed_by, old_values, new_values)
                VALUES ($1, $2::jsonb, $3::jsonb)
                """,
                updated_by,
                json.dumps(dict(old_row)),
                json.dumps({**body.model_dump(), "product_code": product_code}),
            )

    logger.info("Matcha Lite pricing (%s) updated by %s: %s", product_code, updated_by, body.model_dump())
    pricing = row_to_pricing(new_row)
    return MatchaLitePricingConfig(**pricing.__dict__)
