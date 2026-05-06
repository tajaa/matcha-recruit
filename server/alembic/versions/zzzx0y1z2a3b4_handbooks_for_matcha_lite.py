"""Enable handbooks feature for existing matcha-lite tenants.

The signup path was just updated to enable handbooks for new matcha-lite
companies. This migration backfills the same flag on already-provisioned
matcha-lite tenants so they pick up the handbook UI without a re-signup.

Revision ID: zzzx0y1z2a3b4
Revises: zzzw9x0y1z2a3
Create Date: 2026-05-06
"""
from alembic import op


revision = "zzzx0y1z2a3b4"
down_revision = "zzzw9x0y1z2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE companies
        SET enabled_features = jsonb_set(
            COALESCE(enabled_features, '{}'::jsonb),
            '{handbooks}',
            'true'::jsonb,
            true
        )
        WHERE signup_source IN ('matcha_lite', 'ir_only_self_serve')
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE companies
        SET enabled_features = jsonb_set(
            COALESCE(enabled_features, '{}'::jsonb),
            '{handbooks}',
            'false'::jsonb,
            true
        )
        WHERE signup_source IN ('matcha_lite', 'ir_only_self_serve')
    """)
