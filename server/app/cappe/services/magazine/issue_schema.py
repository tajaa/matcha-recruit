"""What an issue's cover and contents may hold, and the cover templates.

An issue's `cover` is a design on a 4:5 artboard: a photo (from the library,
with its focus and zoom), the magazine's masthead, the issue line ("No. 3 ·
October 2026"), up to eight cover lines, an optional darkening (scrim) behind
the words, and where the photo credit sits. Positions are percent of the
artboard and type sizes are percent of its width, so the cover looks the same
at every size: a page of the book, a card in the archive, the editor.

Every value is checked and reshaped here before it is stored, the same way
`story_schema.normalize_story` treats a story: unknown keys are dropped, a
choice outside its list falls back to the first, numbers are clamped, and a
picture is a library `asset_id`, never a URL (its credit is printed from the
library row).

The client mirror is `client/src/cappe/magazine/issues/coverVocab.ts`;
`test_cappe_issue_schema.py` keeps the lists equal.
"""
from __future__ import annotations

import copy
import json
import re
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

MAX_LINES = 8
MAX_STORIES = 40
MAX_COVER_BYTES = 20_000

FILTERS = ("none", "bw", "sepia")
SCRIMS = ("none", "top", "bottom", "full")
ALIGNS = ("left", "center", "right")
WEIGHTS = ("bold", "regular", "black")
CASES = ("asis", "upper")
TRACKINGS = ("normal", "tight", "wide")
FONTS = ("heading", "body")
BOXES = ("none", "solid")
CREDIT_CORNERS = ("br", "bl", "tr", "tl")
TONES = ("light", "dark")
CONTENTS_LAYOUTS = ("list", "grid", "feature")

# Type size, percent of the cover's width.
MIN_SIZE, MAX_SIZE = 1.5, 30.0
MIN_WIDTH = 10.0
ZOOM_MIN, ZOOM_MAX = 100, 250

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September",
           "October", "November", "December")


class IssueError(ValueError):
    """The issue can't be stored as given; the message is for the owner."""


def _str(value: Any, limit: int) -> str:
    return str(value).strip()[:limit] if value is not None else ""


def _choice(value: Any, choices: tuple[str, ...]) -> str:
    return value if value in choices else choices[0]


def _num(value: Any, lo: float, hi: float, default: float) -> float:
    """A number in [lo, hi] rounded to one decimal, half up (the client does
    the same, so a value never differs between the two)."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return default
    if n != n:  # NaN
        return default
    n = max(lo, min(hi, n))
    return int(n * 10 + 0.5) / 10


def _int(value: Any, lo: int, hi: int, default: int) -> int:
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


def _colour(value: Any, default: str) -> str:
    if value == "accent":
        return "accent"
    if isinstance(value, str) and _HEX.match(value):
        return value.lower()
    return default


def _asset_id(value: Any) -> Optional[str]:
    if value in (None, ""):
        return None
    try:
        return str(UUID(str(value)))
    except ValueError as exc:
        raise IssueError("The cover picture isn't from your library.") from exc


def _uuid_or_none(value: Any) -> Optional[str]:
    try:
        return str(UUID(str(value))) if value not in (None, "") else None
    except ValueError:
        return None


def _place(raw: dict, *, x: float, y: float, w: float) -> dict:
    """Where an element sits: its box's left and top edge and its width, in
    percent of the artboard; the box never runs off the right edge."""
    width = _num(raw.get("w"), MIN_WIDTH, 100, w)
    return {"x": _num(raw.get("x"), 0, 100 - width, min(x, 100 - width)),
            "y": _num(raw.get("y"), 0, 100, y), "w": width}


def _type(raw: dict, *, size: float, color: str, align: str = "left", weight: str = "bold",
          case: str = "asis", font: str = "heading") -> dict:
    return {
        "size": _num(raw.get("size"), MIN_SIZE, MAX_SIZE, size),
        "color": _colour(raw.get("color"), color),
        "align": raw.get("align") if raw.get("align") in ALIGNS else align,
        "weight": raw.get("weight") if raw.get("weight") in WEIGHTS else weight,
        "case": raw.get("case") if raw.get("case") in CASES else case,
        "italic": bool(raw.get("italic")),
        "tracking": _choice(raw.get("tracking"), TRACKINGS),
        "font": raw.get("font") if raw.get("font") in FONTS else font,
    }


def _masthead(raw: Any) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    return {**_place(raw, x=4, y=3, w=92),
            **_type(raw, size=16, color="#ffffff", align="center", weight="black", case="upper")}


def _issue_line(raw: Any) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    return {**_place(raw, x=4, y=21, w=92),
            **_type(raw, size=2.6, color="#ffffff", align="center", weight="regular", case="upper", font="body"),
            "text": _str(raw.get("text"), 80), "hidden": bool(raw.get("hidden"))}


def _line(raw: Any) -> Optional[dict]:
    if not isinstance(raw, dict):
        return None
    text = _str(raw.get("text"), 140)
    sub = _str(raw.get("sub"), 200)
    if not text and not sub:
        return None
    return {**_place(raw, x=6, y=60, w=60), **_type(raw, size=6, color="#ffffff"),
            "text": text, "sub": sub, "post_id": _uuid_or_none(raw.get("post_id")),
            "box": _choice(raw.get("box"), BOXES), "box_color": _colour(raw.get("box_color"), "#000000")}


def normalize_cover(raw: Any, *, story_ids: Optional[set[str]] = None) -> dict:
    """The cover as stored. `story_ids` (the issue's stories) keeps a cover
    line from linking to a story that isn't in the issue."""
    raw = raw if isinstance(raw, dict) else {}
    photo = raw.get("photo") if isinstance(raw.get("photo"), dict) else {}
    focal = photo.get("focal") if isinstance(photo.get("focal"), dict) else {}
    scrim = raw.get("scrim") if isinstance(raw.get("scrim"), dict) else {}
    credit = raw.get("credit") if isinstance(raw.get("credit"), dict) else {}
    lines = [ln for ln in (_line(item) for item in (raw.get("lines") or [])[: MAX_LINES * 2]) if ln][:MAX_LINES]
    if story_ids is not None:
        for ln in lines:
            if ln["post_id"] and ln["post_id"] not in story_ids:
                ln["post_id"] = None
    cover = {
        "v": 1,
        "template": raw.get("template") if raw.get("template") in TEMPLATES else "classic",
        "background": _colour(raw.get("background"), "#1b1916"),
        "photo": {
            "asset_id": _asset_id(photo.get("asset_id")),
            "focal": {"x": _int(focal.get("x"), 0, 100, 50), "y": _int(focal.get("y"), 0, 100, 50)},
            "zoom": _int(photo.get("zoom"), ZOOM_MIN, ZOOM_MAX, ZOOM_MIN),
            "filter": _choice(photo.get("filter"), FILTERS),
        },
        "scrim": {"kind": _choice(scrim.get("kind"), SCRIMS), "strength": _int(scrim.get("strength"), 0, 90, 45)},
        "masthead": _masthead(raw.get("masthead")),
        "issue_line": _issue_line(raw.get("issue_line")),
        "lines": lines,
        "credit": {"corner": _choice(credit.get("corner"), CREDIT_CORNERS), "tone": _choice(credit.get("tone"), TONES)},
    }
    if len(json.dumps(cover)) > MAX_COVER_BYTES:
        raise IssueError("This cover has too much on it. Shorten some lines.")
    return cover


def cover_asset_ids(cover: dict) -> list[str]:
    asset = ((cover or {}).get("photo") or {}).get("asset_id")
    return [asset] if asset else []


def normalize_contents(raw: Any) -> dict:
    raw = raw if isinstance(raw, dict) else {}

    def flag(key: str, default: bool) -> bool:
        return bool(raw[key]) if key in raw else default

    return {
        "v": 1,
        "layout": _choice(raw.get("layout"), CONTENTS_LAYOUTS),
        "heading": _str(raw.get("heading"), 60) if raw.get("heading") is not None else "In this issue",
        "show_numbers": flag("show_numbers", True),
        "show_pictures": flag("show_pictures", True),
        "show_deks": flag("show_deks", True),
        "show_bylines": flag("show_bylines", False),
        "accent": _colour(raw.get("accent"), "accent"),
    }


def section_name(value: Any) -> Optional[str]:
    return _str(value, 40) or None


def contents_line(value: Any) -> Optional[str]:
    return _str(value, 200) or None


def issue_line_text(cover: dict, number: int, when: Optional[datetime]) -> str:
    """The issue line as printed: the writer's own words, else "No. 3 ·
    October 2026" (the month it came out, or the current one for a draft)."""
    own = ((cover or {}).get("issue_line") or {}).get("text")
    if own:
        return own
    moment = when or datetime.now()
    return f"No. {number} · {_MONTHS[moment.month - 1]} {moment.year}"


# ── templates ────────────────────────────────────────────────────────────────
# Each is a whole cover: choosing one keeps the photo and the words and moves
# them into its places (the client's `applyTemplate`). The line slots are where
# the first lines go; any beyond them keep their own places.

def _t(**over: Any) -> dict:
    base: dict[str, Any] = {
        "photo": {"asset_id": None, "focal": {"x": 50, "y": 50}, "zoom": 100, "filter": "none"},
        "scrim": {"kind": "top", "strength": 45},
        "background": "#1b1916",
        "masthead": {"x": 4, "y": 3, "w": 92, "size": 16, "color": "#ffffff", "align": "center", "weight": "black",
                     "case": "upper", "tracking": "tight"},
        "issue_line": {"x": 4, "y": 20, "w": 92, "size": 2.4, "color": "#ffffff", "align": "center",
                       "weight": "regular", "case": "upper", "tracking": "wide", "font": "body"},
        "lines": [],
        "credit": {"corner": "br", "tone": "light"},
    }
    for key, value in over.items():
        base[key] = {**base[key], **value} if isinstance(value, dict) and isinstance(base.get(key), dict) else value
    return base


def _slot(x: float, y: float, w: float, size: float, **style: Any) -> dict:
    return {"x": x, "y": y, "w": w, "size": size, "color": "#ffffff", "text": "", "sub": "", **style}


_RAW_TEMPLATES: dict[str, tuple[str, dict]] = {
    "classic": ("Classic", _t(lines=[
        _slot(5, 34, 42, 5.6), _slot(5, 54, 40, 4.2), _slot(5, 70, 40, 4.2),
        _slot(55, 82, 40, 3.2, align="right")])),
    "headline": ("Headline", _t(scrim={"kind": "bottom", "strength": 60}, lines=[
        _slot(5, 64, 90, 11, weight="black", case="upper", tracking="tight"),
        _slot(5, 86, 90, 3.4, weight="regular", font="body")])),
    "minimal": ("Minimal", _t(scrim={"kind": "none", "strength": 0},
                              masthead={"x": 5, "y": 4, "w": 60, "size": 9, "align": "left", "tracking": "normal"},
                              issue_line={"x": 5, "y": 13, "w": 60, "align": "left"},
                              lines=[_slot(5, 84, 70, 4.4, weight="regular")])),
    "boxed": ("Boxed", _t(scrim={"kind": "none", "strength": 0}, lines=[
        _slot(5, 40, 50, 4.8, box="solid", box_color="#000000"),
        _slot(5, 58, 46, 3.6, box="solid", box_color="#000000"),
        _slot(45, 78, 50, 3.6, box="solid", box_color="accent", align="right")])),
    "poster": ("Poster", _t(scrim={"kind": "full", "strength": 35},
                            masthead={"x": 4, "y": 72, "w": 92, "size": 21, "align": "center"},
                            issue_line={"x": 4, "y": 93, "w": 92},
                            lines=[_slot(8, 8, 84, 4.6, align="center", case="upper", tracking="wide")])),
}


def _template(raw: dict, key: str) -> dict:
    cover = normalize_cover({**{k: v for k, v in raw.items() if k != "lines"}, "template": key,
                             "lines": [{**ln, "text": ln.get("text") or "Cover line"} for ln in raw["lines"]]})
    for ln in cover["lines"]:
        ln["text"] = ""
    return cover


TEMPLATES: dict[str, str] = {key: label for key, (label, _raw) in _RAW_TEMPLATES.items()}
# Filled after TEMPLATES exists, since normalize_cover reads its keys.
TEMPLATE_COVERS: dict[str, dict] = {}
for _key, (_label, _raw) in _RAW_TEMPLATES.items():
    TEMPLATE_COVERS[_key] = _template(_raw, _key)


# A masthead letter's width, in ems, at its widest (capitals in a heavy
# display face): what `fit_masthead` allows for so the name fits one line.
MASTHEAD_EM = 0.72


def fit_masthead(cover: dict, name: str) -> dict:
    """The masthead set no larger than fits the magazine's name on one line
    across its box: a long name comes down from the template's size. The
    client's `fitMasthead` does the same when a template is chosen."""
    mast = cover.get("masthead") or {}
    chars = max(len((name or "").strip()), 1)
    fits = _num(float(mast.get("w", 92)) / (chars * MASTHEAD_EM), MIN_SIZE, MAX_SIZE, MAX_SIZE)
    mast["size"] = min(float(mast.get("size", MAX_SIZE)), fits)
    return cover


def starter_cover(template: str = "classic", name: str = "") -> dict:
    """A new issue's cover: the template's places, its masthead fitted to the
    magazine's name, and a first cover line to write over."""
    cover = fit_masthead(copy.deepcopy(TEMPLATE_COVERS.get(template) or TEMPLATE_COVERS["classic"]), name)
    cover["lines"] = cover["lines"][:1]
    if cover["lines"]:
        cover["lines"][0]["text"] = "Your cover line"
    return cover
