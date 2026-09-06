"""Partial indexes for the AutoPR "run now" request lookups.

Revision ID: autoprrun01
Revises: espressoagent02
Create Date: 2026-09-01

The local AutoPR watcher polls "is any card queued?" once a minute, and every
kanban board render resolves the same pending-request state per card. Both
filter mw_task_history on a JSONB expression, which no existing index covers:
the only usable one is (project_id, created_at), so the poll degraded into a
full history walk as the table grew.

These two partial indexes cover exactly the bookkeeping rows AutoPR writes -
a tiny fraction of the table - keyed the way both queries read them: by
project for the poll, by task for the per-card claim lookup. The service also
bounds every one of those queries to a 30-minute window, so the index only
ever has to serve a short tail.
"""
from alembic import op


revision = "autoprrun01"
down_revision = "espressoagent02"
branch_labels = None
depends_on = None


_PREDICATE = (
    "WHERE event_type = 'activity' "
    "AND metadata->>'kind' IN ('autopr_run_request', 'autopr_run_claim')"
)


def upgrade():
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS idx_mw_task_history_autopr_run_project
            ON mw_task_history (project_id, created_at DESC)
            {_PREDICATE}
        """
    )
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS idx_mw_task_history_autopr_run_task
            ON mw_task_history (task_id, created_at DESC)
            {_PREDICATE}
        """
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_mw_task_history_autopr_run_task")
    op.execute("DROP INDEX IF EXISTS idx_mw_task_history_autopr_run_project")
