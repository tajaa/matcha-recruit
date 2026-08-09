"""Curated layouts — the "generated ideas" structural half of the design system.

Each entry builds a complete `FlyerDesign` from the campaign's own copy, so
"generate ideas" returns real, printable flyers rather than lorem shells. The
analogue of Cappe's `section_presets.py`: a hand-authored starting point the
model can reach for with one op instead of composing a page a layer at a time.

Authoring rules (pinned by tests/tellus/test_flyer_ai.py):
  - Every colour is a TOKEN, never a hex — that is what makes one layout
    correct under all five palettes instead of needing a variant each.
    The QR's own fg/bg are the sole exception: contrast there is a scanning
    requirement, not a taste call (see catalog.MIN_QR_CONTRAST).
  - Only FONT_FAMILIES — the model-safe, cross-platform set.
  - Every layer must sit inside the artboard, since `validate_ops` bounds-checks
    the document these produce exactly as it does the model's own output.
"""
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from .catalog import ARTBOARD_PRESETS

QR_FG = "#17140f"
QR_BG = "#ffffff"


def _id() -> str:
    return str(uuid.uuid4())


def _text(*, text: str, x: int, y: int, w: int, size: int, fill: str,
          style: str = "bold", align: str = "center", family: str = "Helvetica Neue",
          line_height: float = 1.15, tracking: int = 0) -> dict[str, Any]:
    return {
        "id": _id(), "type": "text", "x": x, "y": y, "rotation": 0, "opacity": 1,
        "text": text, "fontFamily": family, "fontSize": size, "fontStyle": style,
        "fill": fill, "align": align, "width": w,
        "lineHeight": line_height, "letterSpacing": tracking,
    }


def _rect(*, x: int, y: int, w: int, h: int, fill: str, radius: int = 0,
          stroke: str | None = None, stroke_width: int = 0) -> dict[str, Any]:
    layer: dict[str, Any] = {
        "id": _id(), "type": "shape", "shape": "rect", "x": x, "y": y,
        "rotation": 0, "opacity": 1, "width": w, "height": h,
        "fill": fill, "cornerRadius": radius,
    }
    if stroke:
        layer["stroke"] = stroke
        layer["strokeWidth"] = stroke_width
    return layer


def _line(*, x: int, y: int, w: int, thickness: int, fill: str) -> dict[str, Any]:
    return {
        "id": _id(), "type": "shape", "shape": "line", "x": x, "y": y,
        "rotation": 0, "opacity": 1, "width": w, "height": thickness, "fill": fill,
    }


def _qr(*, x: int, y: int, size: int) -> dict[str, Any]:
    return {
        "id": _id(), "type": "qr", "x": x, "y": y, "rotation": 0, "opacity": 1,
        "size": size, "fg": QR_FG, "bg": QR_BG,
    }


def _sticker(*, asset: str, x: int, y: int, size: int, rotation: int = 0) -> dict[str, Any]:
    return {
        "id": _id(), "type": "sticker", "assetId": asset, "x": x, "y": y,
        "rotation": rotation, "opacity": 1, "width": size, "height": size,
    }


def _doc(preset: str, background: str, layers: list[dict[str, Any]], palette: dict[str, str]) -> dict[str, Any]:
    w, h = ARTBOARD_PRESETS[preset]
    return {
        "version": 1,
        "artboard": {"preset": preset, "w": w, "h": h},
        "background": {"kind": "color", "color": background},
        "palette": palette,
        "layers": layers,
    }


# --- the layouts -----------------------------------------------------------

def _bold_offer(c: dict[str, Any], palette: dict[str, str]) -> dict[str, Any]:
    w, h = ARTBOARD_PRESETS["flyer_letter"]
    return _doc("flyer_letter", "ink", [
        _rect(x=0, y=0, w=w, h=380, fill="brand"),
        _text(text=c["title"].upper(), x=88, y=470, w=w - 176, size=118, fill="paper", tracking=4),
        _text(text=c["reward_text"], x=138, y=690, w=w - 276, size=60, fill="brandSoft", style="normal"),
        _line(x=(w - 300) // 2, y=830, w=300, thickness=6, fill="paper"),
        _text(text="Scan to claim yours", x=238, y=890, w=w - 476, size=38, fill="muted", style="normal", tracking=2),
        _rect(x=(w - 460) // 2, y=990, w=460, h=460, fill=QR_BG, radius=28),
        _qr(x=(w - 400) // 2, y=1020, size=400),
        _text(text="One card per person. While supplies last.", x=238, y=1510, w=w - 476,
              size=26, fill="muted", style="normal", line_height=1.3),
    ], palette)


def _paper_ticket(c: dict[str, Any], palette: dict[str, str]) -> dict[str, Any]:
    w, h = ARTBOARD_PRESETS["flyer_letter"]
    return _doc("flyer_letter", "paper", [
        _rect(x=70, y=70, w=w - 140, h=h - 140, fill="paper", radius=24, stroke="ink", stroke_width=8),
        _text(text="REWARD TICKET", x=188, y=340, w=w - 376, size=38, fill="muted",
              family="Courier New", tracking=12),
        _text(text=c["title"], x=158, y=440, w=w - 316, size=88, fill="ink", family="Georgia"),
        _text(text=c["reward_text"], x=188, y=640, w=w - 376, size=48, fill="muted",
              style="normal", family="Georgia"),
        _line(x=188, y=790, w=w - 376, thickness=4, fill="ink"),
        _sticker(asset="star-burst.svg", x=940, y=610, size=200, rotation=14),
        _rect(x=(w - 440) // 2, y=870, w=440, h=440, fill=QR_BG, radius=20),
        _qr(x=(w - 380) // 2, y=900, size=380),
        _text(text="Scan with your phone camera", x=238, y=1360, w=w - 476, size=34,
              fill="ink", style="normal", family="Courier New", tracking=2),
        _text(text="Show the card at the counter to redeem", x=238, y=1440, w=w - 476,
              size=26, fill="muted", style="normal", family="Courier New"),
    ], palette)


def _counter_card(c: dict[str, Any], palette: dict[str, str]) -> dict[str, Any]:
    w, h = ARTBOARD_PRESETS["reward_card"]
    return _doc("reward_card", "paper", [
        _rect(x=0, y=0, w=420, h=h, fill="ink"),
        _rect(x=70, y=110, w=380, h=380, fill=QR_BG, radius=18),
        _qr(x=100, y=140, size=320),
        _text(text=c["title"], x=500, y=180, w=500, size=54, fill="ink", align="left"),
        _text(text=c["reward_text"], x=500, y=320, w=500, size=30, fill="muted",
              style="normal", align="left", line_height=1.25),
        _line(x=500, y=470, w=200, thickness=5, fill="brand"),
    ], palette)


def _social_drop(c: dict[str, Any], palette: dict[str, str]) -> dict[str, Any]:
    w, h = ARTBOARD_PRESETS["social_square"]
    return _doc("social_square", "ink", [
        _rect(x=640, y=0, w=440, h=440, fill="brand", radius=220),
        _sticker(asset="sparkle.svg", x=84, y=96, size=150, rotation=-12),
        _text(text=c["title"], x=84, y=300, w=800, size=110, fill="paper", align="left", line_height=1.05),
        _text(text=c["reward_text"], x=84, y=500, w=700, size=44, fill="brandSoft",
              style="normal", align="left", line_height=1.25),
        _rect(x=84, y=660, w=360, h=360, fill=QR_BG, radius=22),
        _qr(x=114, y=690, size=300),
        _text(text="Scan to claim", x=490, y=790, w=500, size=44, fill="paper", align="left"),
    ], palette)


def _minimal_mono(c: dict[str, Any], palette: dict[str, str]) -> dict[str, Any]:
    w, h = ARTBOARD_PRESETS["flyer_letter"]
    return _doc("flyer_letter", "paper", [
        _text(text=c["title"], x=140, y=300, w=w - 280, size=104, fill="ink", line_height=1.08),
        _text(text=c["reward_text"], x=200, y=560, w=w - 400, size=46, fill="muted", style="normal"),
        _rect(x=(w - 520) // 2, y=760, w=520, h=520, fill=QR_BG, radius=0, stroke="ink", stroke_width=4),
        _qr(x=(w - 440) // 2, y=800, size=440),
        _text(text="Point your camera here", x=240, y=1350, w=w - 480, size=32,
              fill="muted", style="normal", tracking=3),
    ], palette)


@dataclass(frozen=True)
class LayoutPreset:
    key: str
    label: str
    blurb: str
    preset: str
    build: Callable[[dict[str, Any], dict[str, str]], dict[str, Any]]


LAYOUTS: tuple[LayoutPreset, ...] = (
    LayoutPreset("bold-offer", "Bold offer", "a full-bleed colour band, one huge headline, big centred QR",
                 "flyer_letter", _bold_offer),
    LayoutPreset("paper-ticket", "Paper ticket", "a bordered ticket with typewriter labels and a serif headline",
                 "flyer_letter", _paper_ticket),
    LayoutPreset("counter-card", "Counter card", "landscape card, QR on a solid block to the left, copy right",
                 "reward_card", _counter_card),
    LayoutPreset("social-drop", "Social drop", "square post: oversized headline, sparkle, QR bottom-left",
                 "social_square", _social_drop),
    LayoutPreset("minimal-mono", "Minimal", "type and a framed QR only — nothing else on the page",
                 "flyer_letter", _minimal_mono),
)

LAYOUTS_BY_KEY: dict[str, LayoutPreset] = {layout.key: layout for layout in LAYOUTS}


def layouts_text() -> str:
    return "\n".join(f"- {layout.key}: {layout.blurb}" for layout in LAYOUTS)
