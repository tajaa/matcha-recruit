"""The type a magazine can set: Google Fonts, each with the weights and italics
it really has (from Google's own font list), so a page never asks for a
style that doesn't exist and a picker never offers one.

The client mirror is `client/src/cappe/magazine/design/fonts.ts`;
`test_cappe_design_schema.py` keeps the two lists equal.
"""
from __future__ import annotations

from typing import Optional
from urllib.parse import quote

# name: (category, reads well as body text, weights, italic weights)
FONTS: dict[str, tuple[str, bool, tuple[int, ...], tuple[int, ...]]] = {
    "Inter": ("sans", True, (100, 200, 300, 400, 500, 600, 700, 800, 900), (100, 200, 300, 400, 500, 600, 700, 800, 900)),
    "Manrope": ("sans", True, (200, 300, 400, 500, 600, 700, 800), ()),
    "DM Sans": ("sans", True, (100, 200, 300, 400, 500, 600, 700, 800, 900, 1000), (100, 200, 300, 400, 500, 600, 700, 800, 900, 1000)),
    "Work Sans": ("sans", True, (100, 200, 300, 400, 500, 600, 700, 800, 900), (100, 200, 300, 400, 500, 600, 700, 800, 900)),
    "Mulish": ("sans", True, (200, 300, 400, 500, 600, 700, 800, 900, 1000), (200, 300, 400, 500, 600, 700, 800, 900, 1000)),
    "Public Sans": ("sans", True, (100, 200, 300, 400, 500, 600, 700, 800, 900), (100, 200, 300, 400, 500, 600, 700, 800, 900)),
    "Hanken Grotesk": ("sans", True, (100, 200, 300, 400, 500, 600, 700, 800, 900), (100, 200, 300, 400, 500, 600, 700, 800, 900)),
    "Libre Franklin": ("sans", True, (100, 200, 300, 400, 500, 600, 700, 800, 900), (100, 200, 300, 400, 500, 600, 700, 800, 900)),
    "Plus Jakarta Sans": ("sans", True, (200, 300, 400, 500, 600, 700, 800), (200, 300, 400, 500, 600, 700, 800)),
    "Figtree": ("sans", True, (300, 400, 500, 600, 700, 800, 900), (300, 400, 500, 600, 700, 800, 900)),
    "Onest": ("sans", True, (100, 200, 300, 400, 500, 600, 700, 800, 900), ()),
    "Albert Sans": ("sans", True, (100, 200, 300, 400, 500, 600, 700, 800, 900), (100, 200, 300, 400, 500, 600, 700, 800, 900)),
    "Be Vietnam Pro": ("sans", True, (100, 200, 300, 400, 500, 600, 700, 800, 900), (100, 200, 300, 400, 500, 600, 700, 800, 900)),
    "Epilogue": ("sans", True, (100, 200, 300, 400, 500, 600, 700, 800, 900), (100, 200, 300, 400, 500, 600, 700, 800, 900)),
    "Lexend": ("sans", True, (100, 200, 300, 400, 500, 600, 700, 800, 900), ()),
    "Urbanist": ("sans", True, (100, 200, 300, 400, 500, 600, 700, 800, 900), (100, 200, 300, 400, 500, 600, 700, 800, 900)),
    "Instrument Sans": ("sans", True, (400, 500, 600, 700), (400, 500, 600, 700)),
    "Schibsted Grotesk": ("sans", True, (400, 500, 600, 700, 800, 900), (400, 500, 600, 700, 800, 900)),
    "Sora": ("sans", False, (100, 200, 300, 400, 500, 600, 700, 800), ()),
    "Space Grotesk": ("sans", False, (300, 400, 500, 600, 700), ()),
    "Outfit": ("sans", False, (100, 200, 300, 400, 500, 600, 700, 800, 900), ()),
    "Archivo": ("sans", False, (100, 200, 300, 400, 500, 600, 700, 800, 900), (100, 200, 300, 400, 500, 600, 700, 800, 900)),
    "Familjen Grotesk": ("sans", False, (400, 500, 600, 700), (400, 500, 600, 700)),
    "Red Hat Display": ("sans", False, (300, 400, 500, 600, 700, 800, 900), (300, 400, 500, 600, 700, 800, 900)),
    "Lora": ("serif", True, (400, 500, 600, 700), (400, 500, 600, 700)),
    "Spectral": ("serif", True, (200, 300, 400, 500, 600, 700, 800), (200, 300, 400, 500, 600, 700, 800)),
    "Newsreader": ("serif", True, (200, 300, 400, 500, 600, 700, 800), (200, 300, 400, 500, 600, 700, 800)),
    "PT Serif": ("serif", True, (400, 700), (400, 700)),
    "Source Serif 4": ("serif", True, (200, 300, 400, 500, 600, 700, 800, 900), (200, 300, 400, 500, 600, 700, 800, 900)),
    "EB Garamond": ("serif", True, (400, 500, 600, 700, 800), (400, 500, 600, 700, 800)),
    "Crimson Pro": ("serif", True, (200, 300, 400, 500, 600, 700, 800, 900), (200, 300, 400, 500, 600, 700, 800, 900)),
    "Bitter": ("serif", True, (100, 200, 300, 400, 500, 600, 700, 800, 900), (100, 200, 300, 400, 500, 600, 700, 800, 900)),
    "Frank Ruhl Libre": ("serif", True, (300, 400, 500, 600, 700, 800, 900), ()),
    "Fraunces": ("serif", False, (100, 200, 300, 400, 500, 600, 700, 800, 900), (100, 200, 300, 400, 500, 600, 700, 800, 900)),
    "Playfair Display": ("serif", False, (400, 500, 600, 700, 800, 900), (400, 500, 600, 700, 800, 900)),
    "Cormorant Garamond": ("serif", False, (300, 400, 500, 600, 700), (300, 400, 500, 600, 700)),
    "Libre Baskerville": ("serif", False, (400, 500, 600, 700), (400, 500, 600, 700)),
    "DM Serif Display": ("serif", False, (400,), (400,)),
    "Instrument Serif": ("serif", False, (400,), (400,)),
    "Bodoni Moda": ("serif", False, (400, 500, 600, 700, 800, 900), (400, 500, 600, 700, 800, 900)),
    "Marcellus": ("serif", False, (400,), ()),
    "Gloock": ("serif", False, (400,), ()),
    "Syne": ("display", False, (400, 500, 600, 700, 800), ()),
    "Unbounded": ("display", False, (200, 300, 400, 500, 600, 700, 800, 900), ()),
    "Bricolage Grotesque": ("display", False, (200, 300, 400, 500, 600, 700, 800), ()),
    "Anton": ("display", False, (400,), ()),
    "Bebas Neue": ("display", False, (400,), ()),
    "Archivo Black": ("display", False, (400,), ()),
    "Caprasimo": ("display", False, (400,), ()),
    "JetBrains Mono": ("mono", True, (100, 200, 300, 400, 500, 600, 700, 800), (100, 200, 300, 400, 500, 600, 700, 800)),
    "Space Mono": ("mono", False, (400, 700), (400, 700)),
    "IBM Plex Mono": ("mono", True, (100, 200, 300, 400, 500, 600, 700), (100, 200, 300, 400, 500, 600, 700)),
    "DM Mono": ("mono", False, (300, 400, 500), (300, 400, 500)),
    "Caveat": ("handwriting", False, (400, 500, 600, 700), ()),
    "Dancing Script": ("handwriting", False, (400, 500, 600, 700), ()),
    "Pacifico": ("handwriting", False, (400,), ()),
    "Satisfy": ("handwriting", False, (400,), ()),
    "Abril Fatface": ("display", False, (400,), ()),
    "Oswald": ("sans", True, (200, 300, 400, 500, 600, 700), ()),
    "Montserrat": ("sans", True, (100, 200, 300, 400, 500, 600, 700, 800, 900), (100, 200, 300, 400, 500, 600, 700, 800, 900)),
    "Poppins": ("sans", True, (100, 200, 300, 400, 500, 600, 700, 800, 900), (100, 200, 300, 400, 500, 600, 700, 800, 900)),
    "Raleway": ("sans", True, (100, 200, 300, 400, 500, 600, 700, 800, 900), (100, 200, 300, 400, 500, 600, 700, 800, 900)),
    "Roboto": ("sans", True, (100, 200, 300, 400, 500, 600, 700, 800, 900), (100, 200, 300, 400, 500, 600, 700, 800, 900)),
    "Open Sans": ("sans", True, (300, 400, 500, 600, 700, 800), (300, 400, 500, 600, 700, 800)),
    "Lato": ("sans", True, (100, 300, 400, 700, 900), (100, 300, 400, 700, 900)),
    "Source Sans 3": ("sans", True, (200, 300, 400, 500, 600, 700, 800, 900), (200, 300, 400, 500, 600, 700, 800, 900)),
    "Karla": ("sans", True, (200, 300, 400, 500, 600, 700, 800), (200, 300, 400, 500, 600, 700, 800)),
    "Rubik": ("sans", True, (300, 400, 500, 600, 700, 800, 900), (300, 400, 500, 600, 700, 800, 900)),
    "Nunito": ("sans", True, (200, 300, 400, 500, 600, 700, 800, 900, 1000), (200, 300, 400, 500, 600, 700, 800, 900, 1000)),
    "Josefin Sans": ("sans", True, (100, 200, 300, 400, 500, 600, 700), (100, 200, 300, 400, 500, 600, 700)),
    "Archivo Narrow": ("sans", True, (400, 500, 600, 700), (400, 500, 600, 700)),
    "Barlow Condensed": ("sans", True, (100, 200, 300, 400, 500, 600, 700, 800, 900), (100, 200, 300, 400, 500, 600, 700, 800, 900)),
    "Roboto Condensed": ("sans", True, (100, 200, 300, 400, 500, 600, 700, 800, 900), (100, 200, 300, 400, 500, 600, 700, 800, 900)),
    "Tenor Sans": ("sans", False, (400,), ()),
    "Merriweather": ("serif", True, (300, 400, 500, 600, 700, 800, 900), (300, 400, 500, 600, 700, 800, 900)),
    "Libre Bodoni": ("serif", True, (400, 500, 600, 700), (400, 500, 600, 700)),
    "Libre Caslon Text": ("serif", True, (400, 700), (400,)),
    "Libre Caslon Display": ("serif", False, (400,), ()),
    "Old Standard TT": ("serif", True, (400, 700), (400,)),
    "Cinzel": ("serif", False, (400, 500, 600, 700, 800, 900), ()),
    "Prata": ("serif", False, (400,), ()),
    "Yeseva One": ("serif", False, (400,), ()),
    "Italiana": ("serif", False, (400,), ()),
    "Cormorant": ("serif", True, (300, 400, 500, 600, 700), (300, 400, 500, 600, 700)),
    "Noto Serif Display": ("serif", False, (100, 200, 300, 400, 500, 600, 700, 800, 900), (100, 200, 300, 400, 500, 600, 700, 800, 900)),
    "Rozha One": ("serif", False, (400,), ()),
    "Roboto Slab": ("serif", True, (100, 200, 300, 400, 500, 600, 700, 800, 900), ()),
    "Zilla Slab": ("serif", True, (300, 400, 500, 600, 700), (300, 400, 500, 600, 700)),
    "Alfa Slab One": ("display", False, (400,), ()),
    "League Gothic": ("display", False, (400,), ()),
    "Big Shoulders": ("display", False, (100, 200, 300, 400, 500, 600, 700, 800, 900), ()),
    "Six Caps": ("display", False, (400,), ()),
    "Righteous": ("display", False, (400,), ()),
    "Permanent Marker": ("handwriting", False, (400,), ()),
    "Shadows Into Light": ("handwriting", False, (400,), ()),
}

# What a face falls back to while it loads, or if it can't.
_GENERIC = {
    "serif": "Georgia, 'Times New Roman', serif",
    "sans": "system-ui, -apple-system, 'Segoe UI', sans-serif",
    "display": "system-ui, -apple-system, sans-serif",
    "mono": "ui-monospace, Menlo, monospace",
    "handwriting": "cursive",
}

# The magazine's own pair (its masthead style): what a story's type is set in
# until the writer picks a face.
ROLES = {"heading": "var(--mz-h)", "body": "var(--mz-b)"}


def font_name(value: object, default: str = "heading") -> str:
    """A face from the list, or one of the magazine's own pair."""
    return value if isinstance(value, str) and (value in FONTS or value in ROLES) else default


def font_stack(name: str) -> str:
    if name in ROLES:
        return ROLES[name]
    cat = FONTS[name][0] if name in FONTS else "sans"
    return f"'{name}', {_GENERIC[cat]}"


def weights(name: str) -> tuple[int, ...]:
    """The weights a face has (the magazine's own pair: any, as its face allows)."""
    return FONTS[name][2] if name in FONTS else (100, 200, 300, 400, 500, 600, 700, 800, 900)


def nearest_weight(name: str, weight: object) -> int:
    try:
        w = int(weight)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        w = 400
    have = weights(name)
    # Ties go to the heavier: asked for 500 between 400 and 600, set 600.
    return min(have, key=lambda x: (abs(x - w), -x))


def has_italic(name: str, weight: int) -> bool:
    return name in ROLES or weight in (FONTS[name][3] if name in FONTS else ())


Uses = dict[str, set[tuple[int, bool]]]


def add_use(uses: Uses, name: str, weight: int, italic: bool) -> None:
    if name in FONTS:
        uses.setdefault(name, set()).add((weight, italic))


def fonts_links(uses: Uses) -> str:
    """A stylesheet link for each face a page sets, asking for its regular style
    and each weight and italic used that the face has. One link per face: an
    unknown face or style fails the whole request, so one never takes the
    others down with it."""
    links = []
    for name in sorted(uses):
        if name not in FONTS:
            continue
        _cat, _body, have, italics = FONTS[name]
        styles = {(0, 400)}
        for weight, italic in uses[name]:
            if weight in have:
                styles.add((0, weight))
            if italic and weight in italics:
                styles.add((1, weight))
        spec = ";".join(f"{i},{w}" for i, w in sorted(styles))
        links.append(f'<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family={quote(name)}:ital,wght@{spec}&amp;display=swap">')
    return "".join(links)


def merge_uses(*all_uses: Optional[Uses]) -> Uses:
    out: Uses = {}
    for uses in all_uses:
        for name, styles in (uses or {}).items():
            out.setdefault(name, set()).update(styles)
    return out

