"""relax mw_tasks.board_column CHECK to allow 'changes_requested'

Revision ID: chgreq0001
Revises: 53df72e778a4
Create Date: 2026-05-25

Adds a 5th kanban column, 'changes_requested', that sits between in_progress and
review. When a reviewer sends a task back ("Send back"), it now lands in this
dedicated rework lane instead of polluting 'todo' alongside never-started work
(see project_task_service.reject_project_task).

board_column is VARCHAR(20) with an inline CHECK added by zzzb8c9d0e1f2
(auto-named mw_tasks_board_column_check). This migration drops that constraint
and re-adds it with the new value included. 'changes_requested' is 18 chars, so
it fits the existing VARCHAR(20) — no width change.

The backend SELECT/INSERT will accept the new value unconditionally once
_ALLOWED_COLUMNS includes it, so this MUST be applied to every Postgres instance
before deploying the matching backend.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "chgreq0001"
down_revision: Union[str, Sequence[str], None] = "53df72e778a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE mw_tasks DROP CONSTRAINT IF EXISTS mw_tasks_board_column_check")
    op.execute(
        "ALTER TABLE mw_tasks ADD CONSTRAINT mw_tasks_board_column_check "
        "CHECK (board_column IN ('todo','in_progress','changes_requested','review','done'))"
    )


def downgrade() -> None:
    # Park any rework cards back in 'todo' so the narrower CHECK can re-apply.
    op.execute("UPDATE mw_tasks SET board_column = 'todo' WHERE board_column = 'changes_requested'")
    op.execute("ALTER TABLE mw_tasks DROP CONSTRAINT IF EXISTS mw_tasks_board_column_check")
    op.execute(
        "ALTER TABLE mw_tasks ADD CONSTRAINT mw_tasks_board_column_check "
        "CHECK (board_column IN ('todo','in_progress','review','done'))"
    )
