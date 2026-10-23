"""Gummfit's own graphics for the Studio's bank (`scripts/build_studio_graphics.py`):
shapes, badges, dividers and patterns, drawn here in one colour (black, so
any colour can be put on them as a mask). Ours, so CC0.

Each is `(slug, name, group, tags, svg, fit)`: `fit` is how it fills its box
on a page: `stretch` (shapes and dividers, any proportions), `contain`
(keeps its own) or `tile` (a pattern, repeated).
"""
from __future__ import annotations

import math

Graphic = tuple[str, str, str, list[str], str, str]


def _svg(body: str, w: float = 100, h: float = 100) -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_n(w)} {_n(h)}">{body}</svg>'


def _n(v: float) -> str:
    r = round(v, 2)
    return str(int(r)) if r == int(r) else str(r)


def _pts(points: list[tuple[float, float]]) -> str:
    return " ".join(f"{_n(x)},{_n(y)}" for x, y in points)


def _poly(points: list[tuple[float, float]], extra: str = "") -> str:
    return f'<polygon points="{_pts(points)}"{extra}/>'


def _regular(n: int, r: float = 48, cx: float = 50, cy: float = 50, turn: float = -90) -> list[tuple[float, float]]:
    return [(cx + r * math.cos(math.radians(turn + 360 * k / n)), cy + r * math.sin(math.radians(turn + 360 * k / n)))
            for k in range(n)]


def _star(n: int, inner: float, r: float = 48, cx: float = 50, cy: float = 50) -> list[tuple[float, float]]:
    out = []
    for k in range(2 * n):
        rr = r if k % 2 == 0 else r * inner
        a = math.radians(-90 + 180 * k / n)
        out.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return out


def _wavy_circle(bumps: int, depth: float, r: float = 44, steps: int = 240) -> str:
    pts = []
    for k in range(steps):
        a = 2 * math.pi * k / steps
        rr = r + depth * math.cos(bumps * a)
        pts.append((50 + rr * math.cos(a), 50 + rr * math.sin(a)))
    return "M" + " L".join(f"{_n(x)} {_n(y)}" for x, y in pts) + "Z"


def _scallops(bumps: int, r: float = 40, bump: float = 9) -> str:
    """A seal: a disc ringed with half-circles."""
    parts = [f'<circle cx="50" cy="50" r="{_n(r)}"/>']
    for k in range(bumps):
        a = 2 * math.pi * k / bumps
        parts.append(f'<circle cx="{_n(50 + r * math.cos(a))}" cy="{_n(50 + r * math.sin(a))}" r="{_n(bump)}"/>')
    return "".join(parts)


def shapes() -> list[Graphic]:
    s: list[Graphic] = []

    def add(slug: str, name: str, tags: list[str], body: str, w: float = 100, h: float = 100, fit: str = "stretch") -> None:
        s.append((slug, name, "shapes", tags, _svg(body, w, h), fit))

    add("triangle", "Triangle", ["triangle", "arrow", "up"], _poly([(50, 4), (96, 92), (4, 92)]))
    add("right-triangle", "Right triangle", ["triangle", "corner"], _poly([(4, 4), (4, 96), (96, 96)]))
    add("diamond", "Diamond", ["diamond", "rhombus"], _poly([(50, 2), (98, 50), (50, 98), (2, 50)]))
    add("pentagon", "Pentagon", ["pentagon", "polygon"], _poly(_regular(5)))
    add("hexagon", "Hexagon", ["hexagon", "polygon", "honeycomb"], _poly(_regular(6, turn=0)))
    add("octagon", "Octagon", ["octagon", "polygon", "stop"], _poly(_regular(8, turn=22.5)))
    add("star", "Star", ["star", "favourite", "rating"], _poly(_star(5, 0.42)))
    add("star-6", "Six-point star", ["star", "sparkle"], _poly(_star(6, 0.55)))
    add("sparkle", "Sparkle", ["sparkle", "star", "shine", "twinkle"],
        '<path d="M50 2 C54 34 66 46 98 50 C66 54 54 66 50 98 C46 66 34 54 2 50 C34 46 46 34 50 2Z"/>')
    add("heart", "Heart", ["heart", "love", "like"],
        '<path d="M50 92 C20 70 2 52 2 31 C2 15 14 4 28 4 C38 4 46 10 50 18 C54 10 62 4 72 4 '
        'C86 4 98 15 98 31 C98 52 80 70 50 92Z"/>')
    add("arrow-right", "Arrow", ["arrow", "right", "next", "direction"],
        _poly([(2, 34), (58, 34), (58, 10), (98, 50), (58, 90), (58, 66), (2, 66)]))
    add("arrow-left", "Arrow left", ["arrow", "left", "back"],
        _poly([(98, 34), (42, 34), (42, 10), (2, 50), (42, 90), (42, 66), (98, 66)]))
    add("arrow-up", "Arrow up", ["arrow", "up"],
        _poly([(34, 98), (34, 42), (10, 42), (50, 2), (90, 42), (66, 42), (66, 98)]))
    add("arrow-down", "Arrow down", ["arrow", "down"],
        _poly([(34, 2), (34, 58), (10, 58), (50, 98), (90, 58), (66, 58), (66, 2)]))
    add("arrow-both", "Double arrow", ["arrow", "both", "left", "right"],
        _poly([(2, 50), (30, 18), (30, 36), (70, 36), (70, 18), (98, 50), (70, 82), (70, 64), (30, 64), (30, 82)]))
    add("chevron", "Chevron", ["chevron", "arrow", "next"], _poly([(10, 2), (58, 2), (98, 50), (58, 98), (10, 98), (50, 50)]))
    add("plus", "Plus", ["plus", "cross", "add"], _poly([(36, 2), (64, 2), (64, 36), (98, 36), (98, 64), (64, 64), (64, 98),
                                                          (36, 98), (36, 64), (2, 64), (2, 36), (36, 36)]))
    add("cross", "Cross", ["x", "cross", "close"],
        '<polygon transform="rotate(45 50 50)" points="40,0 60,0 60,40 100,40 100,60 60,60 60,100 40,100 40,60 0,60 0,40 40,40"/>')
    add("moon", "Crescent moon", ["moon", "night", "crescent"],
        '<path d="M62 4 A46 46 0 1 0 96 70 A38 38 0 1 1 62 4Z"/>')
    add("semicircle", "Semicircle", ["half", "circle", "semicircle"], '<path d="M2 98 A48 48 0 0 1 98 98Z"/>', 100, 100)
    add("quarter-circle", "Quarter circle", ["quarter", "circle", "corner"], '<path d="M2 2 L2 98 L98 98 A96 96 0 0 0 2 2Z"/>')
    add("ring", "Ring", ["ring", "donut", "circle", "outline"],
        '<path fill-rule="evenodd" d="M50 2 A48 48 0 1 1 49.99 2Z M50 22 A28 28 0 1 0 50.01 22Z"/>')
    add("arch", "Arch", ["arch", "window", "door"], '<path d="M2 98 L2 50 A48 48 0 0 1 98 50 L98 98Z"/>')
    add("drop", "Drop", ["drop", "water", "tear"], '<path d="M50 2 C70 32 86 50 86 66 A36 36 0 0 1 14 66 C14 50 30 32 50 2Z"/>')
    add("shield", "Shield", ["shield", "badge", "crest"], '<path d="M50 2 L94 16 C94 58 78 82 50 98 C22 82 6 58 6 16Z"/>')
    add("speech", "Speech bubble", ["speech", "bubble", "quote", "talk", "chat"],
        '<path d="M50 4 C76 4 98 20 98 42 C98 64 76 80 50 80 C44 80 38 79 33 78 L12 96 L18 72 C8 64 2 54 2 42 '
        'C2 20 24 4 50 4Z"/>')
    add("speech-square", "Square speech bubble", ["speech", "bubble", "talk", "chat", "comment"],
        '<path d="M8 4 H92 A6 6 0 0 1 98 10 V68 A6 6 0 0 1 92 74 H40 L18 96 V74 H8 A6 6 0 0 1 2 68 V10 A6 6 0 0 1 8 4Z"/>')
    add("thought", "Thought bubble", ["thought", "bubble", "think", "cloud"],
        '<path d="M30 70 C14 70 4 60 6 48 C2 34 14 22 28 24 C32 10 50 4 62 12 C74 4 92 12 92 28 C100 38 96 56 84 60 '
        'C82 72 66 76 56 70 C48 76 36 76 30 70Z"/><circle cx="20" cy="84" r="7"/><circle cx="8" cy="96" r="4"/>')
    add("cloud", "Cloud", ["cloud", "weather", "sky"],
        '<path d="M24 82 C10 82 2 72 2 60 C2 48 12 40 24 40 C26 24 40 14 54 14 C70 14 82 26 84 40 C94 42 98 52 98 62 '
        'C98 74 88 82 76 82Z"/>', 100, 100)
    add("parallelogram", "Parallelogram", ["parallelogram", "slant"], _poly([(26, 10), (98, 10), (74, 90), (2, 90)]))
    add("trapezoid", "Trapezoid", ["trapezoid"], _poly([(24, 12), (76, 12), (98, 88), (2, 88)]))
    add("bolt", "Lightning bolt", ["lightning", "bolt", "flash", "power"],
        _poly([(58, 2), (14, 58), (44, 58), (34, 98), (86, 38), (54, 38), (66, 2)]), fit="contain")
    add("flower", "Flower", ["flower", "petals", "spring", "daisy"],
        "".join(f'<ellipse cx="50" cy="26" rx="14" ry="24" transform="rotate({k * 45} 50 50)"/>' for k in range(8))
        + '<circle cx="50" cy="50" r="14"/>', fit="contain")
    blobs = [
        "M51 4C70 3 90 15 95 35C100 56 88 79 68 90C48 100 22 96 10 78C-2 60 4 35 18 20C27 10 38 5 51 4Z",
        "M58 3C78 6 97 24 97 46C97 66 84 88 62 95C40 102 16 92 7 72C-2 52 6 28 22 14C32 6 44 1 58 3Z",
        "M44 4C63 0 86 8 94 28C102 47 92 62 86 77C79 93 60 99 42 96C22 92 6 78 3 58C0 37 12 10 44 4Z",
        "M50 6C66 6 76 18 86 28C96 40 100 56 92 70C84 84 66 96 48 94C30 92 12 82 6 64C0 46 8 28 20 18C30 10 38 6 50 6Z",
    ]
    for k, d in enumerate(blobs, 1):
        add(f"blob-{k}", f"Blob {k}", ["blob", "organic", "shape", "abstract"], f'<path d="{d}"/>')
    # The ones people reach for most come first in the side panel.
    first = ["triangle", "star", "heart", "diamond", "hexagon", "speech", "arrow-right", "blob-1"]
    return sorted(s, key=lambda g: first.index(g[0]) if g[0] in first else len(first))


def badges() -> list[Graphic]:
    b: list[Graphic] = []

    def add(slug: str, name: str, tags: list[str], body: str, w: float = 100, h: float = 100) -> None:
        b.append((slug, name, "badges", tags, _svg(body, w, h), "contain"))

    for n, inner in ((12, 0.8), (16, 0.84), (24, 0.88)):
        add(f"burst-{n}", f"Starburst {n}", ["burst", "starburst", "sale", "new", "badge", "seal"], _poly(_star(n, inner)))
    add("seal-scalloped", "Scalloped seal", ["seal", "badge", "award", "rosette"], _scallops(18))
    add("seal-wavy", "Wavy seal", ["seal", "badge", "wavy", "sticker"], f'<path d="{_wavy_circle(14, 3.5)}"/>')
    add("seal-ring", "Ringed seal", ["seal", "badge", "ring", "stamp"],
        '<path fill-rule="evenodd" d="M50 2A48 48 0 1 1 49.99 2Z M50 10A40 40 0 1 0 50.01 10Z"/><circle cx="50" cy="50" r="35"/>')
    add("ribbon", "Ribbon banner", ["ribbon", "banner", "title"],
        '<path d="M0 12 H20 V4 H180 V12 H200 L188 26 L200 40 H160 V32 H40 V40 H0 L12 26Z"/>', 200, 44)
    add("ribbon-flat", "Flat banner", ["banner", "label", "ribbon"],
        '<path d="M0 0 H200 L188 20 L200 40 H0 L12 20Z"/>', 200, 40)
    add("tag", "Tag", ["tag", "label", "price"],
        '<path fill-rule="evenodd" d="M2 20 L22 2 H96 A2 2 0 0 1 98 4 V36 A2 2 0 0 1 96 38 H22Z M20 16A4 4 0 1 0 20.01 16Z"/>',
        100, 40)
    add("rosette", "Rosette", ["rosette", "award", "prize", "medal"],
        f'<path d="{_wavy_circle(16, 3, r=34)}" transform="translate(0 -12)"/>'
        '<polygon points="30,62 18,98 34,90 42,100 50,66"/><polygon points="70,62 82,98 66,90 58,100 50,66"/>')
    add("label-round", "Round label", ["label", "pill", "sticker"],
        '<rect x="2" y="2" width="196" height="56" rx="28"/>', 200, 60)
    add("circle-arrow", "Circled arrow", ["arrow", "circle", "go", "next"],
        '<path fill-rule="evenodd" d="M50 2A48 48 0 1 1 49.99 2Z M30 44 H58 V30 L78 50 L58 70 V56 H30Z"/>')
    return b


def lines() -> list[Graphic]:
    out: list[Graphic] = []

    def add(slug: str, name: str, tags: list[str], body: str, w: float = 200, h: float = 20) -> None:
        out.append((slug, name, "lines", tags, _svg(body, w, h), "stretch"))

    wave = "M0 10 " + " ".join(f"Q{_n(10 + 20 * k)} {2 if k % 2 == 0 else 18} {_n(20 + 20 * k)} 10" for k in range(10))
    add("wave", "Wavy line", ["wave", "wavy", "divider", "squiggle"],
        f'<path d="{wave}" fill="none" stroke="#000" stroke-width="2.5" stroke-linecap="round"/>')
    zig = "M0 16 " + " ".join(f"L{_n(10 + 10 * k)} {4 if k % 2 == 0 else 16}" for k in range(20))
    add("zigzag", "Zigzag", ["zigzag", "divider"], f'<path d="{zig}" fill="none" stroke="#000" stroke-width="2.5" stroke-linejoin="round"/>')
    add("dotted", "Dotted line", ["dots", "dotted", "divider"],
        "".join(f'<circle cx="{_n(5 + 10 * k)}" cy="10" r="2.5"/>' for k in range(20)))
    add("dashed", "Dashed line", ["dashed", "divider"],
        '<line x1="0" y1="10" x2="200" y2="10" stroke="#000" stroke-width="3" stroke-dasharray="12 8"/>')
    add("double", "Double rule", ["double", "rule", "divider"],
        '<rect x="0" y="5" width="200" height="2"/><rect x="0" y="13" width="200" height="2"/>')
    add("thick-thin", "Thick and thin rule", ["rule", "divider", "classic"],
        '<rect x="0" y="3" width="200" height="6"/><rect x="0" y="14" width="200" height="1.5"/>')
    add("ornament", "Ornament", ["ornament", "divider", "diamond", "classic"],
        '<rect x="0" y="9" width="84" height="2"/><rect x="116" y="9" width="84" height="2"/>'
        '<polygon points="100,2 108,10 100,18 92,10"/><circle cx="88" cy="10" r="2"/><circle cx="112" cy="10" r="2"/>')
    add("dots-three", "Three dots", ["dots", "asterism", "divider", "break"],
        '<circle cx="80" cy="10" r="4"/><circle cx="100" cy="10" r="4"/><circle cx="120" cy="10" r="4"/>')
    add("arrow-line", "Arrow line", ["arrow", "line", "pointer"],
        '<rect x="0" y="9" width="186" height="2"/><polygon points="184,2 200,10 184,18"/>')
    add("scribble", "Scribble underline", ["scribble", "underline", "hand drawn", "marker"],
        '<path d="M2 12 C40 4 80 6 120 8 C150 9 176 10 198 6 M10 16 C60 10 120 12 190 12" fill="none" stroke="#000" '
        'stroke-width="3" stroke-linecap="round"/>')
    add("brush", "Brush stroke", ["brush", "stroke", "paint", "highlight"],
        '<path d="M4 6 C50 2 120 3 196 5 C199 9 198 14 194 16 C130 18 60 18 6 15 C1 13 1 8 4 6Z"/>')
    return out


def patterns() -> list[Graphic]:
    out: list[Graphic] = []

    def add(slug: str, name: str, tags: list[str], body: str, w: float = 20, h: float = 20) -> None:
        out.append((slug, name, "patterns", tags, _svg(body, w, h), "tile"))

    add("dots", "Dots", ["dots", "polka", "spots"], '<circle cx="10" cy="10" r="3.5"/>')
    add("dots-small", "Small dots", ["dots", "fine", "texture"], '<circle cx="10" cy="10" r="1.5"/>')
    add("dots-offset", "Offset dots", ["dots", "halftone", "polka"],
        '<circle cx="5" cy="5" r="2.5"/><circle cx="15" cy="15" r="2.5"/>')
    add("grid", "Grid", ["grid", "graph", "lines", "squares"],
        '<path d="M0 0.5 H20 M0.5 0 V20" fill="none" stroke="#000" stroke-width="1"/>')
    add("stripes-diagonal", "Diagonal stripes", ["stripes", "diagonal", "lines"],
        '<path d="M-5 5 L5 -5 M0 20 L20 0 M15 25 L25 15" stroke="#000" stroke-width="4"/>')
    add("stripes", "Stripes", ["stripes", "lines", "horizontal"], '<rect x="0" y="0" width="20" height="8"/>')
    add("stripes-upright", "Upright stripes", ["stripes", "vertical", "pinstripe"], '<rect x="0" y="0" width="6" height="20"/>')
    add("checks", "Checks", ["checks", "checkerboard", "squares", "gingham"],
        '<rect x="0" y="0" width="10" height="10"/><rect x="10" y="10" width="10" height="10"/>')
    add("waves", "Waves", ["waves", "water", "sea"],
        '<path d="M0 10 Q5 4 10 10 T20 10" fill="none" stroke="#000" stroke-width="2"/>')
    add("zigzags", "Zigzags", ["zigzag", "chevron", "herringbone"],
        '<path d="M0 14 L5 6 L10 14 L15 6 L20 14" fill="none" stroke="#000" stroke-width="2"/>')
    add("crosses", "Crosses", ["plus", "crosses", "swiss"],
        '<path d="M8.5 5 H11.5 V8.5 H15 V11.5 H11.5 V15 H8.5 V11.5 H5 V8.5 H8.5Z"/>')
    add("triangles", "Triangles", ["triangles", "geometric"], _poly([(10, 4), (16, 15), (4, 15)]))
    add("rings", "Rings", ["circles", "rings", "bubbles"],
        '<circle cx="10" cy="10" r="6" fill="none" stroke="#000" stroke-width="1.5"/>')
    add("diamonds", "Diamonds", ["diamonds", "argyle", "harlequin"], _poly([(10, 2), (18, 10), (10, 18), (2, 10)]))
    add("scales", "Scales", ["scales", "fish", "scallop"],
        '<path d="M0 10 A10 10 0 0 1 20 10 M-10 20 A10 10 0 0 1 10 20 M10 20 A10 10 0 0 1 30 20" fill="none" '
        'stroke="#000" stroke-width="1.5"/>')
    add("bricks", "Bricks", ["bricks", "wall", "tiles"],
        '<path d="M0 0.5 H20 M0 10.5 H20 M10 0 V10 M0.5 10 V20" fill="none" stroke="#000" stroke-width="1"/>')
    return out


def all_graphics() -> list[Graphic]:
    return [*shapes(), *badges(), *lines(), *patterns()]
