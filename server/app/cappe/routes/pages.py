"""Cappe pages — CRUD nested under an owned site."""
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import CappeAccount, CappePage, CappePageCreate, CappePageUpdate
from .render import invalidate_render_cache
from ._shared import get_owned_site, page_row_to_dict, slugify, unique_slug

router = APIRouter()

_PAGE_COLS = "id, site_id, title, slug, content, sort_order, status, created_at, updated_at"


async def _ensure_site_owned(conn, site_id: UUID, account_id: UUID):
    await get_owned_site(conn, site_id, account_id)


@router.get("/sites/{site_id}/pages", response_model=list[CappePage])
async def list_pages(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    """List pages of an owned site, in sort order."""
    async with get_connection() as conn:
        await _ensure_site_owned(conn, site_id, account.id)
        rows = await conn.fetch(
            f"SELECT {_PAGE_COLS} FROM cappe_pages WHERE site_id = $1 ORDER BY sort_order, created_at",
            site_id,
        )
    return [page_row_to_dict(r) for r in rows]


@router.post("/sites/{site_id}/pages", response_model=CappePage, status_code=status.HTTP_201_CREATED)
async def create_page(
    site_id: UUID, body: CappePageCreate, account: CappeAccount = Depends(require_cappe_account)
):
    """Create a page on an owned site (slug unique per site)."""
    async with get_connection() as conn:
        await _ensure_site_owned(conn, site_id, account.id)
        base = slugify(body.slug or body.title)
        # Slug uniqueness is per-site; scope the lookup with a manual check.
        slug = base
        n = 1
        while await conn.fetchval(
            "SELECT 1 FROM cappe_pages WHERE site_id = $1 AND slug = $2", site_id, slug
        ):
            n += 1
            slug = f"{base}-{n}"
        row = await conn.fetchrow(
            f"""INSERT INTO cappe_pages (site_id, title, slug, content, sort_order, status)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING {_PAGE_COLS}""",
            site_id,
            body.title,
            slug,
            json.dumps(body.content),
            body.sort_order,
            body.status,
        )
    await invalidate_render_cache(site_id)
    return page_row_to_dict(row)


@router.put("/sites/{site_id}/pages/{page_id}", response_model=CappePage)
async def update_page(
    site_id: UUID,
    page_id: UUID,
    body: CappePageUpdate,
    account: CappeAccount = Depends(require_cappe_account),
):
    """Update a page on an owned site."""
    async with get_connection() as conn:
        await _ensure_site_owned(conn, site_id, account.id)
        exists = await conn.fetchval(
            "SELECT 1 FROM cappe_pages WHERE id = $1 AND site_id = $2", page_id, site_id
        )
        if not exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")

        sets = []
        args: list = []

        def add(col: str, val):
            args.append(val)
            sets.append(f"{col} = ${len(args)}")

        if body.title is not None:
            add("title", body.title)
        if body.slug is not None:
            add("slug", slugify(body.slug))
        if body.content is not None:
            add("content", json.dumps(body.content))
        if body.sort_order is not None:
            add("sort_order", body.sort_order)
        if body.status is not None:
            add("status", body.status)

        if not sets:
            row = await conn.fetchrow(
                f"SELECT {_PAGE_COLS} FROM cappe_pages WHERE id = $1", page_id
            )
            return page_row_to_dict(row)

        sets.append("updated_at = NOW()")
        args.extend([page_id, site_id])
        try:
            row = await conn.fetchrow(
                f"""UPDATE cappe_pages SET {', '.join(sets)}
                    WHERE id = ${len(args) - 1} AND site_id = ${len(args)}
                    RETURNING {_PAGE_COLS}""",
                *args,
            )
        except Exception as exc:
            if "cappe_pages_site_id_slug_key" in str(exc):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, detail="A page with that slug already exists"
                )
            raise
    await invalidate_render_cache(site_id)
    return page_row_to_dict(row)


@router.delete("/sites/{site_id}/pages/{page_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_page(
    site_id: UUID, page_id: UUID, account: CappeAccount = Depends(require_cappe_account)
):
    """Delete a page on an owned site."""
    async with get_connection() as conn:
        await _ensure_site_owned(conn, site_id, account.id)
        result = await conn.execute(
            "DELETE FROM cappe_pages WHERE id = $1 AND site_id = $2", page_id, site_id
        )
        if result.endswith("0"):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found")
    await invalidate_render_cache(site_id)
