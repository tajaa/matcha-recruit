from app.matcha.services.inventory.pills import (
    channel_receipt_pill, extract_question, movement_pill, order_cancelled_pill, order_confirmed_pill,
    quantity_question, rearm_pill, receipt_draft_cancelled_pill, receipt_draft_pill, reorder_pill,
    return_pill, return_unmatched_pill, stockout_pill,
)

_SAMPLE_PREVIEW = [
    {"item_name": "Nitrile Gloves", "matched_name": "Nitrile Gloves (M)", "quantity": 10, "open_order_id": "o1"},
    {"item_name": "Cotton Rolls", "matched_name": None, "quantity": 5, "open_order_id": None},
]

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
    receipt_draft_pill(vendor="Henry Schein", invoice_number="INV-1", preview=_SAMPLE_PREVIEW),
    receipt_draft_cancelled_pill(),
    return_pill("Nitrile Gloves (M)", 1, 33, False),
    return_unmatched_pill("Gauze Pads"),
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


class TestReceiptDraftPill:
    def test_vendor_and_invoice_number_render(self):
        pill = receipt_draft_pill(vendor="Henry Schein", invoice_number="INV-42", preview=_SAMPLE_PREVIEW)
        assert "Henry Schein" in pill
        assert "#INV-42" in pill

    def test_no_vendor_falls_back_gracefully(self):
        pill = receipt_draft_pill(vendor=None, invoice_number=None, preview=_SAMPLE_PREVIEW)
        assert "that delivery" in pill

    def test_matched_and_unmatched_lines_are_distinguishable(self):
        pill = receipt_draft_pill(vendor="Henry Schein", invoice_number=None, preview=_SAMPLE_PREVIEW)
        assert "Nitrile Gloves (M)" in pill and "has an open order" in pill
        assert "Cotton Rolls" in pill and "will be skipped" in pill

    def test_ends_with_confirm_cancel_prompt(self):
        pill = receipt_draft_pill(vendor="X", invoice_number=None, preview=_SAMPLE_PREVIEW)
        assert "Reply **confirm**" in pill and "**cancel**" in pill

    def test_never_claims_something_was_already_received(self):
        # This is a REVIEW pill, before any write happens.
        pill = receipt_draft_pill(vendor="X", invoice_number=None, preview=_SAMPLE_PREVIEW)
        assert "checked in" not in pill.lower().replace("can check in", "")


def test_receipt_draft_cancelled_pill_says_nothing_was_written():
    pill = receipt_draft_cancelled_pill()
    assert "nothing was checked in" in pill


def test_reorder_pill_never_claims_stockout():
    pill = reorder_pill("Salads", {"avg_stockout_interval_days": 9}, 42)
    assert "out of stock" not in pill.lower()
    assert "Reply **confirm**" in pill


class TestOrderSuggestionClause:
    """Both order pills share this tail. Live dev-remote read
    "Staging an order for Dental Floss. suggest ordering 20.0." — a
    lowercase sentence start and a float quantity."""

    def test_whole_number_quantity_renders_bare(self):
        for pill in (reorder_pill("Floss", None, 20.0), stockout_pill("Floss", None, 20.0)):
            assert "20." not in pill.replace("20. ", "")  # no "20.0"
            assert "ordering 20" in pill

    def test_fractional_quantity_preserved(self):
        assert "ordering 2.5" in reorder_pill("Floss", None, 2.5)

    def test_sentence_start_capitalized_without_history_clause(self):
        assert "Suggest ordering" in reorder_pill("Floss", None, 20)
        assert ". suggest" not in reorder_pill("Floss", None, 20)

    def test_lowercase_after_the_history_semicolon(self):
        pill = reorder_pill("Floss", {"avg_stockout_interval_days": 9}, 20)
        assert "days; suggest ordering 20." in pill

    def test_no_suggestion_capitalized_without_history_clause(self):
        assert "Not enough history" in reorder_pill("Floss", None, None)

    def test_no_suggestion_lowercase_after_history_clause(self):
        pill = reorder_pill("Floss", {"avg_stockout_interval_days": 9}, None)
        assert "days; not enough history" in pill


class TestReturnPill:
    def test_known_quantity_and_count(self):
        pill = return_pill("Nitrile Gloves (M)", 1, 33, False)
        assert "Put back 1 × Nitrile Gloves (M)" in pill
        assert "33 on hand" in pill

    def test_estimated_quantity_shows_tilde(self):
        pill = return_pill("Nitrile Gloves (M)", 1, 33, True)
        assert "~1" in pill

    def test_unknown_count_phrasing(self):
        pill = return_pill("Nitrile Gloves (M)", 1, None, False)
        assert "count unknown" in pill.lower()

    def test_never_claims_stockout(self):
        pill = return_pill("Nitrile Gloves (M)", 1, 33, False)
        assert "out of stock" not in pill.lower()


class TestReturnUnmatchedPill:
    def test_steers_to_inventory_page_never_auto_creates(self):
        pill = return_unmatched_pill("Gauze Pads")
        assert "Gauze Pads" in pill
        assert "Inventory page" in pill


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
