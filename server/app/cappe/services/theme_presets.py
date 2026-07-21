"""Server-side mirror of the whole-site theme presets Merlin may recommend and
apply via `set_theme key="preset"`.

The canonical preset data (fonts, palette, radius, hero/nav style) lives
client-side in `client/src/cappe/data/cappeThemes.ts` — it carries client
rendering concerns (`swatch`, the full `config` object `applyThemeOp` writes
into `theme_config`) that have no reason to exist server-side. This module
carries only what the model needs to be theme-aware: `{id, name, blurb,
premium, mode}`. `tests/cappe/test_theme_presets.py` regex-parses the TS file
and asserts `PRESET_IDS` matches — the parity-test pattern already used for
`test_server_catalog_matches_client_block_schemas` in test_merlin_validation.py.

Keep this list and cappeThemes.ts's `CAPPE_THEMES` in sync by hand; the parity
test is what catches drift, not a build step.
"""
from dataclasses import dataclass

_LIGHT = "light"
_DARK = "dark"


@dataclass(frozen=True)
class ThemePreset:
    id: str
    name: str
    blurb: str
    premium: bool
    mode: str


THEME_PRESETS: tuple[ThemePreset, ...] = (
    ThemePreset("clean", "Clean", "Bright, modern, neutral. A safe default that reads well anywhere.", False, _LIGHT),
    ThemePreset("minimal", "Minimal", "Near-black accents, tight corners. Quiet, confident, gallery-like.", False, _LIGHT),
    ThemePreset("noir", "Noir", "Dark mode with an electric lime pop. Great for creators & studios.", False, _DARK),
    ThemePreset("editorial", "Editorial", "Fraunces serif headlines over clean body text. Warm and premium.", True, _LIGHT),
    ThemePreset("studio", "Studio", "Playfair display on deep charcoal with a gold accent. Luxe & moody.", True, _DARK),
    ThemePreset("sunset", "Sunset", "Soft cream canvas, coral brand, generous rounding. Friendly & fresh.", True, _LIGHT),
    ThemePreset("terra", "Terra", "Warm sand canvas, terracotta brand, Garamond headlines. Grounded & editorial.", True, _LIGHT),
    ThemePreset("cobalt", "Cobalt", "Crisp white, deep-blue brand, Space Grotesk. Confident SaaS/tech.", True, _LIGHT),
    ThemePreset("bloom", "Bloom", "Blush canvas, rose brand, airy Cormorant display. Elegant & soft.", True, _LIGHT),
    ThemePreset("press", "Press", "Near-black canvas, amber brand, Anton display. Bold, loud, headline-first.", True, _DARK),
)

PRESET_IDS: frozenset[str] = frozenset(p.id for p in THEME_PRESETS)
PRESETS_BY_ID: dict[str, ThemePreset] = {p.id: p for p in THEME_PRESETS}


def preset_catalog_text() -> str:
    """One line per preset for the set_theme prompt rule: `id — blurb`."""
    return "\n".join(f"- {p.id} — {p.blurb}" for p in THEME_PRESETS)


# A small mirror of cappeThemes.ts's FONT_PAIRINGS heading/body names — NOT
# validated (fonts.heading/fonts.body accept any text; the renderer degrades
# gracefully on an unrecognized Google Font), just a prompt suggestion so the
# model doesn't invent an odd pairing for "change the fonts" requests. Parity
# with the client list is asserted by test_theme_presets.py, same as PRESET_IDS.
FONT_PAIRINGS: tuple[tuple[str, str], ...] = (
    ("Inter", "Inter"),
    ("Fraunces", "Inter"),
    ("Playfair Display", "Inter"),
    ("Sora", "Inter"),
    ("Space Grotesk", "Inter"),
    ("Lora", "Lora"),
    ("Syne", "Manrope"),
    ("Unbounded", "DM Sans"),
    ("Bricolage Grotesque", "Work Sans"),
    ("DM Serif Display", "DM Sans"),
    ("Cormorant Garamond", "Public Sans"),
    ("Bodoni Moda", "Spectral"),
    ("Bebas Neue", "Hanken Grotesk"),
    ("Plus Jakarta Sans", "Plus Jakarta Sans"),
    ("Marcellus", "Libre Franklin"),
    ("Instrument Serif", "Inter"),
    ("EB Garamond", "Public Sans"),
    ("Newsreader", "Inter"),
    ("Gloock", "Work Sans"),
    ("Anton", "Hanken Grotesk"),
    ("Archivo Black", "Libre Franklin"),
)


def font_pairings_text() -> str:
    """One compact line for the prompt: `heading/body, heading/body, …`."""
    return ", ".join(f"{h}/{b}" for h, b in FONT_PAIRINGS)
