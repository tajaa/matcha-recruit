"""add broker_lite_referral_tokens

Revision ID: zzzp2q3r4s5t6
Revises: zzzo1p2q3r4s5
Create Date: 2026-04-30
"""

from alembic import op

revision = "zzzp2q3r4s5t6"
down_revision = "zzzo1p2q3r4s5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS broker_lite_referral_tokens (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            broker_id    UUID NOT NULL,
            token        VARCHAR(128) NOT NULL UNIQUE,
            label        VARCHAR(255),
            created_by   UUID NOT NULL,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at   TIMESTAMPTZ,
            is_active    BOOL NOT NULL DEFAULT true,
            use_count    INT NOT NULL DEFAULT 0,
            last_used_at TIMESTAMPTZ
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_broker_lite_referral_tokens_broker
            ON broker_lite_referral_tokens (broker_id, created_at DESC)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_broker_lite_referral_tokens_token
            ON broker_lite_referral_tokens (token) WHERE is_active = true
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS broker_lite_referral_tokens")
