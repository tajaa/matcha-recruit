"""tellus_app_08 — internal admin management: audit trail, account status CHECK,
password reset tokens.

Revision ID: tellus_app_08
Revises: tellus_app_07
"""
from alembic import op

revision = "tellus_app_08"
down_revision = "tellus_app_07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Audit trail: every admin mutation writes one row, same transaction.
    op.execute(
        """CREATE TABLE IF NOT EXISTS tellus_admin_audit (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            actor_account_id UUID REFERENCES tellus_accounts(id) ON DELETE SET NULL,
            actor_email TEXT NOT NULL,
            action TEXT NOT NULL,
            target_type TEXT NOT NULL,
            target_id TEXT,
            detail JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )"""
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_tellus_admin_audit_created ON tellus_admin_audit (created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_tellus_admin_audit_target ON tellus_admin_audit (target_type, target_id)")

    # Account status vocabulary. status has DEFAULT 'active' and no writer since
    # tellus_app_01, so the UPDATE is a safety net, not a backfill.
    op.execute("UPDATE tellus_accounts SET status = 'active' WHERE status NOT IN ('active', 'suspended')")
    op.execute(
        """DO $$ BEGIN
            ALTER TABLE tellus_accounts ADD CONSTRAINT ck_tellus_accounts_status
                CHECK (status IN ('active', 'suspended'));
        EXCEPTION WHEN duplicate_object THEN NULL; END $$"""
    )

    # Password reset tokens — Tell-Us had no reset flow at all.
    op.execute(
        """CREATE TABLE IF NOT EXISTS tellus_password_reset_tokens (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            account_id UUID NOT NULL REFERENCES tellus_accounts(id) ON DELETE CASCADE,
            token TEXT NOT NULL UNIQUE,
            expires_at TIMESTAMPTZ NOT NULL,
            used_at TIMESTAMPTZ,
            created_by_email TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )"""
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_tellus_pw_reset_account ON tellus_password_reset_tokens (account_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tellus_password_reset_tokens")
    op.execute("ALTER TABLE tellus_accounts DROP CONSTRAINT IF EXISTS ck_tellus_accounts_status")
    op.execute("DROP TABLE IF EXISTS tellus_admin_audit")
