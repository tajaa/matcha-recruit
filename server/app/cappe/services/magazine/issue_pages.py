"""An issue's pages on the magazine: the issue as one book (`/issues/<n>`),
the archive of covers (`/issues`), and the current issue leading the front.

Built from `issue_render` (the cover and contents) and `pages` (the site's
frame, the book, a story as printed). Like a story's page, an issue's page
holds only each paid story's free part; a subscriber's browser fetches the
rest, story by story, from the existing per-story endpoint.
"""
from __future__ import annotations

from html import escape
from typing import Optional

from ..render.sanitize import _js_obj
from .figures import share_image
from .issue_render import contents_html, cover_html, issue_label, issue_path, story_anchor
from .issue_schema import issue_line_text
from .pages import (
    _masthead,
    _page,
    book_html,
    follow_html,
    paywall_script,
    story_article_html,
    story_cover,
    story_path,
)


def _cover_asset(issue: dict, assets: dict[str, dict]) -> Optional[dict]:
    return assets.get(((issue.get("cover") or {}).get("photo") or {}).get("asset_id") or "")


def _when(issue: dict):
    return issue.get("released_at")


def issue_book(mag: dict, issue: dict, stories: list[dict], assets: dict[str, dict], *, currency: Optional[str],
               site_slug: Optional[str], preview_blocks: int, edit: bool = False) -> str:
    """The issue as one book: the cover, the contents, every story in order.
    `edit`: the owner's editor on the page, every story whole and marked."""
    hrefs = {str(s["id"]): f"#{story_anchor(s['slug'])}" for s in stories}
    cover = cover_html(issue.get("cover") or {}, mag=mag, number=issue["number"], when=_when(issue),
                       asset=_cover_asset(issue, assets), hrefs=hrefs, size="half", eager=True, edit=edit)
    face = f'<div class="mz-issue__face">{cover}</div>'
    covers = {str(s["id"]): story_cover(s, assets)[1] for s in stories}
    entries = [{"post": s, "asset": covers.get(str(s["id"])), "section": s.get("section"),
                "line": s.get("contents_line")} for s in stories]
    label = issue_line_text(issue.get("cover") or {}, issue["number"], _when(issue))
    articles = "".join(
        # A plain Markdown post isn't edited on the page (the issue editor
        # holds only stories' blocks): shown as is, nothing typed in it is lost.
        story_article_html(s, assets, mag=mag, currency=currency, site_slug=site_slug, preview_blocks=preview_blocks,
                           single=False, edit=edit and s.get("format") == "blocks")
        for s in stories
    )
    inner = ('<div class="mz-issue" data-mz-flow>'
             '<div class="mz-issue__mat" data-mz-skip aria-hidden="true"></div>'
             '<div class="mz-issue__cover" aria-hidden="true"></div>'
             f'<div class="mz-issue__contents">{contents_html(issue.get("contents") or {}, entries, label=label, edit=edit)}</div>'
             f"{articles}</div>")
    return book_html(inner, issue=True, face=face, edit=edit)


def _issue_ld(mag: dict, issue: dict, stories: list[dict], *, url: str, origin: str, image: Optional[str]) -> str:
    data = {
        "@context": "https://schema.org",
        "@type": "PublicationIssue",
        "issueNumber": str(issue["number"]),
        "name": issue_label(issue),
        "url": url,
        "datePublished": issue["released_at"].isoformat() if issue.get("released_at") else None,
        "isPartOf": {"@type": "Periodical", "name": mag.get("name")},
        "hasPart": [{"@type": "Article", "headline": (s.get("title") or "")[:110], "url": f"{origin}{story_path(s['slug'])}"}
                    for s in stories],
    }
    if image:
        data["image"] = [image]
    if any(s.get("access") == "paid" for s in stories):
        # Google's paywalled-content markup: each `.mz-paid` box is filled by
        # a subscriber's browser.
        data["isAccessibleForFree"] = False
        data["hasPart"].append({"@type": "WebPageElement", "isAccessibleForFree": False, "cssSelector": ".mz-paid"})
    clean = {k: v for k, v in data.items() if v not in (None, "", [])}
    return f'<script type="application/ld+json">{_js_obj(clean)}</script>'


def render_issue(site: dict, nav: list[dict], mag: dict, issue: dict, stories: list[dict], assets: dict[str, dict], *,
                 origin: str, currency: Optional[str] = None, preview_blocks: int = 3, edit: bool = False) -> str:
    book = issue_book(mag, issue, stories, assets, currency=currency, site_slug=site.get("slug"),
                      preview_blocks=preview_blocks, edit=edit)
    paid = any(s.get("access") == "paid" for s in stories) and not edit
    title = f"{mag.get('name') or ''}, {issue_label(issue)}"
    body = (_masthead(mag, small=True) + f'<h1 class="mz-sr">{escape(title)}</h1>' + book
            + (paywall_script() if paid else "")
            + '<p class="mz-issue__all"><a href="/issues">All issues</a></p>' + follow_html(mag, site.get("slug")))
    url = f"{origin}{issue_path(issue['number'])}"
    image = share_image(_cover_asset(issue, assets))
    titles = [s.get("title") for s in stories if s.get("title")]
    description = ("In this issue: " + ", ".join(titles[:4])) if titles else (mag.get("tagline") or "")
    extra = _issue_ld(mag, issue, stories, url=url, origin=origin, image=image)
    extra += '<meta name="twitter:card" content="summary_large_image" />'
    return _page(site, nav, mag, body, origin=origin, extra_head=extra, issue_css=True, preview=edit, seo={
        "title": title, "description": description[:300], "image": image, "type": "website", "url": url,
    })


def _cover_card(mag: dict, issue: dict, assets: dict[str, dict], *, eager: bool = False) -> str:
    when = issue_line_text({}, issue["number"], _when(issue))
    title = f'<span class="mz-issuecard__title">{escape(issue["title"])}</span>' if issue.get("title") else ""
    cover = cover_html(issue.get("cover") or {}, mag=mag, number=issue["number"], when=_when(issue),
                       asset=_cover_asset(issue, assets), size="card", eager=eager, link_credit=False)
    return (f'<a class="mz-issuecard" href="{issue_path(issue["number"])}">{cover}'
            f'<span class="mz-issuecard__no">{escape(when)}</span>{title}</a>')


def render_archive(site: dict, nav: list[dict], mag: dict, issues: list[dict], assets: dict[str, dict], *,
                   page: int, has_more: bool, origin: str) -> str:
    """Every released issue, newest first, as its cover."""
    cards = "".join(_cover_card(mag, issue, assets, eager=i < 2) for i, issue in enumerate(issues))
    links = []
    if page > 1:
        links.append(f'<a rel="prev" href="{"/issues" if page == 2 else f"/issues?page={page - 1}"}">Newer issues</a>')
    if has_more:
        links.append(f'<a rel="next" href="/issues?page={page + 1}">Older issues</a>')
    pager = f'<nav class="mz-pager">{"".join(links)}</nav>' if links else ""
    body = (_masthead(mag, small=True) + '<h1 class="mz-topic-title">Issues</h1>'
            + f'<div class="mz-issues">{cards}</div>' + pager)
    url = f"{origin}/issues" + (f"?page={page}" if page > 1 else "")
    return _page(site, nav, mag, body, origin=origin, issue_css=True, seo={
        "title": f"Issues — {mag.get('name')}", "description": mag.get("tagline") or "", "type": "website", "url": url,
    })


def current_issue_html(mag: dict, issue: dict, stories: list[dict], assets: dict[str, dict]) -> str:
    """The front page's lead: the current issue's cover beside what is in it."""
    href = issue_path(issue["number"])
    cover = cover_html(issue.get("cover") or {}, mag=mag, number=issue["number"], when=_when(issue),
                       asset=_cover_asset(issue, assets), size="half", eager=True, link_credit=False)
    items = "".join(
        f'<li><a href="{href}#{story_anchor(s["slug"])}">{escape(s.get("title") or "")}</a></li>' for s in stories[:8]
    )
    title = f'<h2 class="mz-current__title">{escape(issue_label(issue))}</h2>'
    when = escape(issue_line_text(issue.get("cover") or {}, issue["number"], _when(issue)))
    return (f'<section class="mz-current"><a class="mz-current__cover" href="{href}" '
            f'aria-label="Open {escape(issue_label(issue), quote=True)}">{cover}</a>'
            f'<div class="mz-current__words"><p class="mz-kicker">The current issue · {when}</p>{title}'
            + (f'<ol class="mz-current__list">{items}</ol>' if items else "")
            + f'<p class="mz-current__links"><a class="mz-current__open" href="{href}">Open the issue</a>'
            '<a href="/issues">All issues</a></p></div></section>')


def current_issue_image(issue: dict, assets: dict[str, dict]) -> Optional[str]:
    return share_image(_cover_asset(issue, assets))
