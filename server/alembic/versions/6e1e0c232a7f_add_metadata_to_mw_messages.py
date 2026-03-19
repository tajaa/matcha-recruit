"""add metadata jsonb to mw_messages

Revision ID: 6e1e0c232a7f
Revises: zs7t8u9v0w1x
Create Date: 2026-03-19
"""

from alembic import op


revision = "6e1e0c232a7f"
down_revision = "zs7t8u9v0w1x"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        ALTER TABLE mw_messages ADD COLUMN IF NOT EXISTS metadata JSONB
        """
    )


def downgrade():
    op.execute(
        """
        ALTER TABLE mw_messages DROP COLUMN IF EXISTS metadata
        """
    )
