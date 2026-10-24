"""Gummfit cuts: faces of the Studio's own, built from open-licensed variable
fonts fixed somewhere other than their default: a display optical size (the
hairline contrast fashion covers are set in), or a condensed or expanded
width. Each is its own family in the Studio (`fonts_manifest.json`), named
here and inside its file (the build renames it), and released under its
source's licence (SIL OFL 1.1).

They are the Studio's only: the classic story editor sets type from Google
Fonts by name (`magazine/fonts.FONTS`), which doesn't serve these. A page
naming a cut whose faces aren't built is set by name in its source family
from Google Fonts (or, for a source the catalog lacks, its `fallback`).

The client keeps the same list (`client/src/cappe/studio/fonts/cuts.ts`;
`test_cappe_studio_fonts_catalog.py` holds them equal).
"""
from __future__ import annotations

from typing import NamedTuple, Optional


class Cut(NamedTuple):
    category: str
    body: bool
    weights: tuple[int, ...]
    italics: tuple[int, ...]
    source: str  # the google/fonts family it is built from
    axes: dict  # where its other axes are fixed
    fallback: str = ""  # set by name (a catalog family) while its faces aren't built; its source when empty

    @property
    def stand_in(self) -> str:
        return self.fallback or self.source


def _w(lo: int, hi: int) -> tuple[int, ...]:
    return tuple(range(lo, hi + 1, 100))


CUTS: dict[str, Cut] = {
    "Bodoni Moda Display": Cut("serif", False, _w(400, 900), _w(400, 900), "Bodoni Moda", {"opsz": 96}),
    "Fraunces Display": Cut("serif", False, _w(100, 900), _w(100, 900), "Fraunces", {"opsz": 144}),
    "Playfair Poster": Cut("serif", False, _w(300, 900), _w(300, 900), "Playfair", {"opsz": 1200},
                          "Playfair Display"),
    "Playfair Condensed Poster": Cut("serif", False, _w(300, 900), _w(300, 900), "Playfair", {"opsz": 1200, "wdth": 87.5},
                                     "Playfair Display"),
    "Noto Serif Display Condensed": Cut("serif", False, _w(100, 900), _w(100, 900), "Noto Serif Display", {"wdth": 62.5}),
    "Anybody Condensed": Cut("display", False, _w(100, 900), _w(100, 900), "Anybody", {"wdth": 50}),
    "Anybody Expanded": Cut("display", False, _w(100, 900), _w(100, 900), "Anybody", {"wdth": 150}),
    "Archivo Condensed": Cut("sans", False, _w(100, 900), _w(100, 900), "Archivo", {"wdth": 62}),
    "Archivo Expanded": Cut("sans", False, _w(100, 900), _w(100, 900), "Archivo", {"wdth": 125}),
    "League Gothic Condensed": Cut("display", False, (400,), (), "League Gothic", {"wdth": 75}),
    "Bricolage Grotesque Condensed": Cut("display", False, _w(200, 800), (), "Bricolage Grotesque", {"wdth": 75}),
}


def cut(name: object) -> Optional[Cut]:
    return CUTS.get(name) if isinstance(name, str) else None


def nearest_weight(name: str, weight: object) -> int:
    """As `magazine.fonts.nearest_weight`, over a cut's weights."""
    try:
        w = int(weight)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        w = 400
    return min(CUTS[name].weights, key=lambda x: (abs(x - w), -x))


def has_italic(name: str, weight: int) -> bool:
    return weight in CUTS[name].italics
