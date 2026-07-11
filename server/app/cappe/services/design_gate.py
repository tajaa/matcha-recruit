"""Server-side premium (Pro/Business) enforcement for Cappe design.

The public renderer (`render.py`) has no account context — it renders whatever
`theme_config`/`content` a site stores. So the premium wall is enforced here, at
the write choke points (`update_site`, `update_page`, `preview_site_page`): for
non-premium plans we strip the premium design keys before they are persisted or
previewed. This is a MONETIZATION gate, not a security fix — the renderer is
injection-safe regardless (every value is enum/clamp/hex/URL-gated).

Design keys that require Pro/Business:
- `theme_config.style`   — the global style system (Phase A: type scale, spacing,
  container, card styling, header/footer).
- `theme_config.type`    — the "Designer" studio typography (heading weight/spacing,
  animated headline).
- `theme_config.premium` — the premium effects layer (mesh/glow/glass/reveal).
- `theme_config.colors.brandGradient` — brand-gradient buttons.
- every block's `_design` bag — the per-section inspector (motion/bg/layout/colors/
  type/border/anchor).

Free/basic controls stay for everyone: presets, brand color, font pairing, corner
radius, light/dark mode.
"""
from copy import deepcopy
from typing import Any

PREMIUM_PLANS = {"pro", "business"}

# Top-level theme_config keys gated to premium plans.
_PREMIUM_THEME_KEYS = ("style", "type", "premium")


def is_premium_plan(plan: Any) -> bool:
    return str(plan or "").lower() in PREMIUM_PLANS


def gate_theme(theme_config: Any, plan: Any) -> Any:
    """Return a copy of `theme_config` with premium-only keys removed for
    non-premium plans. Premium plans (and non-dict input) pass through untouched."""
    if is_premium_plan(plan) or not isinstance(theme_config, dict):
        return theme_config
    cleaned = deepcopy(theme_config)
    for key in _PREMIUM_THEME_KEYS:
        cleaned.pop(key, None)
    colors = cleaned.get("colors")
    if isinstance(colors, dict):
        colors.pop("brandGradient", None)
    return cleaned


def gate_content(content: Any, plan: Any) -> Any:
    """Return a copy of a page's `content` with the premium per-section `_design`
    bag stripped from every block, for non-premium plans."""
    if is_premium_plan(plan) or not isinstance(content, dict):
        return content
    blocks = content.get("blocks")
    if not isinstance(blocks, list):
        return content
    cleaned = deepcopy(content)
    for block in cleaned.get("blocks", []):
        if isinstance(block, dict):
            block.pop("_design", None)
    return cleaned
