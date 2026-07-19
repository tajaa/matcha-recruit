"""Phase 2 motion — new reveal effects, hover/loop animations, and reveal easing.

Pure (render.py + registries are stdlib):
  ./venv/bin/python -m pytest tests/cappe/test_render_motion.py -q

The point of the Phase-0 registry: a new motion value is one enum edit that
flows to validation + prompt + schema; the renderer honors it via _MOTION_FX /
_HOVER_FX / _LOOP_FX / _EASING + a `.cz-*` CSS rule. Easing is consumed as
`var(--cz-ease, <default curve>)`, so an unset section keeps today's motion.
"""
import os

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.cappe.services.merlin_ops import validate_ops  # noqa: E402
from app.cappe.services.render import (  # noqa: E402
    _BASE_CSS,
    _EASING,
    _LOOP_FX,
    render_site_html,
)

_BLOCKS = [{"id": "b1", "type": "hero", "heading": "H"}]


def _render(design):
    site = {"slug": "d", "name": "D", "theme_config": {"mode": "light", "premium": True}}
    page = {"slug": "home", "title": "H",
            "content": {"blocks": [{"id": "h", "type": "hero", "heading": "T", "_design": design}]}}
    return render_site_html(site, page, [{"slug": "home", "title": "Home"}])


def test_new_reveal_effects_are_ai_settable_and_render():
    for fx in ("fade-up", "fade-down", "scale-up", "blur-up"):
        v, r = validate_ops([{"op": "set_design", "block": "b1", "group": "motion",
                              "key": "effect", "value": fx}], _BLOCKS)
        assert len(v) == 1 and not r, fx                       # registry validates it
        assert f"cz-rv--{fx}" in _render({"motion": {"effect": fx}}), fx  # renderer honors it


def test_new_hover_and_loop_effects_render():
    assert "cz-hover-grow" in _render({"motion": {"hover": "grow"}})
    assert "cz-hover-sink" in _render({"motion": {"hover": "sink"}})
    assert "cz-loop-sway" in _render({"motion": {"loop": "sway"}})
    assert "cz-loop-breathe" in _render({"motion": {"loop": "breathe"}})


def test_easing_emits_the_mapped_curve_only_when_set_with_an_effect():
    html = _render({"motion": {"effect": "slide-up", "easing": "spring"}})
    assert f"--cz-ease:{_EASING['spring']}" in html
    # unset easing → no --cz-ease assignment (the var() fallback curve applies)
    assert "--cz-ease:" not in _render({"motion": {"effect": "slide-up"}})


def test_easing_rejects_unknown_and_accepts_known():
    good, _ = validate_ops([{"op": "set_design", "block": "b1", "group": "motion",
                             "key": "easing", "value": "gentle"}], _BLOCKS)
    bad_v, bad_r = validate_ops([{"op": "set_design", "block": "b1", "group": "motion",
                                  "key": "easing", "value": "boing"}], _BLOCKS)
    assert len(good) == 1
    assert not bad_v and "must be one of" in bad_r[0]["reason"]


def test_every_loop_animation_is_disabled_under_reduced_motion():
    """The prefers-reduced-motion block disables loop animations by explicit
    enumeration — a newly added loop that isn't listed keeps animating for users
    who asked for reduced motion (the exact bug this guards: sway/breathe were
    initially missing). Generated from _LOOP_FX so the list can't drift."""
    rm_block = _BASE_CSS.split("@media(prefers-reduced-motion:reduce)")[1]
    for loop in _LOOP_FX:
        assert f".cz-loop-{loop}" in rm_block, f"loop '{loop}' not covered by reduced-motion"


def test_reveal_transition_consumes_the_easing_var():
    """The base .cz-rv transition must reference var(--cz-ease, <default>) so the
    token is live — and the default equals the historical curve."""
    html = _render({"motion": {"effect": "fade"}})
    assert "var(--cz-ease,cubic-bezier(.2,.7,.2,1))" in html
