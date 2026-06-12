"""Cappe template catalog — public, read-only."""
from fastapi import APIRouter, HTTPException, Query, status

from ...database import get_connection
from ..models.cappe import CappeTemplateDetail, CappeTemplateSummary
from ._shared import loads

router = APIRouter()

_SUMMARY_COLS = "id, name, slug, category, description, preview_image_url, is_premium, price_cents"


@router.get("/templates", response_model=list[CappeTemplateSummary])
async def list_templates(category: str | None = Query(default=None)):
    """List active templates, optionally filtered by category."""
    async with get_connection() as conn:
        if category:
            rows = await conn.fetch(
                f"SELECT {_SUMMARY_COLS} FROM cappe_templates "
                "WHERE is_active = true AND category = $1 ORDER BY name",
                category,
            )
        else:
            rows = await conn.fetch(
                f"SELECT {_SUMMARY_COLS} FROM cappe_templates WHERE is_active = true ORDER BY category, name"
            )
    return [dict(r) for r in rows]


@router.get("/templates/{slug}", response_model=CappeTemplateDetail)
async def get_template(slug: str):
    """Get one active template by slug, including its full structure."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            f"SELECT {_SUMMARY_COLS}, structure FROM cappe_templates "
            "WHERE slug = $1 AND is_active = true",
            slug,
        )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    d = dict(row)
    d["structure"] = loads(row["structure"])
    return d
