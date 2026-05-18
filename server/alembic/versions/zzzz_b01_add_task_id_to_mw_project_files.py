"""Add task_id to mw_project_files for kanban task attachments.

Revision ID: zzzz_b01_taskfile
Revises: zzzz_a01_aoscope
Create Date: 2026-05-17
"""
from alembic import op


revision = "zzzz_b01_taskfile"
down_revision = "zzzz_a01_aoscope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE mw_project_files
        ADD COLUMN IF NOT EXISTS task_id UUID NULL
        REFERENCES mw_tasks(id) ON DELETE CASCADE
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_mw_project_files_task_id
        ON mw_project_files(task_id)
        WHERE task_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_mw_project_files_task_id")
    op.execute("ALTER TABLE mw_project_files DROP COLUMN IF EXISTS task_id")
