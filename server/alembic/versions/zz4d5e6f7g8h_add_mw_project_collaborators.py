"""Add mw_project_collaborators table for project sharing.

Revision ID: zz4d5e6f7g8h
Revises: zz3c4d5e6f7g
Create Date: 2026-04-01
"""
from alembic import op

revision = "zz4d5e6f7g8h"
down_revision = "zz3c4d5e6f7g"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS mw_project_collaborators (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL REFERENCES mw_projects(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            invited_by UUID NOT NULL REFERENCES users(id),
            role VARCHAR(20) NOT NULL DEFAULT 'collaborator'
                CHECK (role IN ('owner', 'collaborator')),
            status VARCHAR(20) NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'removed')),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            UNIQUE (project_id, user_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_mw_proj_collab_project ON mw_project_collaborators(project_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mw_proj_collab_user ON mw_project_collaborators(user_id, status)")

    # Backfill: existing project creators become owners
    op.execute("""
        INSERT INTO mw_project_collaborators (project_id, user_id, invited_by, role)
        SELECT id, created_by, created_by, 'owner'
        FROM mw_projects
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS mw_project_collaborators")
