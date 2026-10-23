"""A design: words, shapes and pictures laid over a picture or a page.

A design is `{"layers": [...]}` (a designed page adds its `background`). It
sits on an artboard — a story's picture (its cover, a photo, a picture in a
group) or a page of its own — and every layer is placed in percent of that
artboard: `x`/`w` of its width, `y`/`h` of its height. Type sizes, strokes,
corners, shadows and padding are in percent of the artboard's width, so a
design reads the same at every size: a spread, a phone, a thumbnail. Layers
stack in order, the first at the bottom.

Every value is checked and reshaped here before it is stored, as
`story_schema` does a story: unknown keys are dropped, a choice outside its
list falls back to the first, numbers are clamped and rounded (as the client
rounds them: `design/designOps.ts`), colours are hex or the magazine's
accent, faces come from `fonts.FONTS`, a link is web or mail only, and a
picture is a library `asset_id`, never a URL (its credit is printed from the
library row).

The client mirror is `client/src/cappe/magazine/design/`; the shared
fixture `tests/cappe/fixtures/magazine_design_cases.json` renders equal on
both sides.
"""
from __future__ import annotations

import json
import math
import re
from typing import Any, Iterable, Optional
from uuid import UUID

from .fonts import ROLES, add_use, font_name, has_italic, nearest_weight, Uses
from .richtext import md_to_text
from .rt import RtError, _href, empty_rt, normalize_rt, rt_to_md

MAX_LAYERS = 200
MAX_DEPTH = 4
MAX_DESIGN_BYTES = 80_000
MAX_TEXT = 2_000
MAX_STOPS = 8
MAX_SHADOWS = 4

KINDS = ("text", "image", "shape", "group")
SHAPES = ("rect", "ellipse", "line")
BLENDS = ("normal", "multiply", "screen", "overlay", "darken", "lighten", "color-dodge", "color-burn", "hard-light",
          "soft-light", "difference", "exclusion", "hue", "saturation", "color", "luminosity")
ALIGNS = ("left", "center", "right", "justify")
VALIGNS = ("top", "middle", "bottom")
CASES = ("none", "upper", "lower", "title")
FITS = ("cover", "contain")
FILTERS = ("none", "bw", "sepia")
STROKE_STYLES = ("solid", "dashed", "dotted")
PAINTS = ("none", "solid", "linear", "radial")
AUTOSIZES = ("height", "none")
# A designed page's shape: width over height.
ASPECTS = {"3:4": 0.75, "4:5": 0.8, "2:3": 0.6667, "1:1": 1.0}

_ID = re.compile(r"^[a-z0-9]{1,12}$")
_HEX = re.compile(r"^#[0-9a-f]{6}(?:[0-9a-f]{2})?$")
# Half of a character (an emoji cut by a UTF-16 slice somewhere): never kept.
_HALVES = re.compile(r"[\ud800-\udfff]")


class DesignError(ValueError):
    """The design can't be stored as given; the message is for the owner."""


def num(value: Any, lo: float, hi: float, default: float, places: int = 1) -> float:
    """A number in [lo, hi] rounded half up to `places` decimals, as the client
    rounds (`Math.floor(n * 10 ** places + 0.5) / 10 ** places`), never -0."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return default
    if n != n or n in (math.inf, -math.inf):
        return default
    n = max(lo, min(hi, n))
    scale = 10 ** places
    return math.floor(n * scale + 0.5) / scale + 0.0


def _int(value: Any, lo: int, hi: int, default: int) -> int:
    try:
        n = float(value)
    except (TypeError, ValueError):
        return default
    if n != n or n in (math.inf, -math.inf):
        return default
    return int(max(lo, min(hi, math.floor(n + 0.5))))


def _list(value: Any) -> list:
    """A list as sent, or none (a dict or a number where a list goes)."""
    return value if isinstance(value, list) else []


def _choice(value: Any, choices: tuple[str, ...]) -> str:
    return value if value in choices else choices[0]


def _str(value: Any, limit: int) -> str:
    return _HALVES.sub("", str(value)).strip()[:limit] if isinstance(value, str) else ""


def colour(value: Any, default: str) -> str:
    if value == "accent":
        return "accent"
    if isinstance(value, str) and _HEX.match(value.lower()):
        return value.lower()
    return default


def _asset_id(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    try:
        return str(UUID(str(value)))
    except ValueError as exc:
        raise DesignError("A picture in this design isn't from your library.") from exc


def paint(raw: Any, default: Optional[dict] = None) -> dict:
    """A fill: none, one colour, or a linear or radial gradient of 2–8 stops."""
    base = default or {"kind": "none", "color": "#000000", "angle": 180, "stops": []}
    if not isinstance(raw, dict):
        return dict(base)
    kind = raw.get("kind") if raw.get("kind") in PAINTS else base["kind"]
    out = {"kind": kind, "color": colour(raw.get("color"), base["color"]),
           "angle": _int(raw.get("angle"), 0, 360, 180), "stops": []}
    if kind in ("linear", "radial"):
        stops = [s for s in _list(raw.get("stops")) if isinstance(s, dict)][:MAX_STOPS]
        out["stops"] = sorted(({"color": colour(s.get("color"), "#000000"), "at": _int(s.get("at"), 0, 100, 0)}
                               for s in stops), key=lambda s: s["at"])
        if len(out["stops"]) < 2:
            out["kind"] = "solid"
            out["stops"] = []
    return out


def _stroke(raw: Any) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    return {"color": colour(raw.get("color"), "#000000"), "width": num(raw.get("width"), 0, 10, 0),
            "style": _choice(raw.get("style"), STROKE_STYLES)}


def _radius(raw: Any) -> list[float]:
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        raw = [raw] * 4
    items = list(raw)[:4] if isinstance(raw, list) else []
    items += [0] * (4 - len(items))
    return [num(r, 0, 50, 0) for r in items]


def _shadows(raw: Any) -> list[dict]:
    items = [s for s in (raw if isinstance(raw, list) else []) if isinstance(s, dict)][:MAX_SHADOWS]
    return [{"inner": bool(s.get("inner")), "x": num(s.get("x"), -20, 20, 0), "y": num(s.get("y"), -20, 20, 0.4),
             "blur": num(s.get("blur"), 0, 30, 1.5), "spread": num(s.get("spread"), -10, 10, 0),
             "color": colour(s.get("color"), "#00000066")} for s in items]


def _link(value: Any) -> str:
    """Where a layer takes a reader: a web or mail address, else nowhere."""
    return (_href(value) or "") if isinstance(value, str) and len(value) <= 500 else ""


def _text(raw: dict, out: dict) -> None:
    try:
        doc = normalize_rt(raw.get("rt"), max_chars=MAX_TEXT)
    except RtError:
        doc = None
    face = font_name(raw.get("font"))
    weight = nearest_weight(face, raw.get("weight", 700))
    out.update({
        "rt": doc or empty_rt(),
        "font": face,
        "size": num(raw.get("size"), 0.5, 60, 6),
        "weight": weight,
        "italic": bool(raw.get("italic")) and has_italic(face, weight),
        "color": colour(raw.get("color"), "#ffffff"),
        "align": _choice(raw.get("align"), ALIGNS),
        "valign": _choice(raw.get("valign"), VALIGNS),
        "leading": num(raw.get("leading"), 0.6, 3, 1.15, places=2),
        "tracking": num(raw.get("tracking"), -0.2, 1, 0, places=2),
        "case": _choice(raw.get("case"), CASES),
        "pad": num(raw.get("pad"), 0, 20, 0),
        "autosize": _choice(raw.get("autosize"), AUTOSIZES),
    })


def _image(raw: dict, out: dict) -> bool:
    asset = _asset_id(raw.get("asset_id"))
    if not asset:
        return False
    focal = raw.get("focal") if isinstance(raw.get("focal"), dict) else {}
    out.update({"asset_id": asset, "fit": _choice(raw.get("fit"), FITS),
                "focal": {"x": _int(focal.get("x"), 0, 100, 50), "y": _int(focal.get("y"), 0, 100, 50)},
                "zoom": _int(raw.get("zoom"), 100, 400, 100), "filter": _choice(raw.get("filter"), FILTERS)})
    return True


class _Walk:
    """What normalizing one design has seen: its ids (each once) and its count."""

    def __init__(self) -> None:
        self.ids: set[str] = set()
        self.count = 0

    def id(self, value: Any) -> str:
        lid = value if isinstance(value, str) and _ID.match(value) and value not in self.ids else None
        n = len(self.ids)
        while lid is None or lid in self.ids:
            n += 1
            lid = f"l{n}"
        self.ids.add(lid)
        return lid


def _layer(raw: Any, walk: _Walk, depth: int) -> list[dict]:
    """The layer as stored (a list: a group nested too deep gives up its
    children in its place; a layer that can't be kept gives nothing)."""
    if not isinstance(raw, dict) or raw.get("kind") not in KINDS:
        return []
    kind = raw["kind"]
    if kind == "group" and depth > MAX_DEPTH:
        return [x for child in _list(raw.get("children"))[:MAX_LAYERS] for x in _layer(child, walk, depth)]
    walk.count += 1
    if walk.count > MAX_LAYERS:
        raise DesignError(f"A design holds at most {MAX_LAYERS} layers.")
    out: dict[str, Any] = {
        "id": walk.id(raw.get("id")), "kind": kind, "name": _str(raw.get("name"), 60),
        "x": num(raw.get("x"), -100, 200, 10), "y": num(raw.get("y"), -100, 200, 10),
        "w": num(raw.get("w"), 0.5, 400, 40), "h": num(raw.get("h"), 0.5, 400, 20),
        "rot": num(raw.get("rot"), -180, 180, 0), "flip_x": bool(raw.get("flip_x")), "flip_y": bool(raw.get("flip_y")),
        "opacity": _int(raw.get("opacity"), 0, 100, 100), "blend": _choice(raw.get("blend"), BLENDS),
        "hidden": bool(raw.get("hidden")), "locked": bool(raw.get("locked")),
        "link": _link(raw.get("link")),
    }
    if kind == "group":
        children = [x for child in _list(raw.get("children"))[:MAX_LAYERS] for x in _layer(child, walk, depth + 1)]
        if not children:
            walk.count -= 1
            walk.ids.discard(out["id"])
            return []
        out["children"] = children
        return [out]
    out["fill"] = paint(raw.get("fill"))
    out["stroke"] = _stroke(raw.get("stroke"))
    out["radius"] = _radius(raw.get("radius"))
    out["shadows"] = _shadows(raw.get("shadows"))
    out["blur"] = num(raw.get("blur"), 0, 20, 0)
    if kind == "text":
        _text(raw, out)
    elif kind == "image":
        if not _image(raw, out):
            walk.count -= 1
            walk.ids.discard(out["id"])
            return []
    else:
        out["shape"] = _choice(raw.get("shape"), SHAPES)
    return [out]


def normalize_design(raw: Any, *, page: bool = False) -> Optional[dict]:
    """The design as stored, or None for none. A design on a picture with no
    layers is no design; a designed page always has one (its background)."""
    if not isinstance(raw, dict):
        if not page:
            return None
        raw = {}
    walk = _Walk()
    layers = [x for item in _list(raw.get("layers"))[: MAX_LAYERS * 2] for x in _layer(item, walk, 1)]
    out: dict[str, Any] = {"layers": layers}
    if page:
        out["background"] = paint(raw.get("background"), {"kind": "solid", "color": "#ffffff", "angle": 180, "stops": []})
    elif not layers:
        return None
    if len(json.dumps(out)) > MAX_DESIGN_BYTES:
        raise DesignError("This design has too much on it. Take some layers off.")
    return out


# ── reading a design ─────────────────────────────────────────────────────────

def walk_layers(layers: Iterable[dict]) -> Iterable[dict]:
    """Every layer, children of groups included, bottom to top."""
    for layer in layers:
        yield layer
        if layer.get("kind") == "group":
            yield from walk_layers(layer.get("children") or [])


def design_asset_ids(design: Optional[dict]) -> list[str]:
    return [lay["asset_id"] for lay in walk_layers((design or {}).get("layers") or [])
            if lay.get("kind") == "image" and lay.get("asset_id")]


def _marks(doc: dict) -> set[str]:
    found: set[str] = set()

    def walk(nodes: list) -> None:
        for n in nodes:
            if not isinstance(n, dict):
                continue
            found.update(m.get("type") for m in n.get("marks") or [] if isinstance(m, dict))
            walk(n.get("content") or [])

    walk(doc.get("content") or [])
    return found


def design_fonts(design: Optional[dict], uses: Optional[Uses] = None) -> Uses:
    """The faces and styles a design sets, for the page's font links: each text
    layer's own, and bold and italic where its words are marked so."""
    uses = uses if uses is not None else {}
    for lay in walk_layers((design or {}).get("layers") or []):
        if lay.get("kind") != "text" or lay.get("hidden") or lay.get("font") in ROLES:
            continue
        face, weight, italic = lay["font"], int(lay.get("weight") or 400), bool(lay.get("italic"))
        add_use(uses, face, weight, italic)
        marks = _marks(lay.get("rt") or {})
        if "bold" in marks:
            add_use(uses, face, nearest_weight(face, max(700, weight)), italic)
        if "italic" in marks:
            add_use(uses, face, weight, True)
    return uses


def design_words(design: Optional[dict]) -> list[str]:
    """The words in a design's text layers, as plain text, bottom to top."""
    out = []
    for lay in walk_layers((design or {}).get("layers") or []):
        if lay.get("kind") == "text" and not lay.get("hidden"):
            words = md_to_text(rt_to_md(lay.get("rt"))).strip()
            if words:
                out.append(words)
    return out


# ── words on a photo, from before designs ────────────────────────────────────
# A photo's `overlays` (words centred on a point, in four sizes and two tones,
# with an optional box) become text layers when the story is read, so a story
# made before designs opens with them as layers to move, restyle and type in.

_OVERLAY_SIZE = {"s": 2.6, "m": 3.8, "l": 5.6, "xl": 9.0}
_OVERLAY_WIDTH = {"s": 50, "m": 60, "l": 70, "xl": 86}


def overlays_to_layers(overlays: list[dict]) -> list[dict]:
    layers = []
    for i, o in enumerate(overlays):
        text = (o.get("text") or "").strip()
        if not text:
            continue
        size = o.get("size") or "m"
        w = _OVERLAY_WIDTH.get(size, 60)
        lines = text.count("\n") + 1
        dark = o.get("tone") == "dark"
        box = bool(o.get("box"))
        paragraphs = [{"type": "paragraph", "content": [{"type": "text", "text": line}]} if line.strip()
                      else {"type": "paragraph"} for line in text.split("\n")]
        layers.append({
            "id": f"ov{i + 1}", "kind": "text", "name": text.split("\n")[0][:60],
            "x": max(0, min(100 - w, int(o.get("x", 50)) - w / 2)),
            # Centred on its point: half its lines' height above it (as a
            # share of the width; most photos are wider than tall).
            "y": max(0, int(o.get("y", 50)) - _OVERLAY_SIZE.get(size, 3.8) * 1.15 * lines * 0.75),
            "w": w, "h": 10, "rt": {"type": "doc", "content": paragraphs},
            "font": "heading", "weight": 700, "size": _OVERLAY_SIZE.get(size, 3.8), "leading": 1.15,
            "align": o.get("align") if o.get("align") in ALIGNS else "center",
            "color": "#111111" if dark else "#ffffff",
            "fill": {"kind": "solid", "color": "#ffffffd9" if dark else "#0000008c"} if box else None,
            "pad": 1.2 if box else 0,
            "shadows": [] if box else [{"x": 0, "y": 0.2, "blur": 1.8, "color": "#ffffff80" if dark else "#0000008c"}],
        })
    return layers
