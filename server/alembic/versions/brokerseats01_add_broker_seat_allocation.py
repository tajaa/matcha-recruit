"""broker seat allocation: pool + company-pinned client invites + per-company limit

MVP for the brokerage self-service portal:
- brokers.allocated_seats        : the seat pool the platform admin grants a brokerage
- broker_lite_referral_tokens.*   : turn a generic referral link into a company-pinned,
                                     single-use "client seat invite" (company name + seats + tier)
- companies.seat_limit            : seats granted to a company at redemption (display/track only)

Revision ID: brokerseats01
Revises: mwjfc0001
Create Date: 2026-06-09
"""
from alembic import op

revision = "brokerseats01"
down_revision = "mwjfc0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Seat pool granted to a brokerage.
    op.execute(
        "ALTER TABLE brokers ADD COLUMN IF NOT EXISTS allocated_seats INTEGER NOT NULL DEFAULT 0"
    )

    # 2. Company-pinned client seat invites ride on the existing broker referral token table.
    #    intended_company_name IS NOT NULL  => a single-use client seat invite (vs generic campaign link).
    op.execute(
        """
        ALTER TABLE broker_lite_referral_tokens
            ADD COLUMN IF NOT EXISTS intended_company_name TEXT,
            ADD COLUMN IF NOT EXISTS seat_count INTEGER,
            ADD COLUMN IF NOT EXISTS tier VARCHAR(16),
            ADD COLUMN IF NOT EXISTS redeemed_company_id UUID REFERENCES companies(id) ON DELETE SET NULL
        """
    )
    op.execute(
        """
        ALTER TABLE broker_lite_referral_tokens
            DROP CONSTRAINT IF EXISTS broker_lite_referral_tokens_tier_check
        """
    )
    op.execute(
        """
        ALTER TABLE broker_lite_referral_tokens
            ADD CONSTRAINT broker_lite_referral_tokens_tier_check
            CHECK (tier IS NULL OR tier IN ('matcha_lite', 'matcha_x'))
        """
    )

    # 3. Seats granted to a company (recorded at redemption; null = no cap). Track/display only this MVP.
    op.execute(
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS seat_limit INTEGER"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS seat_limit")
    op.execute(
        "ALTER TABLE broker_lite_referral_tokens DROP CONSTRAINT IF EXISTS broker_lite_referral_tokens_tier_check"
    )
    op.execute(
        """
        ALTER TABLE broker_lite_referral_tokens
            DROP COLUMN IF EXISTS redeemed_company_id,
            DROP COLUMN IF EXISTS tier,
            DROP COLUMN IF EXISTS seat_count,
            DROP COLUMN IF EXISTS intended_company_name
        """
    )
    op.execute("ALTER TABLE brokers DROP COLUMN IF EXISTS allocated_seats")
