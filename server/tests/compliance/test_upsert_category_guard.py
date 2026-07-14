"""category_id resolution on the two jurisdiction_requirements upsert paths.

Regression coverage for the arbitrary-LIMIT-1-fallback bug: an unresolvable
category slug used to COALESCE to whatever row `compliance_categories LIMIT 1`
happened to return (no ORDER BY), mis-tagging the requirement into a random
category instead of its true one.

The fix must satisfy TWO invariants that pull against each other:
  * never an arbitrary category (the original bug), and
  * never silently DROP the row either — the `category` TEXT column is what
    nearly every read path filters on, and the code registry has repeatedly
    gained categories before their compliance_categories seed migration landed
    (baseline01, mfgcat01, catseed01). Dropping would have made e.g. every
    pay_transparency / non_compete research result vanish.
So: park on the `uncategorized` sentinel, and only drop if even that is absent.
"""
import pytest

from app.core.services import compliance_service as cs

CATEGORIES = [
    {"id": "cat-minimum-wage", "slug": "minimum_wage"},
    {"id": "cat-overtime", "slug": "overtime"},
    {"id": "cat-uncategorized", "slug": "uncategorized"},
]

# A DB that predates the `uncategorized` sentinel (zo3p4q5r6s7t) — the only
# case in which dropping the row is the correct last resort.
CATEGORIES_NO_SENTINEL = [
    {"id": "cat-minimum-wage", "slug": "minimum_wage"},
    {"id": "cat-overtime", "slug": "overtime"},
]

# Positional index of category_id in each upsert's arg list ($19 → index 18).
CATEGORY_ID_ARG = 18


class FakeConn:
    """Answers the category lookup + records every INSERT this upsert issues."""

    def __init__(self, categories, existing=()):
        self.categories = categories
        self.existing = list(existing)
        self.executed = []
        self.inserted = []
        self.deleted = []

    async def fetch(self, sql, *args):
        if "FROM compliance_categories" in sql:
            return list(self.categories)
        # _upsert_jurisdiction_requirements' stale-row cleanup query.
        return list(self.existing)

    async def fetchval(self, sql, *args):
        # _upsert_jurisdiction_requirements' trailing count-and-touch step.
        return 0

    async def execute(self, sql, *args):
        if "INSERT INTO jurisdiction_requirements" in sql:
            self.inserted.append(args)
        if "DELETE FROM jurisdiction_requirements" in sql:
            self.deleted.append(args)
        self.executed.append(args)


def _req(category, title="A Requirement"):
    return {"category": category, "title": title, "jurisdiction_level": "state"}


# ── the original bug: never an arbitrary category ────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("upsert", [
    cs._upsert_requirements_additive,
    cs._upsert_jurisdiction_requirements,
])
async def test_unresolvable_category_never_lands_on_an_arbitrary_row(upsert):
    conn = FakeConn(CATEGORIES)

    await upsert(conn, "jur-1", [_req("totally_unmapped_category")])

    assert len(conn.inserted) == 1
    landed = conn.inserted[0][CATEGORY_ID_ARG]
    assert landed == "cat-uncategorized", (
        "an unresolvable category must park on the 'uncategorized' sentinel — "
        "never on whatever row compliance_categories happens to return first"
    )
    assert landed not in ("cat-minimum-wage", "cat-overtime")


# ── the over-correction: never silently drop a legitimate row ────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("upsert", [
    cs._upsert_requirements_additive,
    cs._upsert_jurisdiction_requirements,
])
async def test_unresolvable_category_is_still_written(upsert):
    """Registry↔seed drift must not make research results disappear: the row
    carries a correct `category` TEXT value, which is what nearly every read
    path filters on."""
    conn = FakeConn(CATEGORIES)

    await upsert(conn, "jur-1", [_req("pay_transparency", "Salary Range Disclosure")])

    assert len(conn.inserted) == 1, "row must be written, not dropped"
    # $3 is the category TEXT column — preserved verbatim even when unseeded.
    assert conn.inserted[0][2] == "pay_transparency"


@pytest.mark.asyncio
@pytest.mark.parametrize("upsert", [
    cs._upsert_requirements_additive,
    cs._upsert_jurisdiction_requirements,
])
async def test_dropped_only_when_even_the_sentinel_is_missing(upsert):
    conn = FakeConn(CATEGORIES_NO_SENTINEL)

    await upsert(conn, "jur-1", [_req("totally_unmapped_category")])

    assert conn.inserted == [], (
        "with no 'uncategorized' row to park on there is no correct category_id "
        "to write (the column is NOT NULL) — dropping is the last resort"
    )


# ── the happy path still resolves precisely ──────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("upsert,slug,expected", [
    (cs._upsert_requirements_additive, "overtime", "cat-overtime"),
    (cs._upsert_jurisdiction_requirements, "minimum_wage", "cat-minimum-wage"),
])
async def test_resolvable_category_uses_its_own_id(upsert, slug, expected):
    conn = FakeConn(CATEGORIES)

    await upsert(conn, "jur-1", [_req(slug)])

    assert len(conn.inserted) == 1
    assert conn.inserted[0][CATEGORY_ID_ARG] == expected


# ── the stale-row cleanup must not weaponize a category miss ─────────────────

@pytest.mark.asyncio
async def test_dropped_row_does_not_purge_the_jurisdictions_existing_row():
    """_upsert_jurisdiction_requirements DELETEs rows whose requirement_key
    isn't in the new set. A row skipped for an unresolvable category must still
    contribute its key, or the skip would ALSO delete whatever the jurisdiction
    already had stored under it — turning a tagging miss into data loss."""
    reqs = [_req("totally_unmapped_category", "Orphaned Requirement")]
    key = cs._compute_requirement_key(reqs[0])
    conn = FakeConn(CATEGORIES_NO_SENTINEL,  # forces the drop path
                    existing=[{"id": "row-1", "requirement_key": key}])

    await cs._upsert_jurisdiction_requirements(conn, "jur-1", reqs)

    assert conn.inserted == []          # skipped, as designed
    assert conn.deleted == [], "the skipped row's key must still protect the existing row"
