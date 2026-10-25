"""The launch checklist: what blocks publishing and what is only a nudge.

Run from server/:  ./venv/bin/python -m pytest tests/cappe/test_cappe_readiness.py -q
"""
import asyncio
import json

from app.cappe.services.readiness import compute_readiness


class _Conn:
    def __init__(self, *, blocks, products=0, booking_types=0, forms=0):
        self.pages = [{"content": json.dumps({"blocks": blocks})}]
        self.counts = {"cappe_products": products, "cappe_booking_types": booking_types, "cappe_forms": forms}

    async def fetch(self, _sql, _site_id):
        return self.pages

    async def fetchval(self, sql, _site_id):
        return next(n for table, n in self.counts.items() if table in sql)

    async def fetchrow(self, sql, _site_id):
        return getattr(self, "commerce", None)  # nothing physical or paid to sell


def _readiness(**kw):
    conn = _Conn(**kw)
    return asyncio.run(compute_readiness(conn, "site-id", {"meta_config": None}))


def _item(result, key):
    return next(i for i in result["items"] if i["key"] == key)


_INTRO = [{"type": "hero", "heading": "Corner Bakery"}]


def test_a_site_with_content_and_nothing_to_sell_can_publish():
    """A brochure, menu or portfolio site is a real site."""
    result = _readiness(blocks=_INTRO)
    assert result["ready"] is True
    offering = _item(result, "offering")
    assert offering["required"] is False and offering["done"] is False


def test_a_site_with_no_content_cannot_publish():
    result = _readiness(blocks=[{"type": "hero", "heading": "  "}], products=3)
    assert result["ready"] is False
    assert [i["key"] for i in result["items"] if i["required"]] == ["content"]
    assert _item(result, "offering")["done"] is True


def test_offering_is_still_tracked_as_a_suggestion():
    assert _item(_readiness(blocks=_INTRO, booking_types=1), "offering")["done"] is True


def test_online_starter_requires_a_reviewed_product_and_physical_policies():
    conn = _Conn(blocks=_INTRO, products=0)
    conn.commerce = {"draft_physical": 1, "physical": 0, "policy_kinds": []}
    site = {"meta_config": {}, "template_slug": "online-studio"}
    result = asyncio.run(compute_readiness(conn, "site-id", site))
    assert not result["ready"]
    assert _item(result, "offering")["required"] and not _item(result, "offering")["done"]
    assert _item(result, "policies")["required"] and not _item(result, "policies")["done"]
    conn.counts["cappe_products"] = 1
    conn.commerce.update(physical=1, policy_kinds=["refund", "shipping"])
    assert asyncio.run(compute_readiness(conn, "site-id", site))["ready"]


def test_draft_physical_products_do_not_block_an_ordinary_brochure_site():
    conn = _Conn(blocks=_INTRO)
    conn.commerce = {"draft_physical": 1, "physical": 0, "policy_kinds": []}
    result = asyncio.run(compute_readiness(conn, "site-id", {"meta_config": {}}))
    assert result["ready"] and not any(i["key"] == "policies" for i in result["items"])


def test_bookings_do_not_replace_an_online_starters_first_product():
    conn = _Conn(blocks=_INTRO, booking_types=1)
    result = asyncio.run(compute_readiness(conn, "site-id", {"meta_config": {}, "template_slug": "online-pop"}))
    assert not result["ready"] and not _item(result, "offering")["done"]
