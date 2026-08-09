"""Curated palettes — the "generated ideas" colour half of the design system.

Mirrors `client/tellus/public/designer/palettes.json`, which is what the web
picker reads. The data is duplicated here in Python rather than read off disk on
purpose: the backend image ships `server/` only, so a file read out of the
client tree works locally and 500s in production. `tests/tellus/test_flyer_ai.py`
pins the two against each other, so the duplication cannot drift silently.

Analogue of Cappe's `services/style_recipes.py`, with the same authoring rule:
a preset is a complete token set, so any document written in tokens is correct
under every one of them.
"""
from dataclasses import dataclass

from .catalog import PALETTE_TOKENS


@dataclass(frozen=True)
class PalettePreset:
    key: str
    label: str
    blurb: str          # one line, shown to the model in the prompt catalog
    colors: dict[str, str]


PALETTES: tuple[PalettePreset, ...] = (
    PalettePreset(
        key="warm-paper",
        label="Warm paper",
        blurb="the default — warm off-white stock, near-black ink, orange brand accent",
        colors={
            "ink": "#17140f", "paper": "#f3ede0", "brand": "#f97316",
            "brandSoft": "#fb923c", "accent": "#34d399", "muted": "#8a8371",
        },
    ),
    PalettePreset(
        key="midnight",
        label="Midnight",
        blurb="dark stock with pale ink and an ember accent — high contrast, reads at distance",
        colors={
            "ink": "#f4f1ea", "paper": "#111014", "brand": "#f97316",
            "brandSoft": "#fdba74", "accent": "#38bdf8", "muted": "#8b8894",
        },
    ),
    PalettePreset(
        key="fresh-mint",
        label="Fresh mint",
        blurb="cool pale green stock, deep green ink — calm, food-and-drink friendly",
        colors={
            "ink": "#0f2a22", "paper": "#eaf5ef", "brand": "#0f9d6e",
            "brandSoft": "#5ecfa5", "accent": "#f59e0b", "muted": "#6f8b81",
        },
    ),
    PalettePreset(
        key="bold-citrus",
        label="Bold citrus",
        blurb="saturated yellow stock with black ink — loud, built for a noticeboard",
        colors={
            "ink": "#161206", "paper": "#fde047", "brand": "#dc2626",
            "brandSoft": "#f87171", "accent": "#1d4ed8", "muted": "#7c6f2a",
        },
    ),
    PalettePreset(
        key="mono-ink",
        label="Mono ink",
        blurb="pure black on white with grey support — cheapest to photocopy, never misprints",
        colors={
            "ink": "#000000", "paper": "#ffffff", "brand": "#000000",
            "brandSoft": "#4b4b4b", "accent": "#000000", "muted": "#8a8a8a",
        },
    ),
)

PALETTES_BY_KEY: dict[str, PalettePreset] = {p.key: p for p in PALETTES}


def palettes_text() -> str:
    return "\n".join(f"- {p.key}: {p.blurb}" for p in PALETTES)


def palette_for(key: str) -> dict[str, str]:
    preset = PALETTES_BY_KEY.get(key)
    return dict(preset.colors) if preset else dict(PALETTES[0].colors)


assert all(set(p.colors) == set(PALETTE_TOKENS) for p in PALETTES), (
    "every palette must define exactly the token vocabulary"
)
