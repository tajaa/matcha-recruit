from app.matcha.services.inventory.pills import (
    extract_question, movement_pill, order_cancelled_pill, order_confirmed_pill,
    quantity_question, rearm_pill, receipt_pill, reorder_pill, stockout_pill,
)

_ALL_BUILDERS = [
    movement_pill("Cookies", 1, 12, "gifted to Elizabeth", False),
    quantity_question(movement_pill("Cookies", 1, None, None, True)),
    stockout_pill("Salads", {"avg_stockout_interval_days": 9}, 42),
    reorder_pill("Salads", {"avg_stockout_interval_days": 9}, 42),
    receipt_pill("Cookies", 24, 30),
    order_confirmed_pill("Salads", 42),
    order_cancelled_pill("Salads"),
    rearm_pill(),
]


def test_reorder_pill_never_claims_stockout():
    pill = reorder_pill("Salads", {"avg_stockout_interval_days": 9}, 42)
    assert "out of stock" not in pill.lower()
    assert "Reply **confirm**" in pill


def test_every_pill_starts_with_box_emoji():
    for pill in _ALL_BUILDERS:
        assert pill.startswith("\U0001F4E6"), pill


def test_never_urgent_emoji():
    for pill in _ALL_BUILDERS:
        assert not pill.startswith("\U0001F6A8"), pill


def test_extract_question_round_trip():
    base = movement_pill("Cookies", 1, None, None, True)
    q = quantity_question(base)
    assert extract_question(q) == "How many?"


def test_unknown_count_phrasing():
    pill = movement_pill("Cookies", 1, None, "gifted", True)
    assert "count unknown" in pill.lower()
