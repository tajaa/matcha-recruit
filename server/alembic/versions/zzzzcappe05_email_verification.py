"""Cappe email verification — gate new accounts behind a confirmed email.

Adds the verification columns to `cappe_accounts`. New signups land with
`email_verified_at = NULL` and a `verification_token`; they can't log in until
they click the emailed link. EXISTING accounts are backfilled as verified
(NOW()) so no current user — including seed/test accounts — is locked out.

Additive + idempotent. Apply to dev AND prod (legacy :5433 + RDS pre-cutover).

Revision ID: zzzzcappe05
Revises: zzzzcappe04
"""
from alembic import op

revision = "zzzzcappe05"
down_revision = "zzzzcappe04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE cappe_accounts
            ADD COLUMN IF NOT EXISTS email_verified_at  TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS verification_token  UUID,
            ADD COLUMN IF NOT EXISTS verification_sent_at TIMESTAMPTZ
        """
    )
    # Backfill: every account that already exists predates verification, so
    # treat it as verified. Without this, current users could no longer log in.
    op.execute(
        "UPDATE cappe_accounts SET email_verified_at = NOW() "
        "WHERE email_verified_at IS NULL"
    )
    # Token lookup on the verify endpoint.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_accounts_verification_token "
        "ON cappe_accounts (verification_token) WHERE verification_token IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_cappe_accounts_verification_token")
    op.execute(
        """
        ALTER TABLE cappe_accounts
            DROP COLUMN IF EXISTS email_verified_at,
            DROP COLUMN IF EXISTS verification_token,
            DROP COLUMN IF EXISTS verification_sent_at
        """
    )
