"""Add attachments JSONB column to inbox_messages.

Revision ID: zz7g8h9i0j1k
Revises: zz6f7g8h9i0j
Create Date: 2026-04-02
"""
from alembic import op

revision = "zz7g8h9i0j1k"
down_revision = "zz6f7g8h9i0j"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE inbox_messages
        ADD COLUMN IF NOT EXISTS attachments JSONB DEFAULT '[]'
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE inbox_messages
        DROP COLUMN IF EXISTS attachments
    """)
