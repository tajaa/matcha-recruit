"""Pure-function + source-guard tests for the Tell-Us flyer design assistant.
No DB, no HTTP, no Gemini — same shape as test_promo_cards.py.
"""
import inspect
import json
import pathlib

from app.tellus.dependencies import require_paid_brand
from app.tellus.models.flyer_ai import FlyerAiSelection
from app.tellus.routes import flyer_ai as flyer_ai_routes
from app.tellus.routes import promo as promo_routes
from app.tellus.services.flyer_ai import apply as flyer_apply
from app.tellus.services.flyer_ai import catalog, layouts, ops, palettes, turn

WEB_PACK = pathlib.Path(__file__).resolve().parents[3] / "client" / "tellus" / "public" / "designer"

CAMPAIGN = {"title": "Today only: free coffee", "reward_text": "One free coffee", "description": None}


def _design():
    """A minimal but realistic flyer_letter document: headline, block, QR."""
    return {
        "version": 1,
        "artboard": {"preset": "flyer_letter", "w": 1275, "h": 1650},
        "background": {"kind": "color", "color": "paper"},
        "palette": dict(palettes.PALETTES_BY_KEY["warm-paper"].colors),
        "layers": [
            {
                "id": "head", "type": "text", "x": 100, "y": 200, "rotation": 0, "opacity": 1,
                "text": "Free coffee", "fontFamily": "Helvetica Neue", "fontSize": 90,
                "fontStyle": "bold", "fill": "ink", "align": "center", "width": 1000,
                "lineHeight": 1.15, "letterSpacing": 0,
            },
            {
                "id": "block", "type": "shape", "shape": "rect", "x": 100, "y": 500,
                "rotation": 0, "opacity": 1, "width": 400, "height": 200, "fill": "brand",
                "cornerRadius": 12,
            },
            {
                "id": "qr", "type": "qr", "x": 437, "y": 1000, "rotation": 0, "opacity": 1,
                "size": 400, "fg": "#17140f", "bg": "#ffffff",
            },
        ],
    }


def _all_function_source(module) -> str:
    """Concatenated source of every function defined in `module`, excluding the
    module docstring — so a guard asserts on what the CODE does without tripping
    on prose describing what it avoids."""
    return "\n".join(
        inspect.getsource(obj)
        for _, obj in inspect.getmembers(module, inspect.isfunction)
        if obj.__module__ == module.__name__
    )


def _valid(raw_ops, design=None):
    return ops.validate_ops(raw_ops, design or _design(), CAMPAIGN)


class TestValidateOps:
    def test_unknown_layer_id_rejected(self):
        valid, rejected = _valid([{"op": "set_layer", "layer": "nope", "path": "fill", "value": "brand"}])
        assert valid == []
        assert "no layer" in rejected[0]["reason"]

    def test_non_string_layer_id_rejected_not_raised(self):
        # A hallucinated dict as an id would raise TypeError: unhashable on a
        # bare dict lookup and 500 the whole turn over one bad op.
        valid, rejected = _valid([{"op": "set_layer", "layer": {}, "path": "fill", "value": "brand"}])
        assert valid == [] and len(rejected) == 1

    def test_unknown_op_rejected(self):
        valid, rejected = _valid([{"op": "drop_database"}])
        assert valid == [] and "unknown op" in rejected[0]["reason"]

    def test_token_colour_accepted(self):
        valid, _ = _valid([{"op": "set_layer", "layer": "head", "path": "fill", "value": "brand"}])
        assert len(valid) == 1

    def test_hex_colour_accepted(self):
        valid, _ = _valid([{"op": "set_layer", "layer": "head", "path": "fill", "value": "#abc"}])
        assert len(valid) == 1

    def test_garbage_colour_rejected(self):
        valid, rejected = _valid([{"op": "set_layer", "layer": "head", "path": "fill", "value": "reddish"}])
        assert valid == [] and "hex colour" in rejected[0]["reason"]

    def test_unknown_field_for_kind_rejected(self):
        valid, rejected = _valid([{"op": "set_layer", "layer": "block", "path": "fontSize", "value": 40}])
        assert valid == [] and "no 'fontSize' field" in rejected[0]["reason"]

    def test_out_of_range_value_rejected(self):
        valid, rejected = _valid([{"op": "set_layer", "layer": "head", "path": "fontSize", "value": 9000}])
        assert valid == [] and "between" in rejected[0]["reason"]

    def test_unknown_font_rejected(self):
        valid, rejected = _valid([{"op": "set_layer", "layer": "head", "path": "fontFamily", "value": "Comic Sans MS"}])
        assert valid == [] and "must be one of" in rejected[0]["reason"]

    def test_ios_absent_font_rejected(self):
        # Impact ships on web but not iOS; a design authored on one and exported
        # from the other would reflow. The model is pinned to the portable set.
        valid, rejected = _valid([{"op": "set_layer", "layer": "head", "path": "fontFamily", "value": "Impact"}])
        assert valid == [] and rejected

    def test_bool_is_not_a_number(self):
        # True is an int in Python, so an unguarded range check accepts it.
        valid, rejected = _valid([{"op": "move_layer", "layer": "head", "x": True, "y": 10}])
        assert valid == [] and rejected

    def test_move_out_of_bounds_rejected(self):
        valid, rejected = _valid([{"op": "move_layer", "layer": "qr", "x": 1200, "y": 100}])
        assert valid == [] and "outside the page" in rejected[0]["reason"]

    def test_negative_coordinate_rejected(self):
        valid, rejected = _valid([{"op": "move_layer", "layer": "qr", "x": -10, "y": 100}])
        assert valid == [] and rejected

    def test_move_in_bounds_accepted(self):
        valid, _ = _valid([{"op": "move_layer", "layer": "qr", "x": 100, "y": 100}])
        assert len(valid) == 1

    def test_resize_off_page_rejected(self):
        valid, rejected = _valid([{"op": "resize_layer", "layer": "qr", "width": 1900}])
        assert valid == [] and rejected

    def test_over_max_ops_truncated_and_reported(self):
        many = [{"op": "set_layer", "layer": "head", "path": "fontSize", "value": 40}] * 40
        valid, rejected = _valid(many)
        assert len(valid) == catalog.MAX_OPS_PER_TURN
        # Reported, never silent — a truncated turn that says nothing reads as
        # "everything applied".
        assert rejected and str(catalog.MAX_OPS_PER_TURN) in rejected[0]["reason"]


class TestAddLayer:
    def test_image_layer_cannot_be_added(self):
        # `src` is a URL; letting a model author one turns the document into an
        # arbitrary-fetch primitive.
        valid, rejected = _valid([{
            "op": "add_layer", "kind": "image", "x": 10, "y": 10,
            "width": 100, "height": 100, "src": "https://example.com/x.png",
        }])
        assert valid == [] and "kind must be one of" in rejected[0]["reason"]

    def test_missing_required_field_rejected(self):
        valid, rejected = _valid([{"op": "add_layer", "kind": "text", "x": 10, "y": 10}])
        assert valid == [] and "needs" in rejected[0]["reason"]

    def test_unknown_sticker_rejected(self):
        valid, rejected = _valid([{
            "op": "add_layer", "kind": "sticker", "assetId": "dragon.svg",
            "x": 10, "y": 10, "width": 100, "height": 100,
        }])
        assert valid == [] and rejected

    def test_temp_id_registers_for_a_later_op_in_the_same_turn(self):
        valid, rejected = _valid([
            {"op": "add_layer", "kind": "text", "id": "new-1", "x": 100, "y": 100,
             "text": "Hi", "fontSize": 40, "width": 400},
            {"op": "set_layer", "layer": "new-1", "path": "fill", "value": "brand"},
        ])
        assert len(valid) == 2 and rejected == []


class TestQrInvariants:
    def test_remove_last_qr_rejected(self):
        valid, rejected = _valid([{"op": "remove_layer", "layer": "qr"}])
        assert valid == [] and "only claim QR" in rejected[0]["reason"]

    def test_remove_qr_allowed_when_a_second_exists(self):
        design = _design()
        second = dict(design["layers"][2])
        second["id"] = "qr2"
        second["y"] = 500
        design["layers"].append(second)
        valid, _ = _valid([{"op": "remove_layer", "layer": "qr"}], design)
        assert len(valid) == 1

    def test_low_contrast_qr_colour_rejected(self):
        valid, rejected = _valid([{"op": "set_layer", "layer": "qr", "path": "fg", "value": "#f2f2f2"}])
        assert valid == [] and "contrast" in rejected[0]["reason"]

    def test_high_contrast_qr_colour_accepted(self):
        valid, _ = _valid([{"op": "set_layer", "layer": "qr", "path": "fg", "value": "#101010"}])
        assert len(valid) == 1

    def test_removing_a_non_qr_layer_is_fine(self):
        valid, _ = _valid([{"op": "remove_layer", "layer": "block"}])
        assert len(valid) == 1


class TestOpExpansion:
    def test_set_palette_rewritten_to_values(self):
        valid, _ = _valid([{"op": "set_palette", "preset": "midnight"}])
        assert valid[0]["op"] == "set_palette_values"
        assert valid[0]["palette"] == palettes.PALETTES_BY_KEY["midnight"].colors

    def test_unknown_palette_rejected(self):
        valid, rejected = _valid([{"op": "set_palette", "preset": "neon-vaporwave"}])
        assert valid == [] and "unknown palette" in rejected[0]["reason"]

    def test_apply_layout_rewritten_to_set_document(self):
        valid, rejected = _valid([{"op": "apply_layout", "layout": "counter-card", "palette": "midnight"}])
        assert rejected == []
        assert valid[0]["op"] == "set_document"
        assert valid[0]["design"]["artboard"]["preset"] == "reward_card"

    def test_unknown_layout_rejected(self):
        valid, rejected = _valid([{"op": "apply_layout", "layout": "nope"}])
        assert valid == [] and "unknown layout" in rejected[0]["reason"]

    def test_ops_after_a_layout_are_checked_against_the_new_document(self):
        # The replacement wipes every id the turn started with.
        valid, rejected = _valid([
            {"op": "apply_layout", "layout": "counter-card"},
            {"op": "set_layer", "layer": "head", "path": "fill", "value": "brand"},
        ])
        assert len(valid) == 1 and len(rejected) == 1


class TestValidateDocument:
    def test_accepts_a_good_document(self):
        assert ops.validate_document(_design()) is None

    def test_rejects_a_document_with_no_qr(self):
        design = _design()
        design["layers"] = design["layers"][:2]
        assert "claim QR" in ops.validate_document(design)

    def test_rejects_mismatched_artboard_size(self):
        design = _design()
        design["artboard"]["w"] = 999
        assert "artboard size" in ops.validate_document(design)

    def test_rejects_duplicate_layer_ids(self):
        design = _design()
        design["layers"][1]["id"] = "head"
        assert "unique id" in ops.validate_document(design)

    def test_rejects_partial_palette(self):
        design = _design()
        design["palette"].pop("muted")
        assert "exactly" in ops.validate_document(design)

    def test_rejects_oversize_document(self):
        # The cap applies to the MODEL's output, not just the human PUT — else
        # the assistant is the way around the limit the save path enforces.
        design = _design()
        design["layers"][0]["text"] = "x" * 200
        design["layers"] = [dict(design["layers"][0], id=f"t{i}") for i in range(3000)] + design["layers"][2:]
        assert "too large" in ops.validate_document(design)


class TestApplyOps:
    def test_caller_document_is_not_mutated(self):
        design = _design()
        before = json.dumps(design, sort_keys=True)
        valid, _ = _valid([{"op": "set_layer", "layer": "head", "path": "fill", "value": "brand"}])
        flyer_apply.apply_ops(design, valid)
        assert json.dumps(design, sort_keys=True) == before

    def test_set_layer_applies(self):
        valid, _ = _valid([{"op": "set_layer", "layer": "head", "path": "fill", "value": "brand"}])
        out, results = flyer_apply.apply_ops(_design(), valid)
        assert out["layers"][0]["fill"] == "brand"
        assert results[0]["ok"] is True

    def test_temp_id_resolves_at_apply_time(self):
        valid, _ = _valid([
            {"op": "add_layer", "kind": "text", "id": "new-1", "x": 100, "y": 100,
             "text": "Hi", "fontSize": 40, "width": 400},
            {"op": "set_layer", "layer": "new-1", "path": "fill", "value": "accent"},
        ])
        out, results = flyer_apply.apply_ops(_design(), valid)
        assert all(r["ok"] for r in results)
        assert out["layers"][-1]["fill"] == "accent"
        # The temp name is never persisted — two turns could both say "new-1".
        assert out["layers"][-1]["id"] != "new-1"

    def test_vanished_target_degrades_rather_than_raising(self):
        out, results = flyer_apply.apply_ops(
            _design(), [{"op": "set_layer", "layer": "ghost", "path": "fill", "value": "brand"}],
        )
        assert results[0]["ok"] is False and "no longer exists" in results[0]["summary"]
        assert len(out["layers"]) == 3

    def test_results_length_matches_ops_length(self):
        valid, _ = _valid([
            {"op": "set_layer", "layer": "head", "path": "fill", "value": "brand"},
            {"op": "move_layer", "layer": "block", "x": 120, "y": 520},
        ])
        _, results = flyer_apply.apply_ops(_design(), valid)
        assert len(results) == len(valid) == 2

    def test_set_palette_values_applies(self):
        valid, _ = _valid([{"op": "set_palette", "preset": "mono-ink"}])
        out, _ = flyer_apply.apply_ops(_design(), valid)
        assert out["palette"]["paper"] == "#ffffff"

    def test_set_document_replaces_wholesale(self):
        valid, _ = _valid([{"op": "apply_layout", "layout": "social-drop"}])
        out, _ = flyer_apply.apply_ops(_design(), valid)
        assert out["artboard"]["preset"] == "social_square"
        assert ops.validate_document(out) is None


class TestSelectionDegrades:
    def test_unknown_kind_degrades_instead_of_422(self):
        sel = FlyerAiSelection.model_validate({"layer": "head", "kind": "sparkle"})
        assert sel.kind is None

    def test_overlong_text_is_truncated(self):
        sel = FlyerAiSelection.model_validate({"layer": "head", "text": "x" * 900})
        assert len(sel.text) == 300


class TestSourceGuards:
    def test_no_direct_genai_client_construction(self):
        # get_genai_client is the house factory; it also wraps usage logging.
        assert "genai.Client(" not in _all_function_source(turn)

    def test_no_literal_model_id(self):
        src = inspect.getsource(turn)
        assert '"gemini-' not in src and "'gemini-" not in src

    def test_record_call_sits_in_a_finally(self):
        src = inspect.getsource(turn._generate)
        assert src.index("finally:") < src.index("record_call")

    def test_cost_guard_runs_before_any_generation(self):
        src = inspect.getsource(turn.run_flyer_turn)
        assert src.index("check_limit") < src.index("_build_prompt")

    def test_byte_cap_applied_to_model_output(self):
        assert "DESIGN_MAX_BYTES" in inspect.getsource(ops.validate_document)

    def test_gemini_call_is_not_inside_a_db_connection(self):
        # A pool connection held across a model turn is the flyer-upload rule,
        # an order of magnitude worse: turns take seconds.
        src = inspect.getsource(flyer_ai_routes.assist_design)
        assert "get_connection" not in src
        assert "_campaign_for" in src
        assert src.index("_campaign_for") < src.index("run_flyer_turn")

    def test_ownership_checked_before_the_model_runs(self):
        src = inspect.getsource(flyer_ai_routes._campaign_for)
        assert "assert_campaign_owned" in src

    def test_validate_ops_never_raises_on_a_bad_op(self):
        assert "except Exception" in inspect.getsource(ops.validate_ops)


class TestRateLimits:
    def test_assist_limits_pinned(self):
        src = inspect.getsource(flyer_ai_routes.assist_design)
        assert '"tellus_flyer_ai_burst", 5, 60' in src
        assert '"tellus_flyer_ai", 60, 3600' in src

    def test_ideas_limits_pinned(self):
        src = inspect.getsource(flyer_ai_routes.design_ideas)
        assert '"tellus_flyer_ideas", 30, 3600' in src


class TestBrandGateSweep:
    def test_every_route_requires_paid_brand(self):
        for route in flyer_ai_routes.router.routes:
            deps = [d.call for d in route.dependant.dependencies]
            assert require_paid_brand in deps, f"{route.path} is not require_paid_brand-gated"

    def test_route_count_is_pinned(self):
        assert len(flyer_ai_routes.router.routes) == 3


class TestCatalogParity:
    def test_palette_presets_match_the_web_pack(self):
        # palettes.py duplicates palettes.json because the backend image ships
        # server/ only — a read out of the client tree works locally and 500s in
        # prod. This is what keeps the duplication honest.
        web = json.loads((WEB_PACK / "palettes.json").read_text())
        assert [p["key"] for p in web] == [p.key for p in palettes.PALETTES]
        for entry, preset in zip(web, palettes.PALETTES):
            assert entry["colors"] == preset.colors, entry["key"]

    def test_every_palette_defines_exactly_the_tokens(self):
        for preset in palettes.PALETTES:
            assert set(preset.colors) == set(catalog.PALETTE_TOKENS), preset.key

    def test_every_palette_value_is_hex(self):
        for preset in palettes.PALETTES:
            for token, value in preset.colors.items():
                assert catalog.HEX_RE.match(value), f"{preset.key}.{token}"

    def test_font_families_are_a_subset_of_the_web_manifest(self):
        web = {entry["family"] for entry in json.loads((WEB_PACK / "fonts" / "index.json").read_text())}
        assert catalog.FONT_FAMILIES <= web

    def test_sticker_ids_match_the_web_pack(self):
        web = {entry["file"] for entry in json.loads((WEB_PACK / "stickers" / "index.json").read_text())}
        assert catalog.STICKER_IDS == web

    def test_design_cap_matches_the_save_path(self):
        assert catalog.DESIGN_MAX_BYTES == promo_routes._DESIGN_MAX_BYTES

    def test_every_layout_validates_under_every_palette(self):
        # The recipe drift-gate: a layout is put through the SAME validator the
        # model's own set_document output passes, on every palette, so an
        # authoring slip fails here rather than shipping an unusable idea.
        for layout in layouts.LAYOUTS:
            for preset in palettes.PALETTES:
                doc = layout.build(CAMPAIGN, dict(preset.colors))
                assert ops.validate_document(doc) is None, f"{layout.key}/{preset.key}"

    def test_layout_colours_are_tokens_never_hex(self):
        # A token-only layout is correct under every palette, which is why one
        # layout doesn't need five variants. The two exemptions are both about
        # the QR: its own fg/bg, and the white pad drawn behind it — contrast
        # there is a scanning requirement, not a taste call.
        allowed = set(catalog.PALETTE_TOKENS) | {layouts.QR_BG, layouts.QR_FG}
        for layout in layouts.LAYOUTS:
            doc = layout.build(CAMPAIGN, dict(palettes.PALETTES[0].colors))
            assert doc["background"]["color"] in catalog.PALETTE_TOKENS
            for layer in doc["layers"]:
                if layer["type"] == "qr":
                    continue
                for key in ("fill", "stroke"):
                    value = layer.get(key)
                    if value is not None:
                        assert value in allowed, f"{layout.key}:{layer['id']}.{key}"

    def test_layout_fonts_are_model_safe(self):
        for layout in layouts.LAYOUTS:
            doc = layout.build(CAMPAIGN, dict(palettes.PALETTES[0].colors))
            for layer in doc["layers"]:
                if layer["type"] == "text":
                    assert layer["fontFamily"] in catalog.FONT_FAMILIES


class TestPromptGeneration:
    def test_op_shapes_come_from_the_registry(self):
        text = ops.op_shapes_text()
        for op in ops.FLYER_OPS:
            if op.prompt_shape:
                assert op.prompt_shape in text

    def test_rules_come_from_the_registry(self):
        # Generated, not hand-maintained: a rule can't drift from the op it
        # governs because it is carried on that op's entry.
        rules = ops.op_rules_text()
        expected = [r for op in ops.FLYER_OPS for r in op.prompt_rules]
        assert rules == expected

    def test_the_qr_protection_rule_reaches_the_model(self):
        # The validator refuses to remove the last QR; without the matching rule
        # the model would keep proposing it and keep being told no.
        assert any("claim QR" in r for r in ops.op_rules_text())

    def test_prompt_carries_the_campaign_copy(self):
        prompt = turn._build_prompt(
            message="make it bolder", design=_design(), campaign=CAMPAIGN,
            history=[], selection=None, feedback=None,
        )
        assert CAMPAIGN["reward_text"] in prompt
        assert "SELECTED: nothing" in prompt

    def test_selection_line_names_the_selected_layer(self):
        prompt = turn._build_prompt(
            message="bigger", design=_design(), campaign=CAMPAIGN,
            history=[], selection={"layer": "head"}, feedback=None,
        )
        assert "SELECTED: layer head" in prompt
