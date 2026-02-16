"""add broker client setups

Revision ID: v2w3x4y5z6a
Revises: u1v2w3x4y5z6
Create Date: 2026-02-16
"""

from alembic import op


revision = "v2w3x4y5z6a"
down_revision = "u1v2w3x4y5z6"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS broker_client_setups (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            broker_id UUID NOT NULL REFERENCES brokers(id) ON DELETE CASCADE,
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            status VARCHAR(20) NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft', 'invited', 'activated', 'expired', 'cancelled')),
            contact_name VARCHAR(255),
            contact_email VARCHAR(320),
            contact_phone VARCHAR(50),
            company_size_hint VARCHAR(50),
            headcount_hint INTEGER,
            preconfigured_features JSONB DEFAULT '{}'::jsonb,
            onboarding_template JSONB DEFAULT '{}'::jsonb,
            invite_token VARCHAR(128) UNIQUE,
            invite_expires_at TIMESTAMPTZ,
            invited_at TIMESTAMPTZ,
            activated_at TIMESTAMPTZ,
            expired_at TIMESTAMPTZ,
            cancelled_at TIMESTAMPTZ,
            created_by UUID REFERENCES users(id),
            updated_by UUID REFERENCES users(id),
            metadata JSONB DEFAULT '{}'::jsonb,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            UNIQUE (broker_id, company_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_broker_client_setups_broker_status
        ON broker_client_setups(broker_id, status)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_broker_client_setups_invite_token
        ON broker_client_setups(invite_token)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_broker_client_setups_invite_expires_at
        ON broker_client_setups(invite_expires_at)
        """
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_broker_client_setups_invite_expires_at")
    op.execute("DROP INDEX IF EXISTS idx_broker_client_setups_invite_token")
    op.execute("DROP INDEX IF EXISTS idx_broker_client_setups_broker_status")
    op.execute("DROP TABLE IF EXISTS broker_client_setups")
