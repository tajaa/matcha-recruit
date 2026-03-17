"""add node_mode to mw_threads

Revision ID: zk9l0m1n2o3p
Revises: zj8k9l0m1n2o
Create Date: 2026-03-17
"""

from alembic import op


revision = "zk9l0m1n2o3p"
down_revision = "zj8k9l0m1n2o"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        ALTER TABLE mw_threads
        ADD COLUMN IF NOT EXISTS node_mode BOOLEAN NOT NULL DEFAULT false
        """
    )


def downgrade():
    op.execute(
        """
        ALTER TABLE mw_threads
        DROP COLUMN IF EXISTS node_mode
        """
    )
