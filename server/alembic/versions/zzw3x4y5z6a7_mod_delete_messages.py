"""Soft delete columns on channel_messages so mods can tombstone messages.

Revision ID: zzw3x4y5z6a7
Revises: zzv2w3x4y5z6
Create Date: 2026-04-15
"""
from alembic import op

revision = "zzw3x4y5z6a7"
down_revision = "zzv2w3x4y5z6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE channel_messages
          ADD COLUMN IF NOT EXISTS deleted_at timestamptz,
          ADD COLUMN IF NOT EXISTS deleted_by uuid REFERENCES users(id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_channel_messages_not_deleted
        ON channel_messages(channel_id, created_at DESC)
        WHERE deleted_at IS NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_channel_messages_not_deleted")
    op.execute("""
        ALTER TABLE channel_messages
          DROP COLUMN IF EXISTS deleted_by,
          DROP COLUMN IF EXISTS deleted_at
    """)
