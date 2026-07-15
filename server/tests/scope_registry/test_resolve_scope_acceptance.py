"""§9 acceptance — the flagship case, asserted through resolve_scope's REAL SQL.

The whole engine exists to answer one question correctly:

    a WAREHOUSE in LOS ANGELES gets
      * AB 701 (Cal. Lab. Code §§ 2100-2105)  — warehouse quota law, CA-only
      * 29 CFR 1910.147 (lockout/tagout)      — universal general industry
    and does NOT get
      * 29 CFR 1910.119 (process safety mgmt) — conditional on PSM chemicals,
                                                which a warehouse doesn't have

Every existing test asserted this against hand-built dicts through
`classification_matches` — the pure helper — so the disposition logic was
covered but the SQL that feeds it was not: the confirmed-status filter, the
jurisdiction-chain join, the key-precise catalog join, the codified/uncodified
split. A bug in any of those would pass the pure tests and still serve a
warehouse the PSM standard. This closes that (COMPLIANCE_SYSTEM_GAP_REVIEW.md §8).

Self-contained: seeds its OWN authority index inside a transaction and rolls
back, so it depends on no ambient dev data and leaves none behind. Requires only
that the jurisdictions rows for federal / CA / Los Angeles exist.

Manual, like the other DB tests here — root CLAUDE.md forbids auto-running
DB-touching tests:

    RUN_DB_GAP_TESTS=1 ./venv/bin/python -m pytest \
        tests/scope_registry/test_resolve_scope_acceptance.py -q
"""
import os
from contextlib import asynccontextmanager

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_GAP_TESTS") != "1",
    reason="manual DB integration test — set RUN_DB_GAP_TESTS=1 on dev to run",
)

INDEX_SLUG = "__test_acceptance_idx"


@asynccontextmanager
async def _conn():
    """A direct connection, not the app pool.

    `resolve_scope` takes a connection, so there is no reason to stand up the
    FastAPI-lifespan pool — and an asyncpg pool built in one event loop can't be
    reused from the fresh loop pytest-asyncio gives each test.
    """
    import asyncpg

    from app.config import load_settings

    conn = await asyncpg.connect(load_settings().database_url)
    try:
        yield conn
    finally:
        await conn.close()

# (citation, heading, disposition, applies_to, excludes, entity_condition, regulation_key)
_ITEMS = [
    (
        "29 CFR § 1910.147", "The control of hazardous energy (lockout/tagout)",
        "universal_in_domain", [], [], None, "lockout_tagout",
    ),
    (
        "29 CFR § 1910.119", "Process safety management of highly hazardous chemicals",
        "conditional", [], [],
        # Fires only for a facility that actually holds PSM-covered chemicals.
        # Shape must match seed._PSM_CONDITION exactly — see
        # test_a_malformed_condition_does_not_silently_over_scope below for why
        # an approximation here is not good enough.
        '{"type": "attribute", "key": "psm_covered_chemicals", "operator": "eq", "value": true}',
        "process_safety_management",
    ),
    (
        "Cal. Lab. Code § 2100", "Warehouse distribution centers — quota disclosure (AB 701)",
        "category_specific", ["warehousing"], [], None, "warehouse_quota",
    ),
]


async def _seed(conn) -> None:
    """A tiny federal-level index carrying all three §9 items, confirmed."""
    index_id = await conn.fetchval(
        """
        INSERT INTO authority_indexes
            (slug, name, level, jurisdiction_id, source_type, enumerable,
             domain_categories, item_count, unclassified_count)
        VALUES ($1, 'acceptance fixture', 'federal', NULL, 'curated', false,
                ARRAY['all_industry'], 0, 0)
        RETURNING id
        """,
        INDEX_SLUG,
    )
    for citation, heading, disposition, applies, excludes, cond, key in _ITEMS:
        item_id = await conn.fetchval(
            """
            INSERT INTO authority_index_items
                (authority_index_id, citation, heading)
            VALUES ($1, $2, $3) RETURNING id
            """,
            index_id, citation, heading,
        )
        await conn.execute(
            """
            INSERT INTO authority_item_classifications
                (item_id, disposition, applies_to_categories, excludes_categories,
                 entity_condition, regulation_key, status, proposed_by)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6, 'confirmed', 'admin')
            """,
            item_id, disposition, applies, excludes, cond, key,
        )


def _citations(entries) -> set:
    return {e["citation"] for e in entries}


@pytest.mark.asyncio
async def test_la_warehouse_gets_ab701_and_loto_but_not_psm():
    from app.core.services.scope_registry.resolve import resolve_scope

    async with _conn() as conn:
        tx = conn.transaction()
        await tx.start()
        try:
            await _seed(conn)

            res = await resolve_scope(
                conn,
                category="warehousing",
                state="CA",
                city="Los Angeles",
                # A warehouse holds no PSM-covered chemicals.
                facility_attributes={"employee_count": 250},
                use_cache=False,
            )

            applicable = _citations(res["codified"]) | _citations(res["uncodified"])
            ours = {c for c in applicable if c in {i[0] for i in _ITEMS}}

            assert "Cal. Lab. Code § 2100" in ours, (
                "AB 701 is THE warehouse obligation — a warehouse that doesn't "
                "resolve it is the flagship failure this engine exists to prevent"
            )
            assert "29 CFR § 1910.147" in ours, "lockout/tagout is universal general industry"
            assert "29 CFR § 1910.119" not in ours, (
                "PSM is conditional on psm_covered_chemicals — serving it to a "
                "warehouse is over-scoping, the precision the registry is FOR"
            )
            assert ours == {"Cal. Lab. Code § 2100", "29 CFR § 1910.147"}

            # The conditional that didn't fire is counted, not silently dropped.
            assert res["counts"]["conditional_skipped"] >= 1
        finally:
            await tx.rollback()


@pytest.mark.asyncio
async def test_psm_appears_once_the_facility_actually_holds_the_chemicals():
    """The same coordinate, one attribute different — the conditional must fire.

    Without this, `test_...not_in ours` above would also pass if the engine
    simply never resolved 1910.119 at all (e.g. a broken join), which would be a
    false green on the exclusion.
    """
    from app.core.services.scope_registry.resolve import resolve_scope

    async with _conn() as conn:
        tx = conn.transaction()
        await tx.start()
        try:
            await _seed(conn)

            res = await resolve_scope(
                conn,
                category="warehousing",
                state="CA",
                city="Los Angeles",
                facility_attributes={"employee_count": 250, "psm_covered_chemicals": True},
                use_cache=False,
            )

            applicable = _citations(res["codified"]) | _citations(res["uncodified"])
            assert "29 CFR § 1910.119" in applicable, (
                "the conditional never fires — the exclusion in the test above "
                "would be passing for the wrong reason"
            )
        finally:
            await tx.rollback()


@pytest.mark.asyncio
async def test_a_non_warehouse_does_not_get_ab701():
    """AB 701 is category_specific. A healthcare facility in the same city must
    not inherit it — the other half of scoping precision."""
    from app.core.services.scope_registry.resolve import resolve_scope

    async with _conn() as conn:
        tx = conn.transaction()
        await tx.start()
        try:
            await _seed(conn)

            res = await resolve_scope(
                conn,
                category="healthcare",
                state="CA",
                city="Los Angeles",
                facility_attributes={"employee_count": 250},
                use_cache=False,
            )

            applicable = _citations(res["codified"]) | _citations(res["uncodified"])
            assert "Cal. Lab. Code § 2100" not in applicable
            assert "29 CFR § 1910.147" in applicable, "LOTO is still universal"
        finally:
            await tx.rollback()


@pytest.mark.asyncio
async def test_provisional_classifications_are_invisible_to_the_engine():
    """Every engine read filters status='confirmed'. This is the invariant the
    whole confirm queue rests on — asserted here through the real SQL, because
    the pure tests never touch the status column at all."""
    from app.core.services.scope_registry.resolve import resolve_scope

    async with _conn() as conn:
        tx = conn.transaction()
        await tx.start()
        try:
            await _seed(conn)
            await conn.execute(
                """
                UPDATE authority_item_classifications c
                SET status = 'provisional'
                FROM authority_index_items i, authority_indexes ai
                WHERE c.item_id = i.id AND i.authority_index_id = ai.id
                  AND ai.slug = $1
                """,
                INDEX_SLUG,
            )

            res = await resolve_scope(
                conn,
                category="warehousing",
                state="CA",
                city="Los Angeles",
                facility_attributes={"employee_count": 250},
                use_cache=False,
            )

            applicable = _citations(res["codified"]) | _citations(res["uncodified"])
            assert not (applicable & {i[0] for i in _ITEMS}), (
                "unconfirmed classifications must contribute NOTHING — if they "
                "resolve, the confirm queue is decorative and Gemini's proposals "
                "are being served to tenants unreviewed"
            )
        finally:
            await tx.rollback()
