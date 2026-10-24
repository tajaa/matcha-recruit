"""Cappe blog/CMS — posts CRUD (owner side), which since cappemag02 are also
magazine stories. Public listing lives in routes/public/blog.py; the rendered
pages in routes/render.py.

Two kinds of post share one table and one API:

  * a legacy post (`format='markdown'`) is a title and a Markdown `body` — what
    the iOS app creates and edits, unchanged;
  * a story (`format='blocks'`) keeps its words and pictures in `content`.
    Its `body` is derived from the blocks on every save so the app has
    something to show, and an app edit that changes `body` is refused (409):
    writing plain text back would wipe the layout;
  * a paged story (`format='pages'`) is made here with its first pages and
    designed in the Studio, which saves its document (`routes/studio.py`).
    Here it changes only what isn't on its pages: title, status, topic,
    access and the like.

Every write drops the site's rendered pages from the cache.
"""
import json
import re
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse

from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import (
    CappeAccount,
    CappePost,
    CappePostCreate,
    CappePostUpdate,
    CappeStoryOptions,
    CappeStoryPreview,
)
from ..services.magazine import pages as mag_pages
from ..services.magazine.magazines import get_magazine, preview_blocks
from ..services.magazine.richtext import md_to_text
from ..services.magazine.stories import (
    POST_COLS,
    check_assets,
    cover_asset,
    post_row,
    reading_stats,
    story_text,
    sync_post_assets,
    with_documents,
)
from ..services.magazine.story_schema import (
    LAYOUTS,
    StoryError,
    normalize_layout,
    normalize_story,
    referenced_asset_ids,
    starter_content,
    with_designs,
)
from ..services.magazine.studio import bank as studio_bank
from ..services.magazine.studio import custom_fonts
from ..services.magazine.studio.schema import DocError, normalize_doc, starter_doc
from ..services.magazine.topics import TOPICS, normalize_topic
from ._shared import get_owned_site, slugify, unique_site_slug
from .render import _nav, _site_dict, invalidate_render_cache, tenant_security_headers

router = APIRouter()

EDIT_ON_WEB = "This story has a magazine layout. Edit it on the web at gummfit.com."
EDIT_IN_STUDIO = "This story is made of pages. Change them in the Studio."


def _out(row, *, documents: bool = True) -> dict[str, Any]:
    """A post for the owner. One story (`documents`) carries a document for
    every rich field, for the editor; the list doesn't, so it never converts
    every old story's Markdown on each load. Both give an old photo's
    overlays as its design (the issue editor edits stories from the list)."""
    d = post_row(row)
    d["hidden"] = d.pop("hidden_at", None) is not None
    if d.get("format") == "blocks":
        content = d["content"]
        d["content"] = (with_documents(content) if documents
                        else {**content, "blocks": with_designs(content.get("blocks") or [])})
    if not documents and d.get("format") == "pages":
        d["content"] = None  # a document of pages is the Studio's to open, not the list's
    return d


def _unprocessable(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=message)


def _topic(value: Optional[str]) -> Optional[str]:
    if value in (None, ""):
        return None
    topic = normalize_topic(value)
    if topic is None:
        raise _unprocessable("Pick a topic from the list.")
    return topic


PAID_OFF = "Turn on paid subscriptions in the magazine's settings first."


async def _check_paid(conn, site_id: UUID, access: Optional[str]) -> None:
    """A story can be for subscribers only while the magazine takes them. A
    story already paid stays paid when they're turned off (its readers keep
    what they paid for); it just can't newly become paid."""
    if access == "paid" and not await conn.fetchval(
        "SELECT paid_enabled FROM cappe_magazines WHERE site_id = $1", site_id,
    ):
        raise _unprocessable(PAID_OFF)


async def _story_fields(conn, site_id: UUID, content: dict, cover_asset_id: Optional[UUID]) -> dict[str, Any]:
    """What a story's blocks decide: the stored blocks, the derived body, the
    reading time, the cover picture (and its URL, which old readers of
    `cover_image_url` keep showing)."""
    try:
        clean = normalize_story(content)
        assets = await check_assets(conn, site_id, clean, str(cover_asset_id) if cover_asset_id else None)
    except StoryError as exc:
        raise _unprocessable(str(exc)) from exc
    text = story_text(clean)
    words, minutes = reading_stats(text)
    cover_id = cover_asset(clean, cover_asset_id)
    return {
        "content": clean,
        "body": text,
        "word_count": words,
        "reading_minutes": minutes,
        "cover_image_url": assets[cover_id]["url"] if cover_id else None,
        "_asset_ids": referenced_asset_ids(clean, cover_asset_id),
    }


async def pages_fields(conn, site_id: UUID, raw_doc: Any) -> dict[str, Any]:
    """What a paged story's document decides: the stored document, the text
    the app and the feed read (its Text view), the reading time and its cover
    picture (the biggest on its first page)."""
    try:
        doc = normalize_doc(raw_doc, await studio_bank.doc_graphics(conn, raw_doc),
                            await custom_fonts.doc_faces(conn, site_id, raw_doc))
        content = {"doc": doc}
        assets = await check_assets(conn, site_id, content, None)
    except (DocError, StoryError) as exc:
        raise _unprocessable(str(exc)) from exc
    text = story_text(content)
    words, minutes = reading_stats(text)
    cover_id = cover_asset(content, None)
    return {
        "content": content,
        "body": text,
        "word_count": words,
        "reading_minutes": minutes,
        "cover_asset_id": cover_id,
        "cover_image_url": assets[cover_id]["url"] if cover_id else None,
        "_asset_ids": referenced_asset_ids(content),
    }


def _markdown_stats(body: Optional[str]) -> dict[str, Any]:
    words, minutes = reading_stats(md_to_text(body))
    return {"word_count": words, "reading_minutes": minutes}


@router.get("/sites/{site_id}/posts", response_model=list[CappePost])
async def list_posts(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        rows = await conn.fetch(
            f"SELECT {POST_COLS} FROM cappe_posts WHERE site_id = $1 ORDER BY created_at DESC",
            site_id,
        )
    return [_out(r, documents=False) for r in rows]


@router.post("/sites/{site_id}/posts", response_model=CappePost, status_code=status.HTTP_201_CREATED)
async def create_post(
    site_id: UUID, body: CappePostCreate, account: CappeAccount = Depends(require_cappe_account)
):
    topic = _topic(body.topic)
    layout = normalize_layout(body.layout)
    paged = body.format == "pages"
    is_story = paged or body.format == "blocks" or body.content is not None
    published_clause = "NOW()" if body.status == "published" else "NULL"
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        await _check_paid(conn, site_id, body.access)
        if paged:
            raw_doc = (body.content or {}).get("doc")
            if not raw_doc:
                raw_doc = starter_doc()
                saved = await conn.fetchrow("SELECT identity FROM cappe_studio_identities WHERE site_id = $1", site_id)
                if saved is not None:
                    template = json.loads(saved["identity"]) if isinstance(saved["identity"], str) else saved["identity"]
                    raw_doc["identity"] = template
                    body_style = next((s for s in template.get("paragraphs", []) if s.get("para", {}).get("role", "p") == "p"), None)
                    if body_style:
                        for thread in raw_doc["threads"]:
                            for paragraph in thread["paras"]:
                                paragraph["style"] = body_style["id"]
            derived = await pages_fields(conn, site_id, raw_doc)
        elif is_story:
            derived = await _story_fields(conn, site_id, body.content or starter_content(layout),
                                          body.cover_asset_id)
        else:
            if body.cover_asset_id:
                raise _unprocessable("Only a story has a cover from the library.")
            derived = {"content": {}, "body": body.body, "cover_image_url": body.cover_image_url,
                       "_asset_ids": set(), **_markdown_stats(body.body)}
        slug = await unique_site_slug(conn, "cappe_posts", site_id, slugify(body.slug or body.title))
        async with conn.transaction():
            row = await conn.fetchrow(
                f"""INSERT INTO cappe_posts
                        (site_id, title, slug, excerpt, body, cover_image_url, status, published_at,
                         format, content, kicker, topic, layout, access, cover_asset_id, byline,
                         word_count, reading_minutes)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, {published_clause},
                            $8, $9::jsonb, $10, $11, $12, $17, $13, $14, $15, $16)
                    RETURNING {POST_COLS}""",
                site_id, body.title, slug, body.excerpt, derived["body"], derived["cover_image_url"], body.status,
                "pages" if paged else "blocks" if is_story else "markdown", json.dumps(derived["content"]),
                body.kicker, topic, layout, derived.get("cover_asset_id", body.cover_asset_id), body.byline,
                derived["word_count"], derived["reading_minutes"], body.access or "free",
            )
            if is_story:
                await sync_post_assets(conn, row["id"], site_id, derived["_asset_ids"])
    await invalidate_render_cache(site_id)
    return _out(row)


@router.get("/sites/{site_id}/posts/{post_id}", response_model=CappePost)
async def get_post(site_id: UUID, post_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        row = await conn.fetchrow(
            f"SELECT {POST_COLS} FROM cappe_posts WHERE id = $1 AND site_id = $2", post_id, site_id
        )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    return _out(row)


_SIMPLE = ("title", "excerpt", "status", "kicker", "byline")


def _changed(body: CappePostUpdate, current: dict, col: str) -> bool:
    """Whether `col` was sent with a value other than the stored one."""
    if col not in body.model_fields_set:
        return False
    sent, stored = getattr(body, col), current.get(col)
    if col == "cover_asset_id":
        return (str(sent) if sent else None) != (str(stored) if stored else None)
    return sent != stored
# The address a story is made with ("Untitled story" → untitled-story-3).
_PLACEHOLDER_SLUG = re.compile(r"untitled(-story)?(-\d+)?")
_NULLABLE = {"excerpt", "kicker", "byline", "topic", "cover_asset_id", "cover_image_url", "body"}


@router.put("/sites/{site_id}/posts/{post_id}", response_model=CappePost)
async def update_post(
    site_id: UUID, post_id: UUID, body: CappePostUpdate,
    account: CappeAccount = Depends(require_cappe_account),
):
    sent = body.model_fields_set
    for col in sent:
        if getattr(body, col) is None and col not in _NULLABLE:
            raise _unprocessable(f"These fields cannot be null: {col}")
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        async with conn.transaction():
            current = await conn.fetchrow(
                f"SELECT {POST_COLS} FROM cappe_posts WHERE id = $1 AND site_id = $2 FOR UPDATE", post_id, site_id
            )
            if current is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
            current = post_row(current)
            paged = current["format"] == "pages"
            # A paged story's layout is the Studio's: a change to it is refused
            # here, but the same value sent back (the iOS app sends its cover
            # with every save) is no change.
            if paged and (any(_changed(body, current, col) for col in ("content", "cover_asset_id", "cover_image_url"))
                          or ("format" in sent and body.format != "pages")):
                raise _unprocessable(EDIT_IN_STUDIO)
            if not paged and body.format == "pages":
                raise _unprocessable("A story can't become pages here. Make a new story in the Studio.")
            is_story = not paged and (current["format"] == "blocks" or body.format == "blocks" or "content" in sent)
            if current["format"] == "blocks" and body.format == "markdown":
                raise _unprocessable("A story can't go back to plain text.")
            if current["format"] in ("blocks", "pages") and "body" in sent \
                    and (body.body or "") != (current["body"] or ""):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=EDIT_ON_WEB)

            values: dict[str, Any] = {col: getattr(body, col) for col in _SIMPLE if col in sent}
            if "access" in sent and body.access != current["access"]:
                await _check_paid(conn, site_id, body.access)
                values["access"] = body.access
            if "topic" in sent:
                values["topic"] = _topic(body.topic)
            if "layout" in sent and body.layout is not None:
                values["layout"] = normalize_layout(body.layout)
            if is_story:
                if "cover_asset_id" in sent:
                    values["cover_asset_id"] = body.cover_asset_id
                if sent & {"content", "cover_asset_id", "format"} or current["format"] != "blocks":
                    if "content" in sent:
                        content = body.content
                    elif current["format"] != "blocks":
                        # A plain post becoming a story keeps its words (as sent with
                        # the change, else as stored) as the first text.
                        words = body.body if "body" in sent else current["body"]
                        content = {"blocks": [{"type": "text", "md": words or "", "dropcap": True}]}
                    else:
                        content = current["content"] or None
                    cover_id = values.get("cover_asset_id", current["cover_asset_id"])
                    derived = await _story_fields(conn, site_id, content or starter_content(
                        values.get("layout", current["layout"])), cover_id)
                    values.update(format="blocks", content=json.dumps(derived["content"]), body=derived["body"],
                                  word_count=derived["word_count"], reading_minutes=derived["reading_minutes"],
                                  cover_image_url=derived["cover_image_url"])
                    await sync_post_assets(conn, post_id, site_id, derived["_asset_ids"])
            elif not paged:
                if "cover_asset_id" in sent and body.cover_asset_id:
                    raise _unprocessable("Only a story has a cover from the library.")
                if "body" in sent:
                    values["body"] = body.body
                    values.update(_markdown_stats(body.body))
                if "cover_image_url" in sent:
                    values["cover_image_url"] = body.cover_image_url
            if body.slug is not None:
                values["slug"] = slugify(body.slug)
            elif body.status == "published" and current["published_at"] is None \
                    and _PLACEHOLDER_SLUG.fullmatch(current["slug"] or ""):
                # Going out for the first time still at its placeholder address:
                # take one from the headline (never changed once published).
                title = values.get("title", current["title"]) or ""
                base = slugify(title)
                if re.search(r"[a-z0-9]", title.lower()) and not _PLACEHOLDER_SLUG.fullmatch(base):
                    values["slug"] = await unique_site_slug(conn, "cappe_posts", site_id, base)

            if not values:
                return _out(current)
            sets, args = [], []
            for col, value in values.items():
                args.append(value)
                sets.append(f"{col} = ${len(args)}{'::jsonb' if col == 'content' else ''}")
            # Stamp published_at the first time it goes public.
            if body.status == "published":
                sets.append("published_at = COALESCE(published_at, NOW())")
            sets.append("updated_at = NOW()")
            args.extend([post_id, site_id])
            try:
                row = await conn.fetchrow(
                    f"UPDATE cappe_posts SET {', '.join(sets)} "
                    f"WHERE id = ${len(args) - 1} AND site_id = ${len(args)} RETURNING {POST_COLS}",
                    *args,
                )
            except Exception as exc:
                if "cappe_posts_site_id_slug_key" in str(exc):
                    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A post with that slug exists")
                raise
    await invalidate_render_cache(site_id)
    return _out(row)


@router.delete("/sites/{site_id}/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(site_id: UUID, post_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        result = await conn.execute(
            "DELETE FROM cappe_posts WHERE id = $1 AND site_id = $2", post_id, site_id
        )
    if result.endswith(" 0"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    await invalidate_render_cache(site_id)


# --- The story editor's helpers ---------------------------------------------

@router.get("/sites/{site_id}/stories/options", response_model=CappeStoryOptions)
async def story_options(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    """The layouts (with the blocks each starts with) and the topics."""
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
    return {
        "layouts": [{"key": k, "label": v, "content": with_documents(starter_content(k))} for k, v in LAYOUTS.items()],
        "topics": [{"key": k, "label": v} for k, v in TOPICS.items()],
    }


@router.post("/sites/{site_id}/stories/preview", response_class=HTMLResponse)
async def preview_story(site_id: UUID, body: CappeStoryPreview,
                        account: CappeAccount = Depends(require_cappe_account)):
    """Render an unsaved story as its page will look, in the site's theme —
    the story editor's preview frame, or with `edit` its page to edit on (the
    whole story, marked, with the editor's script). No persistence, never
    cached."""
    paged = body.format == "pages"
    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)
        try:
            if paged:
                raw_doc = body.content.get("doc")
                content = {"doc": normalize_doc(raw_doc, await studio_bank.doc_graphics(conn, raw_doc),
                                                await custom_fonts.doc_faces(conn, site_id, raw_doc))}
            else:
                content = normalize_story(body.content)
            assets = await check_assets(conn, site_id, content,
                                        str(body.cover_asset_id) if body.cover_asset_id else None)
        except (StoryError, DocError) as exc:
            raise _unprocessable(str(exc)) from exc
        magazine = await get_magazine(conn, site_id) or {"name": site["name"], "masthead_style": "classic"}
        nav = await _nav(conn, site_id)
    text = story_text(content)
    _words, minutes = reading_stats(text)
    post = {
        # On the page to edit, an empty headline stays empty so its placeholder shows.
        "id": "preview", "slug": "preview", "title": body.title or ("" if body.edit else "Untitled story"),
        "excerpt": body.excerpt,
        "kicker": body.kicker, "topic": normalize_topic(body.topic), "layout": normalize_layout(body.layout),
        "byline": body.byline, "access": body.access, "format": "pages" if paged else "blocks", "content": content,
        "cover_asset_id": body.cover_asset_id, "reading_minutes": minutes,
        "published_at": datetime.now(timezone.utc), "updated_at": None,
    }
    html = mag_pages.render_story(_site_dict(site), nav, magazine, post, assets, more=[], more_covers={},
                                  origin="", preview_blocks=preview_blocks(magazine), currency=site.get("currency"),
                                  edit=body.edit)
    return HTMLResponse(html, headers={**tenant_security_headers(), "Cache-Control": "no-store"})
