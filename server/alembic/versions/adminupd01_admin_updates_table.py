"""admin updates table

Moves the /admin/updates changelog off a static frontend TS file
(client/src/data/adminUpdates.ts) into the database. It was dev-authored
content, but the file had grown past 1,000 lines and every new entry meant
a frontend redeploy just to publish a paragraph of text.

Revision ID: adminupd01
Revises: indprofrestore01, zzzzcappe20
Create Date: 2026-07-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "adminupd01"
down_revision: Union[str, Sequence[str], None] = ("indprofrestore01", "zzzzcappe20")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "admin_updates",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("whats_new", JSONB(), nullable=False),
        sa.Column("how_to_use", JSONB(), nullable=False),
        sa.Column("setup", JSONB(), nullable=True),
        sa.Column("notes", JSONB(), nullable=True),
        sa.Column("tag", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_admin_updates_position", "admin_updates", ["position"])


def downgrade() -> None:
    op.drop_index("ix_admin_updates_position", table_name="admin_updates")
    op.drop_table("admin_updates")
