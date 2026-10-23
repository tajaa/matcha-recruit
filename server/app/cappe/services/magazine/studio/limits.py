"""How big a paged story can get, and the defaults its sparse JSON leaves out.

The client keeps the same numbers (`client/src/cappe/studio/model/limits.ts`);
`test_cappe_studio_schema.py` reads that file and holds the two equal.
"""
from __future__ import annotations

MAX_DOC_BYTES = 4_000_000
MAX_PAGES = 256
MAX_ITEMS_PER_PAGE = 400
MAX_ITEMS = 6_000
MAX_THREADS = 200
MAX_THREAD_CHARS = 100_000
MAX_DOC_CHARS = 300_000
MAX_PARAS = 10_000
MAX_RUNS = 1_000
MAX_LINES = 30_000
MAX_GUIDES = 1_000
MAX_NAME = 60
MAX_CAPTION = 500

PAGE_MIN = 72.0  # 1 in
PAGE_MAX = 1728.0  # 24 in
COORD = 20_000.0  # how far off its page an item may sit, in pt
SIZE_MAX = 1296.0  # the largest type, in pt
TRACK_MIN, TRACK_MAX = -500, 2000  # thousandths of an em
INDENT_MAX = 1000.0
LEAD_MAX = 2000.0
GUTTER_MAX = 288.0
STROKE_MAX = 144.0
RADIUS_MAX = 1000.0
ZOOM_MIN, ZOOM_MAX = 100, 1000  # percent
TILE_MIN, TILE_MAX = 2.0, 720.0  # a pattern's tile, in pt
TILE_DEFAULT = 24.0

UNITS = ("pt", "pc", "in", "mm", "cm", "px")
KINDS = ("text", "image", "rect", "ellipse", "line", "graphic")
ALIGNS = ("l", "c", "r", "j", "ja")
ROLES = ("p", "h1", "h2", "h3", "quote", "caption")
VALIGNS = ("top", "center", "bottom", "justify")
FITS = ("fill", "fit", "stretch")
GRAPHIC_FITS = ("contain", "stretch", "tile")  # a graphic in its box: its own shape, any, or repeated
LINE_ALIGNS = (0, 1, 2, 3)  # a composed line: left, center, right, justified

# A run's character attributes and a paragraph's own, when not stored.
CHAR_DEFAULTS = {"font": "Source Serif 4", "wt": 400, "it": False, "size": 10.5, "track": 0,
                 "color": "#1a1a1a", "u": False}
PARA_DEFAULTS = {"align": "l", "li": 0.0, "ri": 0.0, "fi": 0.0, "sb": 0.0, "sa": 0.0, "lead": 0.0, "role": "p"}


def limits() -> dict:
    """Every limit and default above, as the client's mirror holds them."""
    return {
        "MAX_DOC_BYTES": MAX_DOC_BYTES, "MAX_PAGES": MAX_PAGES, "MAX_ITEMS_PER_PAGE": MAX_ITEMS_PER_PAGE,
        "MAX_ITEMS": MAX_ITEMS, "MAX_THREADS": MAX_THREADS, "MAX_THREAD_CHARS": MAX_THREAD_CHARS,
        "MAX_DOC_CHARS": MAX_DOC_CHARS, "MAX_PARAS": MAX_PARAS, "MAX_RUNS": MAX_RUNS, "MAX_LINES": MAX_LINES,
        "MAX_GUIDES": MAX_GUIDES, "MAX_NAME": MAX_NAME, "MAX_CAPTION": MAX_CAPTION, "PAGE_MIN": PAGE_MIN,
        "PAGE_MAX": PAGE_MAX, "COORD": COORD, "SIZE_MAX": SIZE_MAX, "TRACK_MIN": TRACK_MIN, "TRACK_MAX": TRACK_MAX,
        "INDENT_MAX": INDENT_MAX, "LEAD_MAX": LEAD_MAX, "GUTTER_MAX": GUTTER_MAX, "STROKE_MAX": STROKE_MAX,
        "RADIUS_MAX": RADIUS_MAX, "ZOOM_MIN": ZOOM_MIN, "ZOOM_MAX": ZOOM_MAX, "TILE_MIN": TILE_MIN,
        "TILE_MAX": TILE_MAX, "TILE_DEFAULT": TILE_DEFAULT, "UNITS": list(UNITS),
        "KINDS": list(KINDS), "ALIGNS": list(ALIGNS), "ROLES": list(ROLES), "VALIGNS": list(VALIGNS),
        "FITS": list(FITS), "GRAPHIC_FITS": list(GRAPHIC_FITS), "CHAR_DEFAULTS": CHAR_DEFAULTS, "PARA_DEFAULTS": PARA_DEFAULTS,
    }
