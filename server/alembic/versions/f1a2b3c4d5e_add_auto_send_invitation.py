"""add auto_send_invitation to onboarding_notification_settings

Revision ID: f1a2b3c4d5e
Revises: z7a8b9c0d1e
Create Date: 2026-03-05
"""

from alembic import op


revision = "f1a2b3c4d5e"
down_revision = "z7a8b9c0d1e"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        ALTER TABLE onboarding_notification_settings
        ADD COLUMN IF NOT EXISTS auto_send_invitation BOOLEAN NOT NULL DEFAULT false
        """
    )


def downgrade():
    op.execute(
        """
        ALTER TABLE onboarding_notification_settings
        DROP COLUMN IF EXISTS auto_send_invitation
        """
    )
