"""Add inbox messaging tables.

Revision ID: zz2b3c4d5e6f
Revises: zz1a2b3c4d5e
Create Date: 2026-04-01
"""
from alembic import op

revision = "zz2b3c4d5e6f"
down_revision = "zz1a2b3c4d5e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS inbox_conversations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            title VARCHAR(255),
            is_group BOOLEAN DEFAULT false,
            created_by UUID NOT NULL REFERENCES users(id),
            last_message_at TIMESTAMPTZ,
            last_message_preview TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_inbox_conversations_last_message
        ON inbox_conversations(last_message_at DESC)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS inbox_participants (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            conversation_id UUID NOT NULL REFERENCES inbox_conversations(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            last_read_at TIMESTAMPTZ,
            is_muted BOOLEAN DEFAULT false,
            joined_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE(conversation_id, user_id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_inbox_participants_user
        ON inbox_participants(user_id, last_read_at)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_inbox_participants_conversation
        ON inbox_participants(conversation_id)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS inbox_messages (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            conversation_id UUID NOT NULL REFERENCES inbox_conversations(id) ON DELETE CASCADE,
            sender_id UUID NOT NULL REFERENCES users(id),
            content TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            edited_at TIMESTAMPTZ
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_inbox_messages_conversation
        ON inbox_messages(conversation_id, created_at DESC)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_inbox_messages_sender
        ON inbox_messages(sender_id)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS inbox_email_batches (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            recipient_id UUID NOT NULL REFERENCES users(id),
            sender_id UUID NOT NULL REFERENCES users(id),
            last_sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(recipient_id, sender_id)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS inbox_email_batches")
    op.execute("DROP TABLE IF EXISTS inbox_messages")
    op.execute("DROP TABLE IF EXISTS inbox_participants")
    op.execute("DROP TABLE IF EXISTS inbox_conversations")
