"""add payer column to broker_lite_referral_tokens

Revision ID: zzzq3r4s5t6u7
Revises: zzzp2q3r4s5t6
Create Date: 2026-04-30
"""

from alembic import op

revision = "zzzq3r4s5t6u7"
down_revision = "zzzp2q3r4s5t6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE broker_lite_referral_tokens
            ADD COLUMN IF NOT EXISTS payer VARCHAR(16) NOT NULL DEFAULT 'business'
    """)
    op.execute("""
        ALTER TABLE broker_lite_referral_tokens
            DROP CONSTRAINT IF EXISTS broker_lite_referral_tokens_payer_check
    """)
    op.execute("""
        ALTER TABLE broker_lite_referral_tokens
            ADD CONSTRAINT broker_lite_referral_tokens_payer_check
            CHECK (payer IN ('broker', 'business'))
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE broker_lite_referral_tokens
            DROP CONSTRAINT IF EXISTS broker_lite_referral_tokens_payer_check
    """)
    op.execute("""
        ALTER TABLE broker_lite_referral_tokens
            DROP COLUMN IF EXISTS payer
    """)
