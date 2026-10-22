"""A story sent to a magazine's followers as an email issue (cappemag04).

The email is built from our own template, never the owner's HTML: tables and
inline styles, so it reads the same in Gmail, Outlook and Apple Mail. It shows
the cover (the 1200 px JPEG every library picture has; email clients don't all
show WebP), the kicker, headline, dek and byline, then either the story's
opening (the default) or, with `include_body`, the whole story. Every picture
carries its credit from the library row, an AI picture "AI illustration".

A paid story is only ever its opening, whatever `include_body` says — its paid
part is never in an email (PR 6's paywall rule).

`UNSUBSCRIBE` is a placeholder the send worker replaces for each reader with
their own unsubscribe link (`personalize`).
"""
from __future__ import annotations

from html import escape
from typing import Optional

from .design_schema import design_words
from .figures import credit_text, share_image
from .pages import story_blocks, story_path
from .richtext import md_to_text, render_md
from .story_render import split_at_paywall

UNSUBSCRIBE = "__CZ_UNSUBSCRIBE__"
OPENING_BLOCKS = 3
OPENING_WORDS = 160

_FONT = "Georgia, 'Times New Roman', serif"
_SANS = "-apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"


def _picture(asset: Optional[dict], *, caption: str = "", width: int = 560) -> str:
    src = share_image(asset)
    if not src:
        return ""
    alt = escape((asset or {}).get("alt") or "", quote=True)
    credit = credit_text(asset or {})
    under = " ".join(p for p in (escape(caption), escape(credit)) if p)
    caption_html = (f'<p style="margin:6px 0 0;font:12px/1.5 {_SANS};color:#78716c;">{under}</p>' if under else "")
    return (f'<tr><td style="padding:16px 0 0;"><img src="{escape(src, quote=True)}" alt="{alt}" width="{width}" '
            f'style="display:block;width:100%;max-width:{width}px;height:auto;border:0;">{caption_html}</td></tr>')


_P = '<p style="margin:0 0 14px;">'


def _text(md: str) -> str:
    html = render_md(md).replace("<p>", _P)
    return f'<tr><td style="padding:16px 0 0;font:17px/1.65 {_FONT};color:#1c1917;">{html}</td></tr>'


def _block(b: dict, assets: dict[str, dict]) -> str:
    kind = b.get("type")
    if kind == "text":
        return _text(b.get("md") or "")
    if kind == "photo":
        # Email can't lay words over a picture, so they go under it.
        words = " · ".join(design_words(b.get("design")))
        caption = " — ".join(p for p in (words, b.get("caption") or "") if p)
        return _picture(assets.get(b.get("asset_id") or ""), caption=caption)
    if kind == "photos":
        return "".join(_picture(assets.get(i.get("asset_id") or ""), caption=i.get("caption") or "")
                       for i in b.get("items") or [])
    if kind == "quote" and b.get("text"):
        who = f'<br><span style="font:13px {_SANS};color:#78716c;">— {escape(b["attribution"])}</span>' \
            if b.get("attribution") else ""
        return (f'<tr><td style="padding:20px 0 4px;font:italic 22px/1.4 {_FONT};color:#1c1917;">'
                f'“{escape(b["text"])}”{who}</td></tr>')
    if kind == "sidebar" and (b.get("title") or b.get("md")):
        title = f'<strong>{escape(b["title"])}</strong>' if b.get("title") else ""
        return (f'<tr><td style="padding:16px;background:#f5f5f4;font:15px/1.6 {_SANS};color:#292524;">'
                f'{title}{render_md(b.get("md") or "")}</td></tr>')
    if kind == "qa":
        return "".join(
            f'<tr><td style="padding:14px 0 0;font:17px/1.65 {_FONT};color:#1c1917;">'
            f'<strong>{escape(i.get("q") or "")}</strong>{render_md(i.get("a_md") or "")}</td></tr>'
            for i in b.get("items") or [])
    return ""


def _opening(blocks: list[dict]) -> list[dict]:
    """The story's first words: its opening blocks, up to about 160 words."""
    out, words = [], 0
    for b in blocks:
        if b.get("type") in ("cover", "paywall", "divider"):
            continue
        out.append(b)
        if b.get("type") == "text":
            words += len(md_to_text(b.get("md")).split())
        if words >= OPENING_WORDS or len(out) >= OPENING_BLOCKS:
            break
    return out


def build_issue(*, site_name: str, mag: dict, post: dict, assets: dict[str, dict], origin: str,
                include_body: bool, subject: Optional[str] = None) -> tuple[str, str, str]:
    """(subject, html, text) for the issue. Both bodies carry `UNSUBSCRIBE`."""
    name = mag.get("name") or site_name
    url = f"{origin}{story_path(post['slug'])}"
    blocks = story_blocks(post)
    cover = blocks[0] if blocks and blocks[0].get("type") == "cover" else None
    cover_asset = assets.get((cover or {}).get("asset_id") or "") or assets.get(str(post.get("cover_asset_id") or ""))
    paid = post.get("access") == "paid"
    if paid:
        body_blocks = _opening(split_at_paywall(blocks)[0])
    elif include_body:
        body_blocks = [b for b in blocks if b.get("type") not in ("cover", "paywall")]
    else:
        body_blocks = _opening(blocks)
    whole = include_body and not paid
    accent = mag.get("accent") or "#1c1917"
    kicker = post.get("kicker") or ""
    rows = [
        f'<tr><td style="padding:0 0 20px;border-bottom:1px solid #e7e5e4;text-align:center;">'
        f'<a href="{escape(origin, quote=True)}" style="font:700 26px {_FONT};color:#1c1917;text-decoration:none;">'
        f'{escape(name)}</a></td></tr>',
        _picture(cover_asset, width=560),
        (f'<tr><td style="padding:20px 0 0;font:600 12px {_SANS};letter-spacing:.08em;text-transform:uppercase;'
         f'color:{escape(accent, quote=True)};">{escape(kicker)}</td></tr>' if kicker else ""),
        f'<tr><td style="padding:8px 0 0;"><a href="{escape(url, quote=True)}" style="font:700 30px/1.2 {_FONT};'
        f'color:#1c1917;text-decoration:none;">{escape(post.get("title") or "")}</a></td></tr>',
        (f'<tr><td style="padding:10px 0 0;font:19px/1.5 {_FONT};color:#57534e;">{escape(post["excerpt"])}</td></tr>'
         if post.get("excerpt") else ""),
        (f'<tr><td style="padding:10px 0 0;font:13px {_SANS};color:#78716c;">By {escape(post["byline"])}</td></tr>'
         if post.get("byline") else ""),
        *(_block(b, assets) for b in body_blocks),
        f'<tr><td style="padding:24px 0 8px;"><a href="{escape(url, quote=True)}" style="display:inline-block;'
        f'padding:12px 22px;background:{escape(accent, quote=True)};color:#ffffff;font:600 15px {_SANS};'
        f'text-decoration:none;border-radius:6px;">{"Read it on the site" if whole else "Read the whole story"}'
        f'</a></td></tr>',
        f'<tr><td style="padding:28px 0 0;border-top:1px solid #e7e5e4;font:12px/1.6 {_SANS};color:#a8a29e;">'
        f"You're getting this because you follow {escape(name)}. "
        f'<a href="{UNSUBSCRIBE}" style="color:#a8a29e;">Unsubscribe</a>.</td></tr>',
    ]
    html = ('<!doctype html><html><body style="margin:0;padding:0;background:#fafaf9;">'
            '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#fafaf9;">'
            '<tr><td align="center" style="padding:32px 16px;">'
            '<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;">'
            + "".join(r for r in rows if r) + "</table></td></tr></table></body></html>")
    text_parts = [name, "", post.get("title") or ""]
    if post.get("excerpt"):
        text_parts += ["", post["excerpt"]]
    for b in body_blocks:
        if b.get("type") == "text":
            text_parts += ["", md_to_text(b.get("md"))]
    text_parts += ["", f"Read the whole story: {url}", "", f"Unsubscribe: {UNSUBSCRIBE}"]
    return (subject or post.get("title") or name)[:200], html, "\n".join(text_parts)


def personalize(body: str, unsubscribe_url: str, *, html: bool) -> str:
    return body.replace(UNSUBSCRIBE, escape(unsubscribe_url, quote=True) if html else unsubscribe_url)
