"""Huume collab-chat draft-PR agent audit and dispatch tables.

Revision ID: huumecode01
Revises: zzzzcappe30
Create Date: 2026-08-10
"""
from alembic import op

revision = "huumecode01"
down_revision = "zzzzcappe30"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS huume_code_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            project_id UUID NOT NULL REFERENCES mw_projects(id) ON DELETE CASCADE,
            channel_id UUID NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            task_id UUID REFERENCES mw_tasks(id) ON DELETE SET NULL,
            requested_by UUID NOT NULL REFERENCES users(id),
            trigger_message_id UUID NOT NULL REFERENCES channel_messages(id),
            status TEXT NOT NULL DEFAULT 'queued', branch TEXT, pr_url TEXT, error TEXT,
            model_calls INTEGER NOT NULL DEFAULT 0, files_changed INTEGER NOT NULL DEFAULT 0,
            token_usage JSONB, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            started_at TIMESTAMPTZ, completed_at TIMESTAMPTZ,
            CONSTRAINT huume_code_runs_status_check CHECK (status IN ('queued', 'running', 'done', 'failed'))
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_huume_code_runs_project_status ON huume_code_runs(project_id, status, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_huume_code_runs_company ON huume_code_runs(company_id, created_at DESC)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS huume_code_steps (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id UUID NOT NULL REFERENCES huume_code_runs(id) ON DELETE CASCADE,
            seq INTEGER NOT NULL, tool TEXT NOT NULL, kind TEXT NOT NULL, label TEXT NOT NULL,
            args JSONB, result JSONB, status TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT huume_code_steps_kind_check CHECK (kind IN ('read', 'write', 'finish')),
            CONSTRAINT huume_code_steps_status_check CHECK (status IN ('ok', 'error', 'skipped'))
        )
    """)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_huume_code_steps_run_seq ON huume_code_steps(run_id, seq)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mw_projects_discussion_channel ON mw_projects ((project_data->>'discussion_channel_id'))")


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_mw_projects_discussion_channel")
    op.execute("DROP TABLE IF EXISTS huume_code_steps")
    op.execute("DROP TABLE IF EXISTS huume_code_runs")
