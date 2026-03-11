"""Add context_summary column to mw_threads for conversation compaction

Revision ID: z9a0b1c2d3e4
Revises: z8a9b0c1d2e3
Create Date: 2026-03-11
"""
from alembic import op

revision = "z9a0b1c2d3e4"
down_revision = "z8a9b0c1d2e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE mw_threads
        ADD COLUMN IF NOT EXISTS context_summary TEXT
    """)
    op.execute("""
        ALTER TABLE mw_threads
        ADD COLUMN IF NOT EXISTS context_summary_at_msg_count INTEGER
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE mw_threads
        DROP COLUMN IF EXISTS context_summary_at_msg_count
    """)
    op.execute("""
        ALTER TABLE mw_threads
        DROP COLUMN IF EXISTS context_summary
    """)
