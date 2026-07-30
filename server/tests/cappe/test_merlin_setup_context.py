"""`build_setup_prompt` — pure prompt assembly from a canned context dict, no
DB access (the DB-reading half, `build_setup_context`, is exercised through
the route in integration, not here — matching the repo rule against
DB-mutating/DB-dependent tests in the unit suite).

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_merlin_setup_context.py -q
"""
import os

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.config import load_settings  # noqa: E402

load_settings()

from app.cappe.services.merlin.setup_context import build_setup_prompt  # noqa: E402

_BASE_CONTEXT = {
    "site_name": "Joyful Bakes", "account_name": "Sam", "account_type": "personal", "plan": "free",
    "plan_name": "Free", "allowed_fulfillment": ["physical", "digital", "service", "booking"],
    "is_premium": False,
    "readiness": {"ready": False, "items": [
        {"key": "content", "required": True, "done": False, "label": "Add an intro / about section"},
        {"key": "offering", "required": True, "done": True, "label": "Add something to book or buy"},
    ]},
    "pages": [], "products": [], "product_count": 0, "booking_type_count": 0,
    "subscriber_count": 0, "promo_bar_enabled": False, "promo_popup_enabled": False,
}


def test_prompt_greets_by_account_name():
    prompt = build_setup_prompt(_BASE_CONTEXT)
    assert "helping Sam" in prompt


def test_prompt_lists_every_action_shape():
    prompt = build_setup_prompt(_BASE_CONTEXT)
    for action in ("create_page", "add_blocks", "create_product", "create_booking_type", "set_promo"):
        assert action in prompt


def test_prompt_names_missing_required_readiness_items():
    prompt = build_setup_prompt(_BASE_CONTEXT)
    assert "Add an intro / about section" in prompt
    # The already-done required item shouldn't be listed as missing.
    assert "still missing" in prompt
    lines = [l for l in prompt.splitlines() if "still missing" in l]
    assert "Add something to book or buy" not in lines[0]


def test_prompt_says_ready_when_nothing_is_missing():
    ctx = {**_BASE_CONTEXT, "readiness": {"ready": True, "items": []}}
    prompt = build_setup_prompt(ctx)
    assert "everything required to publish" in prompt


def test_prompt_branches_on_account_type_personal_vs_business():
    personal = build_setup_prompt({**_BASE_CONTEXT, "account_type": "personal"})
    business = build_setup_prompt({**_BASE_CONTEXT, "account_type": "business"})
    assert "SOLO CREATOR" in personal
    assert "BUSINESS account" in business
    assert personal != business


def test_prompt_states_plan_fulfillment_and_promo_eligibility():
    free_prompt = build_setup_prompt(_BASE_CONTEXT)
    assert "Free" in free_prompt
    assert "are NOT" in free_prompt  # promo banners not available on free

    premium_ctx = {**_BASE_CONTEXT, "plan_name": "Business", "is_premium": True}
    premium_prompt = build_setup_prompt(premium_ctx)
    assert "are NOT" not in premium_prompt


def test_prompt_lists_existing_pages_with_ids_for_add_blocks():
    ctx = {**_BASE_CONTEXT, "pages": [
        {"id": "11111111-1111-1111-1111-111111111111", "title": "Home", "slug": "home", "block_types": ["hero"]},
    ]}
    prompt = build_setup_prompt(ctx)
    assert "11111111-1111-1111-1111-111111111111" in prompt
    assert "Home" in prompt


def test_prompt_notes_no_pages_yet_when_empty():
    prompt = build_setup_prompt(_BASE_CONTEXT)
    assert "none yet" in prompt


def test_prompt_includes_recent_products():
    ctx = {**_BASE_CONTEXT, "products": [
        {"name": "Coaching session", "price_cents": 5000, "fulfillment": "booking", "status": "active"},
    ]}
    prompt = build_setup_prompt(ctx)
    assert "Coaching session" in prompt
    assert "$50.00" in prompt


def test_prompt_states_nothing_staged_when_queue_is_empty():
    prompt = build_setup_prompt(_BASE_CONTEXT)
    assert "nothing is currently staged" in prompt


def test_prompt_lists_a_pending_staged_action_with_its_id():
    ctx = {**_BASE_CONTEXT, "staged_actions": [
        {"id": "aaaaaaaa-1111-1111-1111-111111111111", "type": "create_page", "summary": "Create an About page", "status": "proposed"},
    ]}
    prompt = build_setup_prompt(ctx)
    assert "aaaaaaaa-1111-1111-1111-111111111111" in prompt
    assert "Create an About page" in prompt
    assert "nothing is currently staged" not in prompt
