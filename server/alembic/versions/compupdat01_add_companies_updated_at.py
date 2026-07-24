"""add companies.updated_at + trigger, so tenant sync LWW isn't dev-always-wins

Revision ID: compupdat01
Revises: testacct01
Create Date: 2026-07-24

`companies` was the one table in the tenant-sync merge engine
(scripts/sync_tenants.py) with no `updated_at` column. decide_row() falls
back to "dev wins, WARN" whenever a table has no usable updated_at, which
for `companies` meant every prod-side admin edit to a test tenant
(enabled_features, status, industry, is_test itself) was silently reverted
on the next `sync-test-tenants.sh --auto` (wired into every deploy).

No other table in this codebase uses a DB trigger for updated_at (every
other table's callers set it explicitly in their UPDATE statements) — this
is a deliberate, scoped exception. Retrofitting every one of the ~10 admin
routes that write `companies` to remember `updated_at = NOW()` has the same
failure mode this migration exists to close: one missed callsite silently
reintroduces the bug. A trigger can't be missed.
"""
from alembic import op

revision = "compupdat01"
down_revision = "testacct01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ"
    )
    op.execute(
        # created_at is nullable (database.py:868) and is `timestamp without
        # time zone`, while updated_at is timestamptz — the implicit cast
        # would resolve the naive value against the session TimeZone. These
        # were written by NOW() on UTC hosts, so pin the interpretation to
        # UTC rather than inheriting whatever TZ the migration runs under.
        "UPDATE companies "
        "SET updated_at = COALESCE(created_at AT TIME ZONE 'UTC', NOW()) "
        "WHERE updated_at IS NULL"
    )
    op.execute("ALTER TABLE companies ALTER COLUMN updated_at SET NOT NULL")
    op.execute("ALTER TABLE companies ALTER COLUMN updated_at SET DEFAULT NOW()")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_companies_updated_at() RETURNS trigger AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    # Two separate op.execute calls: alembic's asyncpg driver prepares each
    # statement, and a prepared statement cannot contain multiple commands.
    op.execute("DROP TRIGGER IF EXISTS trg_companies_updated_at ON companies")
    op.execute(
        """
        CREATE TRIGGER trg_companies_updated_at
            BEFORE UPDATE ON companies
            FOR EACH ROW
            EXECUTE FUNCTION set_companies_updated_at()
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_companies_updated_at ON companies")
    op.execute("DROP FUNCTION IF EXISTS set_companies_updated_at()")
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS updated_at")
