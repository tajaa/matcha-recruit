"""Cappe product-option pricing (pure — no DB).

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_options.py -q
"""
import os
import uuid

import pytest

os.environ.setdefault("LIVE_API", "test-key")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-cappe")

from app.cappe.services.options import validate_and_price_options  # noqa: E402

SIZE = uuid.uuid4()
SMALL, LARGE = uuid.uuid4(), uuid.uuid4()
ADDONS = uuid.uuid4()
SHOT, OAT = uuid.uuid4(), uuid.uuid4()

GROUPS = [
    {"id": SIZE, "name": "Size", "select_type": "single", "required": True, "options": [
        {"id": SMALL, "name": "Small", "price_delta_cents": 0},
        {"id": LARGE, "name": "Large", "price_delta_cents": 100},
    ]},
    {"id": ADDONS, "name": "Add-ons", "select_type": "multi", "required": False, "options": [
        {"id": SHOT, "name": "Extra shot", "price_delta_cents": 75},
        {"id": OAT, "name": "Oat milk", "price_delta_cents": 50},
    ]},
]


def test_multi_select_sums_deltas_and_snapshots():
    delta, snap = validate_and_price_options(GROUPS, [LARGE, SHOT, OAT])
    assert delta == 225
    assert [s["name"] for s in snap] == ["Large", "Extra shot", "Oat milk"]
    assert snap[0] == {"group": "Size", "name": "Large", "price_delta_cents": 100}


def test_required_single_missing_raises():
    with pytest.raises(ValueError):
        validate_and_price_options(GROUPS, [])           # Size is required
    with pytest.raises(ValueError):
        validate_and_price_options(GROUPS, [SHOT])       # only an add-on, no size


def test_single_select_rejects_two():
    with pytest.raises(ValueError):
        validate_and_price_options(GROUPS, [SMALL, LARGE])


def test_foreign_option_id_raises():
    with pytest.raises(ValueError):
        validate_and_price_options(GROUPS, [uuid.uuid4()])


def test_zero_delta_small_is_valid():
    delta, snap = validate_and_price_options(GROUPS, [SMALL])
    assert delta == 0 and snap == [{"group": "Size", "name": "Small", "price_delta_cents": 0}]


def test_negative_delta_lowers_price():
    g = [{"id": SIZE, "name": "Size", "select_type": "single", "required": False, "options": [
        {"id": SMALL, "name": "Small", "price_delta_cents": -50}]}]
    delta, _ = validate_and_price_options(g, [SMALL])
    assert delta == -50


def test_no_groups_no_selection_is_free():
    assert validate_and_price_options([], []) == (0, [])
