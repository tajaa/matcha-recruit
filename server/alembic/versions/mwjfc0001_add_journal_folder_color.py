"""add mw_journal_folders.color

Notes/Evernote-style Journals workspace: folders are color-coded in the folder
rail + note list, mirroring how `mw_journals.color` already works.

Revision ID: mwjfc0001
Revises: zzzzfhr1a2b3
Create Date: 2026-06-07
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "mwjfc0001"
down_revision = "zzzzfhr1a2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE mw_journal_folders ADD COLUMN IF NOT EXISTS color VARCHAR(20)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE mw_journal_folders DROP COLUMN IF EXISTS color")
