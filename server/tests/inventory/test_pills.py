from app.matcha.services.inventory.pills import (
    channel_receipt_pill, extract_question, movement_pill, order_cancelled_pill, order_confirmed_pill,
    quantity_question, rearm_pill, reorder_pill, stockout_pill,
)

_ALL_BUILDERS = [
    movement_pill("Cookies", 1, 12, "gifted to Elizabeth", False),
    quantity_question(movement_pill("Cookies", 1, None, None, True)),
    stockout_pill("Salads", {"avg_stockout_interval_days": 9}, 42),
    reorder_pill("Salads", {"avg_stockout_interval_days": 9}, 42),
    channel_receipt_pill([{"item_name": "Cookies", "quantity": 24, "new_count": 30}], []),
    channel_receipt_pill([], ["Cookies"]),
    order_confirmed_pill("Salads", 42),
    order_cancelled_pill("Salads"),
    rearm_pill(),
]


class TestChannelReceiptPill:
    def test_single_received_no_unmatched(self):
        pill = channel_receipt_pill([{"item_name": "Cookies", "quantity": 24, "new_count": 30}], [])
        assert "Cookies" in pill
        assert "checked in against the open order" in pill
        assert "30 in stock now" in pill

    def test_multi_received(self):
        pill = channel_receipt_pill(
            [{"item_name": "Cookies", "quantity": 24, "new_count": 30},
             {"item_name": "Floss", "quantity": 3, "new_count": 12}],
            [],
        )
        assert "Cookies" in pill and "Floss" in pill
        assert "Checked in against open orders" in pill

    def test_all_unmatched_steers_to_receive_delivery(self):
        pill = channel_receipt_pill([], ["Cookies"])
        assert "can't book received stock from chat alone" in pill
        assert "Receive Delivery" in pill

    def test_mixed_received_and_unmatched(self):
        pill = channel_receipt_pill(
            [{"item_name": "Cookies", "quantity": 24, "new_count": 30}], ["Floss"],
        )
        assert "Cookies" in pill
        assert "Couldn't check in Floss" in pill
        assert "no open order" in pill

    def test_never_auto_creates_or_claims_a_bare_in(self):
        # No builder here ever mentions an item being created — the whole
        # point of this pill is that a delivery for an unordered item does
        # NOT write a movement or create an item.
        for pill in (
            channel_receipt_pill([], ["Widgets"]),
            channel_receipt_pill([{"item_name": "Cookies", "quantity": 24, "new_count": 30}], ["Widgets"]),
        ):
            assert "❓" not in pill  # never the question-marker (no clarify round-trip for receipts)


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
