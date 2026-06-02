"""commit-driven subtask suggestions

When a local git commit's changed files map (via element repo_paths globs) to an
element's open tickets, Gemini proposes which subtasks the commit completed. Each
proposal is persisted here as a pending suggestion surfaced on the ticket; the
user Accepts (flips is_done through the normal subtask path) or Dismisses. Never
auto-flips.

Idempotency: UNIQUE (subtask_id, commit_sha) so re-scanning the same commit
(ON CONFLICT DO NOTHING) never duplicates a suggestion. CASCADE from task/subtask
clears suggestions when the parent is deleted.

Revision ID: elembind0002
Revises: elembind0001
Create Date: 2026-06-02
"""

from alembic import op


revision = "elembind0002"
down_revision = "elembind0001"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mw_commit_subtask_suggestions (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id       UUID NOT NULL,
            project_id       UUID NOT NULL REFERENCES mw_projects(id) ON DELETE CASCADE,
            task_id          UUID NOT NULL REFERENCES mw_tasks(id) ON DELETE CASCADE,
            subtask_id       UUID NOT NULL REFERENCES mw_subtasks(id) ON DELETE CASCADE,
            element_id       TEXT REFERENCES mw_project_elements(id) ON DELETE SET NULL,
            commit_sha       TEXT NOT NULL,
            commit_short_sha TEXT,
            commit_message   TEXT,
            confidence       REAL NOT NULL,
            reasoning        TEXT,
            status           TEXT NOT NULL DEFAULT 'pending'
                             CHECK (status IN ('pending', 'accepted', 'dismissed')),
            created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            resolved_at      TIMESTAMPTZ,
            resolved_by      UUID
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_mw_commit_suggestions_subtask_commit
            ON mw_commit_subtask_suggestions (subtask_id, commit_sha)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_mw_commit_suggestions_project_status
            ON mw_commit_subtask_suggestions (project_id, status)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_mw_commit_suggestions_task_status
            ON mw_commit_subtask_suggestions (task_id, status)
        """
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS mw_commit_subtask_suggestions")
