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
# Characters past which a pull quote is set smaller (mz-pull--long).
LONG_QUOTE = 110


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


def _crop_style(crop: Optional[dict]) -> str:
    """The kept part of the picture fills its frame: the picture is scaled up
    and shifted so only that rectangle shows."""
    if not crop:
        return ""
    x, y, w, h = (crop[k] for k in ("x", "y", "w", "h"))
    return (f"position:absolute;max-width:none;width:{10000 / w:.3f}%;height:{10000 / h:.3f}%;"
            f"left:{-100 * x / w:.3f}%;top:{-100 * y / h:.3f}%")


def _overlay(o: dict) -> str:
    text = (o.get("text") or "").strip()
    if not text:
        return ""
    cls = (f"mz-ov mz-ov--{escape(o.get('size') or 'm')} mz-ov--{escape(o.get('tone') or 'light')} "
           f"mz-ov--{escape(o.get('align') or 'center')}" + (" mz-ov--box" if o.get("box") else ""))
    words = escape(text).replace("\n", "<br>")
    return f'<div class="{cls}" style="left:{int(o.get("x", 50))}%;top:{int(o.get("y", 50))}%">{words}</div>'


def photo_html(b: dict, asset: Optional[dict]) -> str:
    """A photo block: its frame (border, shape, colour, crop) with any words
    set on it, then its caption and credit. A crop or a circle/arch shape
    changes the picture, so a CC BY credit says it was cropped."""
    if not asset:
        return ""
    size, shape = b.get("size") or "column", b.get("shape") or "rect"
    crop = b.get("crop") if shape != "circle" else None
    img = img_html(asset, size=size, style=_crop_style(crop))
    if not img:
        return ""
    frame_style, ratio = "", None
    if asset.get("width") and asset.get("height"):
        ratio = asset["width"] / asset["height"]
    if crop and ratio:
        frame_style = f' style="aspect-ratio:{asset["width"] * crop["w"]}/{asset["height"] * crop["h"]}"'
        ratio = ratio * crop["w"] / crop["h"]
    if shape == "circle":
        ratio = 1.0
    overlays = "".join(_overlay(o) for o in b.get("overlays") or [])
    caption = (b.get("caption") or asset.get("caption") or "").strip()
    credit = credit_html(asset, cropped=bool(crop) or shape in ("circle", "arch"))
    figcaption = ""
    if caption or credit:
        cap = f'<span class="mz-cap">{escape(caption)}</span>' if caption else ""
        figcaption = f"<figcaption>{cap}{credit}</figcaption>"
    cls = " ".join(["mz-fig", f"mz-fig--{size}", f"mz-border--{b.get('border') or 'none'}", f"mz-shape--{shape}",
                    f"mz-filter--{b.get('filter') or 'none'}"])
    # `--mz-ar` lets a book page size the picture to fit its height.
    fig_style = f' style="--mz-ar:{ratio:.4f}"' if ratio else ""
    return (f'<figure class="{escape(cls)}"{fig_style}><div class="mz-frame"{frame_style}>{img}{overlays}</div>'
            f"{figcaption}</figure>")


def render_block(b: dict, assets: dict[str, dict], *, first_text: bool = False) -> str:
    kind = b.get("type")
    if kind == "text":
        html = render_md(b.get("md"))
        if not html:
            return ""
        cls = ["mz-text", "mz-measure", f"mz-text--{b.get('variant') or 'body'}", f"mz-align--{b.get('align') or 'left'}"]
        if b.get("dropcap") and first_text:
            cls.append("mz-dropcap")
        if b.get("columns") in (2, 3):
            cls.append("mz-text--cols" if b["columns"] == 2 else "mz-text--cols mz-text--cols3")
        return f'<div class="{escape(" ".join(cls))}">{html}</div>'
    if kind == "photo":
        return photo_html(b, assets.get(b.get("asset_id") or ""))
    if kind == "photos":
        return _photos(b, assets)
    if kind == "quote":
        if not b.get("text"):
            return ""
        cite = f'<cite>{escape(b["attribution"])}</cite>' if b.get("attribution") else ""
        # A long quote is set smaller, so it still fits on one page of the book.
        long = " mz-pull--long" if len(b["text"]) > LONG_QUOTE else ""
        return (f'<blockquote class="mz-pull mz-pull--{escape(b.get("style") or "big")}{long}">'
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
    # Every cover is cut to fit its page in the book (a stacked one's photo
    # fills what the words leave), so the focal point always applies.
    cropped = True
    img = img_html(asset, size="full" if style == "overlay" else ("half" if style == "split" else "wide"),
                   eager=True, cls="mz-cover__img", style=position)
    credit = credit_html(asset, cropped=cropped)
    return (f'<header class="mz-cover mz-cover--{escape(style)} mz-tone--{escape(tone)}">'
            f'<div class="mz-cover__media">{img}</div>{words}'
            f'<p class="mz-cover__credit">{credit}</p></header>')
