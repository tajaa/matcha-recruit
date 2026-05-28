"""Add mw_section_comments — in-app threaded comments on project notes (sections).

Notes (project sections) live in the `mw_projects.sections` JSONB array; each has
a short hex string `id` (e.g. "9cd127aba09db86e"), NOT a UUID — hence
`section_id TEXT`. Collaborators can now leave comments on a note; this table
holds them. `reply_to_comment_id` is reserved for threaded replies (nullable;
the v1 UI renders a flat list).

Idempotent (CREATE TABLE / INDEX IF NOT EXISTS) so re-running against a
partially-upgraded DB is safe.

Revision ID: mwseccmt01
Revises: oshaexec01
Create Date: 2026-05-28
"""
from alembic import op


revision = "mwseccmt01"
down_revision = "oshaexec01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mw_section_comments (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id UUID NOT NULL,
            section_id TEXT NOT NULL,
            company_id UUID NOT NULL,
            user_id UUID NOT NULL,
            content TEXT NOT NULL,
            reply_to_comment_id UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_mw_section_comments_section "
        "ON mw_section_comments(project_id, section_id, created_at)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS mw_section_comments")
