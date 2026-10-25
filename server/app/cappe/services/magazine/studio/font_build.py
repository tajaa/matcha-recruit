"""How a face is made ready for the Studio: one weight, the same vertical
metrics in every table any browser might read, so every engine puts a
baseline where the Studio measured it.

Shared by `server/scripts/build_magazine_fonts.py` (the catalog's faces, Latin
subsets) and `custom_fonts.py` (an owner's own uploads, kept whole). The order
of the steps is part of the catalog build's output: change it only together
with a full rebuild of the manifest.
"""
from __future__ import annotations

import re

from fontTools import subset as _subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

# Latin with typographic punctuation: what the catalog's faces keep.
LATIN = sorted({*range(0x20, 0x7F), *range(0xA0, 0x180), *range(0x2010, 0x2028), *range(0x2030, 0x203B),
                0x2044, 0x20AC, 0x2122, 0x2212, 0xFB01, 0xFB02, 0x0131, 0x02C6, 0x02DA, 0x02DC})


def instance(font: TTFont, weight: int | None = None, at: dict | None = None) -> TTFont:
    """A variable font fixed at `weight` and at `at` (other axes, a Gummfit
    cut's: `cuts.py`), every other axis at its default (no weight: the
    default too). A static font is returned as it is."""
    if "fvar" not in font:
        return font
    axes = {a.axisTag: a for a in font["fvar"].axes}
    loc = {tag: a.defaultValue for tag, a in axes.items()}
    for tag, value in {**(at or {}), **({"wght": weight} if weight is not None else {})}.items():
        if tag in axes:
            loc[tag] = max(axes[tag].minValue, min(axes[tag].maxValue, value))
    return instancer.instantiateVariableFont(font, loc, updateFontNames=False)


def normalize_metrics(font: TTFont) -> TTFont:
    """hhea = OS/2 typo = OS/2 win, line gap 0, USE_TYPO_METRICS on."""
    os2, hhea = font["OS/2"], font["hhea"]
    asc, desc = os2.sTypoAscender, os2.sTypoDescender  # desc is negative
    if asc <= 0:  # a face without typo metrics: take its hhea's
        asc, desc = hhea.ascent, hhea.descent
        os2.sTypoAscender, os2.sTypoDescender = asc, desc
    hhea.ascent, hhea.descent, hhea.lineGap = asc, desc, 0
    os2.sTypoLineGap = 0
    os2.usWinAscent, os2.usWinDescent = max(asc, 0), max(-desc, 0)
    if 2 <= os2.version < 4:
        os2.version = 4  # the flag below is read from version 4 on; 2 and 3 have the same fields
    os2.fsSelection |= 1 << 7  # USE_TYPO_METRICS
    return font


WEIGHT_NAMES = {100: "Thin", 200: "ExtraLight", 300: "Light", 400: "Regular", 500: "Medium", 600: "SemiBold",
                700: "Bold", 800: "ExtraBold", 900: "Black"}


def rename(font: TTFont, family: str, weight: int, italic: bool) -> TTFont:
    """A cut named as itself, inside its file: family and style (the four
    classic styles under the family, any other weight as a family of its own,
    typographic names beside them), full, unique and PostScript names.
    Copyright, licence and designer stay as they are (SIL OFL 1.1: a modified
    version keeps its licence and doesn't go by its source's name)."""
    table = font["name"]
    style = " ".join(x for x in (WEIGHT_NAMES.get(weight, str(weight)) if weight != 400 or not italic else "", "Italic" if italic else "") if x)
    ribbi = weight in (400, 700)
    names = {
        1: family if ribbi else f"{family} {WEIGHT_NAMES.get(weight, weight)}",
        2: ("Bold " if weight == 700 else "") + ("Italic" if italic else "Regular") if ribbi else ("Italic" if italic else "Regular"),
        3: f"{family} {style}",
        4: f"{family} {style}",
        6: re.sub(r"[^A-Za-z0-9-]", "", f"{family}-{style}".replace(" ", ""))[:63],
        16: family,
        17: style,
    }
    names[2] = names[2].replace("Bold Regular", "Bold")
    table.names = [r for r in table.names if r.nameID not in (*names, 21, 22, 25)]
    for name_id, value in names.items():
        table.setName(value, name_id, 3, 1, 0x409)
        table.setName(value, name_id, 1, 0, 0)
    return font


def build_face(font: TTFont, weight: int | None, *, subset: bool = True, at: dict | None = None) -> TTFont:
    """One face at `weight` (and a cut's other axes, `at`): instanced, subset
    to Latin (every OpenType layout feature kept, hinting dropped) when
    `subset`, and its metrics made one."""
    font = instance(font, weight, at)
    if subset:
        opts = _subset.Options()
        opts.layout_features = ["*"]
        opts.name_IDs = ["*"]
        opts.name_languages = ["*"]
        opts.notdef_outline = True
        opts.hinting = False
        opts.glyph_names = False
        opts.drop_tables += ["DSIG", "STAT"]
        sub = _subset.Subsetter(opts)
        sub.populate(unicodes=LATIN)
        sub.subset(font)
    return normalize_metrics(font)


def features(font: TTFont) -> list[str]:
    """The face's OpenType layout features (GSUB and GPOS), sorted."""
    tags: set[str] = set()
    for table in ("GSUB", "GPOS"):
        if table in font and font[table].table.FeatureList:
            tags |= {fr.FeatureTag for fr in font[table].table.FeatureList.FeatureRecord}
    return sorted(tags)


def metrics(font: TTFont) -> dict:
    """What the Studio measures with: units per em, ascent and descent (as
    normalized), cap and x heights."""
    os2 = font["OS/2"]
    return {"upm": font["head"].unitsPerEm, "asc": os2.sTypoAscender, "desc": os2.sTypoDescender,
            "cap": getattr(os2, "sCapHeight", 0) or 0, "x": getattr(os2, "sxHeight", 0) or 0}
