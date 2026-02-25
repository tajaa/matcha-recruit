"""add matcha elements materialized flag

Revision ID: f9a0b1c2d3e4
Revises: e7f8a9b0c1d2
Create Date: 2026-02-25
"""

from alembic import op


revision = "f9a0b1c2d3e4"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        ALTER TABLE mw_elements
        ADD COLUMN IF NOT EXISTS is_materialized BOOLEAN NOT NULL DEFAULT false
        """
    )
    op.execute(
        """
        UPDATE mw_elements
        SET is_materialized = (
            linked_offer_letter_id IS NOT NULL
            OR status = 'finalized'
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_mw_elements_company_materialized
        ON mw_elements(company_id, is_materialized)
        """
    )


def downgrade():
    op.execute(
        """
        DROP INDEX IF EXISTS idx_mw_elements_company_materialized
        """
    )
    op.execute(
        """
        ALTER TABLE mw_elements
        DROP COLUMN IF EXISTS is_materialized
        """
    )
