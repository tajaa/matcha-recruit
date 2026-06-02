"""element repo binding: path globs + branch on mw_project_elements

Repurposes project Elements as logical bindings between a git repo's subpaths
and the kanban. `repo_paths` holds glob patterns (e.g. {'server/**'}) that scope
which changed files in a commit map to this element; `repo_branch` optionally
restricts matching to one branch. Both nullable/defaulted so existing elements
(plain context buckets) are unaffected. No real git submodule — logical only.

Revision ID: elembind0001
Revises: seccmtanchor01
Create Date: 2026-06-02
"""

from alembic import op


revision = "elembind0001"
down_revision = "seccmtanchor01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        ALTER TABLE mw_project_elements
            ADD COLUMN IF NOT EXISTS repo_paths TEXT[] NOT NULL DEFAULT '{}',
            ADD COLUMN IF NOT EXISTS repo_branch TEXT
        """
    )


def downgrade():
    op.execute(
        """
        ALTER TABLE mw_project_elements
            DROP COLUMN IF EXISTS repo_paths,
            DROP COLUMN IF EXISTS repo_branch
        """
    )
