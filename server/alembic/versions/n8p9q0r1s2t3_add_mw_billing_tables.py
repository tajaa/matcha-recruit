"""add mw billing tables

Revision ID: n8p9q0r1s2t3
Revises: k2l3m4n5o6p7
Create Date: 2026-02-27
"""

from alembic import op


revision = "n8p9q0r1s2t3"
down_revision = "k2l3m4n5o6p7"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = 'mw_credit_balances'
            ) THEN
                CREATE TABLE mw_credit_balances (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    company_id UUID NOT NULL UNIQUE REFERENCES companies(id) ON DELETE CASCADE,
                    credits_remaining INTEGER NOT NULL DEFAULT 0 CHECK (credits_remaining >= 0),
                    total_credits_purchased INTEGER NOT NULL DEFAULT 0 CHECK (total_credits_purchased >= 0),
                    total_credits_granted INTEGER NOT NULL DEFAULT 0 CHECK (total_credits_granted >= 0),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            END IF;
        END $$;
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = 'mw_credit_transactions'
            ) THEN
                CREATE TABLE mw_credit_transactions (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                    transaction_type VARCHAR(20) NOT NULL
                        CHECK (transaction_type IN ('purchase', 'grant', 'deduction', 'refund', 'adjustment')),
                    credits_delta INTEGER NOT NULL,
                    credits_after INTEGER NOT NULL CHECK (credits_after >= 0),
                    description TEXT,
                    reference_id UUID,
                    created_by UUID REFERENCES users(id) ON DELETE SET NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            END IF;
        END $$;
        """
    )

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = 'mw_stripe_sessions'
            ) THEN
                CREATE TABLE mw_stripe_sessions (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                    stripe_session_id VARCHAR(255) NOT NULL UNIQUE,
                    credit_pack_id VARCHAR(50) NOT NULL,
                    credits_to_add INTEGER NOT NULL CHECK (credits_to_add > 0),
                    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
                    status VARCHAR(20) NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'completed', 'expired')),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    fulfilled_at TIMESTAMPTZ
                );
            END IF;
        END $$;
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_mw_credit_transactions_company_created
        ON mw_credit_transactions(company_id, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_mw_credit_transactions_company_type
        ON mw_credit_transactions(company_id, transaction_type)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_mw_stripe_sessions_company_status
        ON mw_stripe_sessions(company_id, status)
        """
    )

    op.execute(
        """
        INSERT INTO mw_credit_balances (
            company_id,
            credits_remaining,
            total_credits_purchased,
            total_credits_granted
        )
        SELECT
            c.id,
            0,
            0,
            0
        FROM companies c
        ON CONFLICT (company_id) DO NOTHING
        """
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_mw_stripe_sessions_company_status")
    op.execute("DROP INDEX IF EXISTS idx_mw_credit_transactions_company_type")
    op.execute("DROP INDEX IF EXISTS idx_mw_credit_transactions_company_created")
    op.execute("DROP TABLE IF EXISTS mw_stripe_sessions")
    op.execute("DROP TABLE IF EXISTS mw_credit_transactions")
    op.execute("DROP TABLE IF EXISTS mw_credit_balances")
