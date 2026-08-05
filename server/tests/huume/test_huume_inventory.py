"""Pure-function tests for the inventory-ops staged actions (no DB/Gemini).

    cd server && ./venv/bin/python -m pytest tests/huume/test_huume_inventory.py -q

Covers `evaluate_huume_action`'s inventory_movement / inventory_order_decision /
inventory_item_create / inventory_item_archive / inventory_receipt branches,
the registry entries in `_HR_OPS_TOOL_SPECS`, and the state-block lines that
echo the id each confirm turn must pass back. Mirrors `test_huume_hr_ops.py`'s
shape. `stage_inventory_order` (a plain WRITE tool, not staged) is
deliberately absent from `_HR_OPS_TOOL_SPECS` and so absent from these
registry checks — its DB-bound writer lives in `inventory_skill.stage_order`.
"""

from app.matcha.services.huume.actions import evaluate_huume_action
from app.matcha.services.huume.agent import _HR_OPS_TOOL_SPECS, _build_hr_ops_staged
from app.matcha.services.huume.prompt import build_state_block
from app.matcha.services.huume.tools import TOOLS_BY_NAME

BASE_ON = {"huume": True, "matcha_work": True, "inventory": True}
ITEM_ID = "3f6b1c22-1000-4000-8000-000000000001"
ORDER_ID = "3f6b1c22-1000-4000-8000-000000000002"
LOCATION_ID = "3f6b1c22-1000-4000-8000-000000000003"


def _features(**extra):
    return {**BASE_ON, **extra}


def _movement(**overrides):
    # kind defaults to "out" — "in" is refused (provenance invariant: a
    # received movement must come from an order receive or a receipt commit,
    # never a bare staged movement; see TestMovementValidation.test_kind_in_refuses_with_steering).
    base = {"type": "inventory_movement", "status": "proposed", "confirm_id": "aa11bb22",
            "kind": "out", "item_id": ITEM_ID, "quantity": 12}
    base.update(overrides)
    return base


def _order_decision(**overrides):
    base = {"type": "inventory_order_decision", "status": "proposed",
            "order_id": ORDER_ID, "decision": "approve"}
    base.update(overrides)
    return base


def _item_create(**overrides):
    base = {"type": "inventory_item_create", "status": "proposed", "confirm_id": "cc33dd44",
            "name": "Nitrile Gloves (M)"}
    base.update(overrides)
    return base


def _item_archive(**overrides):
    base = {"type": "inventory_item_archive", "status": "proposed", "item_id": ITEM_ID}
    base.update(overrides)
    return base


def _receipt(**overrides):
    base = {"type": "inventory_receipt", "status": "proposed", "confirm_id": "ee55ff66",
            "lines": [{"item_id": ITEM_ID, "quantity": 10}]}
    base.update(overrides)
    return base


def _evaluate(staged, features, *, role="client", staged_new=False):
    return evaluate_huume_action(
        staged_action=staged, features=features, role=role,
        thread_huume_mode=True, this_turn_staged_new=staged_new,
    )


class TestStageAndAuthz:
    """The shared envelope: fresh call stages, gates refuse BEFORE staging."""

    CASES = [_movement(), _order_decision(), _item_create(), _item_archive(), _receipt()]

    def test_fresh_call_stages(self):
        for staged in self.CASES:
            verdict = _evaluate(staged, _features(), staged_new=True)
            assert verdict.kind == "stage", staged["type"]
            assert not verdict.ok

    def test_confirm_turn_proceeds(self):
        for staged in self.CASES:
            verdict = _evaluate(staged, _features())
            assert verdict.ok, staged["type"]
            assert verdict.action["type"] == staged["type"]

    def test_missing_inventory_flag_refuses_even_when_staging(self):
        for staged in self.CASES:
            verdict = _evaluate(staged, _features(inventory=False), staged_new=True)
            assert verdict.kind == "refuse", staged["type"]
            assert "inventory" in verdict.message

    def test_employee_role_refused(self):
        for staged in self.CASES:
            verdict = _evaluate(staged, _features(), role="employee", staged_new=True)
            assert verdict.kind == "refuse", staged["type"]
            assert "business admin" in verdict.message

    def test_non_proposed_status_refused(self):
        for staged in self.CASES:
            done = {**staged, "status": "recorded"}
            verdict = _evaluate(done, _features())
            assert verdict.kind == "refuse", staged["type"]


class TestMovementValidation:
    def test_unknown_kind_refuses(self):
        verdict = _evaluate(_movement(kind="teleport"), _features())
        assert verdict.kind == "refuse"

    def test_neither_item_id_nor_new_name_refuses(self):
        verdict = _evaluate(_movement(item_id=None), _features())
        assert verdict.kind == "refuse"

    def test_non_uuid_item_id_refuses(self):
        verdict = _evaluate(_movement(item_id="the gloves"), _features())
        assert verdict.kind == "refuse"

    def test_new_item_name_accepted_without_item_id(self):
        verdict = _evaluate(_movement(item_id=None, new_item_name="Cherry Farms Cookies"), _features())
        assert verdict.ok
        assert verdict.action["new_item_name"] == "Cherry Farms Cookies"

    def test_zero_quantity_refuses_for_out(self):
        verdict = _evaluate(_movement(kind="out", quantity=0), _features())
        assert verdict.kind == "refuse"

    def test_kind_in_refuses_with_steering(self):
        """Provenance invariant: a received-stock movement can't be staged
        from chat at all — refuse with a message naming the two real exits,
        not the generic 'tell me the kind' refusal."""
        verdict = _evaluate(_movement(kind="in"), _features())
        assert verdict.kind == "refuse"
        assert "decide_inventory_order" in verdict.message
        assert "stage_receipt_from_attachment" in verdict.message

    def test_negative_quantity_refuses_for_out(self):
        verdict = _evaluate(_movement(kind="out", quantity=-5), _features())
        assert verdict.kind == "refuse"

    def test_missing_quantity_refuses_for_adjust(self):
        verdict = _evaluate(_movement(kind="adjust", quantity=None), _features())
        assert verdict.kind == "refuse"

    def test_zero_quantity_accepted_for_adjust(self):
        # A physical count really can be zero — distinct from `stockout`,
        # which force-sets to zero regardless of what's passed.
        verdict = _evaluate(_movement(kind="adjust", quantity=0), _features())
        assert verdict.ok
        assert verdict.action["quantity"] == 0.0

    def test_stockout_ignores_quantity(self):
        verdict = _evaluate(_movement(kind="stockout", quantity="whatever"), _features())
        assert verdict.ok
        assert verdict.action["quantity"] is None

    def test_bad_location_id_refuses(self):
        verdict = _evaluate(_movement(location_id="the wilshire store"), _features())
        assert verdict.kind == "refuse"

    def test_valid_location_id_kept(self):
        verdict = _evaluate(_movement(location_id=LOCATION_ID), _features())
        assert verdict.ok
        assert verdict.action["location_id"] == LOCATION_ID

    def test_note_truncated(self):
        verdict = _evaluate(_movement(note="x" * 500), _features())
        assert verdict.ok
        assert len(verdict.action["note"]) == 200


class TestOrderDecisionValidation:
    def test_non_uuid_order_id_refuses(self):
        verdict = _evaluate(_order_decision(order_id="the gloves order"), _features())
        assert verdict.kind == "refuse"
        assert "lookup_context" in verdict.message

    def test_unknown_decision_refuses(self):
        verdict = _evaluate(_order_decision(decision="expedite"), _features())
        assert verdict.kind == "refuse"

    def test_receive_with_quantity_proceeds(self):
        verdict = _evaluate(_order_decision(decision="receive", quantity=8), _features())
        assert verdict.ok
        assert verdict.action["quantity"] == 8.0

    def test_receive_without_quantity_proceeds(self):
        verdict = _evaluate(_order_decision(decision="receive"), _features())
        assert verdict.ok
        assert verdict.action["quantity"] is None

    def test_bad_quantity_refuses(self):
        verdict = _evaluate(_order_decision(decision="receive", quantity=-3), _features())
        assert verdict.kind == "refuse"

    def test_cancel_proceeds(self):
        verdict = _evaluate(_order_decision(decision="cancel"), _features())
        assert verdict.ok


class TestItemCreateValidation:
    def test_empty_name_refuses(self):
        verdict = _evaluate(_item_create(name="   "), _features())
        assert verdict.kind == "refuse"

    def test_bad_initial_quantity_refuses(self):
        verdict = _evaluate(_item_create(initial_quantity=-1), _features())
        assert verdict.kind == "refuse"

    def test_bad_location_id_refuses(self):
        verdict = _evaluate(_item_create(location_id="somewhere"), _features())
        assert verdict.kind == "refuse"

    def test_valid_payload_proceeds(self):
        verdict = _evaluate(_item_create(unit="BX", initial_quantity=10, low_stock_threshold=2), _features())
        assert verdict.ok
        assert verdict.action["name"] == "Nitrile Gloves (M)"
        assert verdict.action["initial_quantity"] == 10.0


class TestItemArchiveValidation:
    def test_non_uuid_item_id_refuses(self):
        verdict = _evaluate(_item_archive(item_id="the cookies"), _features())
        assert verdict.kind == "refuse"

    def test_valid_payload_proceeds(self):
        verdict = _evaluate(_item_archive(), _features())
        assert verdict.ok
        assert verdict.action["item_id"] == ITEM_ID


class TestReceiptValidation:
    def test_empty_lines_refuses(self):
        verdict = _evaluate(_receipt(lines=[]), _features())
        assert verdict.kind == "refuse"

    def test_missing_lines_refuses(self):
        staged = _receipt()
        del staged["lines"]
        verdict = _evaluate(staged, _features())
        assert verdict.kind == "refuse"

    def test_too_many_lines_refuses(self):
        verdict = _evaluate(_receipt(lines=[{"item_id": ITEM_ID, "quantity": 1}] * 201), _features())
        assert verdict.kind == "refuse"

    def test_valid_payload_proceeds(self):
        verdict = _evaluate(_receipt(vendor="Henry Schein", invoice_number="INV-1"), _features())
        assert verdict.ok
        assert verdict.action["vendor"] == "Henry Schein"
        assert len(verdict.action["lines"]) == 1

    def test_dup_warning_not_forwarded_to_executor_action(self):
        # dup_warning is model/state-block-facing only — the executor always
        # commits (the confirm turn IS the override, no separate force flag).
        verdict = _evaluate(_receipt(dup_warning="Invoice INV-1 looks already received."), _features())
        assert verdict.ok
        assert "dup_warning" not in verdict.action


class TestBuildHrOpsStaged:
    """The two-turn confirm match, compared against the TURN-START snapshot."""

    def test_movement_no_pre_turn_action_stages_new(self):
        spec = _HR_OPS_TOOL_SPECS["record_stock_movement"]
        staged, confirming = _build_hr_ops_staged(spec, {"kind": "out", "item_id": ITEM_ID, "quantity": 12}, None)
        assert confirming is False
        assert staged["status"] == "proposed"
        assert len(staged["confirm_id"]) == 8

    def test_movement_echoed_confirm_id_confirms(self):
        spec = _HR_OPS_TOOL_SPECS["record_stock_movement"]
        existing = _movement()
        staged, confirming = _build_hr_ops_staged(
            spec, {"kind": "out", "item_id": ITEM_ID, "quantity": 12, "confirm_id": existing["confirm_id"]}, existing,
        )
        assert confirming is True
        assert staged is existing

    def test_movement_changed_quantity_restages_instead_of_executing_stale(self):
        """The bug: admin stages 'out 12', then says 'actually 20' — the model
        calls with the SAME confirm_id but quantity=20. Matching on
        confirm_id alone would return `existing` (quantity=12) with
        confirming=True, silently recording the wrong number."""
        spec = _HR_OPS_TOOL_SPECS["record_stock_movement"]
        existing = _movement(quantity=12)
        staged, confirming = _build_hr_ops_staged(
            spec, {"kind": "out", "item_id": ITEM_ID, "quantity": 20, "confirm_id": existing["confirm_id"]}, existing,
        )
        assert confirming is False
        assert staged["quantity"] == 20

    def test_movement_changed_kind_restages_instead_of_executing_stale(self):
        spec = _HR_OPS_TOOL_SPECS["record_stock_movement"]
        existing = _movement(kind="out")
        staged, confirming = _build_hr_ops_staged(
            spec, {"kind": "adjust", "item_id": ITEM_ID, "quantity": 12, "confirm_id": existing["confirm_id"]}, existing,
        )
        assert confirming is False
        assert staged["kind"] == "adjust"

    def test_order_decision_matches_on_order_id(self):
        spec = _HR_OPS_TOOL_SPECS["decide_inventory_order"]
        existing = _order_decision()
        _, confirming = _build_hr_ops_staged(spec, {"order_id": ORDER_ID, "decision": "approve"}, existing)
        assert confirming is True

    def test_order_decision_changed_decision_restages(self):
        spec = _HR_OPS_TOOL_SPECS["decide_inventory_order"]
        existing = _order_decision(decision="approve")
        staged, confirming = _build_hr_ops_staged(
            spec, {"order_id": ORDER_ID, "decision": "cancel"}, existing,
        )
        assert confirming is False
        assert staged["decision"] == "cancel"

    def test_item_archive_matches_on_item_id_natural_key(self):
        spec = _HR_OPS_TOOL_SPECS["archive_inventory_item"]
        staged, _ = _build_hr_ops_staged(spec, {"item_id": ITEM_ID}, None)
        assert "confirm_id" not in staged   # has a natural id already

    def test_receipt_confirm_reuses_staged_lines_verbatim(self):
        """The model never re-supplies `lines` on the confirm call (they
        aren't even a declared tool parameter) — reusing `existing` unchanged
        is what makes that safe."""
        spec = _HR_OPS_TOOL_SPECS["stage_receipt_from_attachment"]
        existing = _receipt(lines=[{"item_id": ITEM_ID, "quantity": 10}, {"new_item_name": "Floss", "quantity": 3}])
        staged, confirming = _build_hr_ops_staged(
            spec, {"confirm_id": existing["confirm_id"]}, existing,
        )
        assert confirming is True
        assert staged is existing
        assert len(staged["lines"]) == 2


class TestRegistry:
    INVENTORY_STAGED_TOOLS = (
        "record_stock_movement", "decide_inventory_order",
        "create_inventory_item", "archive_inventory_item", "stage_receipt_from_attachment",
    )

    def test_all_inventory_staged_tools_declared_and_staged(self):
        for name in self.INVENTORY_STAGED_TOOLS:
            tool = TOOLS_BY_NAME.get(name)
            assert tool is not None, name
            assert tool.kind == "staged", name
            assert name in _HR_OPS_TOOL_SPECS, name

    def test_stage_inventory_order_is_a_plain_write_tool(self):
        tool = TOOLS_BY_NAME.get("stage_inventory_order")
        assert tool is not None
        assert tool.kind == "write"
        assert "stage_inventory_order" not in _HR_OPS_TOOL_SPECS

    def test_required_params_declared(self):
        expected = {
            "record_stock_movement": {"kind"},
            "decide_inventory_order": {"order_id", "decision"},
            "create_inventory_item": {"name"},
            "archive_inventory_item": {"item_id"},
            "stage_receipt_from_attachment": set(),
        }
        for name, required in expected.items():
            declared = set(TOOLS_BY_NAME[name].declaration.parameters.required or [])
            assert declared == required, name

    def test_movement_kind_enum_excludes_in(self):
        """Schema-level backstop for the provenance invariant — the primary
        gate is the enum itself (Gemini enforces it), the validator refusal
        in TestMovementValidation is the confirm-turn belt."""
        declared = TOOLS_BY_NAME["record_stock_movement"].declaration.parameters.properties["kind"].enum
        assert set(declared) == {"out", "stockout", "adjust"}

    def test_locations_topic_registered_and_gated(self):
        from app.matcha.services.huume.onboarding_skill import _TOPIC_REQUIRED_FEATURE
        from app.matcha.services.huume.tools import LOOKUP_TOPICS

        assert "locations" in LOOKUP_TOPICS
        assert _TOPIC_REQUIRED_FEATURE["locations"] == "inventory"

    def test_every_inventory_action_type_has_a_feature(self):
        from app.matcha.services.huume.actions import _HUUME_ACTION_REQUIRED_FEATURE

        for name in self.INVENTORY_STAGED_TOOLS:
            action_type = _HR_OPS_TOOL_SPECS[name]["action_type"]
            assert _HUUME_ACTION_REQUIRED_FEATURE[action_type] == "inventory"


class TestStateBlock:
    def test_each_type_echoes_its_confirm_key(self):
        cases = [
            (_movement(), "aa11bb22"),
            (_order_decision(), ORDER_ID),
            (_item_create(), "cc33dd44"),
            (_item_archive(), ITEM_ID),
            (_receipt(), "ee55ff66"),
        ]
        for action, needle in cases:
            block = build_state_block({"huume_action": action})
            assert needle in block, action["type"]
            assert "STAGED ACTION" in block

    def test_terminal_action_renders_nothing_staged(self):
        block = build_state_block({"huume_action": _movement(status="recorded")})
        assert "STAGED ACTION" not in block

    def test_order_decision_block_names_the_decision(self):
        block = build_state_block({"huume_action": _order_decision(decision="cancel")})
        assert "cancel" in block

    def test_receipt_block_surfaces_dup_warning(self):
        block = build_state_block({
            "huume_action": _receipt(dup_warning="Invoice INV-1 looks already received."),
        })
        assert "already received" in block
        assert "no separate force step" in block
