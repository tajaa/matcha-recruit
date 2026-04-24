"""Collab project workspace: extend mw_projects.status to include 'completed',
add project_id / board_column / assigned_to to mw_tasks for project-scoped kanban.

Revision ID: zzzb8c9d0e1f2
Revises: zzza7b8c9d0e1
Create Date: 2026-04-24
"""
from alembic import op

revision = "zzzb8c9d0e1f2"
down_revision = "zzza7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE mw_projects DROP CONSTRAINT IF EXISTS mw_projects_status_check")
    op.execute(
        "ALTER TABLE mw_projects ADD CONSTRAINT mw_projects_status_check "
        "CHECK (status IN ('active', 'archived', 'completed'))"
    )

    op.execute(
        "ALTER TABLE mw_tasks ADD COLUMN IF NOT EXISTS project_id UUID "
        "REFERENCES mw_projects(id) ON DELETE CASCADE"
    )
    op.execute(
        "ALTER TABLE mw_tasks ADD COLUMN IF NOT EXISTS board_column VARCHAR(20) "
        "CHECK (board_column IN ('todo','in_progress','review','done'))"
    )
    op.execute(
        "ALTER TABLE mw_tasks ADD COLUMN IF NOT EXISTS assigned_to UUID "
        "REFERENCES users(id) ON DELETE SET NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_mw_tasks_project ON mw_tasks(project_id) "
        "WHERE project_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_mw_tasks_project")
    op.execute("ALTER TABLE mw_tasks DROP COLUMN IF EXISTS assigned_to")
    op.execute("ALTER TABLE mw_tasks DROP COLUMN IF EXISTS board_column")
    op.execute("ALTER TABLE mw_tasks DROP COLUMN IF EXISTS project_id")
    op.execute("ALTER TABLE mw_projects DROP CONSTRAINT IF EXISTS mw_projects_status_check")
    op.execute(
        "ALTER TABLE mw_projects ADD CONSTRAINT mw_projects_status_check "
        "CHECK (status IN ('active', 'archived'))"
    )
