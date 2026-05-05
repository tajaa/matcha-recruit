"""Real-PG regression tests for the kanban toggle UPDATE.

The mocked tests in `test_project_task_toggle.py` cannot catch
`asyncpg.exceptions.AmbiguousParameterError` because that error is raised
at PG **prepare** time — and a `_FakeConn` mock never goes through prepare.

The original snap-back bug fix (commit `ac85e0d`) was exactly that error:
the SQL used `$3` in both `status = $3` (varchar column) and
`CASE WHEN $3 = 'completed' THEN ... ELSE NULL END`, and asyncpg's type
inference saw inconsistent contexts.

These tests gate on `DATABASE_URL`, PREPARE the exact SQL that the service
layer issues, and assert that prepare succeeds. They are read-only — no
rows are inserted or modified — so they are safe to run against the live DB.

Run manually:
    cd server
    DATABASE_URL=... python3 -m pytest tests/matcha_work/test_project_task_toggle_realdb.py -v
"""

import os
import uuid

import pytest
import pytest_asyncio

asyncpg = pytest.importorskip("asyncpg")

DATABASE_URL = os.environ.get("DATABASE_URL", "")

pytestmark = [
    pytest.mark.skipif(not DATABASE_URL, reason="DATABASE_URL not set"),
    pytest.mark.asyncio(loop_scope="module"),
]


# Exact SQL from app/matcha/services/project_task_service.py
# Keep this byte-for-byte in sync with `update_project_task` so a regression
# in the service file's SQL surfaces here at prepare time.
UPDATE_TASK_SQL = """
UPDATE mw_tasks SET
    board_column = $1::text,
    status = $3::text,
    completed_at = CASE
        WHEN $3::text = 'completed' THEN COALESCE(completed_at, $13::timestamptz)
        ELSE NULL
    END,
    title = COALESCE($4::text, title),
    description = CASE WHEN $5::boolean THEN $6::text ELSE description END,
    priority = COALESCE($7::text, priority),
    due_date = CASE WHEN $8::boolean THEN $9::date ELSE due_date END,
    assigned_to = CASE WHEN $10::boolean THEN $11::uuid ELSE assigned_to END,
    updated_at = NOW()
WHERE id = $2 AND project_id = $12
RETURNING id, project_id, company_id, created_by, title, description,
          due_date, priority, status, board_column, assigned_to,
          completed_at, created_at, updated_at
"""


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def pool():
    p = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=2)
    yield p
    await p.close()


async def test_update_sql_prepares_without_ambiguous_parameters(pool):
    """PREPARE the exact UPDATE SQL. Pre-fix this raised
    `asyncpg.exceptions.AmbiguousParameterError: inconsistent types deduced
    for parameter $3 -- text versus character varying`.
    """
    async with pool.acquire() as conn:
        # If prepare raises, the test fails — that's the regression signal.
        stmt = await conn.prepare(UPDATE_TASK_SQL)
        params = stmt.get_parameters()
        assert len(params) == 13, f"expected 13 params, got {len(params)}"


async def test_update_sql_executes_against_nonexistent_row_is_noop(pool):
    """Execute prepare-and-fetch with random UUIDs that don't exist. Returns
    None. Asserts that the SQL is well-typed end-to-end (not just at
    prepare) and that all 13 params can be bound with realistic Python
    values without further coercion errors. No rows are modified."""
    from datetime import date, datetime, timezone

    async with pool.acquire() as conn:
        # Wrap in a transaction we always rollback — belt and suspenders;
        # no row should match the WHERE so this is already a no-op.
        tr = conn.transaction()
        await tr.start()
        try:
            row = await conn.fetchrow(
                UPDATE_TASK_SQL,
                "done",                                          # $1
                uuid.uuid4(),                                    # $2
                "completed",                                     # $3
                None,                                            # $4
                False,                                           # $5
                None,                                            # $6
                None,                                            # $7
                False,                                           # $8
                None,                                            # $9
                False,                                           # $10
                None,                                            # $11
                uuid.uuid4(),                                    # $12
                datetime.now(timezone.utc),                      # $13
            )
            assert row is None
        finally:
            await tr.rollback()


async def test_update_sql_bind_with_due_date_branch_engaged(pool):
    """Engage the due_date CASE branch ($8=True) with a real date value
    bound to $9. Pre-fix variants (no `::timestamptz` cast on $13) failed
    here too because asyncpg's bind-time coercion on the CASE branches
    interacted with the un-typed completed_at NULL branch. Still no-op
    via random UUID + rollback."""
    from datetime import date

    async with pool.acquire() as conn:
        tr = conn.transaction()
        await tr.start()
        try:
            row = await conn.fetchrow(
                UPDATE_TASK_SQL,
                "todo",                                          # $1
                uuid.uuid4(),                                    # $2
                "pending",                                       # $3
                "renamed task",                                  # $4
                True,                                            # $5
                "new desc",                                      # $6
                "high",                                          # $7
                True,                                            # $8
                date(2026, 12, 31),                              # $9
                True,                                            # $10
                uuid.uuid4(),                                    # $11 assigned_to
                uuid.uuid4(),                                    # $12
                None,                                            # $13 (status=pending → NULL branch)
            )
            assert row is None
        finally:
            await tr.rollback()
