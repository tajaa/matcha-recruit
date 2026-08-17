"""Server-side mirror of the whole-site theme presets Merlin may recommend and
apply via `set_theme key="preset"`.

The canonical preset data (fonts, palette, radius, hero/nav style) lives
client-side in `client/src/cappe/data/cappeThemes.ts`. This module carries the
full `config` and `swatch` too, because non-web clients need to render and apply
the same themes without importing the web bundle. `tests/cappe/test_theme_presets.py` regex-parses the TS file
and asserts `PRESET_IDS` matches — the parity-test pattern already used for
`test_server_catalog_matches_client_block_schemas` in test_merlin_validation.py.

Keep this list and cappeThemes.ts's `CAPPE_THEMES` in sync by hand; the parity
test is what catches drift, not a build step.
"""
from dataclasses import dataclass, field
from typing import Any

_LIGHT = "light"
_DARK = "dark"


@dataclass(frozen=True)
class ThemePreset:
    id: str
    name: str
    blurb: str
    premium: bool
    mode: str
    config: dict[str, Any] = field(default_factory=dict)
    swatch: dict[str, str] = field(default_factory=dict)


THEME_PRESETS: tuple[ThemePreset, ...] = (
    ThemePreset("clean", "Clean", "Bright, modern, neutral. A safe default that reads well anywhere.", False, _LIGHT,
                 {"mode": "light", "fonts": {"heading": "Inter", "body": "Inter"}, "radius": "lg", "heroStyle": "centered", "navStyle": "simple"},
                 {"bg": "#ffffff", "surface": "#f6f7f9", "brand": "#10b981", "text": "#16181d"}),
    ThemePreset("minimal", "Minimal", "Near-black accents, tight corners. Quiet, confident, gallery-like.", False, _LIGHT,
                 {"mode": "light", "fonts": {"heading": "Inter", "body": "Inter"}, "radius": "sm", "heroStyle": "minimal", "navStyle": "simple", "colors": {"brand": "#18181b", "brandText": "#ffffff", "accent": "#18181b"}},
                 {"bg": "#ffffff", "surface": "#f4f4f5", "brand": "#18181b", "text": "#18181b"}),
    ThemePreset("noir", "Noir", "Dark mode with an electric lime pop. Great for creators & studios.", False, _DARK,
                 {"mode": "dark", "fonts": {"heading": "Inter", "body": "Inter"}, "radius": "lg", "heroStyle": "centered", "navStyle": "centered"},
                 {"bg": "#0b0b0f", "surface": "#15151d", "brand": "#a3e635", "text": "#f5f6f7"}),
    ThemePreset("editorial", "Editorial", "Fraunces serif headlines over clean body text. Warm and premium.", True, _LIGHT,
                 {"mode": "light", "fonts": {"heading": "Fraunces", "body": "Inter"}, "radius": "md", "heroStyle": "split", "navStyle": "simple", "premium": True, "colors": {"bg": "#fdfbf7", "surface": "#f3eee4", "text": "#1c1a17", "muted": "#6b5f50", "border": "#e6ddcd", "brand": "#b4532a", "brandText": "#ffffff", "accent": "#b4532a"}},
                 {"bg": "#fdfbf7", "surface": "#f3eee4", "brand": "#b4532a", "text": "#1c1a17"}),
    ThemePreset("studio", "Studio", "Playfair display on deep charcoal with a gold accent. Luxe & moody.", True, _DARK,
                 {"mode": "dark", "fonts": {"heading": "Playfair Display", "body": "Inter"}, "radius": "md", "heroStyle": "centered", "navStyle": "centered", "premium": True, "colors": {"bg": "#111014", "surface": "#1c1a22", "text": "#f7f5f0", "muted": "#a89f93", "border": "#2c2933", "brand": "#d4af37", "brandText": "#111014", "accent": "#d4af37"}},
                 {"bg": "#111014", "surface": "#1c1a22", "brand": "#d4af37", "text": "#f7f5f0"}),
    ThemePreset("sunset", "Sunset", "Soft cream canvas, coral brand, generous rounding. Friendly & fresh.", True, _LIGHT,
                 {"mode": "light", "fonts": {"heading": "Sora", "body": "Inter"}, "radius": "2xl", "heroStyle": "centered", "navStyle": "simple", "premium": True, "colors": {"bg": "#fff8f3", "surface": "#ffeee3", "text": "#2a1d18", "muted": "#7a6258", "border": "#f6ddcd", "brand": "#f0603a", "brandText": "#ffffff", "accent": "#f0603a"}},
                 {"bg": "#fff8f3", "surface": "#ffeee3", "brand": "#f0603a", "text": "#2a1d18"}),
    ThemePreset("terra", "Terra", "Warm sand canvas, terracotta brand, Garamond headlines. Grounded & editorial.", True, _LIGHT,
                 {"mode": "light", "fonts": {"heading": "EB Garamond", "body": "Public Sans"}, "radius": "md", "heroStyle": "split", "navStyle": "simple", "premium": True, "type": {"headingScale": 115}, "colors": {"bg": "#faf6f0", "surface": "#f0e8db", "text": "#241f19", "muted": "#6f6353", "border": "#e4d8c6", "brand": "#a86b3c", "brandText": "#ffffff", "accent": "#a86b3c"}},
                 {"bg": "#faf6f0", "surface": "#f0e8db", "brand": "#a86b3c", "text": "#241f19"}),
    ThemePreset("cobalt", "Cobalt", "Crisp white, deep-blue brand, Space Grotesk. Confident SaaS/tech.", True, _LIGHT,
                 {"mode": "light", "fonts": {"heading": "Space Grotesk", "body": "Inter"}, "radius": "md", "heroStyle": "centered", "navStyle": "simple", "premium": True, "type": {"headingScale": 108}, "colors": {"bg": "#ffffff", "surface": "#f2f5fb", "text": "#0f1729", "muted": "#556077", "border": "#e0e6f0", "brand": "#2563eb", "brandText": "#ffffff", "accent": "#2563eb"}},
                 {"bg": "#ffffff", "surface": "#eef2fb", "brand": "#2563eb", "text": "#0f1729"}),
    ThemePreset("bloom", "Bloom", "Blush canvas, rose brand, airy Cormorant display. Elegant & soft.", True, _LIGHT,
                 {"mode": "light", "fonts": {"heading": "Cormorant Garamond", "body": "DM Sans"}, "radius": "2xl", "heroStyle": "centered", "navStyle": "centered", "premium": True, "type": {"headingScale": 122}, "colors": {"bg": "#fef7f6", "surface": "#fbe9ea", "text": "#2b1f22", "muted": "#7d6367", "border": "#f3d9dc", "brand": "#c1466a", "brandText": "#ffffff", "accent": "#c1466a"}},
                 {"bg": "#fef7f6", "surface": "#fbe9ea", "brand": "#c1466a", "text": "#2b1f22"}),
    ThemePreset("press", "Press", "Near-black canvas, amber brand, Anton display. Bold, loud, headline-first.", True, _DARK,
                 {"mode": "dark", "fonts": {"heading": "Anton", "body": "Hanken Grotesk"}, "radius": "none", "heroStyle": "centered", "navStyle": "centered", "premium": True, "type": {"headingScale": 118}, "colors": {"bg": "#0f0f10", "surface": "#1a1a1c", "text": "#f4f4f2", "muted": "#9a9a97", "border": "#2a2a2d", "brand": "#f5c518", "brandText": "#0f0f10", "accent": "#f5c518"}},
                 {"bg": "#0f0f10", "surface": "#1a1a1c", "brand": "#f5c518", "text": "#f4f4f2"}),
)

PRESET_IDS: frozenset[str] = frozenset(p.id for p in THEME_PRESETS)
PRESETS_BY_ID: dict[str, ThemePreset] = {p.id: p for p in THEME_PRESETS}


def preset_catalog_text() -> str:
    """One line per preset for the set_theme prompt rule: `id — blurb`."""
    return "\n".join(f"- {p.id} — {p.blurb}" for p in THEME_PRESETS)


# Native clients need ids and labels; prompts retain the existing heading/body
# tuple shape for compatibility with font_pairings_text().
@dataclass(frozen=True)
class FontPairing:
    id: str
    label: str
    heading: str
    body: str


FONT_PAIRING_LIST: tuple[FontPairing, ...] = (
    FontPairing("inter", "Inter / Inter", "Inter", "Inter"),
    FontPairing("fraunces", "Fraunces / Inter", "Fraunces", "Inter"),
    FontPairing("playfair", "Playfair / Inter", "Playfair Display", "Inter"),
    FontPairing("sora", "Sora / Inter", "Sora", "Inter"),
    FontPairing("space", "Space Grotesk / Inter", "Space Grotesk", "Inter"),
    FontPairing("lora", "Lora / Lora", "Lora", "Lora"),
    FontPairing("syne", "Syne / Manrope", "Syne", "Manrope"),
    FontPairing("unbounded", "Unbounded / DM Sans", "Unbounded", "DM Sans"),
    FontPairing("bricolage", "Bricolage / Work Sans", "Bricolage Grotesque", "Work Sans"),
    FontPairing("dmserif", "DM Serif / DM Sans", "DM Serif Display", "DM Sans"),
    FontPairing("cormorant", "Cormorant / Public Sans", "Cormorant Garamond", "Public Sans"),
    FontPairing("bodoni", "Bodoni Moda / Spectral", "Bodoni Moda", "Spectral"),
    FontPairing("bebas", "Bebas Neue / Hanken Grotesk", "Bebas Neue", "Hanken Grotesk"),
    FontPairing("jakarta", "Plus Jakarta / Plus Jakarta", "Plus Jakarta Sans", "Plus Jakarta Sans"),
    FontPairing("marcellus", "Marcellus / Libre Franklin", "Marcellus", "Libre Franklin"),
    FontPairing("instrument", "Instrument Serif / Inter", "Instrument Serif", "Inter"),
    FontPairing("ebgaramond", "EB Garamond / Public Sans", "EB Garamond", "Public Sans"),
    FontPairing("newsreader", "Newsreader / Inter", "Newsreader", "Inter"),
    FontPairing("gloock", "Gloock / Work Sans", "Gloock", "Work Sans"),
    FontPairing("anton", "Anton / Hanken Grotesk", "Anton", "Hanken Grotesk"),
    FontPairing("archivoblack", "Archivo Black / Libre Franklin", "Archivo Black", "Libre Franklin"),
)

FONT_PAIRINGS: tuple[tuple[str, str], ...] = tuple((p.heading, p.body) for p in FONT_PAIRING_LIST)


def font_pairings_text() -> str:
    """One compact line for the prompt: `heading/body, heading/body, …`."""
    return ", ".join(f"{h}/{b}" for h, b in FONT_PAIRINGS)
