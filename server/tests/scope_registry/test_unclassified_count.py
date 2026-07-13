"""_refresh_unclassified_count must gate on CONFIRMED classifications only.

Regression coverage for the soundness hole flagged in the revision-2 gap
review: the prior query was `LEFT JOIN ... WHERE c.id IS NULL`, which drops
to zero the moment every item has ANY classification row — including
'provisional' ones nobody has confirmed. But registry_expected_keys
(completeness.py) filters c.status='confirmed' for its own denominator, so
a classified-but-unconfirmed index would read unclassified_count=0 (gate
opens) while the expected-keys query then silently serves a shrunken
confirmed-only set as the "full" registry — completeness reads inflated.
"""
import pytest

from app.core.services.scope_registry.classify import _refresh_unclassified_count


class FakeConn:
    """Answers the COUNT query using the same JOIN predicate the SQL text
    carries, so a regression that drops the confirmed-only filter changes
    what this fake computes too — not just what the real function returns.
    """

    def __init__(self, item_statuses):
        # item_id -> classification status, or None for "no classification row"
        self.item_statuses = item_statuses
        self.updated = None

    async def fetchval(self, sql, *args):
        assert "authority_item_classifications" in sql
        confirmed_only = "c.status = 'confirmed'" in sql
        unclassified = 0
        for status in self.item_statuses.values():
            if confirmed_only:
                if status != "confirmed":
                    unclassified += 1
            else:
                if status is None:
                    unclassified += 1
        return unclassified

    async def execute(self, sql, *args):
        assert "UPDATE authority_indexes" in sql
        self.updated = args


@pytest.mark.asyncio
async def test_provisional_only_index_is_not_zero():
    """The soundness-hole scenario: every item has been Gemini-classified
    (provisional) but nothing has gone through admin confirm. The gate must
    still see this as fully unclassified, not as done.
    """
    conn = FakeConn({"item-1": "provisional", "item-2": "provisional"})

    count = await _refresh_unclassified_count(conn, "index-1")

    assert count == 2
    assert conn.updated == (2, "index-1")


@pytest.mark.asyncio
async def test_confirmed_items_are_not_counted():
    conn = FakeConn({"item-1": "confirmed", "item-2": "confirmed"})

    count = await _refresh_unclassified_count(conn, "index-1")

    assert count == 0


@pytest.mark.asyncio
async def test_mixed_confirmed_and_provisional():
    conn = FakeConn({
        "item-1": "confirmed",
        "item-2": "provisional",
        "item-3": None,  # never classified at all
    })

    count = await _refresh_unclassified_count(conn, "index-1")

    assert count == 2
