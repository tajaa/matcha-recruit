"""per-project GitHub repo connection

Replaces the local folder-upload model: a project connects to a GitHub repo
(owner/name + branch) once, and both the commit→subtask scanner and the Prop
code-grounding read from it server-side (read-only GITHUB_TOKEN). Not
machine-tied. Falls back to GITHUB_DEFAULT_REPO when unset.

Revision ID: ghconn0001
Revises: propdraft0002
Create Date: 2026-06-02
"""

from alembic import op


revision = "ghconn0001"
down_revision = "propdraft0002"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        ALTER TABLE mw_projects
            ADD COLUMN IF NOT EXISTS github_repo TEXT,
            ADD COLUMN IF NOT EXISTS github_branch TEXT
        """
    )


def downgrade():
    op.execute(
        """
        ALTER TABLE mw_projects
            DROP COLUMN IF EXISTS github_repo,
            DROP COLUMN IF EXISTS github_branch
        """
    )
