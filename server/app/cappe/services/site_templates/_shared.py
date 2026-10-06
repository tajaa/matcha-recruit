"""Authoring helpers shared by every template module in this package.

Templates are plain data: a theme dict plus pages of renderer blocks. These
helpers keep that data honest at authoring time —

- `page()` builds the page shape `clone_structure` copies into `cappe_pages`.
- `BUSINESS_NAME` is the one substitution token. Copy that names the business
  uses it ("Welcome to {{business_name}}") so a clone reads as the owner's
  site, not the template's. `substitute_tokens` resolves it at clone time.
- `img()` / `pic()` resolve imagery keys through the manifest (`imagery.py`),
  never a third-party host — see that module for why.

Authoring rules the drift test (`tests/cappe/test_site_templates.py`) enforces:
every block field must satisfy `merlin.catalog.BLOCK_FIELDS`, every `_design`
bag must satisfy the design registry, copy must not invent facts (years,
named people, contactable addresses), and no template may need the premium
layer to look finished — `gate_theme`/`gate_content` strip it for free plans.
"""
from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from .imagery import image_url

BUSINESS_NAME = "{{business_name}}"

_TOKEN_RE = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")


def page(title: str, slug: str, order: int, blocks: list[dict[str, Any]]) -> dict[str, Any]:
    return {"title": title, "slug": slug, "sort_order": order, "content": {"blocks": blocks}}


def img(key: str) -> str:
    """URL for a manifest image key — the generated photo once the imagery
    script has run, else the self-hosted placeholder."""
    return image_url(key)


def pic(field: str, key: str) -> dict[str, str]:
    """`{field: url}` for splatting into a block: `{"type": "hero", **pic("image", "cafe-hero")}`."""
    return {field: img(key)}


def substitute_tokens(value: Any, values: dict[str, str]) -> Any:
    """Deep-copy `value` with every `{{token}}` in every string replaced from
    `values`. Unknown tokens are left as-is so the drift test can catch them."""

    def _sub(s: str) -> str:
        return _TOKEN_RE.sub(lambda m: values.get(m.group(1), m.group(0)), s)

    def _walk(v: Any) -> Any:
        if isinstance(v, str):
            return _sub(v)
        if isinstance(v, list):
            return [_walk(x) for x in v]
        if isinstance(v, dict):
            return {k: _walk(x) for k, x in v.items()}
        return v

    return _walk(deepcopy(value))


def find_tokens(value: Any) -> set[str]:
    """Every `{{token}}` name present anywhere in `value` (for the drift test)."""
    found: set[str] = set()

    def _walk(v: Any) -> None:
        if isinstance(v, str):
            found.update(_TOKEN_RE.findall(v))
        elif isinstance(v, list):
            for x in v:
                _walk(x)
        elif isinstance(v, dict):
            for x in v.values():
                _walk(x)

    _walk(value)
    return found
