"""Enable training feature for existing matcha_lite tenants.

The signup path is being updated to enable training for new matcha_lite
companies. This migration backfills the same flag on already-provisioned
matcha_lite tenants so they pick up the Training UI without a re-signup.

Mirror of zzzx0y1z2a3b4_handbooks_for_matcha_lite.py.

Revision ID: zzzz3b4c5d6e7
Revises: zzzz2a3b4c5d6
Create Date: 2026-05-06
"""
from alembic import op


revision = "zzzz3b4c5d6e7"
down_revision = "zzzz2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE companies
        SET enabled_features = jsonb_set(
            COALESCE(enabled_features, '{}'::jsonb),
            '{training}',
            'true'::jsonb,
            true
        )
        WHERE signup_source = 'matcha_lite'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE companies
        SET enabled_features = jsonb_set(
            COALESCE(enabled_features, '{}'::jsonb),
            '{training}',
            'false'::jsonb,
            true
        )
        WHERE signup_source = 'matcha_lite'
        """
    )
