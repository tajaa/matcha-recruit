"""Phase 1 typography — the global heading-size scale (theme_config.type.headingScale).

Pure (render.py is stdlib — no DB / app boot / Gemini):
  ./venv/bin/python -m pytest tests/cappe/test_render_typography.py -q

The scale is consumed by the heading rules as
`calc(var(--cz-h-scale,100)/100*<clamp>)`, so an unset (or 100) scale computes
to the original clamp — visually identical to before the feature existed.
"""
import os

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.cappe.services.render import render_site_html  # noqa: E402

# The heading rules the scale wraps — the original clamps must survive verbatim
# as the scaled operand (that IS the "identical when unset" contract).
_WRAPPED = (
    "calc(var(--cz-h-scale,100)/100*clamp(2.4rem,6vw,4.4rem))",   # hero title
    "calc(var(--cz-h-scale,100)/100*clamp(1.8rem,4vw,2.6rem))",   # section/band h2
    "calc(var(--cz-h-scale,100)/100*clamp(1.6rem,3.5vw,2.2rem))",  # text h2
    "calc(var(--cz-h-scale,100)/100*clamp(2.4rem,5vw,3.4rem))",   # stat number
    "calc(var(--cz-h-scale,100)/100*clamp(1.6rem,3.4vw,2.2rem))",  # product name
    "calc(var(--cz-h-scale,100)/100*clamp(1.6rem,3.5vw,2.4rem))",  # split h2
)


def _render(type_cfg=None):
    tc = {"mode": "light", "premium": True}
    if type_cfg is not None:
        tc["type"] = type_cfg
    site = {"slug": "d", "name": "D", "theme_config": tc}
    page = {"slug": "home", "title": "H", "content": {"blocks": [
        {"id": "h", "type": "hero", "heading": "T"},
        {"id": "s", "type": "stats", "items": [{"value": "9", "label": "x"}]},
    ]}}
    return render_site_html(site, page, [{"slug": "home", "title": "Home"}])


def test_heading_rules_carry_the_scale_wrapper_with_original_clamp():
    html = _render()
    for rule in _WRAPPED:
        assert rule in html, rule


def test_scale_unset_emits_no_assignment():
    """Unset → the var() fallback (100) applies → calc computes to the raw clamp."""
    assert "--cz-h-scale:" not in _render()
    assert "--cz-h-scale:" not in _render({"headingWeight": 700})  # other type keys don't trigger it


def test_scale_default_100_is_a_noop():
    assert "--cz-h-scale:" not in _render({"headingScale": 100})


def test_scale_emits_integer_percent_when_set():
    assert "--cz-h-scale:120" in _render({"headingScale": 120})
    assert "--cz-h-scale:85" in _render({"headingScale": 85})


def test_scale_is_clamped_to_70_140():
    assert "--cz-h-scale:140" in _render({"headingScale": 999})   # over → 140
    assert "--cz-h-scale:70" in _render({"headingScale": 10})     # under → 70


def test_scale_survives_alongside_the_clamp_when_set():
    """Setting the scale doesn't drop the wrapper/clamp — it multiplies it."""
    html = _render({"headingScale": 120})
    assert "calc(var(--cz-h-scale,100)/100*clamp(2.4rem,6vw,4.4rem))" in html
