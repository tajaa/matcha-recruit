"""add review_note to mw_tasks

Revision ID: reviewnote0001
Revises: zzzzci3d4e5f6
Create Date: 2026-05-24

Adds a single nullable `review_note` column to mw_tasks. When a reviewer sends
a task in the `review` column back to `todo` ("mark incomplete"), the reason is
stored here and surfaced as a "needs work" banner on the ticket + emailed to the
assignee. Cleared automatically when the task re-enters `review` or `done`.

Additive + nullable (ADD COLUMN IF NOT EXISTS) — safe and a no-op for existing
rows. The backend SELECT references the column unconditionally, so this MUST be
applied (to every Postgres instance) before deploying the matching backend.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "reviewnote0001"
down_revision: Union[str, Sequence[str], None] = "zzzzci3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE mw_tasks ADD COLUMN IF NOT EXISTS review_note TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE mw_tasks DROP COLUMN IF EXISTS review_note")
