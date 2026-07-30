"""Setup-concierge action registry (migration zzzzcappe27) — pure logic only.

`evaluate_setup_stage`/`evaluate_setup_execute` are DB-free by design (see
services/merlin/setup_actions.py's module docstring), so these tests never
touch a connection — no live database, no FakeConn, matching the repo rule
that DB-mutating tests are never auto-run.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_merlin_setup_actions.py -q
"""
import os

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.config import load_settings  # noqa: E402

load_settings()

from app.cappe.services.entitlements import Entitlements  # noqa: E402
from app.cappe.services.merlin import setup_actions as sa  # noqa: E402

FREE = Entitlements(
    plan_code="free", plan_name="Free", can_sell=True, platform_fee_bps=200,
    allowed_fulfillment=frozenset({"physical", "digital", "service", "booking"}),
    site_limit=1, mailbox_quota_included=0, features={},
)
CREATOR = Entitlements(
    plan_code="creator", plan_name="Creator", can_sell=True, platform_fee_bps=300,
    allowed_fulfillment=frozenset({"service", "booking"}),
    site_limit=None, mailbox_quota_included=0, features={"rider": True},
)
BUSINESS = Entitlements(
    plan_code="business", plan_name="Business", can_sell=True, platform_fee_bps=150,
    allowed_fulfillment=frozenset({"physical", "digital", "service", "booking"}),
    site_limit=None, mailbox_quota_included=0, features={},
)

PAGE_ID = "11111111-1111-1111-1111-111111111111"


# --- payload validation ------------------------------------------------------

def test_unknown_action_type_is_invalid():
    v = sa.evaluate_setup_stage("teleport", {}, entitlements=FREE, plan="free")
    assert v.kind == "invalid"
    assert "teleport" in v.message


def test_create_product_rejects_negative_price():
    v = sa.evaluate_setup_stage(
        "create_product", {"name": "Mug", "price_cents": -5}, entitlements=FREE, plan="free"
    )
    assert v.kind == "invalid"


def test_create_product_rejects_bad_fulfillment():
    v = sa.evaluate_setup_stage(
        "create_product", {"name": "Mug", "fulfillment": "teleport"}, entitlements=FREE, plan="free"
    )
    assert v.kind == "invalid"


def test_add_blocks_rejects_unknown_block_type():
    v = sa.evaluate_setup_stage(
        "add_blocks",
        {"page_id": PAGE_ID, "blocks": [{"type": "not_a_block"}]},
        entitlements=FREE, plan="free",
    )
    assert v.kind == "invalid"


def test_add_blocks_rejects_canvas_block():
    """canvas is structural, not field-based — the concierge doesn't build it."""
    v = sa.evaluate_setup_stage(
        "add_blocks",
        {"page_id": PAGE_ID, "blocks": [{"type": "canvas"}]},
        entitlements=FREE, plan="free",
    )
    assert v.kind == "invalid"


def test_add_blocks_drops_unknown_fields_but_keeps_block():
    v = sa.evaluate_setup_stage(
        "add_blocks",
        {"page_id": PAGE_ID, "blocks": [{"type": "newsletter", "heading": "Join us", "made_up_field": "x"}]},
        entitlements=FREE, plan="free",
    )
    assert v.kind == "stage"
    block = v.payload["blocks"][0]
    assert block["heading"] == "Join us"
    assert "made_up_field" not in block


def test_add_blocks_rejects_bad_page_id():
    v = sa.evaluate_setup_stage(
        "add_blocks", {"page_id": "not-a-uuid", "blocks": [{"type": "newsletter"}]},
        entitlements=FREE, plan="free",
    )
    assert v.kind == "invalid"


def test_create_page_rejects_unknown_preset():
    v = sa.evaluate_setup_stage(
        "create_page", {"title": "Foo", "preset": "nonsense"}, entitlements=FREE, plan="free"
    )
    assert v.kind == "invalid"


def test_create_page_with_known_preset_stages():
    v = sa.evaluate_setup_stage(
        "create_page", {"title": "About Us", "preset": "about"}, entitlements=FREE, plan="free"
    )
    assert v.kind == "stage"
    assert v.payload["preset"] == "about"
    assert v.payload["blocks"] is None  # resolved from the preset at execute time


def test_set_promo_bar_requires_text_when_enabled():
    v = sa.evaluate_setup_stage(
        "set_promo", {"target": "bar", "enabled": True}, entitlements=BUSINESS, plan="business"
    )
    assert v.kind == "invalid"


def test_set_promo_disable_does_not_require_text():
    v = sa.evaluate_setup_stage(
        "set_promo", {"target": "bar", "enabled": False}, entitlements=BUSINESS, plan="business"
    )
    assert v.kind == "stage"


# --- entitlement gate matrix --------------------------------------------------

def test_creator_digital_product_is_blocked_with_alternative():
    v = sa.evaluate_setup_stage(
        "create_product", {"name": "Ebook", "fulfillment": "digital", "price_cents": 500},
        entitlements=CREATOR, plan="creator",
    )
    assert v.kind == "blocked"
    assert "booking" in v.message or "service" in v.message


def test_creator_booking_product_is_allowed():
    v = sa.evaluate_setup_stage(
        "create_product", {"name": "1:1 Session", "fulfillment": "booking", "price_cents": 5000},
        entitlements=CREATOR, plan="creator",
    )
    assert v.kind == "stage"


def test_free_physical_product_is_allowed():
    v = sa.evaluate_setup_stage(
        "create_product", {"name": "Mug", "fulfillment": "physical", "price_cents": 1200},
        entitlements=FREE, plan="free",
    )
    assert v.kind == "stage"


def test_free_promo_is_blocked():
    v = sa.evaluate_setup_stage(
        "set_promo", {"target": "bar", "text": "20% off"}, entitlements=FREE, plan="free"
    )
    assert v.kind == "blocked"


def test_business_promo_is_allowed():
    v = sa.evaluate_setup_stage(
        "set_promo", {"target": "bar", "text": "20% off"}, entitlements=BUSINESS, plan="business"
    )
    assert v.kind == "stage"


def test_booking_type_creation_has_no_entitlement_gate():
    """Every plan — including creator, whose allowed_fulfillment excludes
    physical/digital — may create a booking type; it isn't a `cappe_products`
    row and carries no fulfillment gate."""
    v = sa.evaluate_setup_stage(
        "create_booking_type", {"name": "Coaching call", "duration_minutes": 45},
        entitlements=CREATOR, plan="creator",
    )
    assert v.kind == "stage"


# --- confirm-first + idempotency ---------------------------------------------

def test_execute_refuses_same_turn_staged_id():
    entry = sa.new_staged_entry("create_page", {"title": "X", "preset": None, "blocks": []}, "summary")
    v = sa.evaluate_setup_execute(
        entry, entitlements=FREE, plan="free", this_turn_staged_ids={entry["id"]}
    )
    assert v.kind == "refuse"


def test_execute_proceeds_on_a_later_turn():
    entry = sa.new_staged_entry("create_page", {"title": "X", "preset": None, "blocks": []}, "summary")
    v = sa.evaluate_setup_execute(
        entry, entitlements=FREE, plan="free", this_turn_staged_ids=set()
    )
    assert v.kind == "proceed"


def test_execute_refuses_non_proposed_status():
    entry = sa.new_staged_entry("create_page", {"title": "X", "preset": None, "blocks": []}, "summary")
    entry["status"] = "executed"
    v = sa.evaluate_setup_execute(
        entry, entitlements=FREE, plan="free", this_turn_staged_ids=set()
    )
    assert v.kind == "refuse"


def test_execute_reflects_entitlement_change_between_stage_and_confirm():
    """A create_product proposal staged while premium, confirmed after a
    downgrade, is blocked at confirm time — not just at stage time."""
    entry = sa.new_staged_entry(
        "create_product",
        {"name": "Ebook", "fulfillment": "digital", "price_cents": 500,
         "description": None, "digital_file_url": None, "category": None},
        "summary",
    )
    v = sa.evaluate_setup_execute(
        entry, entitlements=CREATOR, plan="creator", this_turn_staged_ids=set()
    )
    assert v.kind == "blocked"


# --- staged-entry mutation helpers -------------------------------------------

def test_append_entry_adds_to_empty_list():
    entry = sa.new_staged_entry("create_page", {"title": "X"}, "summary")
    result = sa.append_entry(entry)([])
    assert result == [entry]


def test_apply_outcome_marks_executed_with_result():
    entry = sa.new_staged_entry("create_page", {"title": "X"}, "summary")
    outcome = {"ok": True, "status": "executed", "result": {"page_id": "abc"}, "message": "Done"}
    result = sa.apply_outcome(entry["id"], outcome)([entry])
    assert result[0]["status"] == "executed"
    assert result[0]["result"] == {"page_id": "abc"}
    assert result[0]["executed_at"] is not None


def test_dismiss_entry_only_affects_proposed():
    entry = sa.new_staged_entry("create_page", {"title": "X"}, "summary")
    result = sa.dismiss_entry(entry["id"])([entry])
    assert result[0]["status"] == "dismissed"

    executed = {**entry, "status": "executed"}
    result = sa.dismiss_entry(entry["id"])([executed])
    assert result[0]["status"] == "executed"  # unchanged — already terminal


def test_find_entry():
    entry = sa.new_staged_entry("create_page", {"title": "X"}, "summary")
    assert sa.find_entry([entry], entry["id"]) == entry
    assert sa.find_entry([entry], "missing") is None
    assert sa.find_entry(None, "missing") is None
