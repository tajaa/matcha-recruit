"""Index AutoPR holds and round boundaries without changing the run indexes.

Revision ID: autoprrun02
Revises: autoprrun01

The existing run-project index remains useful for the bounded request poll.
This additional task index covers its claim/cancel subquery and the latest
hold/resume/round-boundary lookup, including existing history rows. Build it
concurrently so the history writers remain available. Older app versions can
ignore the extra index; downgrade only removes this optimization.
"""
from alembic import op

revision = "autoprrun02"
down_revision = "autoprrun01"
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        # An interrupted concurrent build can leave an invalid index behind.
        # Remove it before retrying rather than accepting it via IF NOT EXISTS.
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_mw_task_history_autopr_state_task")
        op.execute("""
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_mw_task_history_autopr_state_task
            ON mw_task_history (task_id, created_at DESC)
            WHERE (event_type = 'activity' AND metadata->>'kind' IN (
                'autopr_run_request', 'autopr_run_claim',
                'autopr_run_cancel', 'autopr_additional_context'))
               OR event_type IN ('review_rejected', 'round_started')
        """)


def downgrade():
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_mw_task_history_autopr_state_task")
