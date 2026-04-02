"""Add avatar_url column to users table.

Revision ID: zz3c4d5e6f7g
Revises: zz2b3c4d5e6f
Create Date: 2026-04-01
"""
from alembic import op

revision = "zz3c4d5e6f7g"
down_revision = "zz2b3c4d5e6f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url VARCHAR(500)
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE users DROP COLUMN IF EXISTS avatar_url
    """)
