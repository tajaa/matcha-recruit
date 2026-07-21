"""Phase 5 decorative lane — image filter presets, pattern backgrounds, and
SVG shape dividers.

Pure (render.py + registries are stdlib):
  ./venv/bin/python -m pytest tests/cappe/test_render_decorative.py -q

Filters/patterns are class-toggled CSS; dividers inject enum-keyed inline SVG
(paths from a fixed library, filled with a hex/var color) like bg_media. Every
value is enum/clamp/hex — nothing user-authored reaches the SVG sink. An unset
section is unchanged (only _BASE_CSS gains the new rules).
"""
import os
import re

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.cappe.services.merlin_ops import validate_ops  # noqa: E402
from app.cappe.services.render import _DIVIDER_PATHS, render_site_html  # noqa: E402

_BLOCKS = [{"id": "b1", "type": "hero", "heading": "H"}]


def _render(design, btype="hero"):
    site = {"slug": "d", "name": "D", "theme_config": {"mode": "light", "premium": True}}
    page = {"slug": "home", "title": "H", "content": {"blocks": [{"id": "h", "type": btype, "heading": "T", "_design": design}]}}
    return render_site_html(site, page, [{"slug": "home", "title": "Home"}])


def _section(html):
    return re.search(r"<section[^>]*>", html).group(0)


# --- image filters ------------------------------------------------------------

def test_image_filter_toggles_a_class_and_has_a_css_rule():
    html = _render({"image": {"filter": "warm"}})
    assert "cz-imgf-warm" in _section(html)
    assert ".cz-imgf-warm .cz-bg-media,.cz-imgf-warm img{filter:" in html


def test_image_filter_none_is_inert():
    assert "cz-imgf-" not in _section(_render({"image": {"filter": "none"}}))


# --- pattern backgrounds ------------------------------------------------------

def test_pattern_combines_with_solid_bg_and_takes_a_color():
    html = _render({"bg": {"type": "color", "color": "#101216", "pattern": "grid", "patternColor": "#334455"}})
    sec = _section(html)
    assert "cz-bg--color" in sec and "cz-pat-grid" in sec       # both, layered
    assert "--cz-pat-col:#334455" in sec
    assert ".cz-pat-grid{background-image:" in html


def test_pattern_none_is_inert():
    assert "cz-pat-" not in _section(_render({"bg": {"pattern": "none"}}))


def test_pattern_color_accepts_a_theme_token_and_stays_translucent():
    """The 2026-07-21 fix: a literal hex bypasses the faded-ink default
    entirely; the sanctioned way to color a pattern is a token so it degrades
    gracefully across light/dark instead of going opaque."""
    html = _render({"bg": {"type": "color", "color": "#101216", "pattern": "grid", "patternColor": "ink-faint"}})
    assert "--cz-pat-col:color-mix(in srgb,var(--t-ink) 10%,transparent)" in _section(html)


# --- shape dividers -----------------------------------------------------------

def test_divider_injects_inline_svg_with_clamped_height_and_hex_fill():
    html = _render({"divider": {"top": "wave", "bottom": "slant", "height": 90, "color": "#fdfbf7"}})
    assert 'class="cz-div cz-div--top" style="height:90px"' in html
    assert 'class="cz-div cz-div--bottom" style="height:90px"' in html
    assert _DIVIDER_PATHS["wave"] in html and _DIVIDER_PATHS["slant"] in html
    assert 'style="fill:#fdfbf7"' in html
    assert 'aria-hidden="true"' in html


def test_divider_defaults_height_64_and_page_bg_fill():
    html = _render({"divider": {"top": "curve"}})
    assert 'style="height:64px"' in html
    assert 'style="fill:var(--bg)"' in html   # no color → the page background


def test_divider_height_is_clamped_not_reflected_raw():
    html = _render({"divider": {"top": "peaks", "height": 9999}})
    assert 'style="height:160px"' in html      # clamped to max
    assert "9999" not in html


def test_divider_none_injects_nothing():
    html = _render({"divider": {"top": "none", "bottom": "none"}})
    assert "cz-div" not in html.split("</style>")[-1]  # not in the body (CSS rules aside)


def test_divider_color_accepts_a_theme_token():
    html = _render({"divider": {"top": "wave", "color": "brand-soft"}})
    assert 'style="fill:color-mix(in srgb,var(--t-brand) 18%,transparent)"' in html


# --- AI surface ---------------------------------------------------------------

def test_decorative_keys_are_ai_settable_with_bounds():
    cases = [
        ("image", "filter", "punch", True), ("image", "filter", "hdr", False),
        ("bg", "pattern", "dots", True), ("bg", "pattern", "waves", False),
        ("divider", "top", "wave", True), ("divider", "bottom", "curve", True),
        ("divider", "height", 100, True), ("divider", "height", 5, False),
        ("divider", "color", "#abcdef", True), ("divider", "color", "reddish", False),
    ]
    for grp, key, val, ok in cases:
        v, r = validate_ops([{"op": "set_design", "block": "b1", "group": grp, "key": key, "value": val}], _BLOCKS)
        assert (len(v) == 1 and not r) == ok, (grp, key, val, r)
