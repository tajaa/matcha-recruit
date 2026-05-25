"""add mw_subtasks — checklist items under a kanban task

Revision ID: mwsub0001
Revises: chgreq0001
Create Date: 2026-05-25

A complex feature is more than one card. mw_subtasks lets a task hold an ordered
checklist of trackable child items (title + done), so the card can show "3/7
done" and a reviewer can re-open specific items when sending work back.

Kept as a separate table rather than a parent_id self-reference on mw_tasks:
checklist items don't need columns / priority / pipeline / assignee-pipeline
fields, and a separate table keeps them out of every existing mw_tasks query
(no need to filter children everywhere). ON DELETE CASCADE with the parent task.

Additive — safe no-op for existing data. The list_project_tasks aggregate
subqueries reference this table, so it MUST be applied before deploying the
matching backend.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "mwsub0001"
down_revision: Union[str, Sequence[str], None] = "chgreq0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mw_subtasks (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            task_id      UUID NOT NULL REFERENCES mw_tasks(id) ON DELETE CASCADE,
            project_id   UUID NOT NULL,
            company_id   UUID NOT NULL,
            title        TEXT NOT NULL,
            is_done      BOOLEAN NOT NULL DEFAULT false,
            position     INTEGER NOT NULL DEFAULT 0,
            assigned_to  UUID,
            created_by   UUID,
            completed_at TIMESTAMPTZ,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_mw_subtasks_task "
        "ON mw_subtasks(task_id, position)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_mw_subtasks_task")
    op.execute("DROP TABLE IF EXISTS mw_subtasks")
