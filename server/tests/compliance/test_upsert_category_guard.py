"""category_id resolution guard on the two jurisdiction_requirements upsert paths.

Regression coverage for the arbitrary-LIMIT-1-fallback bug: an unresolvable
category slug used to COALESCE to whatever row `compliance_categories LIMIT 1`
happened to return (no ORDER BY), mis-tagging the requirement into a random
category instead of its true one. Both upserts must now skip the row instead.
"""
import pytest

from app.core.services import compliance_service as cs

CATEGORIES = [
    {"id": "cat-minimum-wage", "slug": "minimum_wage"},
    {"id": "cat-overtime", "slug": "overtime"},
]


class FakeConn:
    """Answers the category lookup + records every INSERT this upsert issues."""

    def __init__(self, categories):
        self.categories = categories
        self.executed = []
        self.inserted = []

    async def fetch(self, sql, *args):
        if "FROM compliance_categories" in sql:
            return list(self.categories)
        # _upsert_jurisdiction_requirements' stale-row cleanup query — no
        # pre-existing rows to reconcile against in these tests.
        return []

    async def fetchval(self, sql, *args):
        # _upsert_jurisdiction_requirements' trailing count-and-touch step.
        return 0

    async def execute(self, sql, *args):
        if "INSERT INTO jurisdiction_requirements" in sql:
            self.inserted.append(args)
        self.executed.append(args)


@pytest.mark.asyncio
async def test_additive_upsert_skips_unresolvable_category():
    conn = FakeConn(CATEGORIES)
    reqs = [{
        "category": "totally_unmapped_category",
        "title": "Orphaned Requirement",
        "jurisdiction_level": "state",
    }]

    await cs._upsert_requirements_additive(conn, "jur-1", reqs, research_source="gemini")

    assert conn.inserted == [], (
        "an unresolvable category must never fall back to an arbitrary "
        "compliance_categories row — the row should be skipped, not inserted"
    )


@pytest.mark.asyncio
async def test_additive_upsert_uses_the_resolved_category_id():
    conn = FakeConn(CATEGORIES)
    reqs = [{
        "category": "overtime",
        "title": "Daily Overtime",
        "jurisdiction_level": "state",
    }]

    await cs._upsert_requirements_additive(conn, "jur-1", reqs, research_source="gemini")

    assert len(conn.inserted) == 1
    # category_id is positional arg index 18 ($19) — see the INSERT param comment.
    assert conn.inserted[0][18] == "cat-overtime"


@pytest.mark.asyncio
async def test_jurisdiction_upsert_skips_unresolvable_category():
    conn = FakeConn(CATEGORIES)
    reqs = [{
        "category": "totally_unmapped_category",
        "title": "Orphaned Requirement",
        "jurisdiction_level": "state",
    }]

    await cs._upsert_jurisdiction_requirements(conn, "jur-1", reqs)

    assert conn.inserted == [], (
        "an unresolvable category must never fall back to an arbitrary "
        "compliance_categories row — the row should be skipped, not inserted"
    )


@pytest.mark.asyncio
async def test_jurisdiction_upsert_uses_the_resolved_category_id():
    conn = FakeConn(CATEGORIES)
    reqs = [{
        "category": "minimum_wage",
        "title": "State Minimum Wage",
        "jurisdiction_level": "state",
    }]

    await cs._upsert_jurisdiction_requirements(conn, "jur-1", reqs)

    assert len(conn.inserted) == 1
    # category_id is positional arg index 18 ($19) — see the INSERT param comment.
    assert conn.inserted[0][18] == "cat-minimum-wage"
