"""Edited pictures (cappemag10): what the Picture Editor uploads becomes a new
library picture that keeps where its pixels came from.

  * It copies its source's provenance and licence, and the source stays as it
    was. A CC BY / BY-SA picture's credit gains "(adapted)", as its licence
    asks of a changed work; an AI picture stays "AI illustration".
  * `parent_asset_id` is the picture whose pixels were edited, so editing it
    again opens that picture with this recipe.
  * The upload must be that picture edited: its size is what the recipe's
    crop makes of the source, and its detail (edges and texture) falls where
    the source's does once cropped the same way. A look changes colours,
    light and contrast, not where the tower's windows are; plain light and
    dark can't tell one sunset landscape from another. Otherwise any picture
    could borrow an archive picture's credit and licence.
"""
from __future__ import annotations

import io
import json
import math
from typing import Any, Optional
from uuid import UUID

from PIL import Image, ImageOps

from ...cappe_assets import AI_CREDIT, COLUMNS, row
from .recipe import RECIPE_VERSION, cover_scale, output_size

ADAPTED = " (adapted)"
SIZE_SLACK = 2  # px: the browser rounds a crop's edges its own way
# Measured on 44 real edits from Chromium and WebKit (every look, extreme
# sliders, crops, turns, cut-outs) against 1,008 unrelated pictures shaped and
# cut out like them: edits scored 0.67 or more, unrelated pictures 0.25 at most.
MIN_LIKENESS = 0.5
_WORK = 256  # px: both pictures are compared at most this big
_CELLS = 64  # what's kept, on its long side
_KEPT = 250  # a cell's opacity to count as kept, so cells across a cut edge are left out
_REACH = 2  # cells: a cell's detail is it less the kept cells this near it
_FLAT = 1.0  # grey levels of detail: less is nothing visible to compare (or to borrow a credit for)
_MIN_CELLS = 16


def credit_for(source: dict) -> Optional[str]:
    """The credit an edit of `source` prints."""
    if source.get("ai_generated"):
        return AI_CREDIT
    credit = source.get("credit_line")
    if credit and source.get("license") in ("by", "by-sa") and not credit.endswith(ADAPTED):
        return credit + ADAPTED
    return credit


def size_matches(source: dict, width: int, height: int, recipe: dict) -> bool:
    if not source.get("width") or not source.get("height"):
        return True  # an old row without its size: nothing to hold it to
    want_w, want_h = output_size(source["width"], source["height"], recipe)
    return abs(want_w - width) <= SIZE_SLACK and abs(want_h - height) <= SIZE_SLACK


def _reference(source: Image.Image, recipe: dict, size: tuple[int, int]) -> Image.Image:
    """The source turned, flipped, straightened and cropped as the recipe says
    (the Studio's shader, roughly), at `size`."""
    img = ImageOps.exif_transpose(source).convert("L")
    crop = recipe.get("crop")
    if crop:
        img = img.rotate(-crop["turn"], expand=True) if crop["turn"] else img
        if crop["flip_h"]:
            img = ImageOps.mirror(img)
        if crop["flip_v"]:
            img = ImageOps.flip(img)
        w, h = img.size
        if crop["angle"]:
            s = cover_scale(w, h, crop["angle"])
            # A positive angle turns the picture clockwise, as the Studio does.
            img = img.resize((round(w * s), round(h * s))).rotate(-crop["angle"], resample=Image.BILINEAR)
            dx, dy = (img.width - w) / 2, (img.height - h) / 2
            img = img.crop((dx, dy, dx + w, dy + h))
        img = img.crop((crop["x"] * w, crop["y"] * h, (crop["x"] + crop["w"]) * w, (crop["y"] + crop["h"]) * h))
    return img.resize(size, Image.BILINEAR)


def _detail(grey: bytes, kept: list[bool], w: int, h: int) -> list[float]:
    """Each kept cell less the average of the kept cells near it: where the
    picture's edges and texture are. Cut-away cells are left out of the
    average, so a cut edge looks the same in the source and the edit."""
    total = [[0] * (w + 1) for _ in range(h + 1)]
    count = [[0] * (w + 1) for _ in range(h + 1)]
    for y in range(h):
        for x in range(w):
            i = y * w + x
            total[y + 1][x + 1] = total[y][x + 1] + total[y + 1][x] - total[y][x] + (grey[i] if kept[i] else 0)
            count[y + 1][x + 1] = count[y][x + 1] + count[y + 1][x] - count[y][x] + kept[i]
    out = []
    for y in range(h):
        y0, y1 = max(0, y - _REACH), min(h, y + _REACH + 1)
        for x in range(w):
            if not kept[y * w + x]:
                continue
            x0, x1 = max(0, x - _REACH), min(w, x + _REACH + 1)
            t = total[y1][x1] - total[y0][x1] - total[y1][x0] + total[y0][x0]
            c = count[y1][x1] - count[y0][x1] - count[y1][x0] + count[y0][x0]
            out.append(grey[y * w + x] - t / c)
    return out


def _spread(v: list[float]) -> float:
    m = sum(v) / len(v)
    return math.sqrt(sum((x - m) ** 2 for x in v) / len(v))


def _correlation(a: list[float], b: list[float]) -> Optional[float]:
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    if not va or not vb:
        return None
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(va * vb)


def looks_like(source_bytes: bytes, edited_bytes: bytes, recipe: dict) -> bool:
    """Whether the edit is the source edited: their detail compared inside
    what the edit keeps (the bounds of a cut-out, scaled up). An edit with
    nothing visible left (all cut away, a sliver, flat) is taken."""
    edited = ImageOps.exif_transpose(Image.open(io.BytesIO(edited_bytes)))
    w, h = edited.size
    k = min(1.0, _WORK / max(w, h))
    size = (max(1, round(w * k)), max(1, round(h * k)))
    ref = _reference(Image.open(io.BytesIO(source_bytes)), recipe, size)
    # Averaged over what's opaque only, so a cut edge's transparent black
    # doesn't darken the cells beside it.
    small = edited.convert("RGBA").convert("RGBa").resize(size, Image.BOX).convert("RGBA")
    grey, alpha = small.convert("L"), small.getchannel("A")
    box = alpha.point(lambda v: 255 if v >= _KEPT else 0).getbbox()
    if box is None:
        return True
    ref, grey, alpha = ref.crop(box), grey.crop(box), alpha.crop(box)
    s = min(1.0, _CELLS / max(grey.size))
    cells = (max(1, round(grey.width * s)), max(1, round(grey.height * s)))
    ref, grey, alpha = ref.resize(cells, Image.BOX), grey.resize(cells, Image.BOX), alpha.resize(cells, Image.BOX)
    kept = [v >= _KEPT for v in alpha.tobytes()]
    if sum(kept) < _MIN_CELLS:
        return True
    theirs, ours = _detail(ref.tobytes(), kept, *cells), _detail(grey.tobytes(), kept, *cells)
    if _spread(ours) < _FLAT:
        return True
    likeness = _correlation(theirs, ours)
    return likeness is not None and likeness >= MIN_LIKENESS


async def insert_edit(conn, *, account_id: UUID, site_id: UUID, source: dict, recipe: dict, url: str,
                      width: int, height: int, size_bytes: int, mime: str, variants: dict[str, Any]) -> dict:
    """The edited picture's library row: the source's provenance and licence,
    its own file and sizes, the recipe, and the source as its parent."""
    title = source.get("title")
    created = await conn.fetchrow(
        f"""
        INSERT INTO cappe_assets (account_id, site_id, kind, url, source, source_id, source_url, title, creator,
                                  creator_url, license, license_version, license_url, provider_label, credit_line,
                                  alt, caption, width, height, bytes, mime, variants, ai_generated,
                                  rights_attested_at, parent_asset_id, recipe, recipe_version, adapted)
        VALUES ($1, $2, 'edit', $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
                $21::jsonb, $22, $23, $24, $25::jsonb, $26, TRUE)
        RETURNING {COLUMNS}
        """,
        account_id, site_id, url, source.get("source"), source.get("source_id"), source.get("source_url"),
        f"{title} (edited)"[:255] if title else None, source.get("creator"), source.get("creator_url"),
        source.get("license"), source.get("license_version"), source.get("license_url"), source.get("provider_label"),
        credit_for(source), source.get("alt"), source.get("caption"), width, height, size_bytes, mime,
        json.dumps(variants), bool(source.get("ai_generated")), source.get("rights_attested_at"), source["id"],
        json.dumps(recipe), RECIPE_VERSION,
    )
    return row(created)
