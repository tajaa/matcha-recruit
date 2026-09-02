"""Matcha Work: durable project-agent runs for repo questions.

Revision ID: espressoagent01
Revises: cappesuggfix01
Create Date: 2026-09-01

The table names are task-kind neutral on purpose.  Repo Q&A is the first
project-agent task; later task-drafting work can add another ``kind`` while
reusing the same queue/audit lifecycle.
"""
from alembic import op


revision = "espressoagent01"
down_revision = "cappesuggfix01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS mw_project_agent_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            project_id UUID NOT NULL REFERENCES mw_projects(id) ON DELETE CASCADE,
            channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            requested_by UUID NOT NULL REFERENCES users(id),
            trigger_message_id UUID NOT NULL REFERENCES channel_messages(id),
            agent_key TEXT NOT NULL DEFAULT 'espresso',
            kind TEXT NOT NULL DEFAULT 'repo_question',
            prompt TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            result JSONB,
            error TEXT,
            model_calls INTEGER NOT NULL DEFAULT 0,
            files_read INTEGER NOT NULL DEFAULT 0,
            token_usage JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            started_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            CONSTRAINT mw_project_agent_runs_status_check
                CHECK (status IN ('queued', 'running', 'done', 'failed')),
            CONSTRAINT mw_project_agent_runs_agent_check
                CHECK (agent_key IN ('espresso')),
            CONSTRAINT mw_project_agent_runs_kind_check
                CHECK (kind IN ('repo_question'))
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_mw_project_agent_runs_trigger
        ON mw_project_agent_runs(trigger_message_id, agent_key)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_mw_project_agent_runs_project_status
        ON mw_project_agent_runs(project_id, status, created_at DESC)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_mw_project_agent_runs_company
        ON mw_project_agent_runs(company_id, created_at DESC)
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS mw_project_agent_steps (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id UUID NOT NULL REFERENCES mw_project_agent_runs(id) ON DELETE CASCADE,
            seq INTEGER NOT NULL,
            tool TEXT NOT NULL,
            kind TEXT NOT NULL,
            label TEXT NOT NULL,
            args JSONB,
            result JSONB,
            status TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT mw_project_agent_steps_kind_check
                CHECK (kind IN ('read', 'finish')),
            CONSTRAINT mw_project_agent_steps_status_check
                CHECK (status IN ('ok', 'error', 'skipped'))
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_mw_project_agent_steps_run_seq
        ON mw_project_agent_steps(run_id, seq)
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS mw_project_agent_steps")
    op.execute("DROP TABLE IF EXISTS mw_project_agent_runs")
