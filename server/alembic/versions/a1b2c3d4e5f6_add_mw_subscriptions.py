"""Add mw_subscriptions table for auto-renewal billing

Revision ID: a1b2c3d4e5f6
Revises: z7a8b9c0d1e_add_onboarding_reminder_infrastructure
Create Date: 2026-02-26 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = 'a1b2c3d4e5f6'
down_revision = 'z7a8b9c0d1e_add_onboarding_reminder_infrastructure'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS mw_subscriptions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            stripe_subscription_id VARCHAR(255) NOT NULL UNIQUE,
            stripe_customer_id VARCHAR(255) NOT NULL,
            pack_id VARCHAR(50) NOT NULL,
            credits_per_cycle INTEGER NOT NULL,
            amount_cents INTEGER NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'active',
            current_period_end TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            canceled_at TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_mw_subscriptions_company_id ON mw_subscriptions(company_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mw_subscriptions_status ON mw_subscriptions(status)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS mw_subscriptions")
