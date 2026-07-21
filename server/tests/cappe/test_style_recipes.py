"""Style recipes — apply_style_recipe + the theme-portable color-token vocab.

Pure (registries + render.py are stdlib):
  ./venv/bin/python -m pytest tests/cappe/test_style_recipes.py -q

The library drift-gate is the important part: every recipe must expand
through the REAL set_design_bulk validation with nothing filtered (a recipe
referencing a renamed design key or a retired color token fails here, not in
front of a user), and must smoke-render on BOTH a light and a dark theme —
a recipe authored in hex would only need one theme to look right; token
recipes must look coherent (i.e. render at all, non-empty) on both.
"""
import json
import os

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.cappe.services.design_registry import DESIGN_COLOR_TOKENS  # noqa: E402
from app.cappe.services.merlin_ops import validate_ops  # noqa: E402
from app.cappe.services.render import render_site_html  # noqa: E402
from app.cappe.services.style_recipes import RECIPES_BY_KEY, STYLE_RECIPES  # noqa: E402

_BLOCKS = [{"id": "b1", "type": "hero", "heading": "H"}]


def _apply(key, blocks="all", **kw):
    return validate_ops([{"op": "apply_style_recipe", "blocks": blocks, "recipe": key}], _BLOCKS, **kw)


# --- library drift-gate -------------------------------------------------------

def test_every_recipe_expands_cleanly_with_nothing_filtered():
    """design == the library's design after the real set_design_bulk
    validation ran — i.e. zero keys were dropped. A drop means the recipe
    drifted from DESIGN_GROUPS (a renamed/retired key or value out of range)."""
    for r in STYLE_RECIPES:
        valid, rejected = _apply(r.key)
        assert len(valid) == 1 and not rejected, (r.key, rejected)
        op = valid[0]
        assert op["op"] == "set_design_bulk", r.key
        assert op["design"] == r.design, f"{r.key}: design filtered — recipe drifted"
        assert op["blocks"] == ["b1"], r.key  # "all" resolved to the snapshot's ids
        assert op["recipe"] == r.key  # provenance survives


def test_every_recipe_only_uses_theme_color_tokens_never_hex():
    """The whole premise of a recipe is theme-portability — a hex slipping in
    would only look right on the theme it was eyeballed against. No design key
    here is a color, so a blanket "no '#' anywhere in the bag" is sufficient
    and simpler than re-deriving each key's kind from the registry."""
    for r in STYLE_RECIPES:
        blob = json.dumps(r.design)
        assert "#" not in blob, f"{r.key}: contains a literal hex — recipes must be token-only"
        # Every gradient stop (the one nested color-bearing shape) must
        # resolve to a real, current token — not just "not a hex".
        for group_vals in r.design.values():
            gradient = group_vals.get("gradient")
            if isinstance(gradient, dict):
                for stop in gradient.get("stops", []):
                    assert stop in DESIGN_COLOR_TOKENS, f"{r.key}: gradient stop {stop!r} is not a known token"


def test_every_recipe_smoke_renders_on_light_and_dark_theme():
    for mode in ("light", "dark"):
        site = {"slug": "d", "name": "D", "theme_config": {"mode": mode, "premium": True}}
        for r in STYLE_RECIPES:
            valid, _ = _apply(r.key)
            op = valid[0]
            block = {"id": "b1", "type": "hero", "heading": "H", "_design": op["design"]}
            html = render_site_html(site, {"slug": "home", "title": "H", "content": {"blocks": [block]}},
                                    [{"slug": "home", "title": "Home"}])
            assert "<section" in html, (r.key, mode)
            assert "cz-design" in html, (r.key, mode)  # the design bag actually took effect


def test_library_data_is_not_mutated_by_expansion():
    first, _ = _apply("soft-elevate")
    first[0]["design"]["bg"]["color"] = "MUTATED"
    second, _ = _apply("soft-elevate")
    assert second[0]["design"]["bg"]["color"] != "MUTATED"
    assert second[0]["design"]["bg"]["color"] == RECIPES_BY_KEY["soft-elevate"].design["bg"]["color"]


# --- op validation ------------------------------------------------------------

def test_unknown_recipe_rejected_with_the_known_keys():
    valid, rejected = _apply("not-a-recipe")
    assert not valid and "unknown style recipe" in rejected[0]["reason"]
    assert "soft-elevate" in rejected[0]["reason"]


def test_apply_style_recipe_refused_on_non_premium():
    valid, rejected = _apply("soft-elevate", premium=False)
    assert not valid and "Pro feature" in rejected[0]["reason"]


def test_apply_style_recipe_targets_explicit_ids():
    blocks = [{"id": "b1", "type": "hero"}, {"id": "b2", "type": "features"}]
    valid, rejected = validate_ops(
        [{"op": "apply_style_recipe", "blocks": ["b2"], "recipe": "framed"}], blocks,
    )
    assert len(valid) == 1 and not rejected
    assert valid[0]["blocks"] == ["b2"]


def test_apply_style_recipe_unknown_block_id_rejected():
    valid, rejected = _apply("framed", blocks=["ghost"])
    assert not valid and "unknown block id" in rejected[0]["reason"]


# --- 2026-07-21 "arguably worse" regression: brand-glow visibility + spotlight -

def test_brand_glow_uses_a_visible_gradient_stop_not_the_faint_one():
    """brand-faint (8% mix) over a near-black bg read as no gradient at all —
    regression guard against reverting to it."""
    stops = RECIPES_BY_KEY["brand-glow"].design["bg"]["gradient"]["stops"]
    assert "brand-soft" in stops
    assert "brand-faint" not in stops


def test_brand_glow_is_a_coordinated_multi_group_restyle():
    """A bg tint alone reads as "nothing happened" for a redesign ask —
    brand-glow must also move layout/typography, not just paint a color."""
    design = RECIPES_BY_KEY["brand-glow"].design
    assert "layout" in design and "motion" in design


def test_spotlight_recipe_exists_for_completely_different_asks():
    r = RECIPES_BY_KEY.get("spotlight")
    assert r is not None
    assert set(r.design) >= {"type", "layout", "bg", "motion"}  # a real structural swing, not one group
