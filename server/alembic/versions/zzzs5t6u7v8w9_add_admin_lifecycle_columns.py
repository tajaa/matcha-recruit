"""add users.is_suspended + companies.deleted_at for admin lifecycle controls

Phase B of the master-admin user-management work. Suspend is intentionally
separate from is_active so we don't conflate "deactivated" (e.g. failed
signup, never logged in) with "suspended by admin." Soft-delete on
companies lets admin remove a tenant without losing referential history.

Revision ID: zzzs5t6u7v8w9
Revises: zzzr4s5t6u7v8
Create Date: 2026-05-03
"""

from alembic import op


revision = "zzzs5t6u7v8w9"
down_revision = "zzzr4s5t6u7v8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_suspended BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("ALTER TABLE companies ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ")
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_companies_deleted_at
            ON companies(deleted_at) WHERE deleted_at IS NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_companies_deleted_at")
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS deleted_at")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS is_suspended")
