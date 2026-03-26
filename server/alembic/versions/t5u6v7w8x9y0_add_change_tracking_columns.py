"""Add change tracking columns to jurisdiction_requirements.

- previous_description: stores old description before overwrite
- change_status: new | changed | unchanged | needs_review

Revision ID: t5u6v7w8x9y0
Revises: s4t5u6v7w8x9
Create Date: 2026-03-25
"""

from alembic import op

revision = "t5u6v7w8x9y0"
down_revision = "s4t5u6v7w8x9"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE jurisdiction_requirements
            ADD COLUMN IF NOT EXISTS previous_description TEXT,
            ADD COLUMN IF NOT EXISTS change_status VARCHAR(20) DEFAULT 'new'
    """)

    # Backfill existing rows as 'active' (they predate the tracking system)
    op.execute("""
        UPDATE jurisdiction_requirements
        SET change_status = 'unchanged'
        WHERE change_status = 'new' OR change_status IS NULL
    """)


def downgrade():
    op.execute("""
        ALTER TABLE jurisdiction_requirements
            DROP COLUMN IF EXISTS previous_description,
            DROP COLUMN IF EXISTS change_status
    """)
