"""turn project elements into a context repository

Revision ID: elementrepo0001
Revises: reviewnote0001
Create Date: 2026-05-24

Elements graduate from a lightweight tag into a context repository: each element
("Inventory") owns its own folders (/invoices, /returns), files, and notes/links.

- mw_project_files.element_id / mw_project_folders.element_id (nullable FK):
  scope a file/folder to an element. NULL = the project's root Files/Media
  (the existing surface). ON DELETE SET NULL so deleting an element is
  non-destructive — its files/folders fall back to the project root.
- mw_element_notes: free-form notes + links pinned to an element. CASCADE on
  element delete (notes are element-only context, nothing to fall back to).

All additive + nullable. The backend filters root Files/Media to
`element_id IS NULL` so element-scoped content stays bucketed under the element.
Apply to every Postgres instance before deploying the matching backend.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "elementrepo0001"
down_revision: Union[str, Sequence[str], None] = "reviewnote0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE mw_project_files
            ADD COLUMN IF NOT EXISTS element_id TEXT
            REFERENCES mw_project_elements(id) ON DELETE SET NULL
        """
    )
    op.execute(
        """
        ALTER TABLE mw_project_folders
            ADD COLUMN IF NOT EXISTS element_id TEXT
            REFERENCES mw_project_elements(id) ON DELETE SET NULL
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mw_element_notes (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            element_id  TEXT NOT NULL REFERENCES mw_project_elements(id) ON DELETE CASCADE,
            project_id  UUID NOT NULL REFERENCES mw_projects(id) ON DELETE CASCADE,
            created_by  UUID REFERENCES users(id) ON DELETE SET NULL,
            kind        TEXT NOT NULL DEFAULT 'note',
            body        TEXT,
            url         TEXT,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_mw_project_files_element ON mw_project_files(element_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mw_project_folders_element ON mw_project_folders(element_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mw_element_notes_element ON mw_element_notes(element_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS mw_element_notes")
    op.execute("ALTER TABLE mw_project_folders DROP COLUMN IF EXISTS element_id")
    op.execute("ALTER TABLE mw_project_files DROP COLUMN IF EXISTS element_id")
