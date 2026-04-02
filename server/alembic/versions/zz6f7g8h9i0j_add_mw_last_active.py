"""Add mw_last_active column to users table for Matcha Work presence.

Revision ID: zz6f7g8h9i0j
Revises: zz5e6f7g8h9i
Create Date: 2026-04-02
"""
from alembic import op

revision = "zz6f7g8h9i0j"
down_revision = "zz5e6f7g8h9i"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS mw_last_active TIMESTAMPTZ")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS mw_last_active")
