"""Cappe shipping pure-function tests — no DB, no app boot.

Covers the shipping money math, the Stripe shipping_options translation, the
webhook address extraction (both API shapes), the order-PATCH model contract,
and the receipt HTML (shipping row + escaped Ship-to block). Run from server/.
"""
import json
import os
from datetime import datetime, timezone

# Defensive: some transitive imports read settings at import time.
os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

import pytest  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from app.cappe.models.shop import CappeOrderStatusUpdate  # noqa: E402
from app.cappe.routes.payments import extract_shipping_details  # noqa: E402
from app.cappe.services.commerce import compute_shipping_cents  # noqa: E402
from app.cappe.services.receipt import build_receipt_html  # noqa: E402
from app.cappe.services.stripe_connect import build_shipping_options  # noqa: E402


# --- compute_shipping_cents --------------------------------------------------

def test_shipping_zero_without_physical():
    assert compute_shipping_cents(
        has_physical=False, subtotal_cents=5000, flat_cents=700, free_threshold_cents=None
    ) == 0


def test_shipping_flat_applied_to_physical():
    assert compute_shipping_cents(
        has_physical=True, subtotal_cents=5000, flat_cents=700, free_threshold_cents=None
    ) == 700


def test_shipping_zero_when_rate_unset():
    assert compute_shipping_cents(
        has_physical=True, subtotal_cents=5000, flat_cents=0, free_threshold_cents=None
    ) == 0


def test_shipping_threshold_met_exactly():
    # Boundary: >= not >
    assert compute_shipping_cents(
        has_physical=True, subtotal_cents=5000, flat_cents=700, free_threshold_cents=5000
    ) == 0


def test_shipping_threshold_not_met():
    assert compute_shipping_cents(
        has_physical=True, subtotal_cents=4999, flat_cents=700, free_threshold_cents=5000
    ) == 700


def test_shipping_threshold_zero_means_always_free():
    assert compute_shipping_cents(
        has_physical=True, subtotal_cents=1, flat_cents=700, free_threshold_cents=0
    ) == 0


# --- build_shipping_options --------------------------------------------------

def test_shipping_options_none_passthrough():
    assert build_shipping_options(None, "usd") is None


def test_shipping_options_shape():
    [opt] = build_shipping_options({"label": "Shipping", "amount_cents": 700}, "USD")
    rate = opt["shipping_rate_data"]
    assert rate["type"] == "fixed_amount"
    assert rate["display_name"] == "Shipping"
    assert rate["fixed_amount"] == {"amount": 700, "currency": "usd"}


def test_shipping_options_free_and_label_fallbacks():
    [opt] = build_shipping_options({"label": None, "amount_cents": 0}, "usd")
    assert opt["shipping_rate_data"]["display_name"] == "Shipping"
    # 0-amount row still emitted so the buyer sees "Free shipping".
    assert opt["shipping_rate_data"]["fixed_amount"]["amount"] == 0


# --- extract_shipping_details ------------------------------------------------

_ADDR = {"name": "Jane Doe", "address": {"line1": "1 Main St", "city": "Reno",
                                         "state": "NV", "postal_code": "89501", "country": "US"}}


def test_extract_shipping_new_api_shape():
    assert extract_shipping_details({"collected_information": {"shipping_details": _ADDR}}) == _ADDR


def test_extract_shipping_legacy_shape():
    assert extract_shipping_details({"shipping_details": _ADDR}) == _ADDR


def test_extract_shipping_prefers_collected():
    obj = {"collected_information": {"shipping_details": {"name": "new"}},
           "shipping_details": {"name": "old"}}
    assert extract_shipping_details(obj)["name"] == "new"


def test_extract_shipping_absent_returns_none():
    assert extract_shipping_details({}) is None
    assert extract_shipping_details({"collected_information": {}}) is None
    assert extract_shipping_details({"collected_information": None}) is None


# --- CappeOrderStatusUpdate --------------------------------------------------

def test_order_update_requires_a_field():
    with pytest.raises(ValidationError):
        CappeOrderStatusUpdate()


def test_order_update_status_only_ok():
    m = CappeOrderStatusUpdate(status="paid")
    assert m.status == "paid" and m.carrier is None


def test_order_update_tracking_only_ok():
    m = CappeOrderStatusUpdate(carrier="USPS")
    assert m.status is None and m.carrier == "USPS"


def test_order_update_explicit_null_carrier_ok():
    m = CappeOrderStatusUpdate.model_validate({"carrier": None})
    assert m.carrier is None and "carrier" in m.model_fields_set


def test_order_update_explicit_null_status_rejected():
    # build_patch would SET status = NULL — the model must refuse it.
    with pytest.raises(ValidationError):
        CappeOrderStatusUpdate.model_validate({"status": None})


def test_order_update_rejects_bad_status():
    with pytest.raises(ValidationError):
        CappeOrderStatusUpdate(status="shipped")


def test_order_update_length_caps():
    with pytest.raises(ValidationError):
        CappeOrderStatusUpdate(carrier="x" * 41)
    with pytest.raises(ValidationError):
        CappeOrderStatusUpdate(tracking_number="x" * 121)


def test_order_update_strips_whitespace_to_none():
    m = CappeOrderStatusUpdate.model_validate({"carrier": "  ", "tracking_number": " 940011 "})
    assert m.carrier is None and m.tracking_number == "940011"


# --- build_receipt_html ------------------------------------------------------

_BASE_ORDER = {
    "currency": "USD", "business_name": "Store", "receipt_number": "INV-00001",
    "customer_name": "Buyer", "customer_email": "buyer@example.com",
    "subtotal_cents": 5000, "tax_cents": 0, "total_cents": None,
    "created_at": datetime(2026, 8, 1, tzinfo=timezone.utc),
}


def test_receipt_shipping_row_rendered():
    html = build_receipt_html(
        {**_BASE_ORDER, "shipping_cents": 700, "shipping_label": "Shipping", "total_cents": 5700}, []
    )
    assert "Shipping" in html and "$7.00" in html


def test_receipt_no_shipping_row_when_zero():
    html = build_receipt_html({**_BASE_ORDER, "shipping_cents": 0}, [])
    assert "Shipping" not in html and "Ship to" not in html


def test_receipt_ship_to_block_and_escaping():
    addr = {"name": "<script>x</script>", "address": _ADDR["address"]}
    html = build_receipt_html({**_BASE_ORDER, "shipping_address": addr}, [])
    assert "Ship to" in html
    assert "&lt;script&gt;" in html and "<script>x" not in html
    assert "1 Main St" in html and "Reno, NV 89501" in html


def test_receipt_ship_to_handles_str_jsonb():
    html = build_receipt_html({**_BASE_ORDER, "shipping_address": json.dumps(_ADDR)}, [])
    assert "Ship to" in html and "Jane Doe" in html


def test_receipt_total_fallback_includes_shipping():
    # total_cents=None → subtotal + tax + shipping
    html = build_receipt_html({**_BASE_ORDER, "shipping_cents": 700}, [])
    assert "$57.00" in html
