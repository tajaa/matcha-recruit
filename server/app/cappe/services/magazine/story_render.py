"""Story blocks → HTML (the body of `/stories/<slug>`).

Separate from the page-block registry (`services/render/blocks.py`): stories
have their own small vocabulary (`story_schema.STORY_BLOCKS`) and their own
CSS (`render/assets/magazine.css`, every class `mz-`). Everything the owner
typed is escaped or goes through `rt.render_rt` (`richtext.render_md` for text
stored before documents); pictures come from the
library rows passed in `assets`, credits included.

Photo groups keep each picture's own shape: a row's pictures are given flex
weights from their width/height, so they line up at one height without
cropping (`pair`, `trio`); `grid` and `mosaic` are CSS columns.

`edit=True` is the owner's editor on the page (the dashboard's `magazine/frame/`),
never a reader's page: each block's first tag carries its place in
`content.blocks` (`data-mz-b`), each piece of words the editor may type into
carries its path (`data-mz-f`, `data-mz-k` plain or rich), and what a reader
never sees is printed so it can be filled in — an empty paragraph, a missing
picture, an empty caption — with a placeholder (`data-mz-ph`). The client's
list of those paths is `client/src/cappe/magazine/canvas/fields.ts`.
"""
from __future__ import annotations

import re
from html import escape
from typing import Optional

from .design_render import design_html, layer_credits, page_style
from .design_schema import ASPECTS
from .figures import credit_html, figure_html, img_html
from .fonts import font_stack
from .richtext import render_md
from .rt import RtError, normalize_rt, render_rt

PAYWALL = "paywall"
# Characters past which a pull quote is set smaller (mz-pull--long).
LONG_QUOTE = 110

_FIRST_TAG = re.compile(r"^<([a-z0-9]+)")


def split_at_paywall(blocks: list[dict], *, preview_blocks: int = 3) -> tuple[list[dict], list[dict]]:
    """(free part, paid part). The owner's paywall marker decides; without one
    the first `preview_blocks` blocks of the body are free (the cover is the
    story's header, not one of them)."""
    for i, b in enumerate(blocks):
        if b.get("type") == PAYWALL:
            return blocks[:i], blocks[i + 1:]
    body = 0
    for i, b in enumerate(blocks):
        if b.get("type") == "cover":
            continue
        if body == preview_blocks:
            return blocks[:i], blocks[i:]
        body += 1
    return blocks, []


def _rich_html(b: dict, md_key: str, rt_key: str) -> str:
    """A rich field's words: from its document (what the editor saves), else
    its Markdown (a story stored before the editor had documents)."""
    doc = b.get(rt_key)
    if isinstance(doc, dict):
        try:
            return render_rt(normalize_rt(doc))
        except RtError:
            pass  # saved under other limits: its Markdown still reads
    return render_md(b.get(md_key))


def field(path: str, *, rich: bool = False, ph: str = "") -> str:
    """The editor's marker for words it may type into."""
    attrs = f' data-mz-f="{escape(path, quote=True)}" data-mz-k="{"rich" if rich else "plain"}"'
    return attrs + (f' data-mz-ph="{escape(ph, quote=True)}"' if ph else "")


def mark(html: str, attrs: str) -> str:
    """`attrs` added to the first tag of a piece of HTML."""
    if not html or not attrs:
        return html
    return _FIRST_TAG.sub(lambda m: f"<{m.group(1)}{attrs}", html, count=1)


def _aspect(asset: Optional[dict]) -> float:
    if asset and asset.get("width") and asset.get("height"):
        return max(0.2, min(5.0, asset["width"] / asset["height"]))
    return 1.5


def _missing(label: str, *, size: str = "column", item: Optional[int] = None) -> str:
    """Where a picture goes, in the editor, before one is chosen."""
    which = f' data-mz-item="{item}"' if item is not None else ""
    return (f'<figure class="mz-fig mz-fig--{escape(size)} mz-ph-pic" data-mz-pick{which}>'
            f'<span class="mz-ph-pic__box">{escape(label)}</span></figure>')


def _photos(b: dict, assets: dict[str, dict], *, edit: bool = False) -> str:
    items = [(i, assets.get(it.get("asset_id") or ""), it.get("caption") or "")
             for i, it in enumerate(b.get("items") or [])]
    if not edit:
        items = [(i, a, c) for i, a, c in items if a]
    if not items:
        return _missing("Choose pictures", size="wide") if edit else ""
    layout = b.get("layout") or "pair"

    designs = [it.get("design") for it in b.get("items") or []]

    def fig(i: int, a: Optional[dict], c: str, *, size: str, cls: str = "mz-fig", style: str = "") -> str:
        if a is None:
            return _missing(f"Choose picture {i + 1}", item=i)
        cap = field(f"items.{i}.caption", ph="Caption") if edit else None
        design = designs[i] if i < len(designs) else None
        over = design_html(design, assets, edit=edit, path=f"items.{i}.design")
        html = figure_html(a, caption=c, size=size, cls=cls, style=style, cap_attrs=cap,
                           over=over if over or edit else None, credits=layer_credits(design, assets, skip=a.get("id")))
        return mark(html, f' data-mz-item="{i}"') if edit else html

    if layout in ("pair", "trio"):
        size = "half" if layout == "pair" else "third"
        figs = "".join(fig(i, a, c, size=size, cls="mz-fig mz-row__item", style=f"flex:{_aspect(a):.4f} 1 0%")
                       for i, a, c in items)
        return f'<div class="mz-photos mz-row mz-row--{layout}">{figs}</div>'
    figs = "".join(fig(i, a, c, size="third") for i, a, c in items)
    return f'<div class="mz-photos mz-cols mz-cols--{layout}">{figs}</div>'


def _qa(b: dict, *, edit: bool = False) -> str:
    rows = "".join(
        f'<div class="mz-qa__item"><p class="mz-qa__q"{field(f"items.{i}.q", ph="Question") if edit else ""}>'
        f'{escape(it.get("q") or "")}</p>'
        f'<div class="mz-qa__a"{field(f"items.{i}.a_md", rich=True, ph="Answer") if edit else ""}>'
        f'{_rich_html(it, "a_md", "a_rt")}</div></div>'
        for i, it in enumerate(b.get("items") or []) if edit or (it.get("q") or it.get("a_md"))
    )
    if not rows and edit:
        rows = '<p class="mz-ph-note">Add a question in the panel.</p>'
    return f'<div class="mz-qa mz-measure">{rows}</div>' if rows else ""


def _crop_style(crop: Optional[dict]) -> str:
    """The kept part of the picture fills its frame: the picture is scaled up
    and shifted so only that rectangle shows."""
    if not crop:
        return ""
    x, y, w, h = (crop[k] for k in ("x", "y", "w", "h"))
    return (f"position:absolute;max-width:none;width:{10000 / w:.3f}%;height:{10000 / h:.3f}%;"
            f"left:{-100 * x / w:.3f}%;top:{-100 * y / h:.3f}%")


def photo_html(b: dict, asset: Optional[dict], *, edit: bool = False, assets: Optional[dict[str, dict]] = None) -> str:
    """A photo block: its frame (border, shape, colour, crop) with its design
    laid over it, then its caption and credits. A crop or a circle/arch shape
    changes the picture, so a CC BY credit says it was cropped."""
    size, shape = b.get("size") or "column", b.get("shape") or "rect"
    if not asset:
        return _missing("Choose a picture", size=size) if edit else ""
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
    over = design_html(b.get("design"), assets or {}, edit=edit)
    caption = (b.get("caption") or asset.get("caption") or "").strip()
    credit = (credit_html(asset, cropped=bool(crop) or shape in ("circle", "arch"))
              + layer_credits(b.get("design"), assets or {}, skip=asset.get("id")))
    figcaption = ""
    if caption or credit or edit:
        cap = (f'<span class="mz-cap"{field("caption", ph="Caption") if edit else ""}>{escape(caption)}</span>'
               if caption or edit else "")
        figcaption = f"<figcaption>{cap}{credit}</figcaption>"
    cls = " ".join(["mz-fig", f"mz-fig--{size}", f"mz-border--{b.get('border') or 'none'}", f"mz-shape--{shape}",
                    f"mz-filter--{b.get('filter') or 'none'}"])
    # `--mz-ar` lets a book page size the picture to fit its height.
    fig_style = f' style="--mz-ar:{ratio:.4f}"' if ratio else ""
    return (f'<figure class="{escape(cls)}"{fig_style}><div class="mz-frame"{frame_style}>{img}{over}</div>'
            f"{figcaption}</figure>")


def text_type_style(b: dict) -> str:
    """A text block's own type, where the writer set it (else the page's)."""
    parts = []
    if b.get("font") and b["font"] != "body":
        parts.append(f"font-family:{font_stack(b['font'])}")
    if b.get("size") and b["size"] != 1:
        parts.append(f"font-size:{format(float(b['size']), 'g')}em")
    if b.get("color"):
        parts.append(f"color:{'var(--mz-accent)' if b['color'] == 'accent' else b['color']}")
    if b.get("leading"):
        parts.append(f"line-height:{format(float(b['leading']), 'g')}")
    return ";".join(parts)


def page_html(b: dict, assets: dict[str, dict], *, edit: bool = False) -> str:
    """A designed page: its artboard, sized as a page of the book, and the
    credits of the pictures on it."""
    design = b.get("design") or {}
    aspect = ASPECTS.get(b.get("aspect") or "", 0.75)
    credits = layer_credits(design, assets)
    credit = f'<p class="mz-page__credit">{credits}</p>' if credits else ""
    art = (f'<div class="mz-page__art" style="{escape(page_style(design, aspect), quote=True)}">'
           f'{design_html(design, assets, edit=edit)}</div>')
    return f'<section class="mz-page">{art}{credit}</section>'


def render_block(b: dict, assets: dict[str, dict], *, first_text: bool = False, edit: bool = False) -> str:
    kind = b.get("type")
    if kind == "text":
        html = _rich_html(b, "md", "rt")
        if not html and not edit:
            return ""
        cls = ["mz-text", "mz-measure", f"mz-text--{b.get('variant') or 'body'}", f"mz-align--{b.get('align') or 'left'}"]
        if b.get("dropcap") and first_text:
            cls.append("mz-dropcap")
        if b.get("columns") in (2, 3):
            cls.append("mz-text--cols" if b["columns"] == 2 else "mz-text--cols mz-text--cols3")
        attrs = field("md", rich=True, ph="Write here") if edit else ""
        style = text_type_style(b)
        if style:
            attrs = f' style="{escape(style, quote=True)}"' + attrs
        return f'<div class="{escape(" ".join(cls))}"{attrs}>{html}</div>'
    if kind == "photo":
        return photo_html(b, assets.get(b.get("asset_id") or ""), edit=edit, assets=assets)
    if kind == "page":
        return page_html(b, assets, edit=edit)
    if kind == "photos":
        return _photos(b, assets, edit=edit)
    if kind == "quote":
        if not b.get("text") and not edit:
            return ""
        cite = (f'<cite{field("attribution", ph="Who said it") if edit else ""}>{escape(b.get("attribution") or "")}</cite>'
                if b.get("attribution") or edit else "")
        # A long quote is set smaller, so it still fits on one page of the book.
        long = " mz-pull--long" if len(b.get("text") or "") > LONG_QUOTE else ""
        return (f'<blockquote class="mz-pull mz-pull--{escape(b.get("style") or "big")}{long}">'
                f'<p{field("text", ph="The words to pull out") if edit else ""}>{escape(b.get("text") or "")}</p>'
                f"{cite}</blockquote>")
    if kind == "sidebar":
        body = _rich_html(b, "md", "rt")
        if not (body or b.get("title")) and not edit:
            return ""
        if edit:
            return (f'<aside class="mz-sidebar"><h3{field("title", ph="Sidebar title")}>{escape(b.get("title") or "")}</h3>'
                    f'<div{field("md", rich=True, ph="Facts, a timeline, where to go")}>{body}</div></aside>')
        title = f"<h3>{escape(b['title'])}</h3>" if b.get("title") else ""
        return f'<aside class="mz-sidebar">{title}{body}</aside>'
    if kind == "qa":
        return _qa(b, edit=edit)
    if kind == "divider":
        return '<hr class="mz-divider" />'
    if kind == PAYWALL and edit:
        return '<div class="mz-paywall-mark"><span>Subscribers only from here</span></div>'
    return ""  # cover (rendered as the header) and, for readers, the paywall marker


def render_blocks(blocks: list[dict], assets: dict[str, dict], *, dropcap: bool = True, edit: bool = False) -> str:
    """The story body. The first text block gets the drop cap if it asks
    (`dropcap=False` for a paid story's second half: its opening had it).
    In the editor each block is marked with its place in the story."""
    out, seen_text = [], not dropcap
    for i, b in enumerate(blocks):
        if b.get("type") == "cover":
            continue
        first = b.get("type") == "text" and not seen_text
        seen_text = seen_text or b.get("type") == "text"
        html = render_block(b, assets, first_text=first, edit=edit)
        out.append(mark(html, f' data-mz-b="{i}"') if edit else html)
    return "".join(out)


def cover_html(post: dict, cover: Optional[dict], asset: Optional[dict], *, byline_html: str,
               edit: bool = False, assets: Optional[dict[str, dict]] = None) -> str:
    """The story's opening spread: the cover picture with the kicker, headline
    and dek over it (`overlay`), below it (`stacked`) or beside it (`split`).
    In the editor the words are typed into here, and the cover block (the
    story's first) is marked as block 0."""
    style = (cover or {}).get("style") or "stacked"
    tone = (cover or {}).get("tone") or "light"
    focal = (cover or {}).get("focal") or {}

    def words_html() -> str:
        if not edit:
            kicker = f'<p class="mz-kicker">{escape(post["kicker"])}</p>' if post.get("kicker") else ""
            dek = f'<p class="mz-dek">{escape(post["excerpt"])}</p>' if post.get("excerpt") else ""
            headline = escape(post.get("title") or "")
            return f'<div class="mz-cover__words">{kicker}<h1 class="mz-headline">{headline}</h1>{dek}{byline_html}</div>'
        return (f'<div class="mz-cover__words"><p class="mz-kicker"{field("@kicker", ph="Kicker")}>'
                f'{escape(post.get("kicker") or "")}</p>'
                f'<h1 class="mz-headline"{field("@title", ph="Headline")}>{escape(post.get("title") or "")}</h1>'
                f'<p class="mz-dek"{field("@excerpt", ph="Dek: a sentence or two that sells the story")}>'
                f'{escape(post.get("excerpt") or "")}</p>{byline_html}</div>')

    block_attr = ' data-mz-b="0"' if edit and cover else ""
    if not asset:
        media = ""
        if edit and cover:
            media = '<div class="mz-cover__media mz-ph-pic" data-mz-pick><span class="mz-ph-pic__box">Choose a cover picture</span></div>'
            return (f'<header class="mz-cover mz-cover--{escape(style)} mz-tone--{escape(tone)}"{block_attr}>'
                    f"{media}{words_html()}</header>")
        return f'<header class="mz-cover mz-cover--plain"{block_attr}>{words_html()}</header>'
    position = f"object-position:{int(focal.get('x', 50))}% {int(focal.get('y', 50))}%"
    # Every cover is cut to fit its page in the book (a stacked one's photo
    # fills what the words leave), so the focal point always applies.
    img = img_html(asset, size="full" if style == "overlay" else ("half" if style == "split" else "wide"),
                   eager=True, cls="mz-cover__img", style=position)
    design = (cover or {}).get("design")
    credit = credit_html(asset, cropped=True) + layer_credits(design, assets or {}, skip=asset.get("id"))
    focal_attr = (f' data-mz-focal="{int(focal.get("x", 50))},{int(focal.get("y", 50))}"' if edit else "")
    # The darkening behind an overlay's words, over the picture and under
    # its design; the design sits on the whole picture, however it is cut.
    scrim = '<div class="mz-cover__scrim"></div>' if style == "overlay" else ""
    ratio = asset["width"] / asset["height"] if asset.get("width") and asset.get("height") else 1.5
    over = design_html(design, assets or {}, edit=edit and bool(cover),
                       picture=(ratio, int(focal.get("x", 50)) / 100, int(focal.get("y", 50)) / 100))
    return (f'<header class="mz-cover mz-cover--{escape(style)} mz-tone--{escape(tone)}"{block_attr}>'
            f'<div class="mz-cover__media"{focal_attr}>{img}{scrim}{over}</div>{words_html()}'
            f'<p class="mz-cover__credit">{credit}</p></header>')
