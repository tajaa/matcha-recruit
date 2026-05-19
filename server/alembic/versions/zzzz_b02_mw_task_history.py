"""Add mw_task_history audit trail for kanban tasks.

Revision ID: zzzz_b02_taskhist
Revises: zzzz_b01_taskfile
Create Date: 2026-05-18

Captures who/when for task lifecycle events: creation, column moves
(todo → in_progress → review → done), assignee changes, completion,
deletion. Feeds both the per-task timeline rendered inside
TaskViewerSheet and the per-project Recent Activity feed on the
Overview tab.

Forward-only — pre-existing tasks won't have history rows. New writes
land starting at upgrade time.
"""
from alembic import op


revision = "zzzz_b02_taskhist"
down_revision = "zzzz_b01_taskfile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mw_task_history (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            -- SET NULL so the delete event itself survives in the activity
            -- feed after a hard task delete. Project-level cascade still
            -- cleans everything up if the project itself is removed.
            task_id UUID NULL REFERENCES mw_tasks(id) ON DELETE SET NULL,
            project_id UUID NOT NULL REFERENCES mw_projects(id) ON DELETE CASCADE,
            actor_user_id UUID NULL REFERENCES users(id) ON DELETE SET NULL,
            event_type TEXT NOT NULL,
            from_value TEXT NULL,
            to_value TEXT NULL,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_mw_task_history_task_created
        ON mw_task_history (task_id, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_mw_task_history_project_created
        ON mw_task_history (project_id, created_at DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_mw_task_history_project_created")
    op.execute("DROP INDEX IF EXISTS idx_mw_task_history_task_created")
    op.execute("DROP TABLE IF EXISTS mw_task_history")
