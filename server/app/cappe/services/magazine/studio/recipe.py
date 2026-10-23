"""A picture edit's recipe: what the Studio's Picture Editor did to a library
picture (a look, its sliders, a crop, a cut-out), kept on the edited picture
(`cappe_assets.recipe`, cappemag10) so the editor can open it again.

The recipe never makes pixels on the server: the Studio renders it (WebGL,
`client/src/cappe/studio/picture/`) and uploads the result. The server keeps a
clean copy of it — every key known, every number clamped and rounded, every
default left out — and uses its crop to check the size of what was uploaded.
`client/src/cappe/studio/picture/recipe.ts` normalizes the same way, held
equal by `tests/cappe/fixtures/picture_recipe_cases.json`.
"""
from __future__ import annotations

import math
from typing import Any, Optional

RECIPE_VERSION = 1

# name: (lowest, highest, decimal places); every slider's default is 0.
SLIDERS: dict[str, tuple[float, float, int]] = {
    "exposure": (-4.0, 4.0, 2),  # stops
    "contrast": (-100, 100, 0),
    "highlights": (-100, 100, 0),
    "shadows": (-100, 100, 0),
    "whites": (-100, 100, 0),
    "blacks": (-100, 100, 0),
    "temp": (-100, 100, 0),
    "tint": (-100, 100, 0),
    "vibrance": (-100, 100, 0),
    "saturation": (-100, 100, 0),
    "clarity": (-100, 100, 0),
    "sharpen": (0, 100, 0),
    "vignette": (-100, 100, 0),
    "grain": (0, 100, 0),
    "fade": (0, 100, 0),
    "sh_hue": (0, 360, 0),  # split toning: the shadows' tint and how much
    "sh_amt": (0, 100, 0),
    "hi_hue": (0, 360, 0),  # and the highlights'
    "hi_amt": (0, 100, 0),
}

# The looks the editor offers (picture/looks.ts); a recipe names the one it
# started from, informationally.
LOOKS = ("vivid", "warm", "cool", "golden", "teal", "matte", "film", "chrome", "faded", "noir", "mono", "sepia", "dusk")

TURNS = (0, 90, 180, 270)
ANGLE_MAX = 45.0
CROP_MIN = 0.02  # of the picture's width or height
MAX_POINTS = 32
FEATHER_MAX = 100


def _num(value: Any, lo: float, hi: float, places: int) -> Optional[float]:
    """A number clamped and rounded half up, as the Studio rounds
    (`Math.floor(n * k + 0.5) / k`); a whole number is an int, never -0."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    scale = 10 ** places
    v = math.floor(min(hi, max(lo, float(value))) * scale + 0.5) / scale + 0.0
    return int(v) if v == int(v) else v


def _crop(raw: Any) -> Optional[dict]:
    if not isinstance(raw, dict):
        return None
    x = _num(raw.get("x"), 0, 1, 4) or 0
    y = _num(raw.get("y"), 0, 1, 4) or 0
    w = _num(raw.get("w"), CROP_MIN, 1, 4)
    h = _num(raw.get("h"), CROP_MIN, 1, 4)
    w = 1 if w is None else w
    h = 1 if h is None else h
    # The box stays on the picture: a box that runs off it is moved back on.
    x = min(x, _num(1 - w, 0, 1, 4))
    y = min(y, _num(1 - h, 0, 1, 4))
    angle = _num(raw.get("angle"), -ANGLE_MAX, ANGLE_MAX, 2) or 0
    turn = raw.get("turn") if raw.get("turn") in TURNS else 0
    out = {"x": x, "y": y, "w": w, "h": h, "angle": angle, "turn": turn,
           "flip_h": raw.get("flip_h") is True, "flip_v": raw.get("flip_v") is True}
    whole = (x, y, w, h, angle, turn) == (0, 0, 1, 1, 0, 0) and not out["flip_h"] and not out["flip_v"]
    return None if whole else out


def _cutout(raw: Any) -> Optional[dict]:
    if not isinstance(raw, dict) or not isinstance(raw.get("points"), list):
        return None
    points = []
    for p in raw["points"][:MAX_POINTS]:
        if not isinstance(p, dict):
            continue
        x, y = _num(p.get("x"), 0, 1, 4), _num(p.get("y"), 0, 1, 4)
        if x is None or y is None:
            continue
        points.append({"x": x, "y": y, "keep": p.get("keep") is not False})
    if not any(p["keep"] for p in points):
        return None
    return {"points": points, "feather": _num(raw.get("feather"), 0, FEATHER_MAX, 0) or 0,
            "invert": raw.get("invert") is True}


def normalize_recipe(raw: Any) -> dict:
    """A clean recipe: known keys only, numbers clamped and rounded, defaults
    left out (an empty dict is "as it was")."""
    if not isinstance(raw, dict):
        return {}
    out: dict[str, Any] = {}
    if raw.get("look") in LOOKS:
        out["look"] = raw["look"]
    for name, (lo, hi, places) in SLIDERS.items():
        v = _num(raw.get(name), lo, hi, places)
        if v:
            out[name] = v
    if raw.get("bw") is True:
        out["bw"] = True
    crop = _crop(raw.get("crop"))
    if crop:
        out["crop"] = crop
    cutout = _cutout(raw.get("cutout"))
    if cutout:
        out["cutout"] = cutout
    return out


def cover_scale(w: float, h: float, angle: float) -> float:
    """How much a picture W×H turned by `angle` must grow to still cover its
    own unturned box (straightening never shows past the picture's edge)."""
    a = math.radians(abs(angle))
    c, s = math.cos(a), math.sin(a)
    return max(c + s * h / w, c + s * w / h)


def output_size(width: int, height: int, recipe: dict) -> tuple[int, int]:
    """The size, in pixels, of the edited picture a recipe makes from a
    picture of `width` × `height` (a quarter turn swaps them; the crop takes
    its share of what is left)."""
    crop = recipe.get("crop")
    if not crop:
        return width, height
    w, h = (height, width) if crop["turn"] in (90, 270) else (width, height)
    return max(1, round(crop["w"] * w)), max(1, round(crop["h"] * h))
