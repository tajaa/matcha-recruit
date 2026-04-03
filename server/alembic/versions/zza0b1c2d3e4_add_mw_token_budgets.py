"""Add mw_token_budgets table for token-based billing.

Revision ID: zza0b1c2d3e4
Revises: zz9i0j1k2l3m
Create Date: 2026-04-02
"""
from alembic import op

revision = "zza0b1c2d3e4"
down_revision = "zz9i0j1k2l3m"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS mw_token_budgets (
            company_id UUID PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
            free_tokens_used BIGINT NOT NULL DEFAULT 0,
            free_token_limit BIGINT NOT NULL DEFAULT 1000000,
            subscription_tokens_used BIGINT NOT NULL DEFAULT 0,
            subscription_token_limit BIGINT NOT NULL DEFAULT 0,
            subscription_period_start TIMESTAMPTZ,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    # Backfill for existing companies
    op.execute("""
        INSERT INTO mw_token_budgets (company_id, free_tokens_used, free_token_limit)
        SELECT
            c.id,
            COALESCE(u.total_used, 0),
            1000000
        FROM companies c
        LEFT JOIN (
            SELECT company_id, SUM(COALESCE(total_tokens, 0))::BIGINT AS total_used
            FROM mw_token_usage_events
            GROUP BY company_id
        ) u ON u.company_id = c.id
        ON CONFLICT (company_id) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS mw_token_budgets")
