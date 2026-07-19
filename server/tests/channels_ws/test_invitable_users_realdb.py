"""Real-PG regression tests for the channels invitable-users SQL.

`channels.search_invitable_users` builds the WHERE clause dynamically from
the request shape. Four meaningfully different SQL strings can come out of
that builder, and each one needs to PREPARE cleanly against PostgreSQL.

The mocked test in `test_invitable_users_plus_workaround.py` validates the
Python branching but cannot catch a regression where the dynamic builder
emits an SQL with un-typed `$N` references that fail at PG prepare time
(same class of bug as the kanban `$3` ambiguity from `ac85e0d`).

These tests gate on `DATABASE_URL`, build each SQL variant with the same
template the route uses, and PREPARE it. They do not execute or modify any
data, so they are safe to run against the live DB.

Run manually:
    cd server
    DATABASE_URL=... python3 -m pytest tests/channels_ws/test_invitable_users_realdb.py -v
"""

import os

import pytest
import pytest_asyncio

asyncpg = pytest.importorskip("asyncpg")

DATABASE_URL = os.environ.get("DATABASE_URL", "")

pytestmark = [
    pytest.mark.skipif(not DATABASE_URL, reason="DATABASE_URL not set"),
    pytest.mark.asyncio(loop_scope="module"),
]


# Mirror the _USER_NAME_EXPR + WHERE template from
# app/werk/routes/channels.py:721. The {name_filter} and
# {exact_email_clause} placeholders are filled per-shape below.
_USER_NAME_EXPR = (
    "COALESCE(c.name, CONCAT(e.first_name, ' ', e.last_name), a.name, u.email)"
)


def _build_sql(name_filter: str, exact_email_clause: str) -> str:
    return f"""
SELECT DISTINCT u.id, u.email, u.role, u.avatar_url,
       {_USER_NAME_EXPR} AS name
FROM users u
LEFT JOIN clients c ON c.user_id = u.id
LEFT JOIN employees e ON e.user_id = u.id
LEFT JOIN admins a ON a.user_id = u.id
WHERE u.id != $1 AND u.is_active = true
  {name_filter}
  AND (
    ($2::uuid IS NOT NULL AND (c.company_id = $2::uuid OR e.org_id = $2::uuid))
    OR EXISTS(
      SELECT 1 FROM inbox_participants ip1
      JOIN inbox_participants ip2 ON ip2.conversation_id = ip1.conversation_id
      WHERE ip1.user_id = $1 AND ip2.user_id = u.id
    )
    OR EXISTS(
      SELECT 1 FROM mw_project_collaborators pc1
      JOIN mw_project_collaborators pc2 ON pc2.project_id = pc1.project_id
      WHERE pc1.user_id = $1 AND pc2.user_id = u.id
      AND pc1.status = 'active' AND pc2.status = 'active'
    )
    OR a.user_id IS NOT NULL
    OR EXISTS(
      SELECT 1 FROM user_connections uc
      WHERE (uc.user_id = $1 AND uc.connected_user_id = u.id AND uc.status = 'accepted')
      OR (uc.connected_user_id = $1 AND uc.user_id = u.id AND uc.status = 'accepted')
    )
    OR {exact_email_clause}
  )
ORDER BY {_USER_NAME_EXPR}
LIMIT 20
"""


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def pool():
    p = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=2)
    yield p
    await p.close()


async def test_prepare_bare_no_search(pool):
    """No `q` provided. WHERE has no name_filter, exact_email_clause is FALSE.
    2 params: $1=user_id (uuid), $2=company_id (nullable uuid)."""
    sql = _build_sql(name_filter="", exact_email_clause="FALSE")
    async with pool.acquire() as conn:
        stmt = await conn.prepare(sql)
        assert len(stmt.get_parameters()) == 2


async def test_prepare_plain_text_search(pool):
    """`q` is non-empty plain text (no space, not an email). One ILIKE filter.
    3 params: user_id, company_id, search-pattern."""
    name_filter = f"AND ({_USER_NAME_EXPR} ILIKE $3 OR u.email ILIKE $3)"
    sql = _build_sql(name_filter=name_filter, exact_email_clause="FALSE")
    async with pool.acquire() as conn:
        stmt = await conn.prepare(sql)
        assert len(stmt.get_parameters()) == 3


async def test_prepare_q_with_space_not_email(pool):
    """`q` has a space but no @. Builder adds `q_alt` ILIKE on email only,
    no exact_email_clause. 4 params: user_id, company_id, search, search_alt."""
    name_filter = (
        f"AND ({_USER_NAME_EXPR} ILIKE $3 OR u.email ILIKE $3 OR u.email ILIKE $4)"
    )
    sql = _build_sql(name_filter=name_filter, exact_email_clause="FALSE")
    async with pool.acquire() as conn:
        stmt = await conn.prepare(sql)
        assert len(stmt.get_parameters()) == 4


async def test_prepare_q_email_with_space_worst_case(pool):
    """The exact `tessu2022 mon@gmail.com` shape (Starlette-decoded `+`).
    Builder produces: ILIKE on q, ILIKE on q_alt, exact email = q.lower(),
    exact email = q_alt.lower(). 6 params total."""
    name_filter = (
        f"AND ({_USER_NAME_EXPR} ILIKE $3 OR u.email ILIKE $3 OR u.email ILIKE $4)"
    )
    exact_email_clause = "(LOWER(u.email) = $5 OR LOWER(u.email) = $6)"
    sql = _build_sql(name_filter=name_filter, exact_email_clause=exact_email_clause)
    async with pool.acquire() as conn:
        stmt = await conn.prepare(sql)
        assert len(stmt.get_parameters()) == 6


async def test_prepare_q_email_no_space(pool):
    """Properly-encoded email query (`%2B` decoded back to `+`). No `q_alt`.
    5 params: user_id, company_id, search, exact_email."""
    name_filter = f"AND ({_USER_NAME_EXPR} ILIKE $3 OR u.email ILIKE $3)"
    exact_email_clause = "(LOWER(u.email) = $4)"
    sql = _build_sql(name_filter=name_filter, exact_email_clause=exact_email_clause)
    async with pool.acquire() as conn:
        stmt = await conn.prepare(sql)
        assert len(stmt.get_parameters()) == 4
