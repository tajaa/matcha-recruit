"""Add channel_invites table for invite link system.

Revision ID: zzk1l2m3n4o5
Revises: zzj0k1l2m3n4
Create Date: 2026-04-09
"""
from alembic import op

revision = "zzk1l2m3n4o5"
down_revision = "zzj0k1l2m3n4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS channel_invites (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            channel_id uuid NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            code text NOT NULL UNIQUE,
            created_by uuid NOT NULL REFERENCES users(id),
            max_uses integer,
            use_count integer NOT NULL DEFAULT 0,
            expires_at timestamptz,
            is_active boolean NOT NULL DEFAULT true,
            note text,
            created_at timestamptz NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_channel_invites_channel_active
        ON channel_invites (channel_id, is_active)
    """)

    # code column already has UNIQUE constraint which creates an implicit index


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS channel_invites")
