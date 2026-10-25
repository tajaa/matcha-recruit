"""How a face is made ready for the Studio: one weight, the same vertical
metrics in every table any browser might read, so every engine puts a
baseline where the Studio measured it.

Shared by `server/scripts/build_magazine_fonts.py` (the catalog's faces, Latin
subsets) and `custom_fonts.py` (an owner's own uploads, kept whole). The order
of the steps is part of the catalog build's output: change it only together
with a full rebuild of the manifest.
"""
from __future__ import annotations

from fontTools import subset as _subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

# Latin with typographic punctuation: what the catalog's faces keep.
LATIN = sorted({*range(0x20, 0x7F), *range(0xA0, 0x180), *range(0x2010, 0x2028), *range(0x2030, 0x203B),
                0x2044, 0x20AC, 0x2122, 0x2212, 0xFB01, 0xFB02, 0x0131, 0x02C6, 0x02DA, 0x02DC})


def instance(font: TTFont, weight: int | None = None) -> TTFont:
    """A variable font fixed at `weight` (every other axis at its default; no
    weight: the default too). A static font is returned as it is."""
    if "fvar" not in font:
        return font
    axes = {a.axisTag: a for a in font["fvar"].axes}
    loc = {tag: a.defaultValue for tag, a in axes.items()}
    if "wght" in axes and weight is not None:
        loc["wght"] = max(axes["wght"].minValue, min(axes["wght"].maxValue, weight))
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


def build_face(font: TTFont, weight: int | None, *, subset: bool = True) -> TTFont:
    """One face at `weight`: instanced, subset to Latin (every OpenType layout
    feature kept, hinting dropped) when `subset`, and its metrics made one."""
    font = instance(font, weight)
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
