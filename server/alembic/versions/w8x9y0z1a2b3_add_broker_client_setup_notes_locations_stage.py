"""add notes, locations, onboarding_stage to broker_client_setups

Revision ID: w8x9y0z1a2b3
Revises: v7w8x9y0z1a2
Create Date: 2026-03-26
"""

from alembic import op


revision = "w8x9y0z1a2b3"
down_revision = "v7w8x9y0z1a2"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        ALTER TABLE broker_client_setups
            ADD COLUMN IF NOT EXISTS notes TEXT,
            ADD COLUMN IF NOT EXISTS locations JSONB NOT NULL DEFAULT '[]'::jsonb,
            ADD COLUMN IF NOT EXISTS onboarding_stage VARCHAR(50) DEFAULT 'submitted'
                CHECK (onboarding_stage IN ('submitted', 'under_review', 'configuring', 'live'))
        """
    )


def downgrade():
    op.execute(
        """
        ALTER TABLE broker_client_setups
            DROP COLUMN IF EXISTS notes,
            DROP COLUMN IF EXISTS locations,
            DROP COLUMN IF EXISTS onboarding_stage
        """
    )
