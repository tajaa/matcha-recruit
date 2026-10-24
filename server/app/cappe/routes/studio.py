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

`POST …/ask` answers a question about the Studio or the page being designed
(`services/magazine/studio/ask.py`). It saves nothing.
"""
import json
from typing import Annotated, Any, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ...core.services.redis_cache import check_rate_limit
from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import CappeAccount
from ..services.entitlements import resolve_entitlements
from ..services.magazine.stories import POST_COLS, post_row, sync_post_assets
from ..services.magazine.story_schema import referenced_asset_ids
from ..services.magazine.studio import ask
from ..services.magazine.studio import bank as studio_bank
from ..services.magazine.studio.identity import portable_identity
from ..services.magazine.studio.schema import DocError
from ..services.magazine.studio.fonts import manifest
from ..services.magazine.studio.limits import limits
from ._shared import get_owned_site
from .blog import pages_fields
from .render import invalidate_render_cache

router = APIRouter()

KEEP_REVISIONS = 50
NOT_PAGES = "This story isn't made of pages. Open it in the story editor."


class StudioIdentitySave(BaseModel):
    base_rev: int = Field(ge=0)
    identity: dict[str, Any]


def _identity_record(row):
    if row is None:
        return {"rev": 0, "identity": None}
    return {"rev": row["rev"], "identity": json.loads(row["identity"]) if isinstance(row["identity"], str) else row["identity"]}


@router.get("/sites/{site_id}/studio/identity")
async def open_identity(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        row = await conn.fetchrow("SELECT rev, identity FROM cappe_studio_identities WHERE site_id = $1", site_id)
    return _identity_record(row)


@router.put("/sites/{site_id}/studio/identity")
async def save_identity(site_id: UUID, body: StudioIdentitySave, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        try:
            bank = await studio_bank.doc_graphics(conn, {"identity": body.identity})
            identity = portable_identity(body.identity, bank)
        except DocError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        async with conn.transaction():
            # Serialize first saves too, and recheck ownership after any wait.
            owned = await conn.fetchval("SELECT id FROM cappe_sites WHERE id = $1 AND account_id = $2 FOR UPDATE", site_id, account.id)
            if owned is None:
                raise HTTPException(status_code=404, detail="Site not found")
            previous = _identity_record(await conn.fetchrow("SELECT rev, identity FROM cappe_studio_identities WHERE site_id = $1", site_id))
            if body.base_rev != previous["rev"]:
                if body.base_rev + 1 == previous["rev"] and identity == previous["identity"]:
                    return previous  # lost successful response: the same snapshot
                raise HTTPException(status_code=409, detail="The magazine identity changed elsewhere. Reload it before saving.")
            saved = {"rev": previous["rev"] + 1, "identity": identity}
            await conn.execute(
                "INSERT INTO cappe_studio_identities (site_id, rev, identity) VALUES ($1, $2, $3::jsonb) "
                "ON CONFLICT (site_id) DO UPDATE SET rev = EXCLUDED.rev, identity = EXCLUDED.identity, updated_at = NOW()",
                site_id, saved["rev"], json.dumps(identity),
            )
    return saved


class StudioSave(BaseModel):
    base_rev: int = Field(ge=0)
    doc: dict[str, Any]
    # A published story: update the live pages (else its working copy).
    publish: bool = False
    # Keep this save as a revision to go back to (autosaves aren't).
    keep: bool = False
    identity_version: Optional[Literal[1]] = None


class StudioRestore(BaseModel):
    base_rev: int = Field(ge=0)
    identity_version: Optional[Literal[1]] = None


_Id = Annotated[str, Field(max_length=40, pattern=r"^[a-z0-9-]+$")]
_Point = Annotated[str, Field(max_length=600)]


class StudioAskTurn(BaseModel):
    q: str = Field(max_length=ask.MAX_QUESTION)
    a: str = Field(max_length=ask.MAX_TURN)


class StudioGuideSection(BaseModel):
    id: _Id
    title: str = Field(max_length=120)
    body: str = Field("", max_length=1_000)
    points: list[_Point] = Field(default_factory=list, max_length=16)


class StudioCommand(BaseModel):
    id: _Id
    label: str = Field(max_length=80)
    keys: str = Field("", max_length=16)
    enabled: bool = True


class StudioPicture(BaseModel):
    media_type: Literal["image/jpeg", "image/png", "image/webp"]
    data: str = Field(max_length=(ask.MAX_PICTURE_BYTES * 4) // 3 + 4)


class StudioAsk(BaseModel):
    question: str = Field(min_length=1, max_length=ask.MAX_QUESTION)
    history: list[StudioAskTurn] = Field(default_factory=list, max_length=ask.MAX_HISTORY)
    guide: list[StudioGuideSection] = Field(default_factory=list, max_length=40)
    commands: list[StudioCommand] = Field(default_factory=list, max_length=150)
    page: str = Field("", max_length=ask.MAX_PAGE_CHARS)
    picture: Optional[StudioPicture] = None


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


def _identity_supported(version, *docs):
    if version != 1 and any(isinstance(doc, dict) and doc.get("identity") is not None for doc in docs):
        raise HTTPException(status_code=409, detail={"code": "studio_upgrade", "message": "This issue uses a magazine identity. Reload the Studio before editing it."})


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
            _identity_supported(body.identity_version, body.doc, _doc_of(row["draft"]), _doc_of(row["content"]))
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
            _identity_supported(body.identity_version, _doc_of(row["draft"]), _doc_of(row["content"]))
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
            _identity_supported(body.identity_version, doc, _doc_of(row["draft"]), _doc_of(row["content"]))
            if doc is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")
            saved = await _write(conn, row, doc, publish=False, keep="restore")
    if saved.pop("live_changed") and row["status"] == "published":
        await invalidate_render_cache(site_id)
    return saved


@router.post("/sites/{site_id}/studio/stories/{post_id}/ask")
async def ask_studio(site_id: UUID, post_id: UUID, body: StudioAsk,
                     account: CappeAccount = Depends(require_cappe_account)):
    """An answer to a question about the Studio or the page in view:
    `{"answer": Markdown, "links": [{"kind": "guide" | "command", "id"}]}`.
    Nothing is saved and nothing on the page changes."""
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        fmt = await conn.fetchval("SELECT format FROM cappe_posts WHERE id = $1 AND site_id = $2", post_id, site_id)
        if fmt is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Story not found")
        if fmt != "pages":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=NOT_PAGES)
        ent = await resolve_entitlements(account.plan, conn=conn)
    try:
        q = ask.question(body.model_dump())
    except ask.AskInvalid as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await check_rate_limit(str(account.id), "cappe_studio_ask", ask.daily_allowance(ent.features), 86_400)
    try:
        return await ask.answer(q)
    except ask.AskUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=ask.UNAVAILABLE) from exc
    except ask.AskFailed as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=ask.FAILED) from exc
