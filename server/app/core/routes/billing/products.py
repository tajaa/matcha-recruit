"""Public product info — powers the generic /p/<slug>/signup page.

Unauthenticated by design (the signup page renders before an account exists),
so it serves only published products and only marketing-safe fields
(ProductDefinition.public_dict): name, description, granted features, pricing.
"""
import logging

from fastapi import APIRouter, HTTPException

from app.database import get_connection
from app.core.services.product_definitions import get_product_by_slug

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/{slug}")
async def get_public_product(slug: str):
    async with get_connection() as conn:
        product = await get_product_by_slug(conn, slug.strip().lower(), published_only=True)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product.public_dict()
