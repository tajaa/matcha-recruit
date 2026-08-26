"""repair auto-send invitation setting schema drift

Revision ID: invitefix01
Revises: compupdat01
Create Date: 2026-08-25
"""

from alembic import op


revision = "invitefix01"
down_revision = "compupdat01"
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
