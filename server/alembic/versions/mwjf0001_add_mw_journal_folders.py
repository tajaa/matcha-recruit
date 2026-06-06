"""add mw_journal_folders + journals.folder_id + journals.kind

Obsidian-style organization for the Journals hub: a per-company adjacency-list
folder tree (mirrors mw_project_folders) that journals can be filed into, plus
a `kind` discriminator so journal-creation templates (note/blog/todo/novel/
screenplay) can seed a starter entry + default icon.

Revision ID: mwjf0001
Revises: brokermile01
Create Date: 2026-06-05
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "mwjf0001"
down_revision = "brokermile01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mw_journal_folders (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            parent_id UUID REFERENCES mw_journal_folders(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            created_by UUID REFERENCES users(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_mw_journal_folders_company "
        "ON mw_journal_folders(company_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_mw_journal_folders_parent "
        "ON mw_journal_folders(parent_id)"
    )

    # Journals gain a folder placement (nullable; SET NULL keeps journals when a
    # folder is deleted) and a kind discriminator for create-time templates.
    op.execute(
        "ALTER TABLE mw_journals ADD COLUMN IF NOT EXISTS folder_id UUID "
        "REFERENCES mw_journal_folders(id) ON DELETE SET NULL"
    )
    op.execute(
        "ALTER TABLE mw_journals ADD COLUMN IF NOT EXISTS kind VARCHAR(20) "
        "NOT NULL DEFAULT 'journal'"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_mw_journals_folder ON mw_journals(folder_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_mw_journals_folder")
    op.execute("ALTER TABLE mw_journals DROP COLUMN IF EXISTS kind")
    op.execute("ALTER TABLE mw_journals DROP COLUMN IF EXISTS folder_id")
    op.execute("DROP TABLE IF EXISTS mw_journal_folders")
