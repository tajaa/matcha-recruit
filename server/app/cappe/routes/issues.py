"""Magazine issues in print: numbered books of a magazine's stories, each with
a cover and contents the writer designs (cappemag07). Not the emailed
"issues" of cappemag04 — those are the owner's Emails (`magazine_emails.py`).

  * `GET  /sites/{id}/magazine/issues/options` — the cover templates, the
    limits, and which stories are already in an issue;
  * `GET  /sites/{id}/magazine/issues` — every issue, newest number first;
  * `POST /sites/{id}/magazine/issues` — start one (the next number);
  * `POST /sites/{id}/magazine/issues/preview` — an unsaved issue as its book
    (never stored, never cached);
  * `GET|PUT|DELETE /sites/{id}/magazine/issues/{issue_id}` — a draft can be
    deleted; a released issue is withdrawn first;
  * `POST …/{issue_id}/release` — publish its draft stories and put it out;
  * `POST …/{issue_id}/withdraw` — back to a draft; its stories stay up.

A released issue stays editable and every save shows at once; a draft story
added to it is published by the save. Every write drops the site's rendered
pages from the cache (the front page leads with the current issue).
"""
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse

from ...core.services.redis_cache import check_rate_limit
from ...database import get_connection
from ..dependencies import require_cappe_account
from ..models.cappe import (
    CappeAccount,
    CappeMagazineIssue,
    CappeMagazineIssueCreate,
    CappeMagazineIssueOptions,
    CappeMagazineIssuePreview,
    CappeMagazineIssueSave,
    CappeMagazineIssueSummary,
)
from ..services.magazine import issue_pages, issues as mag_issues, reader as mag_reader
from ..services.magazine.figures import card_image
from ..services.magazine.issue_schema import (
    MAX_LINES,
    MAX_STORIES,
    TEMPLATE_COVERS,
    TEMPLATES,
    IssueError,
    cover_asset_ids,
    normalize_contents,
    normalize_cover,
)
from ..services.magazine.magazines import get_magazine, live_magazine, preview_blocks
from ..services.magazine.stories import POST_COLS, check_assets, cover_asset, post_row, site_assets
from ..services.magazine.story_schema import StoryError, normalize_layout, normalize_story
from ._shared import get_owned_site
from .render import _nav, _site_dict, invalidate_render_cache, tenant_security_headers

router = APIRouter()

_BASE = "/sites/{site_id}/magazine/issues"
PREVIEWS_PER_HOUR = 600
# Editing on the page re-renders the issue on each change of layout.
EDIT_PREVIEWS_PER_HOUR = 2400


def _unprocessable(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


def _not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Issue not found")


async def _cover_picture(conn, site_id: UUID, cover: dict) -> dict[str, Any] | None:
    ids = cover_asset_ids(cover)
    if not ids:
        return None
    asset = (await site_assets(conn, site_id, ids)).get(ids[0])
    picture = card_image(asset)
    return {**picture, "id": ids[0]} if picture else None


async def _out(conn, site_id: UUID, issue: dict, *, published: list[str] | None = None) -> dict[str, Any]:
    stories = await mag_issues.issue_stories(conn, issue["id"])
    covers = await mag_reader.covers(conn, site_id, stories)
    return {
        **issue,
        "hidden": issue.get("hidden_at") is not None,
        "cover_picture": await _cover_picture(conn, site_id, issue["cover"]),
        "published": published or [],
        "stories": [{
            "post_id": s["id"], "title": s.get("title") or "", "slug": s["slug"], "status": s["status"],
            "access": s.get("access") or "free", "hidden": s.get("hidden_at") is not None,
            "excerpt": s.get("excerpt"), "section": s.get("section"), "contents_line": s.get("contents_line"),
            "picture": card_image(covers.get(str(s["id"])), width=480),
        } for s in stories],
    }


@router.get(f"{_BASE}/options", response_model=CappeMagazineIssueOptions)
async def issue_options(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        taken = await mag_issues.taken_stories(conn, site_id)
        number = await mag_issues.next_number(conn, site_id)
    return {
        "templates": [{"key": k, "label": label, "cover": TEMPLATE_COVERS[k]} for k, label in TEMPLATES.items()],
        "max_lines": MAX_LINES, "max_stories": MAX_STORIES, "next_number": number, "taken": taken,
    }


@router.get(_BASE, response_model=list[CappeMagazineIssueSummary])
async def list_issues(site_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        issues = await mag_issues.list_issues(conn, site_id)
        assets = await site_assets(conn, site_id, [a for i in issues for a in cover_asset_ids(i["cover"])])
    out = []
    for issue in issues:
        ids = cover_asset_ids(issue["cover"])
        out.append({**issue, "hidden": issue.get("hidden_at") is not None,
                    "cover_picture": card_image(assets.get(ids[0])) if ids else None})
    return out


@router.post(_BASE, response_model=CappeMagazineIssue, status_code=status.HTTP_201_CREATED)
async def create_issue(site_id: UUID, body: CappeMagazineIssueCreate | None = None,
                       account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)
        magazine = await get_magazine(conn, site_id)
        name = (magazine or {}).get("name") or site["name"]
        try:
            issue = await mag_issues.create_issue(conn, site_id, name=name, template=(body.template if body else None))
        except IssueError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        return await _out(conn, site_id, issue)


@router.post(f"{_BASE}/preview", response_class=HTMLResponse)
async def preview_issue(site_id: UUID, body: CappeMagazineIssuePreview,
                        account: CappeAccount = Depends(require_cappe_account)):
    """An unsaved issue as its book will look, in the site's theme: the issue
    editor's preview. Drafts show as they will once released; a paid story
    shows what a reader without a subscription sees. With `edit`, the issue
    editor's page to edit on: every story whole and marked, with the stories'
    unsaved words (`stories_content`, each checked as a saved story is)."""
    if body.edit:
        await check_rate_limit(str(account.id), "cappe_issue_edit_preview", EDIT_PREVIEWS_PER_HOUR, 3600)
    else:
        await check_rate_limit(str(account.id), "cappe_issue_preview", PREVIEWS_PER_HOUR, 3600)
    refs = [r.model_dump() for r in body.stories]
    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)
        try:
            ids = list(dict.fromkeys(str(r["post_id"]) for r in refs))
            await mag_issues.check_stories(conn, site_id, None, ids)
            cover = normalize_cover(body.cover, story_ids=set(ids))
            await mag_issues.check_cover_assets(conn, site_id, cover)
        except IssueError as exc:
            raise _unprocessable(exc) from exc
        rows = await conn.fetch(
            f"SELECT {POST_COLS} FROM cappe_posts WHERE site_id = $1 AND id = ANY($2::uuid[]) AND hidden_at IS NULL",
            site_id, ids,
        ) if ids else []
        by_id = {str(r["id"]): post_row(r) for r in rows}
        try:
            for post_id, draft in body.stories_content.items():
                post = by_id.get(str(post_id))
                if post is None:
                    continue
                content = normalize_story(draft.content)
                await check_assets(conn, site_id, content, None)
                # The cover picture as saving these words would leave it (the
                # cover block's, or none): never the saved one it replaces.
                post.update(title=draft.title, excerpt=draft.excerpt, kicker=draft.kicker, byline=draft.byline,
                            format="blocks", content=content, cover_asset_id=cover_asset(content, None))
                if draft.layout:
                    post["layout"] = normalize_layout(draft.layout)
        except StoryError as exc:
            raise _unprocessable(exc) from exc
        stories = [{**by_id[str(r["post_id"])], "section": r.get("section"), "contents_line": r.get("contents_line")}
                   for r in refs if str(r["post_id"]) in by_id]
        released_at = None
        if body.issue_id:
            saved = await mag_issues.get_issue(conn, site_id, body.issue_id)
            released_at = saved["released_at"] if saved else None
        assets = await mag_issues.book_assets(conn, site_id, cover, stories)
        magazine = await get_magazine(conn, site_id) or {"name": site["name"], "masthead_style": "classic"}
        nav = await _nav(conn, site_id)
    issue = {"id": body.issue_id, "number": body.number, "title": body.title, "cover": cover,
             "contents": normalize_contents(body.contents), "released_at": released_at}
    html = issue_pages.render_issue(_site_dict(site), nav, magazine, issue, stories, assets, origin="",
                                    currency=site.get("currency"), preview_blocks=preview_blocks(magazine),
                                    edit=body.edit)
    return HTMLResponse(html, headers={**tenant_security_headers(), "Cache-Control": "no-store"})


@router.get(f"{_BASE}/{{issue_id}}", response_model=CappeMagazineIssue)
async def get_issue(site_id: UUID, issue_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        issue = await mag_issues.get_issue(conn, site_id, issue_id)
        if issue is None:
            raise _not_found()
        return await _out(conn, site_id, issue)


@router.put(f"{_BASE}/{{issue_id}}", response_model=CappeMagazineIssue)
async def save_issue(site_id: UUID, issue_id: UUID, body: CappeMagazineIssueSave,
                     account: CappeAccount = Depends(require_cappe_account)):
    """Save what changed. On a released issue this goes live at once, and a
    draft story added to it is published."""
    fields = body.model_dump(exclude_unset=True)
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        try:
            async with conn.transaction():
                issue, published = await mag_issues.save_issue(conn, site_id, issue_id, fields)
        except LookupError as exc:
            raise _not_found() from exc
        except IssueError as exc:
            raise _unprocessable(exc) from exc
        out = await _out(conn, site_id, issue, published=published)
    await invalidate_render_cache(site_id)
    return out


@router.delete(f"{_BASE}/{{issue_id}}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_issue(site_id: UUID, issue_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    """Delete a draft issue. Its stories stay as they are."""
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        async with conn.transaction():
            was = await mag_issues.delete_issue(conn, site_id, issue_id)
    if was is None:
        raise _not_found()
    if was != "draft":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="This issue is out. Withdraw it before deleting it.")
    await invalidate_render_cache(site_id)


@router.post(f"{_BASE}/{{issue_id}}/release", response_model=CappeMagazineIssue)
async def release_issue(site_id: UUID, issue_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    """Put the issue out: its draft stories are published with it."""
    async with get_connection() as conn:
        site = await get_owned_site(conn, site_id, account.id)
        if not await live_magazine(conn, site):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                detail="Turn on your magazine, on a plan that includes magazines, to release issues.")
        try:
            async with conn.transaction():
                issue, published = await mag_issues.release_issue(conn, site_id, issue_id)
        except LookupError as exc:
            raise _not_found() from exc
        except IssueError as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        out = await _out(conn, site_id, issue, published=published)
    await invalidate_render_cache(site_id)
    return out


@router.post(f"{_BASE}/{{issue_id}}/withdraw", response_model=CappeMagazineIssue)
async def withdraw_issue(site_id: UUID, issue_id: UUID, account: CappeAccount = Depends(require_cappe_account)):
    """Take the issue back to a draft. Its stories stay published."""
    async with get_connection() as conn:
        await get_owned_site(conn, site_id, account.id)
        issue = await mag_issues.withdraw_issue(conn, site_id, issue_id)
        if issue is None:
            raise _not_found()
        out = await _out(conn, site_id, issue)
    await invalidate_render_cache(site_id)
    return out
