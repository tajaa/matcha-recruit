"""The Studio's built-in graphics: icons, stickers, shapes, lines, badges and
patterns a page can hold as a `graphic` item (`schema.py`), drawn by both
renderers from a file addressed by its sha256, the way faces are (`fonts.py`).

`server/scripts/build_studio_graphics.py` builds them from pinned sources
(Lucide icons, ISC; Microsoft Fluent Emoji, flat, MIT; our own shapes,
`graphics_own.py`), cleans every file (`clean_svg`) and writes
`graphics_manifest.json`, committed here. Files are served at
`/api/cappe/public/graphics/<sha>.svg` (`routes/public/graphics.py`) from
`CAPPE_GRAPHICS_DIR` or storage (`cappe/graphics/<sha>.svg`).

Never take an entry out of the manifest: a page that holds it would stop
saving. A one-colour graphic (`mono`) takes any colour, drawn as a mask; a
colourful one is drawn as it is.
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path
from typing import Optional

MANIFEST = Path(__file__).resolve().parent / "graphics_manifest.json"
GRAPHIC_URL = "/api/cappe/public/graphics/{sha}.svg"
STRETCH_URL = "/api/cappe/public/graphics/stretch/{sha}.svg"
GRAPHIC_KEY = "cappe/graphics/{sha}.svg"
GROUPS = ("shapes", "lines", "badges", "icons", "stickers", "patterns")
_SHA = re.compile(r"^[0-9a-f]{64}$")


@lru_cache(maxsize=1)
def manifest() -> dict:
    try:
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    graphics = [g for g in data.get("graphics") or [] if isinstance(g, dict) and _SHA.match(str(g.get("sha", "")))]
    return {"version": data.get("version") or "", "sources": data.get("sources") or [], "graphics": graphics}


@lru_cache(maxsize=1)
def _index() -> dict[str, dict]:
    return {g["sha"]: g for g in manifest()["graphics"]}


def by_sha(sha: object) -> Optional[dict]:
    return _index().get(sha) if isinstance(sha, str) else None


def is_sha(value: object) -> bool:
    """Whether `value` could name a graphic's file (a sha256, lower-case hex)."""
    return isinstance(value, str) and bool(_SHA.match(value))


def url(sha: str, stretch: bool = False) -> str:
    return (STRETCH_URL if stretch else GRAPHIC_URL).format(sha=sha)


# ── cleaning ─────────────────────────────────────────────────────────────────

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
ET.register_namespace("", SVG_NS)
ET.register_namespace("xlink", XLINK_NS)

_TAGS = {
    "svg", "g", "path", "circle", "ellipse", "rect", "line", "polyline", "polygon", "defs", "use",
    "linearGradient", "radialGradient", "stop", "clipPath", "mask", "pattern", "filter", "feColorMatrix",
    "feBlend", "feFlood", "feOffset", "feGaussianBlur", "feComposite", "feMerge", "feMergeNode",
}
_ATTRS = {
    "viewBox", "width", "height", "x", "y", "x1", "x2", "y1", "y2", "cx", "cy", "r", "rx", "ry", "fx", "fy", "d",
    "points", "transform", "id", "fill", "fill-rule", "fill-opacity", "clip-rule", "clip-path", "mask", "filter",
    "opacity", "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin", "stroke-miterlimit",
    "stroke-dasharray", "stroke-dashoffset", "stroke-opacity", "offset", "stop-color", "stop-opacity",
    "gradientUnits", "gradientTransform", "spreadMethod", "patternUnits", "patternContentUnits",
    "patternTransform", "maskUnits", "maskContentUnits", "clipPathUnits", "filterUnits", "primitiveUnits",
    "color-interpolation-filters", "in", "in2", "mode", "type", "values", "result", "dx", "dy", "stdDeviation",
    "flood-color", "flood-opacity", "operator", "k1", "k2", "k3", "k4", "href", "preserveAspectRatio",
}
_URL = re.compile(r"url\(\s*([^)]*?)\s*\)", re.I)
MAX_SVG_BYTES = 200_000


class SvgError(ValueError):
    """Not an SVG the Studio will serve."""


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _safe_value(value: str) -> bool:
    """Only references inside the file itself: `url(#id)`, never another file."""
    low = value.lower()
    if "javascript:" in low or "data:" in low or "expression(" in low:
        return False
    return all(m.group(1).strip("'\"").startswith("#") for m in _URL.finditer(value))


def clean_svg(data: bytes) -> tuple[bytes, float, float]:
    """An SVG kept to drawing alone: no scripts, styles, events, foreign
    content, other files or entities; no width or height, so it fills
    whatever box shows it. Returns it with its viewBox's width and height.
    Raises `SvgError` for anything that isn't one."""
    if len(data) > MAX_SVG_BYTES:
        raise SvgError("too big")
    if re.search(rb"<!(doctype|entity)", data, re.I):
        raise SvgError("declarations aren't allowed")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise SvgError("not XML") from exc
    if root.tag != f"{{{SVG_NS}}}svg":
        raise SvgError("not an SVG")

    def clean(el: ET.Element) -> None:
        for child in list(el):
            if not isinstance(child.tag, str) or not child.tag.startswith(f"{{{SVG_NS}}}") \
                    or _local(child.tag) not in _TAGS:
                el.remove(child)
                continue
            clean(child)
        for key in list(el.attrib):
            name = _local(key)
            value = el.attrib[key]
            if key.startswith("{") and not key.startswith(f"{{{XLINK_NS}}}"):
                del el.attrib[key]
            elif name not in _ATTRS or not _safe_value(value) or (name == "href" and not value.startswith("#")):
                del el.attrib[key]
        el.text = (el.text or "").strip() or None
        el.tail = None

    clean(root)
    box = (root.get("viewBox") or "").replace(",", " ").split()
    if len(box) != 4:
        w, h = root.get("width"), root.get("height")
        try:
            box = ["0", "0", str(float(str(w).rstrip("px"))), str(float(str(h).rstrip("px")))]
        except (TypeError, ValueError) as exc:
            raise SvgError("no viewBox") from exc
        root.set("viewBox", " ".join(box))
    try:
        vw, vh = float(box[2]), float(box[3])
    except ValueError as exc:
        raise SvgError("bad viewBox") from exc
    if vw <= 0 or vh <= 0:
        raise SvgError("empty viewBox")
    for key in ("width", "height"):
        root.attrib.pop(key, None)
    return ET.tostring(root, encoding="unicode", short_empty_elements=True).encode(), vw, vh


_ROOT = re.compile(rb"<svg\b[^>]*>")
_ASPECT = re.compile(rb"""\s+preserveAspectRatio=("[^"]*"|'[^']*')""")


def stretched(svg: bytes) -> bytes:
    """A cleaned file drawn out of its own shape to fill its box (the
    "stretch" fit). However CSS sizes it, a viewBox keeps its proportions,
    centred in the box, unless its root says otherwise."""
    m = _ROOT.search(svg)
    if m is None:
        return svg
    tag = _ASPECT.sub(b"", m.group(0))
    return svg[:m.start()] + tag[:4] + b' preserveAspectRatio="none"' + tag[4:] + svg[m.end():]


# ── browsing ─────────────────────────────────────────────────────────────────

_CARD = ("sha", "name", "group", "mono", "fit", "w", "h")
BROWSE_PER_GROUP = 24
SEARCH_MAX = 120


def card(g: dict) -> dict:
    """What the side panel needs of a graphic to show and place it."""
    out = {k: g[k] for k in _CARD}
    if g.get("set"):
        out["set"] = g["set"]
    return out


@lru_cache(maxsize=1)
def _words() -> list[tuple[dict, str, tuple[str, ...]]]:
    return [(g, g["name"].lower(), tuple(g.get("tags") or ())) for g in manifest()["graphics"]]


def _score(words: list[str], name: str, tags: tuple[str, ...]) -> int:
    """How well every word matches a graphic's name or tags (0: not all do)."""
    total = 0
    name_words = name.split()
    for w in words:
        if name == w:
            total += 6
        elif w in name_words:
            total += 4
        elif name.startswith(w) or any(n.startswith(w) for n in name_words):
            total += 3
        elif w in tags:
            total += 2
        elif any(t.startswith(w) for t in tags):
            total += 1
        else:
            return 0
    return total


def search(q: str = "", group: Optional[str] = None, set_: Optional[str] = None,
           offset: int = 0, limit: int = 60) -> dict:
    """Graphics matching every word of `q` (all of them with none), best first,
    in `group` and the sticker `set` when given."""
    words = q.lower().split()[:6]
    hits: list[tuple[int, int, dict]] = []
    for k, (g, name, tags) in enumerate(_words()):
        if (group and g["group"] != group) or (set_ and g.get("set") != set_):
            continue
        score = _score(words, name, tags) if words else 1
        if score:
            hits.append((-score, k, g))
    hits.sort(key=lambda h: (h[0], h[1]))
    limit = max(1, min(limit, SEARCH_MAX))
    return {"total": len(hits), "items": [card(g) for _, _, g in hits[offset:offset + limit]]}


@lru_cache(maxsize=1)
def browse() -> dict:
    """Each group's first graphics and how many it has, and the sticker sets."""
    groups = []
    for group in GROUPS:
        found = search(group=group, limit=BROWSE_PER_GROUP)
        groups.append({"group": group, "count": found["total"], "items": found["items"]})
    sets: dict[str, int] = {}
    for g in manifest()["graphics"]:
        if g.get("set"):
            sets[g["set"]] = sets.get(g["set"], 0) + 1
    return {"version": manifest()["version"], "groups": groups,
            "sets": [{"set": s, "count": n} for s, n in sets.items()],
            "sources": manifest()["sources"]}
