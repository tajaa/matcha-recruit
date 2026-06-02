"""per-element repo code snapshot (grounding source for Prop chat)

The connector's Werk app reads files matching each element's repo_paths globs
(via FileManager — sandbox-safe, no git) and uploads their text here. This is
the grounding corpus a collaborator's "Prop" chat is answered against, so
product people can ask about code they don't have locally.

Full-replace per element (UNIQUE (element_id, path)); CASCADE from element/
project so deleting either clears the snapshot.

Revision ID: propsnap0001
Revises: elembind0002
Create Date: 2026-06-02
"""

from alembic import op


revision = "propsnap0001"
down_revision = "elembind0002"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mw_element_repo_files (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            element_id   TEXT NOT NULL REFERENCES mw_project_elements(id) ON DELETE CASCADE,
            project_id   UUID NOT NULL REFERENCES mw_projects(id) ON DELETE CASCADE,
            path         TEXT NOT NULL,
            content      TEXT NOT NULL,
            content_hash TEXT,
            size         INTEGER NOT NULL DEFAULT 0,
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_mw_element_repo_files_element_path
            ON mw_element_repo_files (element_id, path)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_mw_element_repo_files_element
            ON mw_element_repo_files (element_id)
        """
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS mw_element_repo_files")
