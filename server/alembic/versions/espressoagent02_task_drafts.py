"""Espresso project-agent task drafting.

Revision ID: espressoagent02
Revises: espressoagent01
Create Date: 2026-09-01

Task drafts originate from the project board rather than a channel message, so
their channel/message foreign keys are nullable. ``request_key`` gives the
desktop client an idempotency key for safely retrying an enqueue request.
"""
from alembic import op


revision = "espressoagent02"
down_revision = "espressoagent01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE mw_project_agent_runs
            ALTER COLUMN channel_id DROP NOT NULL,
            ALTER COLUMN trigger_message_id DROP NOT NULL,
            ADD COLUMN IF NOT EXISTS request_key UUID,
            ADD COLUMN IF NOT EXISTS model_override TEXT
    """)
    op.execute("""
        ALTER TABLE mw_project_agent_runs
            DROP CONSTRAINT IF EXISTS mw_project_agent_runs_kind_check
    """)
    op.execute("""
        ALTER TABLE mw_project_agent_runs
            ADD CONSTRAINT mw_project_agent_runs_kind_check
            CHECK (kind IN ('repo_question', 'task_draft'))
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_mw_project_agent_runs_request
        ON mw_project_agent_runs(request_key, agent_key)
        WHERE request_key IS NOT NULL
    """)


def downgrade():
    # Rows created from the board cannot satisfy the original channel/message
    # NOT NULL contract. Delete only this revision's task kind before restoring
    # the prior schema; repo-question audit history remains intact.
    op.execute("DELETE FROM mw_project_agent_runs WHERE kind='task_draft'")
    op.execute("DROP INDEX IF EXISTS idx_mw_project_agent_runs_request")
    op.execute("""
        ALTER TABLE mw_project_agent_runs
            DROP CONSTRAINT IF EXISTS mw_project_agent_runs_kind_check
    """)
    op.execute("""
        ALTER TABLE mw_project_agent_runs
            ADD CONSTRAINT mw_project_agent_runs_kind_check
            CHECK (kind IN ('repo_question')),
            ALTER COLUMN channel_id SET NOT NULL,
            ALTER COLUMN trigger_message_id SET NOT NULL,
            DROP COLUMN IF EXISTS request_key,
            DROP COLUMN IF EXISTS model_override
    """)
