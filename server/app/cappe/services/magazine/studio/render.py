"""A paged story's pages as HTML, exactly as the Studio composed them.

Every length is `calc(N * var(--u))`, `--u` being one point on screen: the
reader sets it from the width it has (container units, no script), the Studio
from its zoom. Text is printed line by line from the thread's composition
(`schema`), and no browser ever breaks a line again:

  * each paragraph is a `<p>` holding its lines (so it reads, copies and is
    searched as one);
  * each line is a box of the width the composer aligned it in, placed by its
    bottom edge on its baseline: a zero-height line box (`font-size:0;
    line-height:0`) whose runs are zero-height too, so its bottom is the
    baseline in every engine, whatever each rounds a font's ascent to;
  * the browser aligns the line in its box (`text-align`; a justified line is
    `nowrap` with `text-align-last:justify`), so right and justified edges
    land exactly;
  * the spaces (and line breaks) a line broke at follow it in a
    `.lyt-sp` of no size, so copying keeps the words apart.

Type is set in the faces the Studio measured (`fonts`), each under a name of
its own (`f-<sha>`), so an installed font of the same name never stands in.

The Studio prints the same HTML (`client/src/cappe/studio/render/
layoutRender.ts`); `tests/cappe/fixtures/studio_render_cases.json` holds the
two equal, and `layout.css` is the same file on both sides.
"""
from __future__ import annotations

import math
from html import escape
from pathlib import Path
from typing import Optional

from ...render.sanitize import _safe_image
from ..figures import _variants, credit_html
from ..fonts import Uses, add_use, font_stack
from . import fonts as faces
from .limits import CHAR_DEFAULTS, PARA_DEFAULTS
from .schema import flow_frame, len16, para_text, slice16, spreads

CSS = (Path(__file__).resolve().parent / "layout.css").read_text(encoding="utf-8")

_ALIGN_CLASS = {0: "", 1: " lyt-l--c", 2: " lyt-l--r", 3: " lyt-l--j"}
_FLOW_ALIGN = {"l": "left", "c": "center", "r": "right", "j": "justify", "ja": "justify"}
_FIT = {"fill": "cover", "fit": "contain", "stretch": "fill"}

Threads = dict[str, tuple[dict, int, int]]


def n(value: float) -> str:
    """A number as JavaScript prints it, to 2 decimals (half up): 12.0 → "12"."""
    v = math.floor(float(value) * 100 + 0.5) / 100 + 0.0
    return str(int(v)) if v == int(v) else repr(v)


def u(value: float) -> str:
    return f"calc({n(value)} * var(--u))"


def _box(item: dict, *, pad: float = 0) -> str:
    style = (f"left:{u(item['x'] - pad)};top:{u(item['y'] - pad)};"
             f"width:{u(item['w'] + 2 * pad)};height:{u(item['h'] + 2 * pad)}")
    if item.get("rot"):
        style += f";transform:rotate({n(item['rot'])}deg)"
    if item.get("opacity", 100) < 100:
        style += f";opacity:{n(item['opacity'] / 100)}"
    return style


def _stroke(item: dict, radius: str = "") -> str:
    """A stroke drawn inside the frame's edge, over what it holds."""
    s = item.get("stroke")
    if not s:
        return ""
    r = f";border-radius:{radius}" if radius else ""
    return f'<i class="lyt-k" style="box-shadow:inset 0 0 0 {u(s["w"])} {s["c"]}{r}"></i>'


# ── type ─────────────────────────────────────────────────────────────────────

def run_style(attrs: dict, used: Uses) -> str:
    """A run's type: its face (by the name it was measured in), size,
    tracking, colour, underline."""
    a = {**CHAR_DEFAULTS, **attrs}
    face = faces.face(a["font"], a["wt"], a["it"])
    if face:
        family = f"'{faces.family(face['sha'])}'"
    else:
        add_use(used, a["font"], a["wt"], a["it"])
        family = font_stack(a["font"]) + (";font-weight:" + str(a["wt"])) + (";font-style:italic" if a["it"] else "")
    style = f"font-family:{family};font-size:{u(a['size'])}"
    if a["track"]:
        style += f";letter-spacing:{u(a['track'] / 1000 * a['size'])}"
    if a["color"] != CHAR_DEFAULTS["color"]:
        style += f";color:{a['color']}"
    if a["u"]:
        style += ";text-decoration:underline"
    return style


def _spans(runs: list[dict], start: int, end: int, used: Uses) -> str:
    """The runs' text in [start, end) of the paragraph (UTF-16 offsets)."""
    out = []
    at = 0
    for r in runs:
        text = r.get("t", "")
        size = len16(text)
        a, b = max(start, at), min(end, at + size)
        if b > a:
            part = slice16(text, a - at, b - at) or ""
            out.append(f'<span style="{run_style(r, used)}">{escape(part, quote=False)}</span>')
        at += size
    return "".join(out)


def _lines_html(thread: dict, frame_index: int, frame_h: float, used: Uses) -> str:
    """The lines a thread set in one of its frames, paragraph by paragraph."""
    paras = thread["paras"]
    lines = thread["comp"]["lines"]
    out: list[str] = []
    open_para = -1
    for k, (f, p, s, e, x, b, w, a) in enumerate(lines):
        if f != frame_index:
            continue
        if p != open_para:
            if open_para != -1:
                out.append("</p>")
            out.append('<p class="lyt-p">')
            open_para = p
        runs = paras[p]["runs"]
        out.append(f'<span class="lyt-l{_ALIGN_CLASS[a]}" style="left:{u(x)};bottom:{u(frame_h - b)};width:{u(w)}">'
                   f'{_spans(runs, s, e, used)}</span>')
        nxt = lines[k + 1] if k + 1 < len(lines) else None
        if nxt and nxt[1] == p:
            gap = slice16(para_text(paras[p]), e, nxt[2]) or ""
            if gap:
                out.append(f'<span class="lyt-sp">{escape(gap, quote=False)}</span>')
    if open_para != -1:
        out.append("</p>")
    return "".join(out)


def _para_css(p: dict) -> str:
    a = {**PARA_DEFAULTS, **{k: v for k, v in p.items() if k != "runs"}}
    style = f"text-align:{_FLOW_ALIGN[a['align']]}"
    for key, prop in (("li", "padding-left"), ("ri", "padding-right"), ("fi", "text-indent"),
                      ("sb", "margin-top"), ("sa", "margin-bottom")):
        if a[key]:
            style += f";{prop}:{u(a[key])}"
    if a["lead"]:
        style += f";line-height:{u(a['lead'])}"
    return style


def _flowed_html(thread: dict, item: dict, used: Uses) -> str:
    """A thread with no composition (or none we can trust): its words flowed
    by the browser into its first frame, until the Studio sets it again."""
    paras = "".join(
        f'<p style="{_para_css(p)}">'
        + "".join(f'<span style="{run_style(r, used)}">{escape(r.get("t", ""), quote=False)}</span>'
                  for r in p["runs"])
        + "</p>"
        for p in thread["paras"]
    )
    style = f"padding:{u(item['inset'])}"
    if item["cols"] > 1:
        style += f";column-count:{item['cols']};column-gap:{u(item['gutter'])}"
    return f'<div class="lyt-flow" style="{style}">{paras}</div>'


# ── items ────────────────────────────────────────────────────────────────────

def _text_html(item: dict, threads: Threads, used: Uses) -> str:
    style = _box(item)
    if item.get("fill"):
        style += f";background:{item['fill']}"
    inner = ""
    found = threads.get(item["id"])
    if found:
        thread, index, flow = found
        if thread.get("comp"):
            inner = _lines_html(thread, index, item["h"], used)
        elif index == flow:
            inner = _flowed_html(thread, item, used)
    return f'<div class="lyt-item lyt-text" style="{style}">{inner}{_stroke(item)}</div>'


def _image_sizes(item: dict, page_w: float) -> str:
    wide = max(1, math.ceil(item["w"] / (2 * page_w) * 100))
    narrow = max(1, math.ceil(item["w"] / page_w * 100))
    return f"(min-width: 700px) {wide}vw, {narrow}vw"


def _img(asset: dict, *, sizes: str, eager: bool, style: str) -> str:
    """A library picture's `<img>` (as `figures.img_html`, sized for its
    frame), or "" when its URL isn't safe."""
    src = _safe_image(asset.get("url"))
    if not src:
        return ""
    attrs = [f'src="{escape(src, quote=True)}"', f'alt="{escape(asset.get("alt") or "", quote=True)}"']
    variants = _variants(asset)
    if variants:
        attrs.append('srcset="' + ", ".join(f"{escape(url, quote=True)} {w}w" for w, url in variants) + '"')
        attrs.append(f'sizes="{sizes}"')
    attrs.append('fetchpriority="high"' if eager else 'loading="lazy" decoding="async"')
    attrs.append(f'class="lyt-pic" style="{style}"')
    return f"<img {' '.join(attrs)} />"


def _image_html(item: dict, assets: dict[str, dict], page_w: float, eager: bool) -> str:
    radius = u(item["radius"]) if item.get("radius") else ""
    style = _box(item)
    if item.get("fill"):
        style += f";background:{item['fill']}"
    if radius:
        style += f";border-radius:{radius}"
    asset = assets.get(item.get("asset_id") or "")
    inner = ""
    if asset:
        pic = f"object-fit:{_FIT[item['fit']]};object-position:{n(item['fx'])}% {n(item['fy'])}%"
        if item["zoom"] != 100:
            pic += f";transform:scale({n(item['zoom'] / 100)});transform-origin:{n(item['fx'])}% {n(item['fy'])}%"
        img = _img(asset, sizes=_image_sizes(item, page_w), eager=eager, style=pic)
        credit = credit_html(asset)
        if img:
            inner = img + (f'<figcaption class="lyt-credit">{credit}</figcaption>' if credit else "")
    return f'<figure class="lyt-item lyt-img" style="{style}">{inner}{_stroke(item, radius)}</figure>'


def _shape_html(item: dict) -> str:
    radius = "50%" if item["kind"] == "ellipse" else (u(item["radius"]) if item.get("radius") else "")
    style = _box(item)
    if item.get("fill"):
        style += f";background:{item['fill']}"
    if radius:
        style += f";border-radius:{radius}"
    return f'<div class="lyt-item lyt-shape" style="{style}">{_stroke(item, radius)}</div>'


def _line_html(item: dict) -> str:
    s = item["stroke"]
    pad = s["w"] / 2
    w, h = item["w"], item["h"]
    y1, y2 = (h, 0) if item.get("flip") else (0, h)
    view = f"{n(-pad)} {n(-pad)} {n(w + 2 * pad)} {n(h + 2 * pad)}"
    return (f'<svg class="lyt-item lyt-line" style="{_box(item, pad=pad)}" viewBox="{view}" aria-hidden="true">'
            f'<line x1="0" y1="{n(y1)}" x2="{n(w)}" y2="{n(y2)}" stroke="{s["c"]}" stroke-width="{n(s["w"])}"/></svg>')


def item_html(item: dict, doc: dict, assets: dict[str, dict], threads: Threads, used: Uses,
              *, eager: bool = False) -> str:
    kind = item["kind"]
    if kind == "text":
        return _text_html(item, threads, used)
    if kind == "image":
        return _image_html(item, assets, doc["size"]["w"], eager)
    if kind == "line":
        return _line_html(item)
    return _shape_html(item)


def frame_threads(doc: dict, locked_from: Optional[int] = None) -> Threads:
    """Each threaded text frame's thread, its place in it, and the place of
    the frame its words flow into while it has no composition."""
    out: Threads = {}
    for t in doc.get("threads") or []:
        flow = flow_frame(doc, t, locked_from)
        for i, f in enumerate(t["frames"]):
            out[f] = (t, i, flow)
    return out


def page_items_html(doc: dict, index: int, assets: dict[str, dict], used: Optional[Uses] = None,
                    threads: Optional[Threads] = None) -> str:
    """What sits on one page, bottom to top (hidden items left out)."""
    used = used if used is not None else {}
    threads = threads if threads is not None else frame_threads(doc)
    page_id = doc["pages"][index]["id"]
    return "".join(item_html(i, doc, assets, threads, used, eager=index == 0)
                   for i in doc["items"] if i["page"] == page_id and not i.get("hidden"))


# ── pages and spreads ────────────────────────────────────────────────────────

def spread_html(doc: dict, pages: list[int], assets: dict[str, dict], used: Uses,
                threads: Threads, *, locked_from: Optional[int] = None) -> str:
    """One spread: its paper, then each page's items in a layer of their own
    (transparent, so an item running off its page shows on the next).
    `locked_from`: the first page (1-based) for subscribers only, printed
    empty; their browser fills it."""
    pw, ph = doc["size"]["w"], doc["size"]["h"]
    paper = "".join(f'<div class="lyt-paper" data-lyt-n="{index + 1}" style="left:{u(k * pw)};width:{u(pw)}"></div>'
                    for k, index in enumerate(pages))
    layers = []
    for k, index in enumerate(pages):
        number = index + 1
        style = f"left:{u(k * pw)};width:{u(pw)}"
        if locked_from is not None and number >= locked_from:
            # #mz-paywall: the story page's one paywall (pages.paywall_section).
            layers.append(f'<div class="lyt-page lyt-page--locked" data-lyt-lock="{number}" style="{style}">'
                          '<p class="lyt-lock">For subscribers</p>'
                          '<a class="lyt-lock-go" href="#mz-paywall">Subscribe or sign in to read on</a></div>')
        else:
            layers.append(f'<div class="lyt-page" data-lyt-page="{number}" style="{style}">'
                          f"{page_items_html(doc, index, assets, used, threads)}</div>")
    return (f'<div class="lyt-spread" style="width:{u(len(pages) * pw)};height:{u(ph)}">'
            f'{paper}{"".join(layers)}</div>')


def pages_html(doc: dict, assets: dict[str, dict], *, locked_from: Optional[int] = None,
               label: str = "The story's pages") -> tuple[str, Uses]:
    """The whole story as a strip of spreads (one page at a time on a phone),
    and the faces it sets that aren't in the Studio's own set."""
    used: Uses = {}
    threads = frame_threads(doc, locked_from)
    pw, ph = doc["size"]["w"], doc["size"]["h"]
    slots = "".join(
        f'<div class="lyt-slot" data-lyt-spread="{k}">'
        f"{spread_html(doc, pages, assets, used, threads, locked_from=locked_from)}</div>"
        for k, pages in enumerate(spreads(doc))
    )
    sw = 2 * pw if doc.get("facing") else pw
    style = f"--pw:{n(pw)};--ph:{n(ph)};--sw:{n(sw)};--paper:{doc['paper']}"
    html = (f'<div class="lyt" data-lyt style="{style}">'
            f'<div class="lyt-strip" data-lyt-strip tabindex="0" role="region" aria-label="{escape(label)}">'
            f"{slots}</div></div>")
    return html, used


def locked_pages(doc: dict, assets: dict[str, dict], from_page: int) -> list[dict]:
    """The pages for subscribers only, each as its items' HTML (`/paid`)."""
    used: Uses = {}
    threads = frame_threads(doc, from_page)
    return [{"n": i + 1, "html": page_items_html(doc, i, assets, used, threads)}
            for i in range(from_page - 1, len(doc["pages"]))]


def faces_css(doc: dict) -> str:
    """An @font-face for each of the Studio's faces the story sets."""
    shas = sorted({f["sha"] for f in (_run_face(r) for t in doc.get("threads") or []
                                       for p in t["paras"] for r in p["runs"]) if f})
    return "".join(
        f"@font-face{{font-family:'{faces.family(sha)}';src:url({faces.url(sha)}) format('truetype');"
        "font-display:block}" for sha in shas
    )


def _run_face(run: dict) -> Optional[dict]:
    a = {**CHAR_DEFAULTS, **run}
    return faces.face(a["font"], a["wt"], a["it"])
