"""Add user_connections table for friend/follow system.

Revision ID: zzm3n4o5p6q7
Revises: zzl2m3n4o5p6
Create Date: 2026-04-10
"""
from alembic import op

revision = "zzm3n4o5p6q7"
down_revision = "zzl2m3n4o5p6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_connections (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            connected_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(user_id, connected_user_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_user_connections_user ON user_connections(user_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_user_connections_connected ON user_connections(connected_user_id, status)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_connections")
