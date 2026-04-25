"""Newsletter compliance + ops hardening.

Adds the columns and tables required for double opt-in confirmation, bounce
tracking, soft-deleted newsletters, and an admin audit log.

Revision ID: zzzd0e1f2g3h4
Revises: zzzc9d0e1f2g3
Create Date: 2026-04-24
"""
from alembic import op

revision = "zzzd0e1f2g3h4"
down_revision = "zzzc9d0e1f2g3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # newsletter_subscribers: confirmation + bounce tracking.
    # Existing 'active' rows stay as-is — only new subscribes start as 'pending'.
    op.execute("""
        ALTER TABLE newsletter_subscribers
            ADD COLUMN IF NOT EXISTS confirmation_token VARCHAR(64),
            ADD COLUMN IF NOT EXISTS confirmed_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS bounced_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS bounce_reason TEXT
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_newsletter_subscribers_confirmation_token "
        "ON newsletter_subscribers(confirmation_token) WHERE confirmation_token IS NOT NULL"
    )

    # Soft-delete for newsletters so admin actions are auditable.
    op.execute("""
        ALTER TABLE newsletters
            ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
            ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS deleted_by UUID REFERENCES users(id) ON DELETE SET NULL
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_newsletters_active_status "
        "ON newsletters(status) WHERE is_deleted = FALSE"
    )

    # Admin actions audit trail (subscriber export, bulk delete, send, etc.).
    op.execute("""
        CREATE TABLE IF NOT EXISTS newsletter_admin_audit (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            actor_id UUID REFERENCES users(id) ON DELETE SET NULL,
            action VARCHAR(64) NOT NULL,
            target_type VARCHAR(32),
            target_id TEXT,
            metadata JSONB DEFAULT '{}'::jsonb,
            client_ip INET,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_newsletter_admin_audit_actor "
        "ON newsletter_admin_audit(actor_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_newsletter_admin_audit_action "
        "ON newsletter_admin_audit(action, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS newsletter_admin_audit")
    op.execute("DROP INDEX IF EXISTS idx_newsletters_active_status")
    op.execute("""
        ALTER TABLE newsletters
            DROP COLUMN IF EXISTS deleted_by,
            DROP COLUMN IF EXISTS deleted_at,
            DROP COLUMN IF EXISTS is_deleted
    """)
    op.execute("DROP INDEX IF EXISTS idx_newsletter_subscribers_confirmation_token")
    op.execute("""
        ALTER TABLE newsletter_subscribers
            DROP COLUMN IF EXISTS bounce_reason,
            DROP COLUMN IF EXISTS bounced_at,
            DROP COLUMN IF EXISTS confirmed_at,
            DROP COLUMN IF EXISTS confirmation_token
    """)
