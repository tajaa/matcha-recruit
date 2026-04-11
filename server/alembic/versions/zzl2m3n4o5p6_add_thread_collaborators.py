"""Add thread collaborators table for real-time collaborative threads.

Revision ID: zzl2m3n4o5p6
Revises: zzk1l2m3n4o5
Create Date: 2026-04-10
"""
from alembic import op

revision = "zzl2m3n4o5p6"
down_revision = "zzk1l2m3n4o5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS mw_thread_collaborators (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            thread_id UUID NOT NULL REFERENCES mw_threads(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            invited_by UUID REFERENCES users(id),
            role TEXT NOT NULL DEFAULT 'collaborator',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(thread_id, user_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_thread_collaborators_thread ON mw_thread_collaborators(thread_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_thread_collaborators_user ON mw_thread_collaborators(user_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS mw_thread_collaborators")
