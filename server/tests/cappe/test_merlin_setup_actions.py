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


def test_add_blocks_rejects_a_known_field_with_the_wrong_type():
    """A known field (here 'items', a list-kind field on 'faq') given a value
    of the wrong kind must be refused, not silently dropped — this writes
    straight to `cappe_pages.content` with no client-side schema defaults to
    fall back on, unlike `ops._v_add_block`'s identical-looking filter."""
    v = sa.evaluate_setup_stage(
        "add_blocks",
        {"page_id": PAGE_ID, "blocks": [{"type": "faq", "items": "three common questions"}]},
        entitlements=FREE, plan="free",
    )
    assert v.kind == "invalid"
    assert "items" in v.message


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


def test_create_page_requires_either_a_preset_or_blocks():
    """{"title": "...", "preset": null, "blocks": null} is a shape
    `prompt_shape` advertises as legal — without this guard it creates an
    empty page (`_validate_blocks(None)` returns `([], None)`, no error)."""
    v = sa.evaluate_setup_stage(
        "create_page", {"title": "About", "preset": None, "blocks": None},
        entitlements=FREE, plan="free",
    )
    assert v.kind == "invalid"


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


def test_set_promo_bar_payload_uses_the_renderer_camelcase_schema():
    """`services/render/page.py:_promos` and `PromosPanel.tsx` both read/write
    `ctaLabel`/`ctaHref` — a staged payload using the old `cta_label`/
    `cta_href` snake_case renders with a dead CTA (nothing populates the
    renderer's expected keys)."""
    v = sa.evaluate_setup_stage(
        "set_promo",
        {"target": "bar", "enabled": True, "text": "Summer sale",
         "ctaLabel": "Shop now", "ctaHref": "/p/shop"},
        entitlements=BUSINESS, plan="business",
    )
    assert v.kind == "stage"
    assert v.payload["ctaLabel"] == "Shop now"
    assert v.payload["ctaHref"] == "/p/shop"
    assert "cta_label" not in v.payload and "cta_href" not in v.payload

    from app.cappe.services.render.page import _promos

    meta = {"promos": {"bar": {k: v_ for k, v_ in v.payload.items() if k != "target"}}}
    bar_html, _popup_html, _js = _promos(meta, {})
    assert '<a class="cz-promobar__cta" href="/p/shop">Shop now</a>' in bar_html


def test_set_promo_popup_code_mode_round_trips_through_the_renderer():
    """The popup's 'code' mode had no `code` field at all — the discount
    modal always rendered empty."""
    v = sa.evaluate_setup_stage(
        "set_promo",
        {"target": "popup", "enabled": True, "heading": "10% off", "mode": "code",
         "code": "WELCOME10", "ctaLabel": "Shop now", "ctaHref": "/p/shop"},
        entitlements=BUSINESS, plan="business",
    )
    assert v.kind == "stage"
    assert v.payload["code"] == "WELCOME10"

    from app.cappe.services.render.page import _promos

    meta = {"promos": {"popup": {k: v_ for k, v_ in v.payload.items() if k != "target"}}}
    _bar_html, popup_html, _js = _promos(meta, {})
    assert "<b>WELCOME10</b>" in popup_html
    assert 'data-code="WELCOME10"' in popup_html


def test_set_promo_ctalabel_omitted_leaves_payload_without_the_key():
    """Presence-gated: a `set_promo` call that never mentions `ctaLabel`
    carries no `ctaLabel` key at all, so `_execute_set_promo`'s merge leaves
    whatever is already stored untouched."""
    v = sa.evaluate_setup_stage(
        "set_promo", {"target": "bar", "enabled": True, "text": "Summer sale"},
        entitlements=BUSINESS, plan="business",
    )
    assert v.kind == "stage"
    assert "ctaLabel" not in v.payload
    assert "ctaHref" not in v.payload


def test_set_promo_ctalabel_explicit_null_clears():
    """'remove the button from the announcement bar' → ctaLabel/ctaHref sent
    explicitly as null. The validator must carry that through as a real
    `None` in the payload (not drop the key) — `_execute_set_promo`'s merge
    (exercised against a live conn, out of scope for this DB-free file) reads
    a present `None` as "clear it" and an absent key as "leave it alone"; the
    bug this covers is the OLD merge treating every `None` as "leave it
    alone" regardless of whether the key was sent at all."""
    v = sa.evaluate_setup_stage(
        "set_promo",
        {"target": "bar", "enabled": True, "text": "Summer sale", "ctaLabel": None, "ctaHref": None},
        entitlements=BUSINESS, plan="business",
    )
    assert v.kind == "stage"
    assert "ctaLabel" in v.payload and v.payload["ctaLabel"] is None
    assert "ctaHref" in v.payload and v.payload["ctaHref"] is None


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


def test_apply_outcome_retryable_block_leaves_entry_proposed():
    """An entitlement gate is a STATE the user can fix by upgrading — it must
    stay `proposed` (with the reason surfaced as `message`) so Approve is
    still there after they do, instead of a terminal `blocked` with no way
    back."""
    entry = sa.new_staged_entry("set_promo", {"target": "bar"}, "summary")
    outcome = {"ok": False, "status": "blocked", "retryable": True, "message": "Upgrade first."}
    result = sa.apply_outcome(entry["id"], outcome)([entry])
    assert result[0]["status"] == "proposed"
    assert result[0]["message"] == "Upgrade first."


def test_apply_outcome_non_retryable_block_is_terminal():
    """A `SetupActionError` (e.g. the target page was deleted) is not
    something the user can fix by retrying — this stays `blocked`."""
    entry = sa.new_staged_entry("add_blocks", {"page_id": PAGE_ID}, "summary")
    outcome = {"ok": False, "status": "blocked", "retryable": False, "message": "That page doesn't exist anymore."}
    result = sa.apply_outcome(entry["id"], outcome)([entry])
    assert result[0]["status"] == "blocked"
    assert result[0]["message"] == "That page doesn't exist anymore."


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
