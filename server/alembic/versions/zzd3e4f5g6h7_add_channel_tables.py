"""Add channel tables for Slack-style group chat in Matcha Work.

Revision ID: zzd3e4f5g6h7
Revises: zzc2d3e4f5g6
Create Date: 2026-04-03
"""
from alembic import op

revision = "zzd3e4f5g6h7"
down_revision = "zzc2d3e4f5g6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS channels (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id),
            name VARCHAR(100) NOT NULL,
            slug VARCHAR(120) NOT NULL,
            description TEXT,
            created_by UUID NOT NULL REFERENCES users(id),
            is_archived BOOLEAN DEFAULT false,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(company_id, slug)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_channels_company
        ON channels(company_id, is_archived, updated_at DESC)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS channel_members (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            joined_at TIMESTAMPTZ DEFAULT NOW(),
            last_read_at TIMESTAMPTZ,
            is_muted BOOLEAN DEFAULT false,
            UNIQUE(channel_id, user_id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_channel_members_user
        ON channel_members(user_id)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS channel_messages (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            sender_id UUID NOT NULL REFERENCES users(id),
            content TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            edited_at TIMESTAMPTZ
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_channel_messages_channel
        ON channel_messages(channel_id, created_at DESC)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS channel_messages")
    op.execute("DROP TABLE IF EXISTS channel_members")
    op.execute("DROP TABLE IF EXISTS channels")
