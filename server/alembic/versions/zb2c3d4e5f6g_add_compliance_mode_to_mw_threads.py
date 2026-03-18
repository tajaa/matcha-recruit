"""add compliance_mode to mw_threads

Revision ID: zb2c3d4e5f6g
Revises: 92583427c259, za1b2c3d4e5f6
Create Date: 2026-03-18
"""

from alembic import op


revision = "zb2c3d4e5f6g"
down_revision = ("92583427c259", "za1b2c3d4e5f6")
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        ALTER TABLE mw_threads
        ADD COLUMN IF NOT EXISTS compliance_mode BOOLEAN NOT NULL DEFAULT false
        """
    )


def downgrade():
    op.execute(
        """
        ALTER TABLE mw_threads
        DROP COLUMN IF EXISTS compliance_mode
        """
    )
