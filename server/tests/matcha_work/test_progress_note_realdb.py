"""Real-PG regression tests for the `mw_tasks.progress_note` column.

Symptom we're guarding against: backend returns 500 with
`asyncpg.exceptions.UndefinedColumnError: column t.progress_note does not exist`
on `GET /api/matcha-work/tasks/open` and `GET /api/matcha-work/projects/{id}/tasks`.

Both endpoints select `t.progress_note` from `mw_tasks t`. The column was
added by Alembic migration `zzzy1z2a3b4c5_add_progress_note_to_mw_tasks.py`.
If the column is missing or a stale asyncpg pool emits the cached error,
these prepare-time tests catch the regression by failing to PREPARE.

Read-only — no rows are inserted or modified — so safe against live DB.

Run manually:
    cd server
    DATABASE_URL=postgresql://matcha:matcha_dev@localhost:5432/matcha \
        python3 -m pytest tests/matcha_work/test_progress_note_realdb.py -v
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


# Byte-for-byte SQL from server/app/matcha/routes/matcha_work.py:3653-3672
# (`@router.get("/tasks/open")` — `list_open_tasks_endpoint`).
TASKS_OPEN_SQL = """
SELECT t.id, t.project_id, t.title, t.priority, t.status,
       t.due_date, t.progress_note, t.assigned_to, t.created_by,
       t.updated_at,
       p.title AS project_title, p.project_type
FROM mw_tasks t
LEFT JOIN mw_projects p ON p.id = t.project_id
WHERE t.company_id = $1
  AND t.status = 'pending'
  AND t.project_id IS NOT NULL
  AND (t.assigned_to = $2 OR t.created_by = $2 OR t.assigned_to IS NULL)
ORDER BY
    CASE t.priority
        WHEN 'critical' THEN 0 WHEN 'high' THEN 1
        WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4
    END,
    t.due_date NULLS LAST,
    t.updated_at DESC
LIMIT 50
"""


# Byte-for-byte SQL from server/app/matcha/services/project_task_service.py
# `list_project_tasks` — used by the kanban tab and selects t.progress_note.
LIST_PROJECT_TASKS_SQL = """
SELECT t.id, t.project_id, t.company_id, t.created_by, t.title, t.description,
       t.due_date, t.priority, t.status, t.board_column, t.assigned_to,
       t.completed_at, t.created_at, t.updated_at, t.progress_note,
       COALESCE(a.name, u.email) AS assigned_name
FROM mw_tasks t
LEFT JOIN users u ON u.id = t.assigned_to
LEFT JOIN admins a ON a.user_id = t.assigned_to
WHERE t.project_id = $1 AND t.status != 'cancelled'
ORDER BY
    CASE t.priority
        WHEN 'critical' THEN 0 WHEN 'high' THEN 1
        WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4
    END,
    t.created_at DESC
"""


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def pool():
    p = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=2)
    yield p
    await p.close()


async def test_progress_note_column_exists(pool):
    """Asserts `mw_tasks.progress_note` exists in information_schema. If the
    Alembic migration `zzzy1z2a3b4c5` hasn't been applied to this DB, this
    test fails with a clear message instead of an obscure 500."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT data_type
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = 'mw_tasks'
              AND column_name = 'progress_note'
            """
        )
        assert row is not None, (
            "mw_tasks.progress_note column missing — "
            "alembic migration zzzy1z2a3b4c5 not applied"
        )
        assert row["data_type"] == "text"


async def test_tasks_open_query_prepares(pool):
    """PREPARE the `/tasks/open` SELECT. Pre-fix (column missing) raised
    `UndefinedColumnError: column t.progress_note does not exist`."""
    async with pool.acquire() as conn:
        stmt = await conn.prepare(TASKS_OPEN_SQL)
        params = stmt.get_parameters()
        assert len(params) == 2, f"expected 2 params, got {len(params)}"


async def test_tasks_open_query_executes_with_random_company(pool):
    """Bind + execute with random UUIDs that match no rows. Confirms the
    SQL is well-typed end-to-end. Read-only — no rows touched."""
    async with pool.acquire() as conn:
        tr = conn.transaction()
        await tr.start()
        try:
            rows = await conn.fetch(
                TASKS_OPEN_SQL,
                uuid.uuid4(),  # $1 company_id
                uuid.uuid4(),  # $2 current_user.id
            )
            assert rows == []
        finally:
            await tr.rollback()


async def test_list_project_tasks_query_prepares(pool):
    """PREPARE the kanban list-tasks SELECT. Same `progress_note` regression
    guard for the `GET /api/matcha-work/projects/{id}/tasks` endpoint."""
    async with pool.acquire() as conn:
        stmt = await conn.prepare(LIST_PROJECT_TASKS_SQL)
        params = stmt.get_parameters()
        assert len(params) == 1, f"expected 1 param, got {len(params)}"


async def test_list_project_tasks_query_executes_with_random_project(pool):
    """Bind + execute with random UUID that matches no rows. Read-only."""
    async with pool.acquire() as conn:
        tr = conn.transaction()
        await tr.start()
        try:
            rows = await conn.fetch(
                LIST_PROJECT_TASKS_SQL,
                uuid.uuid4(),  # $1 project_id
            )
            assert rows == []
        finally:
            await tr.rollback()
