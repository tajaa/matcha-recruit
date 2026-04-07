"""Add channel visibility and member roles for admin-gated channels.

Revision ID: zzg7h8i9j0k1
Revises: zzf6g7h8i9j0
Create Date: 2026-04-07
"""
from alembic import op

revision = "zzg7h8i9j0k1"
down_revision = "zzf6g7h8i9j0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Channel visibility
    op.execute("""
        ALTER TABLE channels ADD COLUMN IF NOT EXISTS visibility VARCHAR(20) DEFAULT 'public'
    """)

    # Member roles
    op.execute("""
        ALTER TABLE channel_members ADD COLUMN IF NOT EXISTS role VARCHAR(20) DEFAULT 'member'
    """)

    # Backfill: set channel creators as owners
    op.execute("""
        UPDATE channel_members cm
        SET role = 'owner'
        FROM channels ch
        WHERE cm.channel_id = ch.id AND cm.user_id = ch.created_by AND cm.role = 'member'
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE channel_members DROP COLUMN IF EXISTS role")
    op.execute("ALTER TABLE channels DROP COLUMN IF EXISTS visibility")
