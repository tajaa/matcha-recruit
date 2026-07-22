"""Merlin op validation is pure — no DB, no app boot, no Gemini call.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_merlin_validation.py -q
"""
import os

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.cappe.services.merlin import validate_ops  # noqa: E402
from app.cappe.services.merlin_catalog import CANVAS_MAX_ELEMENTS, MAX_OPS_PER_TURN  # noqa: E402

_HERO = {"id": "b1", "type": "hero", "heading": "Old", "subheading": "Sub"}
_CANVAS = {
    "id": "b2", "type": "canvas", "grid": {"cols": 24, "rowH": 24, "rows": 30},
    "elements": [{"id": "e1", "kind": "text", "text": "hi", "d": {"x": 1, "y": 1, "w": 4, "h": 2}}],
}
_FEATURES = {"id": "b4", "type": "features", "items": [{"title": "a"}, {"title": "b"}, {"title": "c"}]}
_SPLIT = {"id": "b5", "type": "split", "heading": "H", "bullets": ["one"], "reverse": False}
_BLOCKS = [_HERO, _CANVAS, _FEATURES, _SPLIT]


def _only(ops):
    valid, rejected = validate_ops(ops, _BLOCKS)
    return valid, rejected


# --- set_field ---------------------------------------------------------------

def test_set_field_valid():
    valid, rejected = _only([{"op": "set_field", "block": "b1", "path": "heading", "value": "New"}])
    assert len(valid) == 1 and not rejected


def test_set_field_unknown_block_rejected():
    valid, rejected = _only([{"op": "set_field", "block": "nope", "path": "heading", "value": "x"}])
    assert not valid and len(rejected) == 1 and "not found" in rejected[0]["reason"]


def test_set_field_unknown_field_rejected():
    valid, rejected = _only([{"op": "set_field", "block": "b1", "path": "notarealfield", "value": "x"}])
    assert not valid and len(rejected) == 1


def test_set_field_subpath_into_scalar_rejected():
    # `heading` is a text field — nothing addresses into it.
    valid, rejected = _only([{"op": "set_field", "block": "b1", "path": "heading.0.title", "value": "x"}])
    assert not valid and "no sub-fields" in rejected[0]["reason"]


# --- set_field: path/value shape (the list-clobber class of bug) --------------

def test_set_field_named_key_into_list_rejected():
    """`items.title` made the client replace the whole list with {title: ...},
    deleting every card while reporting success."""
    valid, rejected = _only([{"op": "set_field", "block": "b4", "path": "items.title", "value": "Fast"}])
    assert not valid and "must be a list index" in rejected[0]["reason"]


def test_set_field_list_index_valid():
    valid, rejected = _only([{"op": "set_field", "block": "b4", "path": "items.1.title", "value": "New"}])
    assert len(valid) == 1 and not rejected


def test_set_field_append_at_length_allowed():
    valid, rejected = _only([{"op": "set_field", "block": "b4", "path": "items.3.title", "value": "New"}])
    assert len(valid) == 1 and not rejected


def test_set_field_index_past_end_rejected():
    # Padding to index 9 would leave undefined holes the renderer iterates.
    valid, rejected = _only([{"op": "set_field", "block": "b4", "path": "items.9.title", "value": "x"}])
    assert not valid and "past the end" in rejected[0]["reason"]


def test_set_field_list_assigned_a_string_rejected():
    valid, rejected = _only([{"op": "set_field", "block": "b4", "path": "items", "value": "hello"}])
    assert not valid and "list of objects" in rejected[0]["reason"]


def test_set_field_whole_list_of_objects_allowed():
    valid, rejected = _only([{"op": "set_field", "block": "b4", "path": "items", "value": [{"title": "z"}]}])
    assert len(valid) == 1 and not rejected


def test_set_field_bool_field_type_checked():
    ok, _ = _only([{"op": "set_field", "block": "b5", "path": "reverse", "value": True}])
    bad_v, bad_r = _only([{"op": "set_field", "block": "b5", "path": "reverse", "value": "yes"}])
    assert len(ok) == 1
    assert not bad_v and "true or false" in bad_r[0]["reason"]


def test_set_field_strlist_type_checked():
    ok, _ = _only([{"op": "set_field", "block": "b5", "path": "bullets", "value": ["a", "b"]}])
    bad_v, bad_r = _only([{"op": "set_field", "block": "b5", "path": "bullets", "value": [1, 2]}])
    assert len(ok) == 1
    assert not bad_v and "list of strings" in bad_r[0]["reason"]


def test_set_field_select_option_enforced():
    ok, _ = _only([{"op": "set_field", "block": "b1", "path": "overlay", "value": "dark"}])
    bad_v, bad_r = _only([{"op": "set_field", "block": "b1", "path": "overlay", "value": "darker"}])
    assert len(ok) == 1
    assert not bad_v and "must be one of" in bad_r[0]["reason"]


# --- unhashable / non-string values must never raise -------------------------

def test_unhashable_op_values_are_rejected_not_raised():
    """Every id/key/kind is used as a dict/set lookup key; a hallucinated dict
    or list there used to raise TypeError and 500 the whole turn."""
    cases = [
        {"op": "set_field", "block": {"a": 1}, "path": "heading", "value": "x"},
        {"op": "remove_block", "block": ["a"]},
        {"op": "move_block", "block": {"a": 1}, "to": 0},
        {"op": "set_theme", "key": {"a": 1}, "value": "x"},
        {"op": "set_theme", "key": "mode", "value": {"a": 1}},
        {"op": "canvas_add", "block": "b2", "element": {"kind": ["x"], "d": {"x": 0, "y": 0, "w": 2, "h": 1}}},
        {"op": "canvas_update", "block": "b2", "el": {"a": 1}, "patch": {"text": "x"}},
        {"op": "canvas_remove", "block": "b2", "el": {"a": 1}},
    ]
    for case in cases:
        valid, rejected = _only([case])  # must not raise
        assert not valid and len(rejected) == 1, case


# --- add_block / remove_block / move_block -----------------------------------

def test_add_block_valid_and_strips_unknown_content_keys():
    valid, rejected = _only([{
        "op": "add_block", "type": "faq", "at": 1,
        "content": {"heading": "FAQ", "_design": {"x": 1}, "bogus": "y"},
    }])
    assert not rejected
    assert valid[0]["content"] == {"heading": "FAQ"}


def test_add_block_unknown_type_rejected():
    valid, rejected = _only([{"op": "add_block", "type": "not_a_type", "at": 0}])
    assert not valid and rejected


def test_remove_block_unknown_id_rejected():
    valid, rejected = _only([{"op": "remove_block", "block": "nope"}])
    assert not valid and rejected


def test_move_block_missing_to_rejected():
    valid, rejected = _only([{"op": "move_block", "block": "b1"}])
    assert not valid and rejected


# --- set_theme -----------------------------------------------------------------

def test_set_theme_known_key_valid():
    valid, rejected = _only([{"op": "set_theme", "key": "colors.brand", "value": "#112233"}])
    assert len(valid) == 1 and not rejected


def test_set_theme_prefixed_key_valid():
    valid, rejected = _only([{"op": "set_theme", "key": "style.container", "value": "wide"}])
    assert len(valid) == 1 and not rejected


def test_set_theme_bad_mode_rejected():
    valid, rejected = _only([{"op": "set_theme", "key": "mode", "value": "purple"}])
    assert not valid and rejected


def test_set_theme_unknown_key_rejected():
    valid, rejected = _only([{"op": "set_theme", "key": "not.a.thing", "value": 1}])
    assert not valid and rejected


# --- canvas --------------------------------------------------------------------

def test_canvas_add_valid():
    valid, rejected = _only([{
        "op": "canvas_add", "block": "b2",
        "element": {"kind": "heading", "text": "Hi", "d": {"x": 1, "y": 5, "w": 10, "h": 3}},
    }])
    assert len(valid) == 1 and not rejected


def test_canvas_add_rejects_non_canvas_target():
    valid, rejected = _only([{
        "op": "canvas_add", "block": "b1",
        "element": {"kind": "heading", "d": {"x": 0, "y": 0, "w": 4, "h": 2}},
    }])
    assert not valid and "not a canvas block" in rejected[0]["reason"]


def test_canvas_add_rejects_out_of_bounds():
    valid, rejected = _only([{
        "op": "canvas_add", "block": "b2",
        "element": {"kind": "text", "d": {"x": 20, "y": 0, "w": 10, "h": 2}},
    }])
    assert not valid and "out of bounds" in rejected[0]["reason"]


def test_canvas_add_strips_unknown_style_keys():
    valid, rejected = _only([{
        "op": "canvas_add", "block": "b2",
        "element": {"kind": "text", "d": {"x": 0, "y": 0, "w": 4, "h": 2}, "style": {"color": "#fff", "hacked": 1}},
    }])
    assert not rejected
    assert valid[0]["element"]["style"] == {"color": "#fff"}


def test_canvas_add_enforces_max_elements_across_batch():
    # Pre-fill to 2 below the cap so the MAX_OPS_PER_TURN guard (20) doesn't
    # mask the CANVAS_MAX_ELEMENTS guard this test targets.
    existing = [{"id": f"pre{i}", "kind": "text", "d": {"x": 0, "y": i, "w": 2, "h": 1}}
                for i in range(CANVAS_MAX_ELEMENTS - 2)]
    canvas = {"id": "b3", "type": "canvas", "grid": {"cols": 24}, "elements": existing}
    ops = [{"op": "canvas_add", "block": "b3", "element": {"kind": "text", "d": {"x": 0, "y": 100 + i, "w": 2, "h": 1}}}
           for i in range(5)]
    valid, rejected = validate_ops(ops, [canvas])
    assert len(valid) == 2
    assert len(rejected) == 3
    assert all("max" in r["reason"] for r in rejected)


def test_canvas_add_rejects_bool_coordinate():
    # `True` is an int in Python — {"x": true} must not pass as a coordinate.
    valid, rejected = _only([{
        "op": "canvas_add", "block": "b2",
        "element": {"kind": "text", "d": {"x": True, "y": 0, "w": 2, "h": 1}},
    }])
    assert not valid and "out of bounds" in rejected[0]["reason"]


def test_canvas_add_rejects_y_past_grid_rows():
    # Renderer clamps y, but the editor canvas doesn't — the element would land
    # somewhere the user can never scroll to.
    valid, rejected = _only([{
        "op": "canvas_add", "block": "b2",
        "element": {"kind": "text", "d": {"x": 0, "y": 999999, "w": 2, "h": 50000}},
    }])
    assert not valid and "out of bounds" in rejected[0]["reason"]


def test_canvas_update_patch_strips_id_and_kind():
    """A patched `id` can collide two elements; a patched `kind` the renderer
    doesn't whitelist drops the element from the published page only."""
    valid, rejected = _only([{
        "op": "canvas_update", "block": "b2", "el": "e1",
        "patch": {"text": "hi", "id": "EVIL", "kind": "iframe", "bogus": 1},
    }])
    assert not rejected
    assert valid[0]["patch"] == {"text": "hi"}


def test_canvas_update_unknown_element_rejected():
    valid, rejected = _only([{"op": "canvas_update", "block": "b2", "el": "nope", "patch": {"text": "x"}}])
    assert not valid and rejected


def test_canvas_remove_valid():
    valid, rejected = _only([{"op": "canvas_remove", "block": "b2", "el": "e1"}])
    assert len(valid) == 1 and not rejected


# --- turn-level guards -----------------------------------------------------------

def test_unknown_op_name_rejected():
    valid, rejected = _only([{"op": "delete_everything", "block": "b1"}])
    assert not valid and "unknown op" in rejected[0]["reason"]


def test_non_dict_op_rejected():
    valid, rejected = _only(["not-a-dict"])
    assert not valid and rejected


def test_over_max_ops_per_turn_truncated_and_reported():
    ops = [{"op": "set_field", "block": "b1", "path": "heading", "value": str(i)}
           for i in range(MAX_OPS_PER_TURN + 3)]
    valid, rejected = validate_ops(ops, _BLOCKS)
    assert len(valid) == MAX_OPS_PER_TURN
    assert len(rejected) == 3
    assert all("op limit" in r["reason"] for r in rejected)


def test_mixed_valid_and_invalid_ops_partial_apply():
    valid, rejected = _only([
        {"op": "set_field", "block": "b1", "path": "heading", "value": "New"},
        {"op": "remove_block", "block": "ghost"},
        {"op": "canvas_add", "block": "b2", "element": {"kind": "button", "text": "Go", "d": {"x": 1, "y": 10, "w": 4, "h": 2}}},
    ])
    assert len(valid) == 2
    assert len(rejected) == 1


# --- catalog drift ------------------------------------------------------------

def test_server_catalog_matches_client_block_schemas():
    """merlin_catalog.BLOCK_FIELDS is a hand-maintained mirror of the frontend's
    blockSchemas.ts (its own docstring says so). Drift is silent in both
    directions: a type only the client knows is rejected as 'unknown block
    type', and a type only the server knows is offered to the model but has no
    `make()` to build it."""
    import pathlib
    import re

    from app.cappe.services.merlin_catalog import BLOCK_TYPES

    schemas = pathlib.Path(__file__).resolve().parents[2] / (
        "../client/src/cappe/pages/site/PageEditor/blockSchemas.ts"
    )
    source = schemas.resolve().read_text()
    order = re.search(r"export const BLOCK_ORDER = \[(.*?)\]", source, re.S)
    assert order, "couldn't find BLOCK_ORDER in blockSchemas.ts"
    client_types = set(re.findall(r"'([a-z]+)'", order.group(1)))

    assert client_types == set(BLOCK_TYPES), (
        f"catalog drift — client-only: {sorted(client_types - set(BLOCK_TYPES))}, "
        f"server-only: {sorted(set(BLOCK_TYPES) - client_types)}"
    )


# --- mobile placement gets the same bounds check as desktop -------------------

_MOBILE_CANVAS = {
    "id": "b6", "type": "canvas",
    "grid": {"cols": 24, "rows": 30}, "mobile": {"cols": 8, "rows": 60},
    "elements": [{"id": "m1", "kind": "text", "d": {"x": 0, "y": 0, "w": 2, "h": 1}}],
}


def test_canvas_mobile_position_out_of_bounds_rejected():
    """`m` is spread onto the element client-side exactly like `d`, so leaving
    it unchecked reopened the unreachable-element hole on mobile."""
    valid, rejected = validate_ops([{
        "op": "canvas_update", "block": "b6", "el": "m1",
        "patch": {"m": {"x": 6, "y": 0, "w": 8, "h": 2}},  # x+w=14 > 8 mobile cols
    }], [_MOBILE_CANVAS])
    assert not valid and "mobile element position" in rejected[0]["reason"]


def test_canvas_mobile_position_in_bounds_allowed():
    valid, rejected = validate_ops([{
        "op": "canvas_update", "block": "b6", "el": "m1",
        "patch": {"m": {"x": 1, "y": 2, "w": 6, "h": 2}},
    }], [_MOBILE_CANVAS])
    assert len(valid) == 1 and not rejected


def test_canvas_add_mobile_bounds_checked():
    valid, rejected = validate_ops([{
        "op": "canvas_add", "block": "b6",
        "element": {"kind": "text", "d": {"x": 0, "y": 0, "w": 2, "h": 1},
                    "m": {"x": 0, "y": 0, "w": 99, "h": 1}},
    }], [_MOBILE_CANVAS])
    assert not valid and "mobile element position" in rejected[0]["reason"]


# --- add_block.content is kind-checked, like set_field -----------------------

def test_add_block_content_drops_wrong_typed_values():
    """Without this, the value types set_field rejects just walk in via
    add_block instead."""
    valid, rejected = _only([{
        "op": "add_block", "type": "features", "at": 0,
        "content": {"heading": "Real", "items": "not-a-list"},
    }])
    assert not rejected
    assert valid[0]["content"] == {"heading": "Real"}  # bad `items` dropped, block still built


def test_add_block_content_keeps_correctly_typed_values():
    valid, rejected = _only([{
        "op": "add_block", "type": "features", "at": 0,
        "content": {"heading": "Real", "items": [{"title": "a"}]},
    }])
    assert not rejected
    assert valid[0]["content"] == {"heading": "Real", "items": [{"title": "a"}]}


def test_add_block_drops_columns_design_on_a_non_grid_block_type():
    # hero isn't grid-shaped — columns is dropped (add_block's "keep the
    # block, drop the bad entry" philosophy), not rejected outright.
    valid, rejected = _only([{
        "op": "add_block", "type": "hero", "at": 0,
        "design": {"layout": {"columns": 3}, "motion": {"effect": "fade"}},
    }])
    assert not rejected
    assert valid[0]["design"] == {"motion": {"effect": "fade"}}


def test_add_block_keeps_columns_design_on_a_grid_block_type():
    valid, rejected = _only([{
        "op": "add_block", "type": "features", "at": 0,
        "design": {"layout": {"columns": 3}},
    }])
    assert not rejected
    assert valid[0]["design"] == {"layout": {"columns": 3}}


# --- request size caps --------------------------------------------------------

def test_request_model_bounds_snapshot_and_history():
    """The whole snapshot is inlined into the prompt (twice, if the validation
    retry fires) and Merlin shares the GLOBAL Gemini budget, so oversized
    requests must be refused before any model call."""
    import pytest
    from pydantic import ValidationError

    from app.cappe.models.cappe import CappeMerlinChatRequest

    ok = CappeMerlinChatRequest(page_id="p", message="hi", blocks=[{"id": "b"}] * 200)
    assert len(ok.blocks) == 200

    with pytest.raises(ValidationError):
        CappeMerlinChatRequest(page_id="p", message="hi", blocks=[{"id": "b"}] * 201)
    with pytest.raises(ValidationError):
        CappeMerlinChatRequest(page_id="p", message="hi",
                               history=[{"role": "user", "content": "x"}] * 21)
    with pytest.raises(ValidationError):
        CappeMerlinChatRequest(page_id="p", message="hi",
                               history=[{"role": "user", "content": "x" * 4001}])
    with pytest.raises(ValidationError):
        CappeMerlinChatRequest(page_id="p", message="x" * 2001)


def test_snapshot_byte_ceiling_is_far_below_the_nginx_body_cap():
    from app.cappe.routes.merlin import _MAX_SNAPSHOT_BYTES
    assert 0 < _MAX_SNAPSHOT_BYTES <= 1_000_000


# --- set_design: the op whose absence caused the destructive-substitution bug --
#
# Reported failure: "make this section animate the main text somehow" →
# Merlin switched the whole theme and rewrote a heading, because it had no op
# that could animate anything. `_design.motion.heading` was always the answer.

def test_set_design_animates_the_heading():
    valid, rejected = _only([{
        "op": "set_design", "block": "b1", "group": "motion", "key": "heading", "value": "shimmer",
    }])
    assert len(valid) == 1 and not rejected


def test_set_design_enforces_enum_values():
    ok, _ = _only([{"op": "set_design", "block": "b1", "group": "motion", "key": "heading", "value": "rise"}])
    bad_v, bad_r = _only([{"op": "set_design", "block": "b1", "group": "motion", "key": "heading", "value": "sparkle"}])
    assert len(ok) == 1
    assert not bad_v and "must be one of" in bad_r[0]["reason"]


def test_set_design_enforces_numeric_ranges():
    ok, _ = _only([{"op": "set_design", "block": "b1", "group": "motion", "key": "duration", "value": 700}])
    bad_v, bad_r = _only([{"op": "set_design", "block": "b1", "group": "motion", "key": "duration", "value": 99999}])
    assert len(ok) == 1
    assert not bad_v and "between 100 and 2000" in bad_r[0]["reason"]


def test_set_design_rejects_unknown_group_and_key():
    _, bad_group = _only([{"op": "set_design", "block": "b1", "group": "nope", "key": "x", "value": 1}])
    _, bad_key = _only([{"op": "set_design", "block": "b1", "group": "motion", "key": "bogus", "value": 1}])
    assert "unknown design group" in bad_group[0]["reason"]
    assert "is not a motion setting" in bad_key[0]["reason"]


def test_set_design_null_clears_a_key():
    valid, rejected = _only([{"op": "set_design", "block": "b1", "group": "motion", "key": "heading", "value": None}])
    assert len(valid) == 1 and not rejected


def test_set_design_validates_colors_as_hex():
    ok, _ = _only([{"op": "set_design", "block": "b1", "group": "colors", "key": "heading", "value": "#1a2b3c"}])
    bad_v, bad_r = _only([{"op": "set_design", "block": "b1", "group": "colors", "key": "heading", "value": "reddish"}])
    assert len(ok) == 1
    assert not bad_v and "hex color" in bad_r[0]["reason"]


def test_set_design_accepts_a_semantic_color_token():
    """2026-07-21: colors may also be a theme token (DESIGN_COLOR_TOKENS) — the
    token resolves through the theme's own vars, unlike a blind hex guess."""
    ok, _ = _only([{"op": "set_design", "block": "b1", "group": "colors", "key": "accent", "value": "brand-soft"}])
    assert len(ok) == 1
    bad_v, bad_r = _only([{"op": "set_design", "block": "b1", "group": "colors", "key": "accent", "value": "brand-medium"}])
    assert not bad_v and "theme token" in bad_r[0]["reason"]


def test_set_design_refused_on_non_premium_with_an_honest_reason():
    """`gate_content` strips `_design` on save for free plans, so applying it
    in-editor would look like it worked and then silently vanish."""
    valid, rejected = validate_ops(
        [{"op": "set_design", "block": "b1", "group": "motion", "key": "heading", "value": "shimmer"}],
        _BLOCKS, premium=False,
    )
    assert not valid and "Pro feature" in rejected[0]["reason"]


# --- Phase 1: vocab completion + range unification ---------------------------

def test_set_design_heading_and_body_size_now_ai_settable():
    ok, _ = _only([{"op": "set_design", "block": "b1", "group": "type", "key": "headingSize", "value": 64}])
    assert len(ok) == 1
    bad_v, bad_r = _only([{"op": "set_design", "block": "b1", "group": "type", "key": "headingSize", "value": 999}])
    assert not bad_v and "between 16 and 96" in bad_r[0]["reason"]
    ok2, _ = _only([{"op": "set_design", "block": "b1", "group": "type", "key": "bodySize", "value": 16}])
    assert len(ok2) == 1


def test_set_design_columns_now_ai_settable():
    # b4 is a `features` block — grid-shaped (in COLUMN_BLOCK_TYPES).
    ok, _ = _only([{"op": "set_design", "block": "b4", "group": "layout", "key": "columns", "value": 3}])
    assert len(ok) == 1
    bad_v, bad_r = _only([{"op": "set_design", "block": "b4", "group": "layout", "key": "columns", "value": 12}])
    assert not bad_v and "between 1 and 6" in bad_r[0]["reason"]


def test_set_design_columns_rejected_on_non_grid_block():
    # b1 is a `hero` block — not grid-shaped; --cz-cols would go unread.
    bad_v, bad_r = _only([{"op": "set_design", "block": "b1", "group": "layout", "key": "columns", "value": 3}])
    assert not bad_v and "no effect on a hero block" in bad_r[0]["reason"]


def test_set_design_blur_is_now_numeric_not_bool():
    ok, _ = _only([{"op": "set_design", "block": "b1", "group": "bg", "key": "blur", "value": 12}])
    assert len(ok) == 1
    bad_v, bad_r = _only([{"op": "set_design", "block": "b1", "group": "bg", "key": "blur", "value": True}])
    assert not bad_v and "between 0 and 40" in bad_r[0]["reason"]


def test_set_design_border_width_range_matches_renderer_clamp():
    ok, _ = _only([{"op": "set_design", "block": "b1", "group": "border", "key": "width", "value": 4}])
    assert len(ok) == 1
    bad_v, bad_r = _only([{"op": "set_design", "block": "b1", "group": "border", "key": "width", "value": 15}])
    assert not bad_v and "between 1 and 8" in bad_r[0]["reason"]


def test_set_design_overlay_opacity_accepted_in_range():
    ok, _ = _only([{"op": "set_design", "block": "b1", "group": "bg", "key": "overlayOpacity", "value": 60}])
    assert len(ok) == 1
    bad_v, bad_r = _only([{"op": "set_design", "block": "b1", "group": "bg", "key": "overlayOpacity", "value": 150}])
    assert not bad_v and "between 0 and 100" in bad_r[0]["reason"]


def test_set_design_gradient_happy_path():
    ok, _ = _only([{
        "op": "set_design", "block": "b1", "group": "bg", "key": "gradient",
        "value": {"angle": 135, "stops": ["#111111", "#eeeeee"]},
    }])
    assert len(ok) == 1


def test_set_design_gradient_accepts_theme_tokens_as_stops():
    ok, _ = _only([{
        "op": "set_design", "block": "b1", "group": "bg", "key": "gradient",
        "value": {"stops": ["brand-faint", "transparent"]},
    }])
    assert len(ok) == 1
    ok2, _ = _only([{
        "op": "set_design", "block": "b1", "group": "bg", "key": "gradient",
        "value": {"stops": ["surface-2", "#eeeeee", "brand-soft"]},
    }])
    assert len(ok2) == 1


def test_set_design_gradient_rejects_bad_stops():
    _, one_stop = _only([{
        "op": "set_design", "block": "b1", "group": "bg", "key": "gradient",
        "value": {"stops": ["#111111"]},
    }])
    assert "stops" in one_stop[0]["reason"]
    _, bad_hex = _only([{
        "op": "set_design", "block": "b1", "group": "bg", "key": "gradient",
        "value": {"stops": ["not-a-color", "#eeeeee"]},
    }])
    assert "stops" in bad_hex[0]["reason"]
    _, not_dict = _only([{
        "op": "set_design", "block": "b1", "group": "bg", "key": "gradient", "value": "purple",
    }])
    assert not_dict


def test_set_design_gradient_rejects_bad_angle():
    _, rejected = _only([{
        "op": "set_design", "block": "b1", "group": "bg", "key": "gradient",
        "value": {"angle": 999, "stops": ["#111111", "#eeeeee"]},
    }])
    assert "angle" in rejected[0]["reason"]


# --- duplicate_block -----------------------------------------------------------

def test_duplicate_block_valid():
    ok, _ = _only([{"op": "duplicate_block", "block": "b1"}])
    assert len(ok) == 1


def test_duplicate_block_with_explicit_at():
    ok, _ = _only([{"op": "duplicate_block", "block": "b1", "at": 2}])
    assert len(ok) == 1


def test_duplicate_block_unknown_id_rejected():
    _, rejected = _only([{"op": "duplicate_block", "block": "ghost"}])
    assert rejected and "not found" in rejected[0]["reason"]


def test_duplicate_block_invalid_at_rejected():
    _, rejected = _only([{"op": "duplicate_block", "block": "b1", "at": "two"}])
    assert rejected and "at" in rejected[0]["reason"]


def test_duplicate_block_with_id_then_set_design_same_turn():
    """duplicate_block's `id` registers the clone the same way add_block's
    does, so "duplicate this section, then restyle the copy" resolves within
    one turn instead of the second op hitting 'block id not found'."""
    valid, rejected = _only([
        {"op": "duplicate_block", "block": "b1", "id": "dup-1"},
        {"op": "set_design", "block": "dup-1", "group": "bg", "key": "color", "value": "surface"},
    ])
    assert not rejected
    assert len(valid) == 2


def test_duplicate_block_id_collides_with_existing_block_rejected():
    _, rejected = _only([{"op": "duplicate_block", "block": "b1", "id": "b1"}])
    assert rejected and "collides" in rejected[0]["reason"]


# --- set_design_bulk -----------------------------------------------------------

def test_set_design_bulk_explicit_ids_valid():
    ok, _ = _only([{
        "op": "set_design_bulk", "blocks": ["b1", "b4"],
        "design": {"bg": {"overlay": "dark"}},
    }])
    assert len(ok) == 1
    assert ok[0]["blocks"] == ["b1", "b4"]


def test_set_design_bulk_all_resolves_to_every_known_id():
    ok, _ = _only([{"op": "set_design_bulk", "blocks": "all", "design": {"bg": {"overlay": "dark"}}}])
    assert len(ok) == 1
    assert set(ok[0]["blocks"]) == {"b1", "b2", "b4", "b5"}


def test_set_design_bulk_unknown_id_rejected():
    _, rejected = _only([{
        "op": "set_design_bulk", "blocks": ["b1", "ghost"],
        "design": {"bg": {"overlay": "dark"}},
    }])
    assert rejected and "ghost" in rejected[0]["reason"]


def test_set_design_bulk_empty_blocks_rejected():
    _, rejected = _only([{"op": "set_design_bulk", "blocks": [], "design": {"bg": {"overlay": "dark"}}}])
    assert rejected


def test_set_design_bulk_bad_design_bag_rejected():
    _, rejected = _only([{"op": "set_design_bulk", "blocks": ["b1"], "design": {"bg": {"overlay": "nope"}}}])
    assert rejected and "no valid" in rejected[0]["reason"]


def test_set_design_bulk_cleans_partial_bag_keeping_valid_keys():
    ok, _ = _only([{
        "op": "set_design_bulk", "blocks": ["b1"],
        "design": {"bg": {"overlay": "dark", "color": "not-a-hex"}, "bogus_group": {"x": 1}},
    }])
    assert len(ok) == 1
    assert ok[0]["design"] == {"bg": {"overlay": "dark"}}


def test_set_design_bulk_columns_ok_when_every_target_is_grid_shaped():
    ok, _ = _only([{
        "op": "set_design_bulk", "blocks": ["b4"], "design": {"layout": {"columns": 3}},
    }])
    assert len(ok) == 1


def test_set_design_bulk_columns_rejected_when_any_target_is_not_grid_shaped():
    # b1 (hero) can't take columns even though b4 (features) can — reject
    # the whole op rather than silently applying to only some targets.
    _, rejected = _only([{
        "op": "set_design_bulk", "blocks": ["b1", "b4"], "design": {"layout": {"columns": 3}},
    }])
    assert rejected and "no effect on" in rejected[0]["reason"] and "b1" in rejected[0]["reason"]


def test_set_design_bulk_refused_on_non_premium():
    valid, rejected = validate_ops(
        [{"op": "set_design_bulk", "blocks": ["b1"], "design": {"bg": {"overlay": "dark"}}}],
        _BLOCKS, premium=False,
    )
    assert not valid and "Pro feature" in rejected[0]["reason"]


# --- same-turn refs: add_block(id=...) resolved by later ops in this turn -----

def test_add_block_with_id_then_set_field_same_turn():
    valid, rejected = _only([
        {"op": "add_block", "type": "hero", "at": 0, "id": "new-1"},
        {"op": "set_field", "block": "new-1", "path": "heading", "value": "Hi"},
    ])
    assert not rejected
    assert len(valid) == 2


def test_add_block_with_id_then_set_design_same_turn():
    valid, rejected = _only([
        {"op": "add_block", "type": "hero", "at": 0, "id": "new-1"},
        {"op": "set_design", "block": "new-1", "group": "motion", "key": "heading", "value": "shimmer"},
    ])
    assert not rejected
    assert len(valid) == 2


def test_add_block_with_id_then_generate_image_same_turn():
    valid, rejected = _only([
        {"op": "add_block", "type": "hero", "at": 0, "id": "new-1"},
        {"op": "generate_image", "block": "new-1", "prompt": "a mountain sunrise"},
    ])
    assert not rejected
    assert len(valid) == 2


def test_add_block_id_collides_with_existing_block_rejected():
    _, rejected = _only([{"op": "add_block", "type": "hero", "at": 0, "id": "b1"}])
    assert rejected and "collides" in rejected[0]["reason"]


def test_add_block_id_collides_with_earlier_same_turn_add_rejected():
    valid, rejected = _only([
        {"op": "add_block", "type": "hero", "at": 0, "id": "new-1"},
        {"op": "add_block", "type": "faq", "at": 1, "id": "new-1"},
    ])
    assert len(valid) == 1
    assert rejected and "collides" in rejected[0]["reason"]


def test_op_before_its_defining_add_block_is_not_found():
    """Ops validate in order — a reference to an id its add_block hasn't
    registered yet (because it comes later in the list) degrades to the
    ordinary 'not found', not a special ordering error."""
    valid, rejected = _only([
        {"op": "set_field", "block": "new-1", "path": "heading", "value": "Hi"},
        {"op": "add_block", "type": "hero", "at": 0, "id": "new-1"},
    ])
    assert len(valid) == 1
    assert rejected and "not found" in rejected[0]["reason"]


def test_add_block_non_string_id_rejected():
    _, rejected = _only([{"op": "add_block", "type": "hero", "at": 0, "id": 123}])
    assert rejected and "'id' must be a string" in rejected[0]["reason"]


# --- theme swaps need explicit intent ----------------------------------------

def test_preset_swap_refused_without_theme_intent():
    """A whole-site restyle must not ride along on an unrelated request — this
    is what turned "animate this text" into a theme change."""
    valid, rejected = validate_ops(
        [{"op": "set_theme", "key": "preset", "value": "studio"}], _BLOCKS, theme_intent=False,
    )
    assert not valid and "unless you ask" in rejected[0]["reason"]


def test_preset_swap_allowed_when_the_user_asked_for_a_theme():
    valid, rejected = validate_ops(
        [{"op": "set_theme", "key": "preset", "value": "studio"}], _BLOCKS, theme_intent=True,
    )
    assert len(valid) == 1 and not rejected


def test_non_preset_theme_keys_are_unaffected_by_intent_gate():
    # Narrow theme tweaks (a brand color) stay available — only the whole-site
    # preset swap is gated.
    valid, rejected = validate_ops(
        [{"op": "set_theme", "key": "colors.brand", "value": "#112233"}], _BLOCKS, theme_intent=False,
    )
    assert len(valid) == 1 and not rejected
