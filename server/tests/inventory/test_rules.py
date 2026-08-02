from decimal import Decimal

from app.matcha.services.inventory.rules import evaluate_inventory_action, parse_quantity_reply

FEATURES_ON = {"inventory": True}
FEATURES_OFF = {"inventory": False}


def test_employee_can_record_movement():
    v = evaluate_inventory_action(role="employee", features=FEATURES_ON, stage="movement")
    assert v.ok


def test_employee_cannot_approve_order():
    v = evaluate_inventory_action(role="employee", features=FEATURES_ON, stage="approve_order")
    assert not v.ok


def test_client_can_approve_order():
    v = evaluate_inventory_action(role="client", features=FEATURES_ON, stage="approve_order")
    assert v.ok


def test_admin_can_approve_order():
    v = evaluate_inventory_action(role="admin", features=FEATURES_ON, stage="approve_order")
    assert v.ok


def test_flag_off_refuses_both_stages():
    assert not evaluate_inventory_action(role="admin", features=FEATURES_OFF, stage="movement").ok
    assert not evaluate_inventory_action(role="admin", features=FEATURES_OFF, stage="approve_order").ok


def test_parse_quantity_reply_table():
    assert parse_quantity_reply("12") == Decimal("12")
    assert parse_quantity_reply("about 12") == Decimal("12")
    assert parse_quantity_reply("a dozen") == Decimal(12)
    assert parse_quantity_reply("12 boxes") == Decimal("12")
    assert parse_quantity_reply("yes") is None
    assert parse_quantity_reply("") is None
