"""Design registry is the single source of truth for the `_design` vocabulary.

Pure — no DB, no app boot, no Gemini (render.py + design_registry are stdlib):
  ./venv/bin/python -m pytest tests/cappe/test_design_registry.py -q

Guards two things the Phase-0 registry refactor must never break:
 1. The AI-facing DESIGN_GROUPS derived from the registry stays byte-equal to
    the historical hand-written catalog — a silent widening would offer the
    model keys the renderer may not honor, a narrowing would drop a capability.
 2. The registry-driven emission (colors/type groups) still reaches the
    rendered HTML — the exact css-vars/classes the former inline blocks wrote.
"""
import os

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import app.cappe.services.design_registry as design_registry  # noqa: E402
from app.cappe.services.design_registry import (  # noqa: E402
    DESIGN_KEYS,
    DesignKey,
    RenderRule,
    build_design_groups,
)
from app.cappe.services.merlin_catalog import DESIGN_GROUPS  # noqa: E402
from app.cappe.services.render import _emit_design_group, render_site_html  # noqa: E402

# The historical, hand-written AI surface. If a real change to what Merlin may
# set is intended, update BOTH the registry and this expectation deliberately.
_EXPECTED_DESIGN_GROUPS = {
    "motion": {
        "effect": frozenset({
            "none", "fade", "slide-up", "slide-down", "slide-left", "slide-right",
            "zoom", "blur-in", "flip", "rotate", "mask-up", "bounce",
            "fade-up", "fade-down", "scale-up", "blur-up",
        }),
        "heading": frozenset({"none", "rise", "shimmer"}),
        "hover": frozenset({"none", "lift", "tilt", "glow", "grow", "sink"}),
        "loop": frozenset({"none", "float", "pulse", "sway", "breathe"}),
        "easing": frozenset({"smooth", "gentle", "spring", "snappy", "linear"}),
        "delay": (0, 2000),
        "duration": (100, 2000),
        "parallaxStrength": (0, 80),
        "stagger": "bool",
        "parallax": "bool",
        "kenburns": "bool",
    },
    "bg": {
        "type": frozenset({"none", "color", "gradient", "image", "video"}),
        "overlay": frozenset({"none", "light", "medium", "dark"}),
        "color": "color",
        "image": "text",
        "video": "text",
        "blur": "bool",
        # decorative (Phase 5b)
        "pattern": frozenset({"none", "dots", "grid", "diagonal"}),
        "patternColor": "color",
    },
    "layout": {
        "align": frozenset({"default", "left", "center"}),
        "maxWidth": frozenset({"default", "narrow", "wide", "full"}),
        "minHeight": frozenset({"default", "tall", "screen"}),
        "padTop": "text",
        "padBottom": "text",
        # responsive (Phase 3) — AI-settable variants of the AI-settable base keys
        "padTopMd": "text",
        "padTopSm": "text",
        "padBottomMd": "text",
        "padBottomSm": "text",
        "alignMd": frozenset({"default", "left", "center"}),
        "alignSm": frozenset({"default", "left", "center"}),
    },
    "colors": {"heading": "color", "text": "color", "accent": "color"},
    "border": {"top": "bool", "bottom": "bool", "width": (0, 20), "color": "color"},
    "anchor": {"id": "text"},
    # decorative lane (Phase 5a/5c)
    "image": {"filter": frozenset({"none", "mono", "warm", "cool", "soft", "punch"})},
    "divider": {
        "top": frozenset({"none", "wave", "slant", "curve", "peaks"}),
        "bottom": frozenset({"none", "wave", "slant", "curve", "peaks"}),
        "height": (20, 160),
        "color": "color",
    },
}


def test_design_groups_derivation_is_byte_equal_to_history():
    assert build_design_groups() == _EXPECTED_DESIGN_GROUPS
    # And the catalog symbol Merlin actually validates against is the derived one.
    assert DESIGN_GROUPS == _EXPECTED_DESIGN_GROUPS


def test_renderer_only_keys_are_not_offered_to_merlin():
    """type.* / layout.columns etc. are honored by the renderer but must NOT be
    in the AI surface — they carry merlin_spec=None."""
    settable = {(dk.group, dk.key) for dk in DESIGN_KEYS if dk.merlin_settable}
    assert ("type", "headingSize") not in settable
    assert ("type", "bodySize") not in settable
    # colors IS settable (sanity that the split isn't inverted)
    assert ("colors", "accent") in settable


def _render_with_design(design):
    site = {"slug": "d", "name": "D", "theme_config": {"mode": "light", "premium": True}}
    page = {"slug": "home", "title": "H",
            "content": {"blocks": [{"id": "h", "type": "hero", "heading": "T", "_design": design}]}}
    return render_site_html(site, page, [{"slug": "home", "title": "Home"}])


def test_registry_driven_colors_emission_reaches_html():
    html = _render_with_design({"colors": {"text": "#0a0b0c", "heading": "#123456", "accent": "#ff8800"}})
    assert "--cz-text:#0a0b0c" in html
    assert "--cz-heading:#123456" in html
    # accent fans out to both brand + accent vars and adds the cz-acc class.
    assert "--cz-brand:#ff8800" in html
    assert "--cz-accent:#ff8800" in html
    assert "cz-acc" in html


def test_registry_driven_type_emission_reaches_html():
    html = _render_with_design({"type": {"headingSize": 48, "bodySize": 18}})
    assert "--cz-h-size:48px" in html and "cz-has-hsize" in html
    assert "--cz-p-size:18px" in html and "cz-has-psize" in html


def test_int_px_legacy_skip_on_zero_is_byte_identical():
    """Default int_px (allow_zero=False) keeps the historical behavior: an
    absent key emits nothing, and a present 0 clamps UP to `lo` (so 0 never
    survives to mean 'off' for the min>0 tokens). This is the byte-identity the
    colors/type registry migration must preserve."""
    css: list = []
    _emit_design_group("type", {"headingSize": 0}, [], css)
    assert "--cz-h-size:16px" in css          # present 0 → clamped to lo=16
    css = []
    _emit_design_group("type", {}, [], css)
    assert not any(c.startswith("--cz-h-size") for c in css)  # absent → skip


def test_int_px_allow_zero_distinguishes_explicit_zero_from_unset():
    """allow_zero=True lets a token whose 0 is a real value (e.g. a gap/spacing
    token with lo=0) emit `0px`, while an absent or non-numeric key is still
    'unset' and skipped. This is what the type-scale / responsive lanes need."""
    probe = DesignKey("__probe__", "gap", None,
                      render=RenderRule("int_px", "--cz-probe", lo=0, hi=80, allow_zero=True))
    design_registry.DESIGN_KEYS_BY_GROUP["__probe__"] = (probe,)
    try:
        cases = {0: "--cz-probe:0px", 40: "--cz-probe:40px", None: None, "junk": None}
        for raw, expect in cases.items():
            values = {} if raw is None else {"gap": raw}  # None → absent key (unset)
            css: list = []
            _emit_design_group("__probe__", values, [], css)
            got = css[0] if css else None
            assert got == expect, (raw, got, expect)
    finally:
        design_registry.DESIGN_KEYS_BY_GROUP.pop("__probe__", None)


def test_unset_design_keys_emit_no_assignment():
    """The var-fallback contract: an empty group assigns no css-var *value*, so
    the section carries no override and the `_BASE_CSS` var() fallback applies.

    `_BASE_CSS` references the token names and class rules itself, so a plain
    substring check is meaningless — this is differential: a distinctive value
    appears in the document ONLY when the key is set."""
    set_html = _render_with_design({"colors": {"accent": "#abc123"}, "type": {"headingSize": 71}})
    unset_html = _render_with_design({"colors": {}, "type": {}})
    for token in ("--cz-brand:#abc123", "--cz-accent:#abc123", "--cz-h-size:71px"):
        assert token in set_html
        assert token not in unset_html
