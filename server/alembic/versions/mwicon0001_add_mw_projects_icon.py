"""add icon column to mw_projects

Revision ID: mwicon0001
Revises: irlink0001
Create Date: 2026-05-26

Werk sidebar shows a chosen icon per project (mirrors mw_journals.icon).
Stores an SF Symbol name (e.g. "folder", "doc.text"); nullable — the client
falls back to "folder" when unset. Additive, no backfill needed.

mw_projects is created via migration (zx2y3z4a5b6c), not database.py:init_db,
so this ALTER is the only place the column needs adding.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "mwicon0001"
down_revision: Union[str, Sequence[str], None] = "irlink0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE mw_projects ADD COLUMN IF NOT EXISTS icon VARCHAR(64)")


def downgrade() -> None:
    op.execute("ALTER TABLE mw_projects DROP COLUMN IF EXISTS icon")
