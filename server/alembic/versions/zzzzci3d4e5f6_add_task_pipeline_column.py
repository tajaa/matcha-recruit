"""Add pipeline_column to mw_tasks for dual board+pipeline views.

Tasks previously stored either a kanban column (todo/in_progress/review/done)
OR a sales stage (lead/qualified/…/closed) in board_column, making the two views
mutually exclusive. This adds a dedicated pipeline_column so a task can live
simultaneously in a kanban position AND a pipeline stage.

Migration also back-fills existing tasks: tasks whose board_column is a sales
stage are assumed to come from a pipeline-mode project — their pipeline_column
is set to that stage and board_column is reset to 'todo'.

Revision ID: zzzzci3d4e5f6
Revises: zzzzbi2c3d4e5
Create Date: 2026-05-23
"""
from alembic import op

revision = "zzzzci3d4e5f6"
down_revision = ("50268295866e", "mwfold0001")
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE mw_tasks ADD COLUMN IF NOT EXISTS pipeline_column TEXT DEFAULT 'lead'")
    op.execute("""
        UPDATE mw_tasks
           SET pipeline_column = board_column,
               board_column    = 'todo'
         WHERE board_column IN ('lead', 'qualified', 'proposal', 'negotiation', 'closed')
    """)


def downgrade():
    op.execute("ALTER TABLE mw_tasks DROP COLUMN IF EXISTS pipeline_column")
