"""Add `category` column to channels for browse/filter UX.

Revision ID: zzzz8g9h0i1j2
Revises: zzzz7f8g9h0i1
Create Date: 2026-05-14
"""
from alembic import op


revision = "zzzz8g9h0i1j2"
down_revision = "zzzz7f8g9h0i1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE channels
        ADD COLUMN IF NOT EXISTS category VARCHAR(50)
    """)
    # Index supports the discover/browse endpoint's "filter by category" path.
    # NULL category rows are fine and remain queryable by the broader list.
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_channels_category
            ON channels(company_id, category)
            WHERE category IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_channels_category")
    op.execute("ALTER TABLE channels DROP COLUMN IF EXISTS category")
