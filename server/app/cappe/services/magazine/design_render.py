"""A design → HTML: its layers drawn over their artboard (`design_schema`).

A design is a `.mzd` box laid over its artboard. Each layer carries its place
as numbers (`--x`, `--y`, `--w`, `--h`, percent of the artboard) and
`render/assets/design.css` turns them into a position through the artboard's
units: `--bw` (1% of its width) and `--bh` (1% of its height), offset by
`--bx`/`--by`. On a photo's frame or a designed page those are the frame's own
(`1cqw`, `1%`); on a cover, whose picture is cut to fit its page, they are
the whole picture's, so a layer stays on the part of the picture it was put
on whatever the page's shape. Sizes (type, strokes, corners, shadows) are in
`--bw`, so a design scales with its artboard.

Everything typed is escaped or goes through `rt.render_rt`; colours, faces
and numbers were checked when stored; pictures come from the library rows in
`assets`. The client renders the same HTML (`client/src/cappe/magazine/
design/designRender.ts`) to show a change at once while the page is set
again; `tests/cappe/fixtures/magazine_design_cases.json` holds both to it.

`edit=True` is the owner's editor: each layer is named (`data-mzd-l`), a
text layer's words are a field to type into (`data-mz-f`, opened on a double
click), and a probe (`.mzd__box`) marks the artboard's edges.
"""
from __future__ import annotations

from html import escape
from typing import Any, Optional

from .design_schema import design_asset_ids, num
from .figures import credit_html, img_html
from .fonts import font_stack
from .rt import LINK_REL, render_rt

_CASE = {"upper": "uppercase", "lower": "lowercase", "title": "capitalize"}
_VALIGN = {"middle": " mzd__l--vm", "bottom": " mzd__l--vb"}


def n(value: float) -> str:
    """12.0 → "12", 0.5 → "0.5" (as JavaScript prints them)."""
    v = float(value) + 0.0
    return str(int(v)) if v == int(v) else format(v, "g")


def css_colour(value: str) -> str:
    return "var(--mz-accent)" if value == "accent" else value


def u(value: float) -> str:
    """A size in the artboard's width units."""
    return f"calc({n(value)} * var(--bw))"


def paint_css(p: dict) -> str:
    kind = p.get("kind")
    if kind == "solid":
        return css_colour(p["color"])
    if kind in ("linear", "radial"):
        stops = ",".join(f"{css_colour(s['color'])} {n(s['at'])}%" for s in p.get("stops") or [])
        if kind == "linear":
            return f"linear-gradient({n(p.get('angle', 180))}deg,{stops})"
        return f"radial-gradient(circle,{stops})"
    return ""


def _shadow(s: dict, *, spread: bool = True) -> str:
    parts = [u(s["x"]), u(s["y"]), u(s["blur"])]
    if spread:
        parts.append(u(s["spread"]))
    return ("inset " if s.get("inner") and spread else "") + " ".join(parts) + f" {css_colour(s['color'])}"


def layer_style(lay: dict) -> str:
    """Where a layer sits and how it is painted: its element's style."""
    kind = lay["kind"]
    auto = kind == "text" and lay.get("autosize") == "height"
    parts = [f"--x:{n(lay['x'])}", f"--y:{n(lay['y'])}", f"--w:{n(lay['w'])}"]
    if not auto:
        parts.append(f"--h:{n(lay['h'])}")
    transform = []
    if lay.get("rot"):
        transform.append(f"rotate({n(lay['rot'])}deg)")
    if lay.get("flip_x") or lay.get("flip_y"):
        transform.append(f"scale({-1 if lay.get('flip_x') else 1},{-1 if lay.get('flip_y') else 1})")
    if transform:
        parts.append("transform:" + " ".join(transform))
    if lay.get("opacity", 100) != 100:
        parts.append(f"opacity:{n(lay['opacity'] / 100)}")
    if lay.get("blend", "normal") != "normal":
        parts.append(f"mix-blend-mode:{lay['blend']}")
    if kind == "group":
        return ";".join(parts)
    fill = paint_css(lay.get("fill") or {}) if kind != "image" else ""
    if fill:
        parts.append(f"background:{fill}")
    stroke = lay.get("stroke") or {}
    if stroke.get("width") and not (kind == "shape" and lay.get("shape") == "line"):
        parts.append(f"border:{u(stroke['width'])} {stroke['style']} {css_colour(stroke['color'])}")
    if kind == "shape" and lay.get("shape") == "ellipse":
        parts.append("border-radius:50%")
    elif any(lay.get("radius") or []):
        parts.append("border-radius:" + " ".join(u(r) for r in lay["radius"]))
    shadows = lay.get("shadows") or []
    filters = []
    if shadows:
        if kind == "image":
            filters += [f"drop-shadow({_shadow(s, spread=False)})" for s in shadows if not s.get("inner")]
        elif kind == "shape" or fill:
            parts.append("box-shadow:" + ",".join(_shadow(s) for s in shadows))
    if lay.get("blur"):
        filters.append(f"blur({u(lay['blur'])})")
    if filters:
        parts.append("filter:" + " ".join(filters))
    if kind == "text" and lay.get("pad"):
        parts.append(f"padding:{u(lay['pad'])}")
    return ";".join(parts)


def text_style(lay: dict) -> str:
    parts = [f"font-family:{font_stack(lay['font'])}", f"font-size:{u(lay['size'])}",
             f"font-weight:{lay['weight']}"]
    if lay.get("italic"):
        parts.append("font-style:italic")
    parts += [f"color:{css_colour(lay['color'])}", f"text-align:{lay['align']}", f"line-height:{n(lay['leading'])}"]
    if lay.get("tracking"):
        parts.append(f"letter-spacing:{n(lay['tracking'])}em")
    if lay.get("case") in _CASE:
        parts.append(f"text-transform:{_CASE[lay['case']]}")
    if not paint_css(lay.get("fill") or {}):
        shadows = [s for s in lay.get("shadows") or [] if not s.get("inner")]
        if shadows:
            parts.append("text-shadow:" + ",".join(_shadow(s, spread=False) for s in shadows))
    return ";".join(parts)


def image_style(lay: dict) -> str:
    focal = lay.get("focal") or {}
    parts = [f"object-fit:{lay['fit']}", f"object-position:{int(focal.get('x', 50))}% {int(focal.get('y', 50))}%"]
    if lay.get("zoom", 100) > 100:
        parts.append(f"transform:scale({n(lay['zoom'] / 100)})")
    if lay.get("filter") == "bw":
        parts.append("filter:grayscale(1)")
    elif lay.get("filter") == "sepia":
        parts.append("filter:sepia(.85)")
    return ";".join(parts)


def _classes(lay: dict) -> str:
    kind = lay["kind"]
    cls = f"mzd__l mzd__l--{kind}"
    if kind == "text":
        cls += " mzd__l--auto" if lay.get("autosize") == "height" else _VALIGN.get(lay.get("valign") or "", "")
    elif kind == "shape" and lay.get("shape") == "line":
        cls += " mzd__l--line"
    return cls


def layer_html(lay: dict, assets: dict[str, dict], *, edit: bool = False, path: str = "design") -> str:
    if lay.get("hidden"):
        return ""
    kind = lay["kind"]
    attrs = ""
    if edit:
        attrs = f' data-mzd-l="{escape(lay["id"])}"' + (" data-mzd-lock" if lay.get("locked") else "")
    if kind == "group":
        inner = "".join(layer_html(c, assets, edit=edit, path=path) for c in lay.get("children") or [])
        return f'<div class="mzd__g" style="{escape(layer_style(lay), quote=True)}"{attrs}>{inner}</div>'
    if kind == "text":
        field = (f' data-mz-f="{escape(path)}.{escape(lay["id"])}" data-mz-k="rich" data-mz-lazy'
                 ' data-mz-ph="Type something"') if edit else ""
        inner = f'<div class="mzd__t" style="{escape(text_style(lay), quote=True)}"{field}>{render_rt(lay.get("rt"))}</div>'
    elif kind == "image":
        asset = assets.get(lay.get("asset_id") or "")
        inner = img_html(asset, size="wide", cls="mzd__img", style=image_style(lay)) if asset else ""
        if not inner and not edit:
            return ""
    elif lay.get("shape") == "line":
        stroke = lay.get("stroke") or {}
        width = stroke.get("width") or 0.3
        inner = (f'<i class="mzd__line" style="border-top:{u(width)} {stroke.get("style") or "solid"} '
                 f'{css_colour(stroke.get("color") or "#000000")}"></i>')
    else:
        inner = ""
    style = escape(layer_style(lay), quote=True)
    if lay.get("link") and not edit:
        return (f'<a class="{_classes(lay)}" style="{style}" href="{escape(lay["link"], quote=True)}" '
                f'rel="{LINK_REL}">{inner}</a>')
    return f'<div class="{_classes(lay)}" style="{style}"{attrs}>{inner}</div>'


def design_html(design: Optional[dict], assets: dict[str, dict], *, edit: bool = False, path: str = "design",
                picture: Optional[tuple[float, float, float]] = None) -> str:
    """The design's box with its layers, for a picture or a page. `picture`:
    a cover's picture (its width over height and the focal point it is cut
    to, 0–1), whose layers sit on the whole picture. In the editor every
    picture gets its box, designed or not, to add layers to."""
    layers = (design or {}).get("layers") or []
    if not layers and not edit:
        return ""
    vars_ = ""
    if picture:
        ratio, fx, fy = picture
        vars_ = f' style="--ar:{n(num(ratio, 0.2, 5, 1.5, places=4))};--fx:{n(fx)};--fy:{n(fy)}"'
    marks = f' data-mzd="{escape(path)}"' if edit else ""
    probe = '<i class="mzd__box" aria-hidden="true"></i>' if edit else ""
    inner = "".join(layer_html(lay, assets, edit=edit, path=path) for lay in layers)
    return f'<div class="mzd"{vars_}{marks}>{probe}{inner}</div>'


def page_style(design: Optional[dict], aspect: float) -> str:
    """A designed page's artboard: its shape and its background."""
    parts = [f"--ar:{n(aspect)}"]
    background = paint_css((design or {}).get("background") or {})
    if background:
        parts.append(f"background:{background}")
    return ";".join(parts)


def layer_credits(design: Optional[dict], assets: dict[str, dict], *, skip: Any = None) -> str:
    """The credit of each picture a design lays down (each once; `skip` is
    the picture under it, credited already: a library row's id, a UUID)."""
    out, seen = [], {str(skip)} if skip else set()
    for asset_id in design_asset_ids(design):
        asset = assets.get(asset_id)
        if asset_id in seen or not asset:
            continue
        seen.add(asset_id)
        out.append(credit_html(asset))
    return "".join(out)
