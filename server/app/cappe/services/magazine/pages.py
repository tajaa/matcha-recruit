"""The magazine's server-rendered pages: its front, a story, a topic, and the
RSS feed.

Each page goes through `render_site_html(body_override=...)` like the product
page does, so it wears the site's header, footer and theme; the magazine adds
its own masthead fonts and `magazine.css`. Server-rendered so a story shared on
Instagram or found on Google shows its picture, headline and words before any
script runs: Open Graph `article` tags and Article structured data.

A paid story's page holds only its free part (`story_render.split_at_paywall`);
the paid part is never in this HTML, in the cache, or in the feed. A
subscriber's browser fetches it (`render/assets/paywall.js` →
`GET /public/sites/{slug}/stories/{story}/paid`, never cached) and puts it in
the empty `.mz-paid` box under the paywall.
"""
from __future__ import annotations

import json

from datetime import datetime
from email.utils import format_datetime
from html import escape
from pathlib import Path
from urllib.parse import quote as url_quote
from typing import Optional
from xml.sax.saxutils import escape as xml_escape

from ..render.design import _font_stack, _gfonts_link
from ..render.page import render_site_html
from ..render.sanitize import _js_obj
from .design_schema import design_fonts, walk_layers
from .figures import figure_html, img_html, share_image
from .fonts import Uses, add_use, fonts_links
from .magazines import masthead_fonts
from .richtext import render_md
from .rt import RtError, md_to_rt, normalize_rt
from .story_render import cover_html, field, render_blocks, split_at_paywall
from .story_schema import cover_block, with_designs
from .topics import topic_label

_ASSETS = Path(__file__).resolve().parent.parent / "render" / "assets"
_CSS = (_ASSETS / "magazine.css").read_text(encoding="utf-8")
_ISSUE_CSS = (_ASSETS / "issue.css").read_text(encoding="utf-8")
_DESIGN_CSS = (_ASSETS / "design.css").read_text(encoding="utf-8")
_FOLLOW_JS = (_ASSETS / "follow.js").read_text(encoding="utf-8")
_PAYWALL_JS = (_ASSETS / "paywall.js").read_text(encoding="utf-8")
_BOOK_JS = (_ASSETS / "book.js").read_text(encoding="utf-8")
_SYMBOLS = {"USD": "$", "CAD": "CA$", "AUD": "A$", "NZD": "NZ$", "EUR": "€", "GBP": "£"}

PAGE_SIZE = 12
MAX_PAGE = 50


def reader_path(site_slug: str) -> str:
    """A magazine on a reader account's dashboard (the SPA, under /cappe)."""
    return f"/reader/m/{url_quote(site_slug, safe='')}"


def story_path(slug: str) -> str:
    return f"/stories/{slug}"


def topic_path(key: str) -> str:
    return f"/topics/{key}"


def front_path(mag: dict) -> str:
    return "/" if mag.get("front_at_root") else "/magazine"


def _date(ts: Optional[datetime]) -> str:
    return f"{ts.strftime('%B')} {ts.day}, {ts.year}" if ts else ""


def _head(mag: dict, origin: str, *, issue_css: bool = False) -> str:
    """The masthead fonts, the magazine's CSS (and an issue's: its cover and
    contents) and the feed link."""
    heading, body = masthead_fonts(mag)
    accent = mag.get("accent") or ""
    vars_ = f"--mz-h:{_font_stack(heading)};--mz-b:{_font_stack(body)};"
    if accent:
        vars_ += f"--mz-accent:{accent};"
    feed = escape(f"{origin}/feed.xml", quote=True)
    title = escape(mag.get("name") or "", quote=True)
    css = _CSS + _DESIGN_CSS + (_ISSUE_CSS if issue_css else "")
    return (_gfonts_link(heading, body) + f"<style>.mz{{{vars_}}}{css}</style>"
            f'<link rel="alternate" type="application/rss+xml" title="{title}" href="{feed}" />')


def _masthead(mag: dict, *, small: bool = False) -> str:
    tagline = f'<p class="mz-masthead__tagline">{escape(mag["tagline"])}</p>' if mag.get("tagline") and not small else ""
    tag = "p" if small else "h1"
    cls = "mz-masthead mz-masthead--small" if small else "mz-masthead"
    return (f'<header class="{cls}"><{tag} class="mz-masthead__name">'
            f'<a href="{front_path(mag)}">{escape(mag.get("name") or "")}</a></{tag}>{tagline}</header>')


def _topics_nav(keys: list[str], current: Optional[str] = None) -> str:
    links = []
    for k in keys:
        if not topic_label(k):
            continue
        here = ' aria-current="page"' if k == current else ""
        links.append(f'<a href="{topic_path(k)}"{here}>{escape(topic_label(k))}</a>')
    return f'<nav class="mz-topics" aria-label="Topics">{"".join(links)}</nav>' if links else ""


def _meta(post: dict, *, edit: bool = False) -> str:
    bits = []
    if edit:
        bits.append(f'<span class="mz-by">By <span{field("@byline", ph="Your name")}>{escape(post.get("byline") or "")}'
                    "</span></span>")
    elif post.get("byline"):
        bits.append(f'<span class="mz-by">By {escape(post["byline"])}</span>')
    if post.get("published_at"):
        ts = post["published_at"]
        bits.append(f'<time datetime="{escape(ts.isoformat(), quote=True)}">{escape(_date(ts))}</time>')
    if post.get("reading_minutes"):
        bits.append(f"<span>{int(post['reading_minutes'])} min read</span>")
    return f'<p class="mz-meta">{" · ".join(bits)}</p>' if bits else ""


def card_html(post: dict, asset: Optional[dict], *, big: bool = False) -> str:
    """A story on the front or a topic page: picture, kicker, headline, dek."""
    img = img_html(asset, size="wide" if big else "card", eager=big, cls="mz-card__img") if asset else ""
    media = f'<div class="mz-card__media">{img}</div>' if img else ""
    kicker = post.get("kicker") or topic_label(post.get("topic"))
    kicker_html = f'<p class="mz-kicker">{escape(kicker)}</p>' if kicker else ""
    dek = f'<p class="mz-dek">{escape(post["excerpt"])}</p>' if post.get("excerpt") else ""
    title = f'<h2 class="mz-card__title">{escape(post.get("title") or "")}</h2>'
    cls = "mz-card mz-card--lead" if big else "mz-card"
    href = escape(story_path(post["slug"]), quote=True)
    return (f'<article class="{cls}"><a href="{href}">{media}<div class="mz-card__words">'
            f"{kicker_html}{title}{dek}{_meta({**post, 'byline': None})}</div></a></article>")


def _key(post: dict) -> str:
    return str(post["id"])


def _grid(posts: list[dict], covers: dict[str, dict]) -> str:
    cards = "".join(card_html(p, covers.get(_key(p))) for p in posts)
    return f'<div class="mz-grid">{cards}</div>' if cards else ""


def _pager(base: str, page: int, has_more: bool) -> str:
    links = []
    if page > 1:
        prev = base if page == 2 else f"{base}?page={page - 1}"
        links.append(f'<a rel="prev" href="{escape(prev, quote=True)}">Newer stories</a>')
    if has_more and page < MAX_PAGE:
        links.append(f'<a rel="next" href="{escape(base, quote=True)}?page={page + 1}">Older stories</a>')
    return f'<nav class="mz-pager">{"".join(links)}</nav>' if links else ""


def follow_html(mag: dict, site_slug: Optional[str] = None) -> str:
    """The reader's "follow by email" box (double opt-in, `routes/public/
    magazine.py`), and a link to follow from a Gummfit account instead (the
    dashboard follows on arrival, `?follow=1`; `routes/reader.py`). This page
    can't see the dashboard's sign-in, so the follow happens there. Off when
    the owner turned follows off."""
    from ..email import dashboard_url

    if not mag.get("follow_enabled", True):
        return ""
    name = escape(mag.get("name") or "")
    account = (f'<p class="mz-follow__alt" data-mz-alt>Have a Gummfit account? <a href="'
               f'{escape(dashboard_url(reader_path(site_slug)) + "?follow=1", quote=True)}" rel="noopener">'
               "Follow it there</a>.</p>" if site_slug else "")
    return (f'<section class="mz-follow" id="mz-follow"><h2 class="mz-follow__title">Follow {name}</h2>'
            "<p>New stories by email. Leave any time.</p>"
            '<form class="mz-follow__form"><label class="mz-sr" for="mz-follow-email">Your email</label>'
            '<input id="mz-follow-email" type="email" required autocomplete="email" placeholder="you@example.com">'
            '<button type="submit">Follow</button></form>'
            f'<p class="mz-follow__msg" data-mz-msg role="status"></p>{account}</section><script>{_FOLLOW_JS}</script>')


def price_label(cents: int, currency: Optional[str]) -> str:
    """$5 or $5.50 — whole amounts without the cents."""
    cur = (currency or "USD").upper()
    amount = f"{cents // 100}" if cents % 100 == 0 else f"{cents / 100:.2f}"
    sym = _SYMBOLS.get(cur)
    return f"{sym}{amount}" if sym else f"{amount} {cur}"


def paywall_section(mag: dict, post: dict, *, currency: Optional[str], site_slug: Optional[str] = None,
                    single: bool = True) -> str:
    """Under a paid story's free part: the pitch and price (the same for every
    reader, so the page caches) and an empty `.mz-paid` box for the paid part.
    A magazine that has stopped taking subscribers still lets the ones it has
    sign in. A link offers the same magazine on a Gummfit reader account's
    dashboard (`routes/reader.py`). An issue holds one per paid story
    (`single=False`), all served by one `paywall_script()`."""
    from ..email import dashboard_url

    open_ = bool(mag.get("paid_enabled") and mag.get("price_cents"))
    price = price_label(int(mag["price_cents"]), currency) if open_ else ""
    pitch = f'<p class="mz-paywall__pitch">{escape(mag["paid_pitch"])}</p>' if mag.get("paid_pitch") else ""
    offer = f'<p class="mz-paywall__price">{escape(price)} a month. Cancel any time.</p>' if open_ else ""
    alt = (f'<p class="mz-paywall__alt" data-mz-alt>Read with a Gummfit reader account? <a href="'
           f'{escape(dashboard_url(reader_path(site_slug)), quote=True)}" rel="noopener">Open it on your dashboard</a>.</p>'
           if site_slug else "")
    slug = escape(post["slug"], quote=True)
    ident = ' id="mz-paywall"' if single else ""
    return (
        f'<section class="mz-paywall mz-measure"{ident} data-mz-paywall data-mz-story="{slug}" '
        f'data-mz-open="{1 if open_ else 0}" data-mz-price="{escape(price, quote=True)}">'
        f'<p class="mz-paywall__lede">The rest of this story is for subscribers.</p>{pitch}{offer}'
        '<div class="mz-paywall__actions" data-mz-actions><noscript>Turn on JavaScript to subscribe or sign in.'
        f'</noscript></div><p class="mz-paywall__msg" data-mz-msg role="status"></p>{alt}</section>'
        f'<div class="mz-story__body mz-paid" data-mz-paid="{slug}" hidden></div>'
    )


def paywall_script() -> str:
    """Signs a reader in, starts their subscription, or fills each paid box."""
    return f"<script>{_PAYWALL_JS}</script>"


def paywall_html(mag: dict, post: dict, *, currency: Optional[str], site_slug: Optional[str] = None) -> str:
    """A story page's one paywall and its script."""
    return paywall_section(mag, post, currency=currency, site_slug=site_slug) + paywall_script()


def _page(site: dict, nav: list[dict], mag: dict, body: str, *, origin: str, seo: dict, extra_head: str = "",
          issue_css: bool = False, preview: bool = False) -> str:
    """`preview`: the owner's editor (the site's own scripts stay idle)."""
    return render_site_html(
        site, {"title": seo.get("title") or mag.get("name"), "slug": "__magazine", "content": {}}, nav,
        preview=preview, body_override=f'<div class="mz">{body}</div>',
        extra_head=_head(mag, origin, issue_css=issue_css) + extra_head, seo=seo,
    )


def render_front(site: dict, nav: list[dict], mag: dict, *, lead: Optional[dict], posts: list[dict],
                 covers: dict[str, dict], topics: list[str], page: int, has_more: bool, origin: str,
                 current_html: str = "", current_image: Optional[str] = None) -> str:
    """The magazine's front: masthead, the current issue (`current_html`,
    `issue_pages.current_issue_html`) or else the cover story, then the
    latest."""
    lead_html = ""
    if current_html and page == 1:
        lead_html = current_html
    elif lead and page == 1:
        lead_html = f'<section class="mz-lead">{card_html(lead, covers.get(_key(lead)), big=True)}</section>'
    about = ""
    if page == 1 and mag.get("about"):
        about = f'<section class="mz-about mz-measure">{render_md(mag["about"])}</section>'
    empty = '<p class="mz-empty">The first stories are on their way.</p>' if not (lead_html or posts) else ""
    body = (_masthead(mag) + _topics_nav(topics) + lead_html + _grid(posts, covers) + empty
            + _pager(front_path(mag), page, has_more) + about + follow_html(mag, site.get("slug")))
    url = f"{origin}{front_path(mag)}" + (f"?page={page}" if page > 1 else "")
    lead_img = current_image or (share_image(covers.get(_key(lead))) if lead else None)
    return _page(site, nav, mag, body, origin=origin, issue_css=bool(current_html), seo={
        "title": mag.get("name") + (f" — page {page}" if page > 1 else ""),
        "description": mag.get("tagline") or "", "image": lead_img, "type": "website", "url": url,
    })


def render_topic(site: dict, nav: list[dict], mag: dict, topic: str, *, posts: list[dict],
                 covers: dict[str, dict], topics: list[str], page: int, has_more: bool, origin: str) -> str:
    label = topic_label(topic)
    body = (_masthead(mag, small=True) + _topics_nav(topics, current=topic)
            + f'<h1 class="mz-topic-title">{escape(label)}</h1>' + _grid(posts, covers)
            + _pager(topic_path(topic), page, has_more))
    return _page(site, nav, mag, body, origin=origin, seo={
        "title": f"{label} — {mag.get('name')}", "description": mag.get("tagline") or "",
        "type": "website", "url": f"{origin}{topic_path(topic)}",
    })


def article_ld(post: dict, mag: dict, *, url: str, image: Optional[str], paid: bool = False) -> str:
    published = post["published_at"].isoformat() if post.get("published_at") else None
    data = {
        "@context": "https://schema.org",
        "@type": "NewsArticle" if post.get("layout") == "dispatch" else "Article",
        "headline": (post.get("title") or "")[:110],
        "description": post.get("excerpt") or "",
        "mainEntityOfPage": url,
        "datePublished": published,
        "dateModified": post["updated_at"].isoformat() if post.get("updated_at") else published,
        "author": ({"@type": "Person", "name": post["byline"]} if post.get("byline")
                   else {"@type": "Organization", "name": mag.get("name")}),
        "publisher": {"@type": "Organization", "name": mag.get("name")},
    }
    if image:
        data["image"] = [image]
    if post.get("topic"):
        data["articleSection"] = topic_label(post["topic"])
    clean = {k: v for k, v in data.items() if v}
    if paid:
        # Google's paywalled-content markup: the part behind the paywall is
        # the `.mz-paid` box, which a subscriber's browser fills.
        clean["isAccessibleForFree"] = False
        clean["hasPart"] = {"@type": "WebPageElement", "isAccessibleForFree": False, "cssSelector": ".mz-paid"}
    return f'<script type="application/ld+json">{_js_obj(clean)}</script>'


def story_blocks(post: dict) -> list[dict]:
    """A story's blocks; a legacy Markdown post is one text block."""
    if post.get("format") == "blocks":
        return with_designs(list((post.get("content") or {}).get("blocks") or []))
    return [{"type": "text", "md": post.get("body") or "", "dropcap": False, "columns": 1}]


def story_cover(post: dict, assets: dict[str, dict]) -> tuple[Optional[dict], Optional[dict]]:
    """A story's cover block and its picture (the block's, else the story's own)."""
    cover = cover_block({"blocks": story_blocks(post)})
    asset = assets.get((cover or {}).get("asset_id") or "") or assets.get(str(post.get("cover_asset_id") or ""))
    return cover, asset


def story_article_html(post: dict, assets: dict[str, dict], *, mag: dict, currency: Optional[str] = None,
                       site_slug: Optional[str] = None, preview_blocks: int = 3, single: bool = True,
                       issue: Optional[dict] = None, edit: bool = False) -> str:
    """A story as it is printed: its opener, its free part, then (paid) its
    paywall. In an issue (`single=False`) it carries its anchor for the
    contents to jump to and starts on a new page; on its own page it links to
    the issue it is in (`issue`). In the owner's editor (`edit`) a paid story
    is printed whole, with a mark where readers without a subscription stop,
    and the article names its story (`data-mz-s`)."""
    blocks = story_blocks(post)
    cover, cover_asset = story_cover(post, assets)
    free = blocks
    paywall = ""
    if post.get("access") == "paid" and not edit:
        free, rest = split_at_paywall(blocks, preview_blocks=preview_blocks)
        # A story no longer than its free preview has nothing to subscribe for.
        paywall = paywall_section(mag, post, currency=currency, site_slug=site_slug, single=single) if rest else ""
    topic = post.get("topic")
    topic_link = (f'<p class="mz-story__topic"><a href="{topic_path(topic)}">{escape(topic_label(topic))}</a></p>'
                  if topic_label(topic) and single else "")
    from_issue = ""
    if issue and single:
        href = escape(f"/issues/{int(issue['number'])}#mz-s-{post['slug']}", quote=True)
        from_issue = (f'<p class="mz-story__issue">From No. {int(issue["number"])} — '
                      f'<a href="{href}">read it in the issue</a></p>')
    layout = escape(post.get("layout") or "standard")
    attrs = "" if single else f' id="mz-s-{escape(post["slug"], quote=True)}"'
    if edit:
        attrs += f' data-mz-s="{escape(str(post.get("id") or ""), quote=True)}"'
    cls = f"mz-story mz-layout-{layout}" + ("" if single else " mz-issue__story")
    return (
        f'<article class="{cls}"{attrs}>'
        + cover_html(post, cover, cover_asset, byline_html=_meta(post, edit=edit), edit=edit, assets=assets)
        + f'<div class="mz-story__body">{render_blocks(free, assets, edit=edit)}</div>{paywall}{from_issue}{topic_link}'
        + (rich_registry(blocks) if edit else "")
        + "</article>"
    )


def story_fonts(blocks: list[dict], uses: Optional[Uses] = None) -> Uses:
    """The faces a story sets beyond the magazine's own pair: its text blocks'
    and its designs'."""
    uses = uses if uses is not None else {}
    for b in blocks:
        if b.get("type") == "text" and b.get("font") and b["font"] != "body":
            add_use(uses, b["font"], 400, False)
            add_use(uses, b["font"], 700, False)
            add_use(uses, b["font"], 400, True)
        design_fonts(b.get("design"), uses)
        for item in b.get("items") or []:
            if isinstance(item, dict):
                design_fonts(item.get("design"), uses)
    return uses


def _layer_docs(docs: dict[str, dict], block: int, path: str, design: Optional[dict]) -> None:
    for lay in walk_layers((design or {}).get("layers") or []):
        if lay.get("kind") == "text":
            docs[f"{block}|{path}.{lay['id']}"] = lay.get("rt") or md_to_rt("")


def rich_registry(blocks: list[dict]) -> str:
    """The documents behind a story's rich fields, for the editor on the page
    to open them exactly (`"<block>|<field>"` → document), not by reading the
    page's HTML back: its text, sidebars and answers, and the words in its
    designs (`design.<layer>`). Only in edit renders."""
    docs: dict[str, dict] = {}
    for i, b in enumerate(blocks):
        kind = b.get("type")
        if kind in ("text", "sidebar"):
            docs[f"{i}|md"] = _doc(b, "md", "rt")
        elif kind == "qa":
            for j, item in enumerate(b.get("items") or []):
                docs[f"{i}|items.{j}.a_md"] = _doc(item, "a_md", "a_rt")
        _layer_docs(docs, i, "design", b.get("design"))
        for j, item in enumerate(b.get("items") or []):
            if isinstance(item, dict):
                _layer_docs(docs, i, f"items.{j}.design", item.get("design"))
    data = json.dumps(docs, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    return f'<script type="application/json" data-mz-rt>{data}</script>'


def _doc(b: dict, md_key: str, rt_key: str) -> dict:
    try:
        doc = normalize_rt(b.get(rt_key))
    except RtError:
        doc = None
    return doc or md_to_rt(b.get(md_key))


def render_story(site: dict, nav: list[dict], mag: dict, post: dict, assets: dict[str, dict], *,
                 more: list[dict], more_covers: dict[str, dict], origin: str, preview_blocks: int = 3,
                 currency: Optional[str] = None, issue: Optional[dict] = None, edit: bool = False) -> str:
    """A story's page. `edit`: the owner's editor on the page (whole, marked,
    with the editor's script; never cached or shown to a reader)."""
    paid = post.get("access") == "paid" and not edit
    article = story_article_html(post, assets, mag=mag, currency=currency, site_slug=site.get("slug"),
                                 preview_blocks=preview_blocks, issue=issue, edit=edit)
    more_html = ""
    if more:
        cards = "".join(card_html(p, more_covers.get(_key(p))) for p in more)
        more_html = (f'<section class="mz-more"><h2 class="mz-more__title">More from {escape(mag.get("name") or "")}'
                     f'</h2><div class="mz-grid">{cards}</div></section>')
    body = (_masthead(mag, small=True) + book_html(article, edit=edit) + (paywall_script() if paid else "")
            + follow_html(mag, site.get("slug")) + more_html)
    _cover, cover_asset = story_cover(post, assets)
    topic = post.get("topic")
    url = f"{origin}{story_path(post['slug'])}"
    image = share_image(cover_asset)
    extra = fonts_links(story_fonts(story_blocks(post))) + article_ld(post, mag, url=url, image=image, paid=paid)
    if post.get("published_at"):
        extra += f'<meta property="article:published_time" content="{escape(post["published_at"].isoformat(), quote=True)}" />'
    if topic_label(topic):
        extra += f'<meta property="article:section" content="{escape(topic_label(topic), quote=True)}" />'
    extra += '<meta name="twitter:card" content="summary_large_image" />'
    return _page(site, nav, mag, body, origin=origin, extra_head=extra, preview=edit, seo={
        "title": f"{post.get('title')} — {mag.get('name')}", "description": post.get("excerpt") or "",
        "image": image, "type": "article", "url": url,
    })


def book_html(inner: str, *, issue: bool = False, face: str = "", edit: bool = False) -> str:
    """The story as pages turned left and right: a matte cover, then glossy
    pages, lying on a dark mat. The words flow from page to page in columns of
    the page's height (a two-page spread from 960 px, one page on a phone);
    `render/assets/book.js` turns them with the arrows, the keys or a swipe,
    counts the pages and marks the spread showing (`data-mz-at`), which takes
    the gloss off the cover. Without it the pages still scroll sideways.
    `.mz-gloss` is the light on the paper: it stays put while pages move.
    `.mz-end` is placed by the script so the pages end on a whole spread (a
    browser never counts the space after the last column, so the last spread
    could not be turned to).

    An issue (`issue=True`, `issue_pages.render_issue`) is one book: `face`
    is its cover, drawn over the first page from outside the flowing columns,
    and `inner` holds the rest (`data-mz-flow`, which the script measures).

    `edit`: the owner's editor on the page (`data-mz-edit`; the dashboard
    adds its own script and styles, client `magazine/frame/`)."""
    what = "The issue" if issue else "The story"
    return (
        f'<div class="mz-reader" data-mz-book{" data-mz-issue" if issue else ""}{" data-mz-edit" if edit else ""}>'
        '<button type="button" class="mz-turn mz-turn--prev" data-mz-prev aria-label="Previous page" hidden>&#8249;</button>'
        '<div class="mz-spread">'
        f'<div class="mz-book" tabindex="0" role="region" aria-label="{what}. Use the left and right arrow keys to turn pages.">'
        f'<div class="mz-pages">{face}{inner}<i class="mz-end" aria-hidden="true"></i></div></div>'
        '<div class="mz-gloss" aria-hidden="true"></div></div>'
        '<button type="button" class="mz-turn mz-turn--next" data-mz-next aria-label="Next page" hidden>&#8250;</button>'
        '<p class="mz-folio" data-mz-folio aria-live="polite"></p>'
        f"</div><script>{_BOOK_JS}</script>"
    )


def _cdata(html: str) -> str:
    return "<![CDATA[" + html.replace("]]>", "]]]]><![CDATA[>") + "]]>"


def render_feed(mag: dict, posts: list[dict], assets: dict[str, dict], *, origin: str) -> str:
    """RSS 2.0: the latest stories, in full when free, the dek when paid."""
    items = []
    for p in posts:
        link = f"{origin}{story_path(p['slug'])}"
        if p.get("access") == "paid":
            content = f"<p>{escape(p.get('excerpt') or '')}</p>"
        else:
            cover = assets.get(str(p.get("cover_asset_id") or ""))
            content = (figure_html(cover) if cover else "") + render_blocks(story_blocks(p), assets)
        pub = f"<pubDate>{format_datetime(p['published_at'])}</pubDate>" if p.get("published_at") else ""
        items.append(
            "<item>"
            f"<title>{xml_escape(p.get('title') or '')}</title><link>{xml_escape(link)}</link>"
            f'<guid isPermaLink="true">{xml_escape(link)}</guid>{pub}'
            f"<description>{xml_escape(p.get('excerpt') or '')}</description>"
            f"<content:encoded>{_cdata(content)}</content:encoded>"
            "</item>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">'
        f"<channel><title>{xml_escape(mag.get('name') or '')}</title>"
        f"<link>{xml_escape(origin + front_path(mag))}</link>"
        f"<description>{xml_escape(mag.get('tagline') or mag.get('name') or '')}</description>"
        + "".join(items) + "</channel></rss>\n"
    )
