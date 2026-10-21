"""Story blocks → HTML (the body of `/stories/<slug>`).

Separate from the page-block registry (`services/render/blocks.py`): stories
have their own small vocabulary (`story_schema.STORY_BLOCKS`) and their own
CSS (`render/assets/magazine.css`, every class `mz-`). Everything the owner
typed is escaped or goes through `richtext.render_md`; pictures come from the
library rows passed in `assets`, credits included.

Photo groups keep each picture's own shape: a row's pictures are given flex
weights from their width/height, so they line up at one height without
cropping (`pair`, `trio`); `grid` and `mosaic` are CSS columns.
"""
from __future__ import annotations

from html import escape
from typing import Optional

from .figures import credit_html, figure_html, img_html
from .richtext import render_md

PAYWALL = "paywall"


def split_at_paywall(blocks: list[dict], *, preview_blocks: int = 3) -> tuple[list[dict], list[dict]]:
    """(free part, paid part). The owner's paywall marker decides; without one
    the first `preview_blocks` blocks are free."""
    for i, b in enumerate(blocks):
        if b.get("type") == PAYWALL:
            return blocks[:i], blocks[i + 1:]
    return blocks[:preview_blocks], blocks[preview_blocks:]


def _aspect(asset: Optional[dict]) -> float:
    if asset and asset.get("width") and asset.get("height"):
        return max(0.2, min(5.0, asset["width"] / asset["height"]))
    return 1.5


def _photos(b: dict, assets: dict[str, dict]) -> str:
    items = [(assets.get(i.get("asset_id") or ""), i.get("caption") or "") for i in b.get("items") or []]
    items = [(a, c) for a, c in items if a]
    if not items:
        return ""
    layout = b.get("layout") or "pair"
    if layout in ("pair", "trio"):
        size = "half" if layout == "pair" else "third"
        figs = "".join(
            figure_html(a, caption=c, size=size, cls="mz-fig mz-row__item", style=f"flex:{_aspect(a):.4f} 1 0%")
            for a, c in items
        )
        return f'<div class="mz-photos mz-row mz-row--{layout}">{figs}</div>'
    figs = "".join(figure_html(a, caption=c, size="third") for a, c in items)
    return f'<div class="mz-photos mz-cols mz-cols--{layout}">{figs}</div>'


def _qa(b: dict) -> str:
    rows = "".join(
        f'<div class="mz-qa__item"><p class="mz-qa__q">{escape(i.get("q") or "")}</p>'
        f'<div class="mz-qa__a">{render_md(i.get("a_md"))}</div></div>'
        for i in b.get("items") or [] if (i.get("q") or i.get("a_md"))
    )
    return f'<div class="mz-qa mz-measure">{rows}</div>' if rows else ""


def render_block(b: dict, assets: dict[str, dict], *, first_text: bool = False) -> str:
    kind = b.get("type")
    if kind == "text":
        html = render_md(b.get("md"))
        if not html:
            return ""
        cls = ["mz-text", "mz-measure"]
        if b.get("dropcap") and first_text:
            cls.append("mz-dropcap")
        if b.get("columns") == 2:
            cls.append("mz-text--cols")
        return f'<div class="{" ".join(cls)}">{html}</div>'
    if kind == "photo":
        size = b.get("size") or "column"
        return figure_html(assets.get(b.get("asset_id") or ""), caption=b.get("caption") or "", size=size,
                           cls=f"mz-fig mz-fig--{size}")
    if kind == "photos":
        return _photos(b, assets)
    if kind == "quote":
        if not b.get("text"):
            return ""
        cite = f'<cite>{escape(b["attribution"])}</cite>' if b.get("attribution") else ""
        return (f'<blockquote class="mz-pull mz-pull--{escape(b.get("style") or "big")}">'
                f"<p>{escape(b['text'])}</p>{cite}</blockquote>")
    if kind == "sidebar":
        body = render_md(b.get("md"))
        if not (body or b.get("title")):
            return ""
        title = f"<h3>{escape(b['title'])}</h3>" if b.get("title") else ""
        return f'<aside class="mz-sidebar">{title}{body}</aside>'
    if kind == "qa":
        return _qa(b)
    if kind == "divider":
        return '<hr class="mz-divider" />'
    return ""  # cover (rendered as the header) and the paywall marker


def render_blocks(blocks: list[dict], assets: dict[str, dict], *, dropcap: bool = True) -> str:
    """The story body. The first text block gets the drop cap if it asks
    (`dropcap=False` for a paid story's second half: its opening had it)."""
    out, seen_text = [], not dropcap
    for b in blocks:
        if b.get("type") == "cover":
            continue
        first = b.get("type") == "text" and not seen_text
        seen_text = seen_text or b.get("type") == "text"
        out.append(render_block(b, assets, first_text=first))
    return "".join(out)


def cover_html(post: dict, cover: Optional[dict], asset: Optional[dict], *, byline_html: str) -> str:
    """The story's opening spread: the cover picture with the kicker, headline
    and dek over it (`overlay`), below it (`stacked`) or beside it (`split`)."""
    style = (cover or {}).get("style") or "stacked"
    tone = (cover or {}).get("tone") or "light"
    focal = (cover or {}).get("focal") or {}
    kicker = f'<p class="mz-kicker">{escape(post["kicker"])}</p>' if post.get("kicker") else ""
    dek = f'<p class="mz-dek">{escape(post["excerpt"])}</p>' if post.get("excerpt") else ""
    words = f'<div class="mz-cover__words">{kicker}<h1 class="mz-headline">{escape(post.get("title") or "")}</h1>{dek}{byline_html}</div>'
    if not asset:
        return f'<header class="mz-cover mz-cover--plain">{words}</header>'
    position = f"object-position:{int(focal.get('x', 50))}% {int(focal.get('y', 50))}%"
    cropped = style in ("overlay", "split")
    img = img_html(asset, size="full" if style == "overlay" else ("half" if style == "split" else "wide"),
                   eager=True, cls="mz-cover__img", style=position if cropped else "")
    credit = credit_html(asset, cropped=cropped)
    return (f'<header class="mz-cover mz-cover--{escape(style)} mz-tone--{escape(tone)}">'
            f'<div class="mz-cover__media">{img}</div>{words}'
            f'<p class="mz-cover__credit">{credit}</p></header>')
