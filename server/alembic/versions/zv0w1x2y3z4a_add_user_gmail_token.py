"""Add gmail_token JSONB column to users for per-user Gmail OAuth.

Revision ID: zv0w1x2y3z4a
Revises: zu9v0w1x2y3z
Create Date: 2026-03-30
"""
from alembic import op

revision = "zv0w1x2y3z4a"
down_revision = "zu9v0w1x2y3z"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS gmail_token JSONB DEFAULT NULL
    """)


def downgrade():
    op.execute("""
        ALTER TABLE users
        DROP COLUMN IF EXISTS gmail_token
    """)
