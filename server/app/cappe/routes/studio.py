"""Gummfit Studio: opening and saving a paged story's document.

A paged story (`format='pages'`) is made by `POST /sites/{id}/posts` with
`format: "pages"` and designed here. Every save names the revision it
started from (`base_rev`) and is refused with 409 `stale_rev` when another
save came first (a second tab, a second person), so nothing is silently
overwritten.

While a story is unpublished, a save is the story. Once it is published,
readers keep its live pages: the Studio saves to its working copy (`draft`)
until the owner updates the live story (`publish: true`), or throws the
working copy away. Pictures in either are recorded as the story's, so the
library won't delete one while it is on a page.

Each update of the live story, each restore and each save the owner asks to
keep (`keep: true`) is kept as a revision to go back to (the last
`KEEP_REVISIONS`).
"""
import json
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import CappeAccount
from ..services.magazine.stories import POST_COLS, post_row, sync_post_assets
from ..services.magazine.story_schema import referenced_asset_ids
from ..services.magazine.studio.fonts import manifest
from ..services.magazine.studio.limits import limits
from ._shared import get_owned_site
from .blog import pages_fields
from .render import invalidate_render_cache

router = APIRouter()

KEEP_REVISIONS = 50
NOT_PAGES = "This story isn't made of pages. Open it in the story editor."


class StudioSave(BaseModel):
    base_rev: int = Field(ge=0)
    doc: dict[str, Any]
    # A published story: update the live pages (else its working copy).
    publish: bool = False
    # Keep this save as a revision to go back to (autosaves aren't).
    keep: bool = False


class StudioRestore(BaseModel):
    base_rev: int = Field(ge=0)


def _stale(rev: int) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail={
        "code": "stale_rev", "rev": rev,
        "message": "This story was saved somewhere else since you opened it. Reload it to see those changes.",
    })


def _doc_of(value: Any) -> Optional[dict]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return None
    return value.get("doc") if isinstance(value, dict) and isinstance(value.get("doc"), dict) else None


def _opened(row) -> dict[str, Any]:
    post = post_row(row)
    draft = _doc_of(row["draft"])
    live = post["status"] == "published"
    return {
        "post": {k: post.get(k) for k in ("id", "site_id", "title", "slug", "excerpt", "kicker", "byline", "topic",
                                          "access", "status", "published_at", "updated_at", "rev")},
        "doc": draft or (post["content"] or {}).get("doc"),
        "draft": draft is not None,
        "live": live,
    }


async def _locked_story(conn, site_id: UUID, post_id: UUID):
    row = await conn.fetchrow(
        f"SELECT {POST_COLS}, draft FROM cappe_posts WHERE id = $1 AND site_id = $2 FOR UPDATE", post_id, site_id,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Story not found")
    if row["format"] != "pages":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=NOT_PAGES)
    return row


async def _keep(conn, row, kind: str, content: dict, rev: int) -> None:
    await conn.execute(
        "INSERT INTO cappe_post_revisions (post_id, site_id, rev, kind, title, content) VALUES ($1, $2, $3, $4, $5, $6::jsonb)",
        row["id"], row["site_id"], rev, kind, row["title"], json.dumps(content),
    )
    await conn.execute(
        "DELETE FROM cappe_post_revisions WHERE post_id = $1 AND id NOT IN "
        "(SELECT id FROM cappe_post_revisions WHERE post_id = $1 ORDER BY created_at DESC LIMIT $2)",
        row["id"], KEEP_REVISIONS,
    )


async def _write(conn, row, raw_doc: dict, *, publish: bool, keep: Optional[str]) -> dict[str, Any]:
    """Save a document: the story itself, or (published, not `publish`) its
    working copy. Returns the new revision and where it went."""
    derived = await pages_fields(conn, row["site_id"], raw_doc)
    rev = row["rev"] + 1
    to_draft = row["status"] == "published" and not publish
    if to_draft:
        await conn.execute("UPDATE cappe_posts SET draft = $1::jsonb, rev = $2, updated_at = NOW() WHERE id = $3",
                           json.dumps(derived["content"]), rev, row["id"])
        live_ids = referenced_asset_ids(post_row(row)["content"] or {})
    else:
        await conn.execute(
            "UPDATE cappe_posts SET content = $1::jsonb, draft = NULL, body = $2, word_count = $3, "
            "reading_minutes = $4, cover_asset_id = $5, cover_image_url = $6, rev = $7, updated_at = NOW() "
            "WHERE id = $8",
            json.dumps(derived["content"]), derived["body"], derived["word_count"], derived["reading_minutes"],
            derived["cover_asset_id"], derived["cover_image_url"], rev, row["id"],
        )
        live_ids = set()
    await sync_post_assets(conn, row["id"], row["site_id"], derived["_asset_ids"] | live_ids)
    if keep:
        await _keep(conn, row, keep, derived["content"], rev)
    return {"rev": rev, "draft": to_draft, "doc": derived["content"]["doc"], "live_changed": not to_draft}


@router.get("/sites/{site_id}/studio/limits")
async def studio_limits(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    """The limits a paged story is held to, and the faces the Studio sets
    type in (`fonts_manifest.json`)."""
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
    return {"limits": limits(), "fonts": manifest()}


@router.get("/sites/{site_id}/studio/stories/{post_id}")
async def open_story(site_id: UUID, post_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    """A paged story to design: its working copy if it has one, else the story."""
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        row = await conn.fetchrow(f"SELECT {POST_COLS}, draft FROM cappe_posts WHERE id = $1 AND site_id = $2",
                                  post_id, site_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Story not found")
    if row["format"] != "pages":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=NOT_PAGES)
    return _opened(row)


@router.put("/sites/{site_id}/studio/stories/{post_id}")
async def save_story(site_id: UUID, post_id: UUID, body: StudioSave,
                     account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        async with conn.transaction():
            row = await _locked_story(conn, site_id, post_id)
            if body.base_rev != row["rev"]:
                raise _stale(row["rev"])
            published = row["status"] == "published"
            keep = "publish" if (published and body.publish) else ("save" if body.keep else None)
            saved = await _write(conn, row, body.doc, publish=body.publish, keep=keep)
    if saved.pop("live_changed") and published:
        await invalidate_render_cache(site_id)
    return saved


@router.post("/sites/{site_id}/studio/stories/{post_id}/discard")
async def discard_draft(site_id: UUID, post_id: UUID, body: StudioRestore,
                        account: CappeAccount = Depends(require_cappe_account)):
    """Throw a published story's working copy away: back to its live pages."""
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        async with conn.transaction():
            row = await _locked_story(conn, site_id, post_id)
            if body.base_rev != row["rev"]:
                raise _stale(row["rev"])
            rev = row["rev"] + 1
            await conn.execute("UPDATE cappe_posts SET draft = NULL, rev = $1, updated_at = NOW() WHERE id = $2",
                               rev, post_id)
            content = post_row(row)["content"] or {}
            await sync_post_assets(conn, post_id, site_id, referenced_asset_ids(content))
    return {"rev": rev, "draft": False, "doc": content.get("doc")}


@router.get("/sites/{site_id}/studio/stories/{post_id}/revisions")
async def list_revisions(site_id: UUID, post_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        rows = await conn.fetch(
            "SELECT id, rev, kind, title, created_at FROM cappe_post_revisions WHERE post_id = $1 AND site_id = $2 "
            "ORDER BY created_at DESC", post_id, site_id,
        )
    return [dict(r) for r in rows]


@router.post("/sites/{site_id}/studio/stories/{post_id}/revisions/{revision_id}/restore")
async def restore_revision(site_id: UUID, post_id: UUID, revision_id: UUID, body: StudioRestore,
                           account: CappeAccount = Depends(require_cappe_account)):
    """Bring back an earlier version, as a save: to the working copy of a
    published story (update the live story to show it), else the story."""
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        async with conn.transaction():
            row = await _locked_story(conn, site_id, post_id)
            if body.base_rev != row["rev"]:
                raise _stale(row["rev"])
            kept = await conn.fetchval(
                "SELECT content FROM cappe_post_revisions WHERE id = $1 AND post_id = $2 AND site_id = $3",
                revision_id, post_id, site_id,
            )
            doc = _doc_of(kept)
            if doc is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
            saved = await _write(conn, row, doc, publish=False, keep="restore")
    if saved.pop("live_changed") and row["status"] == "published":
        await invalidate_render_cache(site_id)
    return saved

