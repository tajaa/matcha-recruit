"""add mw_project_folders + folder_id on mw_project_files

Revision ID: mwfold0001
Revises: irp1a2b3c4d5e
Create Date: 2026-05-22

Adds manual folder organization to project Files and supports the new
chat-attachment -> project Files mirroring:

  * mw_project_folders — per-project folders, optional self-referential
    parent_id for nesting. ON DELETE CASCADE with the project; deleting a
    folder sets its files' folder_id to NULL (files fall back to the root,
    never orphaned).
  * mw_project_files.folder_id — nullable; NULL = root of the Files tab.
  * partial UNIQUE index on (project_id, storage_url) WHERE task_id IS NULL —
    lets the chat->Files sync dedupe root-level mirrors of the same object
    (message edits / WS redelivery won't double-insert). Scoped to root files
    so task-scoped attachments are untouched. Existing root duplicates are
    collapsed first so the unique index can be created.

All additive / nullable and reversible.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "mwfold0001"
down_revision: Union[str, Sequence[str], None] = "irp1a2b3c4d5e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mw_project_folders (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id  UUID NOT NULL REFERENCES mw_projects(id) ON DELETE CASCADE,
            parent_id   UUID REFERENCES mw_project_folders(id) ON DELETE CASCADE,
            name        TEXT NOT NULL,
            created_by  UUID,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_mw_project_folders_project_id "
        "ON mw_project_folders(project_id)"
    )
    op.execute(
        "ALTER TABLE mw_project_files "
        "ADD COLUMN IF NOT EXISTS folder_id UUID "
        "REFERENCES mw_project_folders(id) ON DELETE SET NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_mw_project_files_folder_id "
        "ON mw_project_files(folder_id) WHERE folder_id IS NOT NULL"
    )
    # Collapse pre-existing root-level duplicates (same object mirrored twice)
    # so the partial unique index below can be built. Keeps the earliest row.
    op.execute(
        """
        DELETE FROM mw_project_files a
        USING mw_project_files b
        WHERE a.task_id IS NULL
          AND b.task_id IS NULL
          AND a.project_id = b.project_id
          AND a.storage_url = b.storage_url
          AND a.ctid > b.ctid
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_mw_project_files_project_url "
        "ON mw_project_files(project_id, storage_url) WHERE task_id IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_mw_project_files_project_url")
    op.execute("DROP INDEX IF EXISTS idx_mw_project_files_folder_id")
    op.execute("ALTER TABLE mw_project_files DROP COLUMN IF EXISTS folder_id")
    op.execute("DROP INDEX IF EXISTS idx_mw_project_folders_project_id")
    op.execute("DROP TABLE IF EXISTS mw_project_folders")
