"""Attachment-driven receipt ingest — the pure trigger logic.

A CSV/PDF attachment is unambiguously a document, so it's tried regardless
of wording. A photo is ambiguous (could be an incident photo of a burst
pipe), so it's only tried when the message text itself reads as a
delivery/invoice mention. `_pick_receipt_attachment` is the whole trigger
decision, pure and DB-free.

    cd server && ./venv/bin/python -m pytest tests/ems/test_receipt_attachment_dispatch.py -q
"""

from app.werk.routes.channels_ws import _RECEIPT_MAX_BYTES, _pick_receipt_attachment


def _att(filename, size=1000, **over):
    base = {"url": f"https://cdn.example.com/{filename}", "filename": filename,
            "content_type": "application/octet-stream", "size": size}
    base.update(over)
    return base


class TestPickReceiptAttachment:
    def test_no_attachments_returns_none(self):
        assert _pick_receipt_attachment(None, "@huume here's the invoice") is None
        assert _pick_receipt_attachment([], "@huume here's the invoice") is None

    def test_csv_triggers_regardless_of_wording(self):
        att = _att("gloves.csv")
        assert _pick_receipt_attachment([att], "@huume") == att

    def test_pdf_triggers_regardless_of_wording(self):
        att = _att("packing-slip.pdf")
        assert _pick_receipt_attachment([att], "@huume") == att

    def test_photo_without_receipt_wording_is_not_picked(self):
        # A photo attached to "this pipe burst" must NOT hijack an incident
        # report into a receipt-ingest attempt.
        att = _att("photo.jpg")
        assert _pick_receipt_attachment([att], "@huume this pipe burst") is None

    def test_photo_with_receipt_wording_is_picked(self):
        att = _att("photo.jpg")
        assert _pick_receipt_attachment([att], "@huume here's the delivery invoice") == att

    def test_photo_wording_variants(self):
        for word in ["invoice", "receipt", "packing slip", "delivery", "shipment", "restock",
                     "the order came", "the order arrived", "the order is here"]:
            att = _att("photo.png")
            assert _pick_receipt_attachment([att], f"@huume {word}") == att, word

    def test_oversized_attachment_is_skipped(self):
        att = _att("invoice.csv", size=_RECEIPT_MAX_BYTES + 1)
        assert _pick_receipt_attachment([att], "@huume invoice") is None

    def test_unrelated_extension_is_skipped(self):
        att = _att("cat.gif")
        assert _pick_receipt_attachment([att], "@huume invoice") is None

    def test_most_recent_matching_attachment_wins(self):
        old = _att("old-invoice.csv")
        new = _att("new-invoice.csv")
        assert _pick_receipt_attachment([old, new], "@huume") == new

    def test_skips_oversized_and_finds_the_next_one(self):
        too_big = _att("huge.pdf", size=_RECEIPT_MAX_BYTES + 1)
        ok = _att("small.csv")
        assert _pick_receipt_attachment([ok, too_big], "@huume") == ok

    def test_case_insensitive_extension_and_wording(self):
        att = _att("INVOICE.CSV")
        assert _pick_receipt_attachment([att], "@huume DELIVERY is here") == att
