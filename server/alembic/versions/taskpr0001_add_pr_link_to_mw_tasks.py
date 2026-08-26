"""add pr_url/pr_number to mw_tasks

Revision ID: taskpr0001
Revises: sales02
Create Date: 2026-08-26

Lets a kanban card carry a link to the GitHub PR that implements it (the
kanban-autopr loop writes these; a human can also paste pr_url by hand).
Additive, nullable, no backfill — every existing row has neither.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "taskpr0001"
down_revision: Union[str, Sequence[str], None] = "sales02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("mw_tasks", sa.Column("pr_url", sa.Text(), nullable=True))
    op.add_column("mw_tasks", sa.Column("pr_number", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("mw_tasks", "pr_number")
    op.drop_column("mw_tasks", "pr_url")
