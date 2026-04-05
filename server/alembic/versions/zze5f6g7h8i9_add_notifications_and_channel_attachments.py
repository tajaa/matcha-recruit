"""Add mw_notifications table and channel_messages.attachments column.

Revision ID: zze5f6g7h8i9
Revises: zzd3e4f5g6h7
Create Date: 2026-04-04
"""
from alembic import op

revision = "zze5f6g7h8i9"
down_revision = "zzd3e4f5g6h7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Notifications table
    op.execute("""
        CREATE TABLE IF NOT EXISTS mw_notifications (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT,
            link TEXT,
            metadata JSONB DEFAULT '{}'::jsonb,
            is_read BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_mw_notifications_user
        ON mw_notifications(user_id, is_read, created_at DESC)
    """)

    # Channel message attachments
    op.execute("""
        ALTER TABLE channel_messages ADD COLUMN IF NOT EXISTS attachments JSONB DEFAULT '[]'::jsonb
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE channel_messages DROP COLUMN IF EXISTS attachments")
    op.execute("DROP INDEX IF EXISTS idx_mw_notifications_user")
    op.execute("DROP TABLE IF EXISTS mw_notifications")
