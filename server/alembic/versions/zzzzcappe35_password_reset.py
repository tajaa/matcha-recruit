"""Cappe password reset — single-use, time-boxed reset tokens.

Adds the reset columns to `cappe_accounts`. Only a SHA-256 of the emailed token
is stored, so a database read does not yield a working reset link. The partial
unique index backs the lookup on the reset endpoint.

Additive + idempotent.

Revision ID: zzzzcappe35
Revises: assistdom01
"""
from alembic import op

revision = "zzzzcappe35"
down_revision = "assistdom01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE cappe_accounts
            ADD COLUMN IF NOT EXISTS password_reset_token_hash VARCHAR(64),
            ADD COLUMN IF NOT EXISTS password_reset_sent_at    TIMESTAMPTZ
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_cappe_accounts_password_reset_token_hash "
        "ON cappe_accounts (password_reset_token_hash) WHERE password_reset_token_hash IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_cappe_accounts_password_reset_token_hash")
    op.execute(
        """
        ALTER TABLE cappe_accounts
            DROP COLUMN IF EXISTS password_reset_token_hash,
            DROP COLUMN IF EXISTS password_reset_sent_at
        """
    )
