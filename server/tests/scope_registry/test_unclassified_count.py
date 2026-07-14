"""`unclassified_count` must mean "has no CONFIRMED classification".

Regression coverage for the soundness hole flagged in the gap review: the
original query was `LEFT JOIN ... WHERE c.id IS NULL`, which drops to zero the
moment every item has ANY classification row — including 'provisional' ones
nobody has confirmed. But registry_expected_keys (completeness.py) filters
c.status='confirmed' for its own denominator, so a classified-but-unconfirmed
index would read unclassified_count=0 (gate opens) while the expected-keys
query silently serves a shrunken confirmed-only set as the "full" registry —
completeness reads INFLATED. Every other gap in the system fails toward going
dark; this one fails toward the score lying high.

THREE writers touch this column and all three must agree, or the first confirm
or re-ingest silently reverts the fix:
  * classify._refresh_unclassified_count
  * strata.recompute_strata's bulk refresh  (runs on EVERY admin confirm)
  * authority_ingest._recount               (runs on EVERY ingest)
"""
import re

import pytest

from app.core.services.scope_registry.authority_ingest import _recount
from app.core.services.scope_registry.classify import _refresh_unclassified_count

# The three SQL texts, extracted from the modules that own them, so this test
# fails if any writer drifts back to the any-row predicate.
from app.core.services.scope_registry import authority_ingest, classify, strata


# ── the predicate itself, asserted structurally ──────────────────────────────

def _join_clause(sql: str) -> str:
    """The ON clause of the classifications LEFT JOIN."""
    m = re.search(
        r"LEFT JOIN authority_item_classifications\s+c?\s*ON(.*?)(?:WHERE|GROUP BY|$)",
        sql, re.S | re.I,
    )
    assert m, f"no classifications LEFT JOIN found in:\n{sql}"
    return m.group(1)


def _unclassified_queries(module) -> list:
    """Every SQL string in `module` that computes the unclassified count.

    Deliberately narrow: the modules contain other LEFT JOINs onto
    authority_item_classifications with legitimately different semantics (e.g.
    classify.materialize_inherited_children's any-row join), which this test
    must not police.
    """
    import inspect
    src = inspect.getsource(module)
    return [
        chunk for chunk in re.findall(r'"""(.*?)"""', src, re.S)
        if "authority_item_classifications" in chunk
        and ("unclassified" in chunk.lower()
             or re.search(r"COUNT\(\*\)(\s+FILTER)?", chunk, re.I))
        and "IS NULL" in chunk
        and "ON CONFLICT" not in chunk  # the inheritance INSERT, not a count
    ]


@pytest.mark.parametrize("module,marker", [
    (classify, "_refresh_unclassified_count"),
    (strata, "recompute_strata bulk refresh"),
    (authority_ingest, "_recount"),
])
def test_every_writer_filters_confirmed_inside_the_join(module, marker):
    """The status filter must live in the JOIN's ON clause, not the WHERE.

    In the WHERE it would filter out the very NULL rows the count looks for and
    the count would always read 0 — a total inversion. Asserting the substring
    alone (anywhere in the SQL) would not catch that.
    """
    queries = _unclassified_queries(module)
    assert queries, f"{marker}: no unclassified-count query found"
    for sql in queries:
        on_clause = _join_clause(sql)
        assert "c.status = 'confirmed'" in on_clause, (
            f"{marker}: the confirmed-only filter must be in the JOIN's ON clause "
            f"(found ON:{on_clause!r}). In the WHERE it inverts the count to 0."
        )


# ── behavior, via a fake that honours the real predicate ─────────────────────

class FakeConn:
    """Computes the count the way the SQL's predicate says to, so a regression
    that changes the predicate changes what this fake returns too."""

    def __init__(self, item_statuses):
        # item_id -> classification status, or None for "no classification row"
        self.item_statuses = item_statuses
        self.updated = None

    async def fetchval(self, sql, *args):
        if "COUNT(*) FROM authority_index_items" in sql and "LEFT JOIN" not in sql:
            return len(self.item_statuses)  # _recount's item_count query
        assert "authority_item_classifications" in sql
        confirmed_only = "c.status = 'confirmed'" in _join_clause(sql)

        def _is_unclassified(status):
            # The JOIN's ON clause decides which rows survive to be NULL-checked.
            return status != "confirmed" if confirmed_only else status is None

        return sum(1 for s in self.item_statuses.values() if _is_unclassified(s))

    async def execute(self, sql, *args):
        assert "UPDATE authority_indexes" in sql
        self.updated = args


@pytest.mark.asyncio
async def test_provisional_only_index_is_not_zero():
    """The soundness-hole scenario: every item Gemini-classified (provisional),
    nothing confirmed. The gate must still see this as fully unclassified."""
    conn = FakeConn({"item-1": "provisional", "item-2": "provisional"})

    count = await _refresh_unclassified_count(conn, "index-1")

    assert count == 2
    assert conn.updated == (2, "index-1")


@pytest.mark.asyncio
async def test_confirmed_items_are_not_counted():
    conn = FakeConn({"item-1": "confirmed", "item-2": "confirmed"})
    assert await _refresh_unclassified_count(conn, "index-1") == 0


@pytest.mark.asyncio
async def test_mixed_confirmed_provisional_and_unclassified():
    conn = FakeConn({
        "item-1": "confirmed",
        "item-2": "provisional",
        "item-3": None,  # never classified at all
    })
    assert await _refresh_unclassified_count(conn, "index-1") == 2


@pytest.mark.asyncio
async def test_ingest_recount_agrees_with_classify():
    """_recount runs on every ingest and rewrites the same column — if it kept
    the any-row predicate it would silently revert the fix."""
    conn = FakeConn({"item-1": "provisional", "item-2": "confirmed"})

    item_count, unclassified = await _recount(conn, "index-1")

    assert (item_count, unclassified) == (2, 1)
