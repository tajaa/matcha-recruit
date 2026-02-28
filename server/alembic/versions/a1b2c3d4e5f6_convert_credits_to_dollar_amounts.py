"""Convert credits from integer to dollar-based NUMERIC(10,6)

Revision ID: a1b2c3d4e5f6
Revises: z7a8b9c0d1e
Create Date: 2026-02-27

"""

from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "z7a8b9c0d1e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- mw_credit_balances: drop CHECK constraints, alter type, re-add checks ---
    op.execute("ALTER TABLE mw_credit_balances DROP CONSTRAINT IF EXISTS mw_credit_balances_credits_remaining_check")
    op.execute("ALTER TABLE mw_credit_balances DROP CONSTRAINT IF EXISTS mw_credit_balances_total_credits_purchased_check")
    op.execute("ALTER TABLE mw_credit_balances DROP CONSTRAINT IF EXISTS mw_credit_balances_total_credits_granted_check")

    op.execute("ALTER TABLE mw_credit_balances ALTER COLUMN credits_remaining TYPE NUMERIC(10,6) USING credits_remaining::NUMERIC(10,6)")
    op.execute("ALTER TABLE mw_credit_balances ALTER COLUMN total_credits_purchased TYPE NUMERIC(10,6) USING total_credits_purchased::NUMERIC(10,6)")
    op.execute("ALTER TABLE mw_credit_balances ALTER COLUMN total_credits_granted TYPE NUMERIC(10,6) USING total_credits_granted::NUMERIC(10,6)")

    op.execute("ALTER TABLE mw_credit_balances ADD CONSTRAINT mw_credit_balances_credits_remaining_check CHECK (credits_remaining >= 0)")
    op.execute("ALTER TABLE mw_credit_balances ADD CONSTRAINT mw_credit_balances_total_credits_purchased_check CHECK (total_credits_purchased >= 0)")
    op.execute("ALTER TABLE mw_credit_balances ADD CONSTRAINT mw_credit_balances_total_credits_granted_check CHECK (total_credits_granted >= 0)")

    # --- mw_credit_transactions ---
    op.execute("ALTER TABLE mw_credit_transactions DROP CONSTRAINT IF EXISTS mw_credit_transactions_credits_after_check")

    op.execute("ALTER TABLE mw_credit_transactions ALTER COLUMN credits_delta TYPE NUMERIC(10,6) USING credits_delta::NUMERIC(10,6)")
    op.execute("ALTER TABLE mw_credit_transactions ALTER COLUMN credits_after TYPE NUMERIC(10,6) USING credits_after::NUMERIC(10,6)")

    op.execute("ALTER TABLE mw_credit_transactions ADD CONSTRAINT mw_credit_transactions_credits_after_check CHECK (credits_after >= 0)")

    # --- mw_stripe_sessions ---
    op.execute("ALTER TABLE mw_stripe_sessions DROP CONSTRAINT IF EXISTS mw_stripe_sessions_credits_to_add_check")

    op.execute("ALTER TABLE mw_stripe_sessions ALTER COLUMN credits_to_add TYPE NUMERIC(10,6) USING credits_to_add::NUMERIC(10,6)")

    op.execute("ALTER TABLE mw_stripe_sessions ADD CONSTRAINT mw_stripe_sessions_credits_to_add_check CHECK (credits_to_add > 0)")

    # --- mw_subscriptions ---
    op.execute("ALTER TABLE mw_subscriptions ALTER COLUMN credits_per_cycle TYPE NUMERIC(10,6) USING credits_per_cycle::NUMERIC(10,6)")

    # --- mw_token_usage_events: add cost_dollars column ---
    op.execute("ALTER TABLE mw_token_usage_events ADD COLUMN IF NOT EXISTS cost_dollars NUMERIC(10,6)")

    # --- Reset all existing balances to 0 (old integer credits are meaningless now) ---
    op.execute("UPDATE mw_credit_balances SET credits_remaining = 0, total_credits_purchased = 0, total_credits_granted = 0")


def downgrade() -> None:
    # Reverse column types back to INTEGER
    op.execute("ALTER TABLE mw_credit_balances DROP CONSTRAINT IF EXISTS mw_credit_balances_credits_remaining_check")
    op.execute("ALTER TABLE mw_credit_balances DROP CONSTRAINT IF EXISTS mw_credit_balances_total_credits_purchased_check")
    op.execute("ALTER TABLE mw_credit_balances DROP CONSTRAINT IF EXISTS mw_credit_balances_total_credits_granted_check")

    op.execute("ALTER TABLE mw_credit_balances ALTER COLUMN credits_remaining TYPE INTEGER USING credits_remaining::INTEGER")
    op.execute("ALTER TABLE mw_credit_balances ALTER COLUMN total_credits_purchased TYPE INTEGER USING total_credits_purchased::INTEGER")
    op.execute("ALTER TABLE mw_credit_balances ALTER COLUMN total_credits_granted TYPE INTEGER USING total_credits_granted::INTEGER")

    op.execute("ALTER TABLE mw_credit_balances ADD CONSTRAINT mw_credit_balances_credits_remaining_check CHECK (credits_remaining >= 0)")
    op.execute("ALTER TABLE mw_credit_balances ADD CONSTRAINT mw_credit_balances_total_credits_purchased_check CHECK (total_credits_purchased >= 0)")
    op.execute("ALTER TABLE mw_credit_balances ADD CONSTRAINT mw_credit_balances_total_credits_granted_check CHECK (total_credits_granted >= 0)")

    op.execute("ALTER TABLE mw_credit_transactions DROP CONSTRAINT IF EXISTS mw_credit_transactions_credits_after_check")
    op.execute("ALTER TABLE mw_credit_transactions ALTER COLUMN credits_delta TYPE INTEGER USING credits_delta::INTEGER")
    op.execute("ALTER TABLE mw_credit_transactions ALTER COLUMN credits_after TYPE INTEGER USING credits_after::INTEGER")
    op.execute("ALTER TABLE mw_credit_transactions ADD CONSTRAINT mw_credit_transactions_credits_after_check CHECK (credits_after >= 0)")

    op.execute("ALTER TABLE mw_stripe_sessions DROP CONSTRAINT IF EXISTS mw_stripe_sessions_credits_to_add_check")
    op.execute("ALTER TABLE mw_stripe_sessions ALTER COLUMN credits_to_add TYPE INTEGER USING credits_to_add::INTEGER")
    op.execute("ALTER TABLE mw_stripe_sessions ADD CONSTRAINT mw_stripe_sessions_credits_to_add_check CHECK (credits_to_add > 0)")

    op.execute("ALTER TABLE mw_subscriptions ALTER COLUMN credits_per_cycle TYPE INTEGER USING credits_per_cycle::INTEGER")

    op.execute("ALTER TABLE mw_token_usage_events DROP COLUMN IF EXISTS cost_dollars")
