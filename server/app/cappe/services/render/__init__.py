"""Self-contained Cappe public-site renderer.

Renders a published site's design tokens (`theme_config`) + a page's content
blocks into a standalone HTML document styled by ONE inline `<style>` — no
external CSS framework, no runtime CDN. The page is always styled (no flash, no
dependency on a third party). Per-site palette + fonts are injected as CSS
custom properties; a static, designed stylesheet (`_BASE_CSS`) consumes them, so
every template looks bespoke from the same engine.

Interactive widgets (store / booking / newsletter / contact) ship a tiny vanilla
JS runtime that talks to the same-origin public API. All user content is escaped;
URLs are scheme-checked.

Block types: hero, features, gallery, pricing, testimonial, cta, menu, posts,
stats, logos, faq, bento, split, credentials, reviews, map, hours, text,
contact, store, booking, newsletter.

Split (2026-07-26) into sanitize.py (pure string/regex primitives, a leaf) ->
design.py (token system + `_design` layer + base stylesheet) -> blocks.py
(block renderers + widget JS + canvas) -> page.py (document assembly +
`render_site_html`). In-app callers only ever need `render_site_html`; the
re-binds below exist for the render test files that reach module-attribute
privates (e.g. `from app.cappe.services import render as R; R._render_block`).
"""
from .page import render_site_html  # noqa: F401

from .design import _BASE_CSS, _DIVIDER_PATHS, _EASING, _LOOP_FX, _emit_design_group, _tokens  # noqa: F401
from .sanitize import _anchor_id  # noqa: F401
from .blocks import _render_block  # noqa: F401
