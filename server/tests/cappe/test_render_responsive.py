"""Phase 3 responsive layout — per-breakpoint overrides via a scoped <style>.

Pure (render.py + registries are stdlib):
  ./venv/bin/python -m pytest tests/cappe/test_render_responsive.py -q

Base layout emission is untouched, so a section with no *Md/*Sm key renders
identically; a responsive one gains a deterministic scope class cz-rb{index}
and an injected @media style block (!important, scoped — a stylesheet rule can't
override the inline base custom properties otherwise).
"""
import os
import re

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.cappe.services.merlin_ops import validate_ops  # noqa: E402
from app.cappe.services.render import render_site_html  # noqa: E402

_BLOCKS = [{"id": "b1", "type": "features", "heading": "H", "items": [{"title": "a"}]}]


def _render(design, btype="features"):
    site = {"slug": "d", "name": "D", "theme_config": {"mode": "light", "premium": True}}
    block = {"id": "h", "type": btype, "heading": "T", "items": [{"title": "a"}], "_design": design}
    page = {"slug": "home", "title": "H", "content": {"blocks": [block]}}
    return render_site_html(site, page, [{"slug": "home", "title": "Home"}])


def test_no_responsive_key_emits_no_scoped_style():
    html = _render({"layout": {"columns": 3, "padTop": "lg", "align": "center"}})
    assert "cz-rb0" not in html
    assert "@media(max-width:640px)" not in html  # no responsive block


def test_columns_override_is_a_var_at_each_breakpoint():
    html = _render({"layout": {"columns": 3, "columnsMd": 2, "columnsSm": 1}})
    assert "@media(max-width:1024px){.cz-rb0{--cz-cols:repeat(2,minmax(0,1fr))!important}}" in html
    assert "@media(max-width:640px){.cz-rb0{--cz-cols:repeat(1,minmax(0,1fr))!important}}" in html
    # base column count stays inline, unchanged
    assert "--cz-cols:repeat(3,minmax(0,1fr))" in html
    # the section actually carries the scope class
    assert "cz-rb0" in re.search(r"<section[^>]*>", html).group(0)


def test_padding_and_align_are_direct_properties():
    html = _render({"layout": {"padTopSm": "sm", "padBottomSm": "none", "alignSm": "left"}})
    block = re.search(r"@media\(max-width:640px\)\{\.cz-rb0\{([^}]*)\}", html).group(1)
    assert "padding-top:2rem!important" in block
    assert "padding-bottom:0rem!important" in block
    assert "text-align:left!important" in block


def test_mobile_authored_after_tablet_so_it_wins():
    html = _render({"layout": {"padTopMd": "lg", "padTopSm": "sm"}})
    assert html.index("max-width:1024px") < html.index("max-width:640px")


def test_default_value_is_no_override():
    """'default' / unmapped enum = inherit desktop (renderer emits nothing)."""
    html = _render({"layout": {"padTopSm": "default", "alignSm": "default"}})
    assert "cz-rb0" not in html  # nothing to override → no scoped style at all


def test_ai_can_set_the_exposed_responsive_keys_but_not_columns():
    # padTop/padBottom/align responsive are AI-settable (mirror their base keys)…
    for key in ("padTopSm", "padBottomMd", "alignSm"):
        val = "left" if key.startswith("align") else "sm"
        v, r = validate_ops([{"op": "set_design", "block": "b1", "group": "layout",
                              "key": key, "value": val}], _BLOCKS)
        assert len(v) == 1 and not r, key
    # …columns responsive is renderer/inspector-only (base columns isn't AI-settable either)
    v, r = validate_ops([{"op": "set_design", "block": "b1", "group": "layout",
                          "key": "columnsSm", "value": 1}], _BLOCKS)
    assert not v and r  # rejected: not a layout setting in the AI surface
