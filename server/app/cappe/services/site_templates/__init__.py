"""Cappe site templates — the catalog a new site is cloned from.

Code-owned, like `section_presets` / `style_recipes` / `theme_presets`: one
`SiteTemplate` per entry, grouped by Discover category in a module per
category, aggregated here. `tests/cappe/test_site_templates.py` is the drift
gate — every block through the real `add_block` validation, every page through
`render_site_html` gated AND ungated, every category covered.

Why code and not the `cappe_templates` table it replaces: the table was filled
by a hand-run seed script no deploy ever called, so an unseeded environment
showed an empty gallery, nothing validated a template against the block
vocabulary, and prod/dev could silently disagree. A registry ships with the
code that renders it. (`cappe_templates` and `cappe_sites.template_id` are left
in place but unused; dropping them is a separate, approved migration.)

Plan rule: **every template is available on every plan.** Templates are the
free plan's path to a finished site — Merlin's agent loop is the paid one. A
template is authored complete, premium polish included (`theme.premium`,
`theme.type`, `theme.style`, per-block `_design`); `clone_structure` runs the
same `gate_theme`/`gate_content` the editor uses, so a free clone is exactly
what the editor will keep, and a paid clone gets the polish. Nothing is priced
per template.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Optional

from ..design_gate import gate_content, gate_theme
from ..directory import CATEGORY_LABELS
from . import (
    art_design,
    automotive,
    beauty_grooming,
    education,
    events,
    fitness,
    food_drink,
    music_audio,
    other,
    pets,
    photo_video,
    professional,
    retail,
    tech,
    trades_home,
    wellness,
)
from ._model import SiteTemplate
from ._shared import BUSINESS_NAME, substitute_tokens

__all__ = [
    "BUSINESS_NAME",
    "SITE_TEMPLATES",
    "TEMPLATES_BY_SLUG",
    "SiteTemplate",
    "clone_structure",
    "get_template",
    "list_templates",
    "template_summary",
    "template_theme",
]

# Gallery order: by category label, then by name — the API sorts the same way
# the old table did, so the shelf reads as grouped.
_MODULES = (
    art_design, automotive, beauty_grooming, education, events, fitness, food_drink, music_audio,
    other, pets, photo_video, professional, retail, tech, trades_home, wellness,
)

SITE_TEMPLATES: tuple[SiteTemplate, ...] = tuple(
    sorted(
        (t for m in _MODULES for t in m.TEMPLATES),
        key=lambda t: (CATEGORY_LABELS.get(t.category, t.category), t.name),
    )
)
TEMPLATES_BY_SLUG: dict[str, SiteTemplate] = {t.slug: t for t in SITE_TEMPLATES}


def list_templates(category: Optional[str] = None) -> list[SiteTemplate]:
    if category:
        return [t for t in SITE_TEMPLATES if t.category == category]
    return list(SITE_TEMPLATES)


def get_template(slug: Any) -> Optional[SiteTemplate]:
    return TEMPLATES_BY_SLUG.get(slug) if isinstance(slug, str) else None


def template_summary(t: SiteTemplate) -> dict[str, Any]:
    """The gallery card shape (`CappeTemplateSummary`)."""
    return {
        "slug": t.slug,
        "name": t.name,
        "category": t.category,
        "category_label": CATEGORY_LABELS.get(t.category, t.category),
        "tags": list(t.tags),
        "description": t.description,
        "mode": t.mode,
        "heading_font": t.heading_font,
        "swatch": t.swatch,
        "pages": t.nav,
    }


def template_theme(t: SiteTemplate, *, plan: Any) -> dict[str, Any]:
    """The template's theme as it should be stored for `plan`: premium keys
    kept for premium plans, stripped otherwise (the same `gate_theme` the
    editor's save path runs), plus a `template` marker so the dashboard can
    offer "back to the template's original look"."""
    theme = gate_theme(deepcopy(t.theme), plan)
    theme["template"] = t.slug
    return theme


def clone_structure(
    t: SiteTemplate, *, business_name: str, plan: Any,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """`(theme_config, pages)` ready to INSERT for a site named `business_name`
    on `plan`. Deterministic: token substitution, then the plan gate. No model
    call — personalisation beyond the name is the setup concierge's job."""
    values = {"business_name": business_name.strip() or t.sample_name}
    theme = template_theme(t, plan=plan)
    pages: list[dict[str, Any]] = []
    for i, p in enumerate(t.pages):
        content = substitute_tokens(p.get("content") or {}, values)
        pages.append({
            "title": str(p.get("title") or f"Page {i + 1}")[:255],
            "slug": str(p.get("slug") or ""),
            "sort_order": int(p.get("sort_order", i)),
            "content": gate_content(content, plan),
        })
    return theme, pages
