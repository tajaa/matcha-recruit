"""Add channel_broadcasts table for LiveKit-backed live video sessions.

Revision ID: zzzz5d6e7f8g9
Revises: zzzz4c5d6e7f8
Create Date: 2026-05-08
"""
from alembic import op


revision = "zzzz5d6e7f8g9"
down_revision = "zzzz4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS channel_broadcasts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            started_by UUID NOT NULL REFERENCES users(id),
            livekit_room VARCHAR(120) NOT NULL,
            started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            ended_at TIMESTAMPTZ,
            title VARCHAR(255)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_channel_broadcasts_active
            ON channel_broadcasts(channel_id) WHERE ended_at IS NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_channel_broadcasts_channel_id
            ON channel_broadcasts(channel_id)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS channel_broadcasts")
