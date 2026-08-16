"""Flyer-designer vocabulary — the single source both the prompt and the
validators read.

Mirrors `client/tellus/src/utils/designer.ts` and `src/api/types.ts`. Anything
the model is allowed to say about a flyer is spelled out here once, so the
catalog the prompt advertises cannot drift from what `ops.validate_ops` will
actually accept (the same reason `merlin/catalog.py` exists on the Cappe side).
"""
import re
from typing import Any, Optional

# --- colour ----------------------------------------------------------------

# Semantic tokens. Every colour field accepts one of these OR a hex literal;
# a token resolves through the document's own `palette` at render time.
PALETTE_TOKENS: tuple[str, ...] = ("ink", "paper", "brand", "brandSoft", "accent", "muted")

DEFAULT_PALETTE: dict[str, str] = {
    "ink": "#17140f",
    "paper": "#f3ede0",
    "brand": "#f97316",
    "brandSoft": "#fb923c",
    "accent": "#34d399",
    "muted": "#8a8371",
}

HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def is_color(value: Any) -> bool:
    return isinstance(value, str) and (value in PALETTE_TOKENS or bool(HEX_RE.match(value)))


def resolve_color(palette: Optional[dict[str, Any]], value: str) -> str:
    """Token -> hex, hex -> itself. Mirrors utils/designer.ts:resolveColor,
    including the fall-through to DEFAULT_PALETTE for a token the document's own
    palette doesn't define."""
    if not isinstance(value, str) or not value:
        return DEFAULT_PALETTE["ink"]
    if value.startswith("#"):
        return value
    if isinstance(palette, dict):
        got = palette.get(value)
        if isinstance(got, str) and got.startswith("#"):
            return got
    return DEFAULT_PALETTE.get(value, DEFAULT_PALETTE["ink"])


def _channel(component: int) -> float:
    c = component / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast_ratio(fg_hex: str, bg_hex: str) -> float:
    a, b = relative_luminance(fg_hex), relative_luminance(bg_hex)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


# A QR whose modules don't contrast with their quiet zone is a flyer that looks
# finished and scans as nothing. 4.5 is the WCAG AA text floor — well below what
# a printed code wants, and comfortably above the cases that actually fail
# (a token pair that inverts under a dark palette, a brand colour on paper).
MIN_QR_CONTRAST = 4.5


# --- geometry --------------------------------------------------------------

ARTBOARD_PRESETS: dict[str, tuple[int, int]] = {
    "flyer_letter": (1275, 1650),
    "reward_card": (1050, 600),
    "social_square": (1080, 1080),
    "story": (1080, 1920),
}

# --- layers ----------------------------------------------------------------

LAYER_KINDS: frozenset[str] = frozenset({"text", "image", "sticker", "shape", "qr"})

# `image` is absent on purpose: its `src` is a URL, and letting a model author
# one turns a design document into an arbitrary-fetch primitive. The brand's own
# logo is placed by the human picker; the model can still move, resize, reorder
# and delete an image layer that already exists.
ADDABLE_LAYER_KINDS: frozenset[str] = frozenset({"text", "sticker", "shape", "qr"})

# Fonts the MODEL may choose. Deliberately narrower than
# public/designer/fonts/index.json, which also offers Arial Black, Impact and
# Brush Script MT: those three are absent on iOS, and a design can be authored
# on web and exported from the phone. Different metrics mean different line
# breaks in a print export, so the model is pinned to the families that exist
# everywhere. Humans keep the full list on web.
FONT_FAMILIES: frozenset[str] = frozenset({
    "Helvetica Neue",
    "Georgia",
    "Times New Roman",
    "Courier New",
    "Trebuchet MS",
})

# Filenames, matching client/tellus/public/designer/stickers/index.json and the
# iOS asset catalog (basename, extension stripped). Parity is pinned by test.
STICKER_IDS: frozenset[str] = frozenset({
    "star-burst.svg", "star.svg", "sparkle.svg", "ribbon.svg",
    "tag.svg", "coffee-cup.svg", "heart.svg", "arrow-down.svg",
    "sun.svg", "wave.svg", "palm.svg", "ice-cream.svg", "confetti.svg",
    "balloon.svg", "snowflake.svg", "holly.svg", "cocktail.svg", "moon.svg",
})

# Value specs: frozenset = enum, (lo, hi) = numeric range, "color"/"text"/"bool".
COMMON_FIELDS: dict[str, Any] = {
    "x": (-4000, 4000),
    "y": (-4000, 4000),
    "rotation": (-180, 180),
    "opacity": (0.05, 1),
    "locked": "bool",
}

TEXT_FIELDS: dict[str, Any] = {
    "text": "text",
    "fontFamily": FONT_FAMILIES,
    "fontSize": (8, 400),
    "fontStyle": frozenset({"normal", "bold", "italic"}),
    "fill": "color",
    "align": frozenset({"left", "center", "right"}),
    "width": (24, 4000),
    "lineHeight": (0.7, 3.0),
    "letterSpacing": (-20, 80),
}

SHAPE_FIELDS: dict[str, Any] = {
    "shape": frozenset({"rect", "circle", "line"}),
    "width": (4, 4000),
    "height": (2, 4000),
    "fill": "color",
    "stroke": "color",
    "strokeWidth": (0, 64),
    "cornerRadius": (0, 400),
}

STICKER_FIELDS: dict[str, Any] = {
    "assetId": STICKER_IDS,
    "width": (8, 4000),
    "height": (8, 4000),
}

IMAGE_FIELDS: dict[str, Any] = {
    "width": (8, 4000),
    "height": (8, 4000),
}

QR_FIELDS: dict[str, Any] = {
    "size": (96, 2000),
    "fg": "color",
    "bg": "color",
}

FIELDS_BY_KIND: dict[str, dict[str, Any]] = {
    "text": {**COMMON_FIELDS, **TEXT_FIELDS},
    "shape": {**COMMON_FIELDS, **SHAPE_FIELDS},
    "sticker": {**COMMON_FIELDS, **STICKER_FIELDS},
    "image": {**COMMON_FIELDS, **IMAGE_FIELDS},
    "qr": {**COMMON_FIELDS, **QR_FIELDS},
}

MAX_TEXT_LEN = 400

# Same ceiling routes/promo.py enforces on a human PUT. Applied to the MODEL's
# output too — otherwise the assistant is simply the way around the cap the save
# path enforces. Pinned equal to promo's by test.
DESIGN_MAX_BYTES = 256 * 1024

# One turn's worth of edits. Above this the model is redesigning rather than
# editing, and a 60-op turn is unreviewable in the transcript.
MAX_OPS_PER_TURN = 24


def spec_text(spec: Any) -> str:
    """Render one value spec for the prompt catalog."""
    if isinstance(spec, frozenset):
        return "|".join(sorted(spec))
    if isinstance(spec, tuple):
        return f"{spec[0]}-{spec[1]}"
    return str(spec)


def fields_text() -> str:
    lines = []
    for kind in sorted(FIELDS_BY_KIND):
        rendered = [f"{k}({spec_text(v)})" for k, v in sorted(FIELDS_BY_KIND[kind].items())]
        lines.append(f"- {kind}: {', '.join(rendered)}")
    return "\n".join(lines)
