"""Cappe blog/CMS — posts CRUD (owner side). Public listing lives in public.py."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import CappeAccount, CappePost, CappePostCreate, CappePostUpdate
from ._shared import get_owned_site, slugify, unique_site_slug

router = APIRouter()

_POST_COLS = (
    "id, site_id, title, slug, excerpt, body, cover_image_url, status, "
    "published_at, created_at, updated_at"
)


@router.get("/sites/{site_id}/posts", response_model=list[CappePost])
async def list_posts(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        rows = await conn.fetch(
            f"SELECT {_POST_COLS} FROM cappe_posts WHERE site_id = $1 ORDER BY created_at DESC",
            site_id,
        )
    return [dict(r) for r in rows]


@router.post("/sites/{site_id}/posts", response_model=CappePost, status_code=status.HTTP_201_CREATED)
async def create_post(
    site_id: UUID, body: CappePostCreate, account: CappeAccount = Depends(require_cappe_account)
):
    published_clause = "NOW()" if body.status == "published" else "NULL"
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        slug = await unique_site_slug(conn, "cappe_posts", site_id, slugify(body.slug or body.title))
        row = await conn.fetchrow(
            f"""INSERT INTO cappe_posts
                    (site_id, title, slug, excerpt, body, cover_image_url, status, published_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, {published_clause})
                RETURNING {_POST_COLS}""",
            site_id, body.title, slug, body.excerpt, body.body, body.cover_image_url, body.status,
        )
    return dict(row)


@router.get("/sites/{site_id}/posts/{post_id}", response_model=CappePost)
async def get_post(site_id: UUID, post_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        row = await conn.fetchrow(
            f"SELECT {_POST_COLS} FROM cappe_posts WHERE id = $1 AND site_id = $2", post_id, site_id
        )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    return dict(row)


@router.put("/sites/{site_id}/posts/{post_id}", response_model=CappePost)
async def update_post(
    site_id: UUID, post_id: UUID, body: CappePostUpdate,
    account: CappeAccount = Depends(require_cappe_account),
):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        sets, args = [], []
        for col in ("title", "excerpt", "body", "cover_image_url", "status"):
            val = getattr(body, col)
            if val is not None:
                args.append(val)
                sets.append(f"{col} = ${len(args)}")
        if body.slug is not None:
            args.append(slugify(body.slug))
            sets.append(f"slug = ${len(args)}")
        # Stamp published_at the first time it goes public.
        if body.status == "published":
            sets.append("published_at = COALESCE(published_at, NOW())")
        if not sets:
            row = await conn.fetchrow(
                f"SELECT {_POST_COLS} FROM cappe_posts WHERE id = $1 AND site_id = $2", post_id, site_id
            )
            if row is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
            return dict(row)
        sets.append("updated_at = NOW()")
        args.extend([post_id, site_id])
        try:
            row = await conn.fetchrow(
                f"UPDATE cappe_posts SET {', '.join(sets)} "
                f"WHERE id = ${len(args) - 1} AND site_id = ${len(args)} RETURNING {_POST_COLS}",
                *args,
            )
        except Exception as exc:
            if "cappe_posts_site_id_slug_key" in str(exc):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A post with that slug exists")
            raise
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    return dict(row)


@router.delete("/sites/{site_id}/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(site_id: UUID, post_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        result = await conn.execute(
            "DELETE FROM cappe_posts WHERE id = $1 AND site_id = $2", post_id, site_id
        )
    if result.endswith(" 0"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
