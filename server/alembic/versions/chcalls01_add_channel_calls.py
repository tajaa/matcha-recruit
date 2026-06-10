"""Add channel_calls + channel_call_invites for LiveKit-backed audio call sessions.

Up to 4 participants per call. The owner picks the join policy at start time:
'invite_only' (channel_call_invites rows gate joining) or 'members' (any
channel member until full).

Revision ID: chcalls01
Revises: brokerseats01
Create Date: 2026-06-09
"""
from alembic import op


revision = "chcalls01"
down_revision = "brokerseats01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS channel_calls (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            started_by UUID NOT NULL REFERENCES users(id),
            mode VARCHAR(20) NOT NULL CHECK (mode IN ('invite_only', 'members')),
            livekit_room VARCHAR(120) NOT NULL,
            started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            ended_at TIMESTAMPTZ
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_channel_calls_active
            ON channel_calls(channel_id) WHERE ended_at IS NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_channel_calls_channel_id
            ON channel_calls(channel_id)
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS channel_call_invites (
            call_id UUID NOT NULL REFERENCES channel_calls(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            invited_by UUID NOT NULL REFERENCES users(id),
            invited_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (call_id, user_id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_channel_call_invites_user
            ON channel_call_invites(user_id)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS channel_call_invites")
    op.execute("DROP TABLE IF EXISTS channel_calls")
