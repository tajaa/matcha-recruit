"""Curated style recipes — professionally-authored `_design` bags for
RESTYLING existing sections (as opposed to `section_presets.py`, which
authors content+design for a brand-new block).

Every value here is a semantic color TOKEN (`design_registry.DESIGN_COLOR_TOKENS`),
never a literal hex. That's the point of this module: a single recipe bag is
correct on every theme (light, dark, custom brand) because a token resolves
through the THEME'S OWN var()/color-mix relationship at render time — there is
no light/dark variant to author or keep in sync. This is the direct fix for
the 2026-07-21 incidents where Merlin invented literal hexes with no
awareness of the theme it was editing (an invisible dark-on-dark gradient, a
bright wireframe-grid overlay).

Merlin applies one via:

    {"op":"apply_style_recipe","blocks":["<id>",...]|"all","recipe":"<key>"}

which `merlin_ops._v_apply_style_recipe` REWRITES at validation time into a
`set_design_bulk` op (recipe's `design` bag verbatim, deep-copied) — the
client never needs this library; it sees an ordinary, fully-editable
`set_design_bulk`. Same trick as `_v_apply_section_preset` → `add_block`.

Authoring rules (enforced by tests/cappe/test_style_recipes.py — the
drift-gate runs every recipe through the real `_clean_design_bag` and a
render smoke test on BOTH a light and a dark theme):
  - `design` groups/keys/values must satisfy the AI-facing DESIGN_GROUPS specs.
  - Every color value must be a token from DESIGN_COLOR_TOKENS — never a hex.
    A recipe that needs a hex is a sign the look isn't actually theme-portable.
  - No `layout.columns`/`columnsMd`/`columnsSm` — those gate on block type
    (COLUMN_BLOCK_TYPES) and `set_design_bulk` rejects a mixed-type target
    list outright rather than partially applying; recipes are meant to run
    against `"all"` or an arbitrary selection, so column keys don't belong here.
"""
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class StyleRecipe:
    key: str
    label: str
    blurb: str            # one line, shown to the model in the prompt catalog
    design: dict[str, dict[str, Any]] = field(default_factory=dict)


STYLE_RECIPES: tuple[StyleRecipe, ...] = (
    StyleRecipe(
        key="soft-elevate",
        label="Soft elevate",
        blurb="one step of surface elevation with a soft hairline top/bottom border and a gentle fade-up",
        design={
            "bg": {"type": "color", "color": "surface-2"},
            "border": {"top": True, "bottom": True, "color": "line-soft", "width": 1},
            "motion": {"effect": "fade-up", "easing": "gentle"},
        },
    ),
    StyleRecipe(
        key="brand-glow",
        label="Brand glow",
        blurb="a visible brand-tinted gradient wash, roomier padding, a rising heading, glow hover",
        design={
            # brand-soft (18%), not brand-faint (8%) — 8% over a near-black bg
            # read as no gradient at all (2026-07-21 "arguably worse" report).
            "bg": {"type": "gradient", "gradient": {"angle": 135, "stops": ["brand-soft", "transparent"]}},
            "colors": {"accent": "brand"},
            "layout": {"padTop": "lg", "padBottom": "lg"},
            "motion": {"heading": "rise", "hover": "glow", "easing": "gentle"},
        },
    ),
    StyleRecipe(
        key="editorial-air",
        label="Editorial air",
        blurb="generous top/bottom breathing room, narrow centered column, a heading that rises in",
        design={
            "layout": {"padTop": "xl", "padBottom": "xl", "maxWidth": "narrow", "align": "center"},
            "motion": {"heading": "rise", "easing": "gentle"},
        },
    ),
    StyleRecipe(
        key="framed",
        label="Framed",
        blurb="a full hairline frame top and bottom with generous padding — quiet, structured",
        design={
            "border": {"top": True, "bottom": True, "color": "line", "width": 2},
            "layout": {"padTop": "lg", "padBottom": "lg"},
        },
    ),
    StyleRecipe(
        key="subtle-texture",
        label="Subtle texture",
        blurb="a faint dot-grid texture, barely visible — the ONLY sanctioned use of bg.pattern",
        design={
            "bg": {"pattern": "dots", "patternColor": "ink-faint"},
        },
    ),
    StyleRecipe(
        key="punchy",
        label="Punchy",
        blurb="brand-colored heading with a snappy lift-on-hover — energetic, for a CTA-shaped section",
        design={
            "colors": {"heading": "brand"},
            "motion": {"hover": "lift", "easing": "snappy"},
        },
    ),
    StyleRecipe(
        key="spotlight",
        label="Spotlight",
        blurb="the biggest structural swing: a large centered heading, generous framed padding, a subtle "
              "top-down surface wash, and a staggered fade-up — reach for this on \"completely different / "
              "from-scratch redesign\" asks a single-group tweak can't deliver",
        design={
            "type": {"headingSize": 56},
            "layout": {"padTop": "xl", "padBottom": "xl", "align": "center", "maxWidth": "narrow"},
            "bg": {"type": "gradient", "gradient": {"angle": 180, "stops": ["surface-2", "transparent"]}},
            "border": {"top": True, "color": "line-soft", "width": 1},
            "motion": {"effect": "fade-up", "stagger": True, "heading": "rise", "easing": "gentle"},
        },
    ),
)

RECIPES_BY_KEY: dict[str, StyleRecipe] = {r.key: r for r in STYLE_RECIPES}
