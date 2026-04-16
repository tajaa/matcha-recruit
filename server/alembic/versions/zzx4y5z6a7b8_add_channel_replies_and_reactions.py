"""add channel replies and reactions

Revision ID: zzx4y5z6a7b8
Revises: zzw3x4y5z6a7
Create Date: 2026-04-16
"""

from alembic import op


revision = "zzx4y5z6a7b8"
down_revision = "zzw3x4y5z6a7"
branch_labels = None
depends_on = None


def upgrade():
    # Reply threading — optional FK to parent message
    op.execute("""
        ALTER TABLE channel_messages
        ADD COLUMN IF NOT EXISTS reply_to_id UUID REFERENCES channel_messages(id) ON DELETE SET NULL
    """)

    # Reactions table — one row per user per emoji per message (toggle on/off)
    op.execute("""
        CREATE TABLE IF NOT EXISTS channel_reactions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            message_id UUID NOT NULL REFERENCES channel_messages(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            emoji TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (message_id, user_id, emoji)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_channel_reactions_message
        ON channel_reactions(message_id)
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS channel_reactions")
    op.execute("ALTER TABLE channel_messages DROP COLUMN IF EXISTS reply_to_id")
