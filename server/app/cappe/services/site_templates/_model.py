"""The `SiteTemplate` record every template module builds.

Kept apart from `__init__.py` so category modules can import it without a
circular import through the registry that aggregates them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SiteTemplate:
    slug: str
    name: str
    # One of `services.directory.CATEGORY_SLUGS` — the same taxonomy Discover
    # browses by, so one onboarding answer drives both the template shelf and
    # the directory listing.
    category: str
    description: str
    # Free-form facets the gallery can filter on (booking / store / menu /
    # portfolio / blog / services …). Not a taxonomy; add freely.
    tags: tuple[str, ...]
    # Brand text shown in the gallery preview's header, standing in for
    # `{{business_name}}` until a real business clones the template.
    sample_name: str
    # Complete `theme_config`, premium keys included. `gate_theme` strips the
    # premium layer for free plans, so the base palette/fonts/radius/hero/nav
    # must already read as finished.
    theme: dict[str, Any]
    # `page()`-shaped dicts in nav order; the first must be `home`.
    pages: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    @property
    def mode(self) -> str:
        return str(self.theme.get("mode") or "light")

    @property
    def heading_font(self) -> str:
        fonts = self.theme.get("fonts") if isinstance(self.theme.get("fonts"), dict) else {}
        return str(fonts.get("heading") or "Inter")

    @property
    def swatch(self) -> dict[str, str]:
        colors = self.theme.get("colors") if isinstance(self.theme.get("colors"), dict) else {}
        return {k: str(colors.get(k, "")) for k in ("bg", "surface", "brand", "text")}

    @property
    def nav(self) -> list[dict[str, str]]:
        return [{"slug": str(p["slug"]), "title": str(p["title"])} for p in self.pages]

    def page(self, slug: str) -> dict[str, Any] | None:
        return next((p for p in self.pages if p.get("slug") == slug), None)
