"""Integration tests for PostgreSQL row-level security (RLS).

These tests verify that RLS policies work correctly using SET ROLE
to simulate a non-superuser application role. They require:
  1. DATABASE_URL set in environment
  2. The matcha_app role to exist (created by migration b2c3d4e5f6g7)
  3. RLS policies to be applied (migrations e72bfad5eca9 + a1b2c3d4e5f6)

Run manually:
    cd server
    DATABASE_URL=... python3 -m pytest tests/test_rls_isolation.py -v

These tests are READ-ONLY against existing tables — they use
SET ROLE / RESET ROLE to test RLS enforcement without creating
any tables, roles, or modifying schema.
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

FAKE_COMPANY_A = str(uuid.uuid4())
FAKE_COMPANY_B = str(uuid.uuid4())
FAKE_USER = str(uuid.uuid4())


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def pool():
    p = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=3)
    yield p
    await p.close()


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def has_app_role(pool):
    """Check if matcha_app role exists. Skip tests if not."""
    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname = 'matcha_app')"
        )
    if not exists:
        pytest.skip("matcha_app role not created yet — run migration b2c3d4e5f6g7 first")
    return True


# ── Session variable tests (don't need matcha_app role) ──────────────

async def test_session_var_persists_with_false_flag(pool):
    """set_config with is_local=false should persist across statements."""
    async with pool.acquire() as conn:
        await conn.execute(
            "SELECT set_config('app.current_tenant_id', $1, false)",
            FAKE_COMPANY_A,
        )
        val1 = await conn.fetchval(
            "SELECT current_setting('app.current_tenant_id', true)"
        )
        val2 = await conn.fetchval(
            "SELECT current_setting('app.current_tenant_id', true)"
        )
        assert val1 == FAKE_COMPANY_A
        assert val2 == FAKE_COMPANY_A
        # Cleanup
        await conn.execute(
            "SELECT set_config('app.current_tenant_id', '', false)"
        )


async def test_session_var_resets_after_cleanup(pool):
    """Simulating the finally block: value should be empty after reset."""
    async with pool.acquire() as conn:
        await conn.execute(
            "SELECT set_config('app.current_tenant_id', $1, false)",
            FAKE_COMPANY_A,
        )
        await conn.execute(
            "SELECT set_config('app.current_tenant_id', '', false)"
        )
        val = await conn.fetchval(
            "SELECT current_setting('app.current_tenant_id', true)"
        )
        assert val == ""


async def test_admin_flag_session_var(pool):
    """app.is_admin should be settable and readable."""
    async with pool.acquire() as conn:
        await conn.execute(
            "SELECT set_config('app.is_admin', 'true', false)"
        )
        val = await conn.fetchval(
            "SELECT current_setting('app.is_admin', true)"
        )
        assert val == "true"
        await conn.execute(
            "SELECT set_config('app.is_admin', '', false)"
        )


async def test_user_id_session_var(pool):
    """app.current_user_id should be settable and readable."""
    async with pool.acquire() as conn:
        await conn.execute(
            "SELECT set_config('app.current_user_id', $1, false)",
            FAKE_USER,
        )
        val = await conn.fetchval(
            "SELECT current_setting('app.current_user_id', true)"
        )
        assert val == FAKE_USER
        await conn.execute(
            "SELECT set_config('app.current_user_id', '', false)"
        )


# ── RLS enforcement tests (require matcha_app role) ──────────────────
# These use SET ROLE matcha_app to drop superuser privileges within the
# session, then RESET ROLE to restore. This tests real RLS enforcement
# without needing a separate connection.

async def test_rls_blocks_without_tenant_context(pool, has_app_role):
    """With no tenant set and SET ROLE to non-superuser, RLS should block rows."""
    async with pool.acquire() as conn:
        # Check if any RLS-protected table has data
        count = await conn.fetchval("SELECT count(*) FROM ir_incidents")
        if count == 0:
            pytest.skip("No ir_incidents data to test against")

        await conn.execute(
            "SELECT set_config('app.current_tenant_id', '', false)"
        )
        await conn.execute(
            "SELECT set_config('app.is_admin', '', false)"
        )
        await conn.execute("SET ROLE matcha_app")
        try:
            rows = await conn.fetch("SELECT id FROM ir_incidents LIMIT 10")
            assert len(rows) == 0, (
                "RLS should block all rows when no tenant context is set"
            )
        finally:
            await conn.execute("RESET ROLE")


async def test_rls_allows_matching_tenant(pool, has_app_role):
    """With the correct tenant_id set, RLS should return matching rows."""
    async with pool.acquire() as conn:
        # Find a real company_id that has incidents
        row = await conn.fetchrow(
            "SELECT company_id FROM ir_incidents LIMIT 1"
        )
        if not row:
            pytest.skip("No ir_incidents data to test against")

        real_company_id = str(row["company_id"])
        await conn.execute(
            "SELECT set_config('app.current_tenant_id', $1, false)",
            real_company_id,
        )
        await conn.execute(
            "SELECT set_config('app.is_admin', '', false)"
        )
        await conn.execute("SET ROLE matcha_app")
        try:
            rows = await conn.fetch("SELECT company_id FROM ir_incidents LIMIT 10")
            assert len(rows) > 0
            assert all(str(r["company_id"]) == real_company_id for r in rows)
        finally:
            await conn.execute("RESET ROLE")
            await conn.execute(
                "SELECT set_config('app.current_tenant_id', '', false)"
            )


async def test_rls_denies_wrong_tenant(pool, has_app_role):
    """With a non-matching tenant_id, RLS should return zero rows."""
    async with pool.acquire() as conn:
        count = await conn.fetchval("SELECT count(*) FROM ir_incidents")
        if count == 0:
            pytest.skip("No ir_incidents data to test against")

        await conn.execute(
            "SELECT set_config('app.current_tenant_id', $1, false)",
            str(uuid.uuid4()),  # random UUID that won't match anything
        )
        await conn.execute(
            "SELECT set_config('app.is_admin', '', false)"
        )
        await conn.execute("SET ROLE matcha_app")
        try:
            rows = await conn.fetch("SELECT id FROM ir_incidents LIMIT 10")
            assert len(rows) == 0
        finally:
            await conn.execute("RESET ROLE")
            await conn.execute(
                "SELECT set_config('app.current_tenant_id', '', false)"
            )


async def test_admin_bypass_allows_all(pool, has_app_role):
    """With app.is_admin='true', all rows should be visible."""
    async with pool.acquire() as conn:
        count = await conn.fetchval("SELECT count(*) FROM ir_incidents")
        if count == 0:
            pytest.skip("No ir_incidents data to test against")

        await conn.execute(
            "SELECT set_config('app.current_tenant_id', '', false)"
        )
        await conn.execute(
            "SELECT set_config('app.is_admin', 'true', false)"
        )
        await conn.execute("SET ROLE matcha_app")
        try:
            rows = await conn.fetch("SELECT id FROM ir_incidents LIMIT 10")
            assert len(rows) > 0, "Admin bypass should see all rows"
        finally:
            await conn.execute("RESET ROLE")
            await conn.execute(
                "SELECT set_config('app.is_admin', '', false)"
            )


async def test_employee_self_lookup(pool, has_app_role):
    """Employees should see their own record via user_id self-lookup policy."""
    async with pool.acquire() as conn:
        # Find an employee with a user_id
        emp = await conn.fetchrow(
            "SELECT user_id, org_id FROM employees WHERE user_id IS NOT NULL LIMIT 1"
        )
        if not emp:
            pytest.skip("No employees with user_id to test against")

        await conn.execute(
            "SELECT set_config('app.current_tenant_id', '', false)"
        )
        await conn.execute(
            "SELECT set_config('app.is_admin', '', false)"
        )
        await conn.execute(
            "SELECT set_config('app.current_user_id', $1, false)",
            str(emp["user_id"]),
        )
        await conn.execute("SET ROLE matcha_app")
        try:
            rows = await conn.fetch(
                "SELECT user_id FROM employees WHERE user_id = $1",
                emp["user_id"],
            )
            assert len(rows) == 1, (
                "Self-lookup policy should let user see their own employee record"
            )
        finally:
            await conn.execute("RESET ROLE")
            await conn.execute(
                "SELECT set_config('app.current_user_id', '', false)"
            )
