"""Off-platform client-intake links: broker_external_intake_tokens

Revision ID: extintake01
Revises: rescare01
Create Date: 2026-06-20

Shareable token so an off-platform prospect self-completes the EPL questionnaire
(+ optional WC counts) without onboarding (WTW p.11 "digitize the value chain").
Public, token-gated, single-use-ish (locked once completed).
"""

from alembic import op


revision = "extintake01"
down_revision = "rescare01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS broker_external_intake_tokens (
            id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            token              VARCHAR(64) NOT NULL UNIQUE,
            external_client_id UUID NOT NULL REFERENCES broker_external_clients(id) ON DELETE CASCADE,
            broker_id          UUID NOT NULL REFERENCES brokers(id) ON DELETE CASCADE,
            created_by         UUID REFERENCES users(id) ON DELETE SET NULL,
            status             VARCHAR(12) NOT NULL DEFAULT 'active'
                                 CHECK (status IN ('active','completed','expired')),
            expires_at         TIMESTAMP NOT NULL,
            completed_at       TIMESTAMP,
            created_at         TIMESTAMP NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_ext_intake_client ON broker_external_intake_tokens(external_client_id)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS broker_external_intake_tokens")
