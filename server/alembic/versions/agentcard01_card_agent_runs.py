"""Matcha Work: agent cards run as durable project-agent runs.

Revision ID: agentcard01
Revises: zzzzcappe34
Create Date: 2026-09-28

An `agent` kanban card ("find me the best organic lip balm") is answered by a
server-side web agent. Each pass is one `mw_project_agent_runs` row with
kind='card_agent', bound to its card (`task_id`) and review round (`round`);
the structured result lives in the existing `result` JSONB. The partial unique
index is the one-live-run-per-card guard the enqueue path relies on.
"""
from alembic import op


revision = "agentcard01"
down_revision = "zzzzcappe34"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE mw_project_agent_runs
            ADD COLUMN IF NOT EXISTS task_id UUID REFERENCES mw_tasks(id) ON DELETE CASCADE,
            ADD COLUMN IF NOT EXISTS round INTEGER,
            ADD COLUMN IF NOT EXISTS search_calls INTEGER NOT NULL DEFAULT 0
    """)
    op.execute("""
        ALTER TABLE mw_project_agent_runs
            DROP CONSTRAINT IF EXISTS mw_project_agent_runs_kind_check
    """)
    op.execute("""
        ALTER TABLE mw_project_agent_runs
            ADD CONSTRAINT mw_project_agent_runs_kind_check
            CHECK (kind IN ('repo_question', 'task_draft', 'card_agent'))
    """)
    op.execute("""
        ALTER TABLE mw_project_agent_runs
            DROP CONSTRAINT IF EXISTS mw_project_agent_runs_card_agent_task
    """)
    op.execute("""
        ALTER TABLE mw_project_agent_runs
            ADD CONSTRAINT mw_project_agent_runs_card_agent_task
            CHECK (kind <> 'card_agent' OR (task_id IS NOT NULL AND round IS NOT NULL))
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_mw_project_agent_runs_task_live
        ON mw_project_agent_runs(task_id)
        WHERE kind = 'card_agent' AND status IN ('queued', 'running')
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_mw_project_agent_runs_task_round
        ON mw_project_agent_runs(task_id, round DESC)
        WHERE kind = 'card_agent'
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_mw_project_agent_runs_card_user_month
        ON mw_project_agent_runs(requested_by, created_at)
        WHERE kind = 'card_agent'
    """)
    op.execute("""
        ALTER TABLE mw_project_agent_steps
            DROP CONSTRAINT IF EXISTS mw_project_agent_steps_kind_check
    """)
    op.execute("""
        ALTER TABLE mw_project_agent_steps
            ADD CONSTRAINT mw_project_agent_steps_kind_check
            CHECK (kind IN ('read', 'finish', 'search', 'fetch', 'image'))
    """)


def downgrade():
    op.execute("DELETE FROM mw_project_agent_runs WHERE kind = 'card_agent'")
    op.execute("DROP INDEX IF EXISTS idx_mw_project_agent_runs_card_user_month")
    op.execute("DROP INDEX IF EXISTS idx_mw_project_agent_runs_task_round")
    op.execute("DROP INDEX IF EXISTS idx_mw_project_agent_runs_task_live")
    op.execute("""
        DELETE FROM mw_project_agent_steps
        WHERE kind NOT IN ('read', 'finish')
    """)
    op.execute("""
        ALTER TABLE mw_project_agent_steps
            DROP CONSTRAINT IF EXISTS mw_project_agent_steps_kind_check
    """)
    op.execute("""
        ALTER TABLE mw_project_agent_steps
            ADD CONSTRAINT mw_project_agent_steps_kind_check
            CHECK (kind IN ('read', 'finish'))
    """)
    op.execute("""
        ALTER TABLE mw_project_agent_runs
            DROP CONSTRAINT IF EXISTS mw_project_agent_runs_card_agent_task
    """)
    op.execute("""
        ALTER TABLE mw_project_agent_runs
            DROP CONSTRAINT IF EXISTS mw_project_agent_runs_kind_check
    """)
    op.execute("""
        ALTER TABLE mw_project_agent_runs
            ADD CONSTRAINT mw_project_agent_runs_kind_check
            CHECK (kind IN ('repo_question', 'task_draft')),
            DROP COLUMN IF EXISTS search_calls,
            DROP COLUMN IF EXISTS round,
            DROP COLUMN IF EXISTS task_id
    """)
