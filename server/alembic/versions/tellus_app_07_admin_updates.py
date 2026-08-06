"""tellus_app_07 — admin changelog table + autogen watermark.

Twin of `admin_updates` (migration adminupd01) for the new Tell-Us internal
admin surface at /tellus/admin/updates, plus a single-row state table the
changelog generator (server/scripts/generate_changelog.py) uses to remember
the last merged PR number it fully processed. The watermark is GLOBAL across
both product tables — a PR only advances it once every product it touches
has an entry generated, so a `--product`-narrowed run never advances state
past a PR whose other-product half is still pending.

Revision ID: tellus_app_07
Revises: tellus_app_06
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "tellus_app_07"
down_revision: Union[str, Sequence[str], None] = "tellus_app_06"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tellus_admin_updates",
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
    op.create_index("ix_tellus_admin_updates_position", "tellus_admin_updates", ["position"])

    op.create_table(
        "changelog_autogen_state",
        sa.Column("id", sa.Integer(), primary_key=True, server_default=sa.text("1")),
        sa.Column("last_pr_number", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_changelog_autogen_state_singleton"),
    )


def downgrade() -> None:
    op.drop_table("changelog_autogen_state")
    op.drop_index("ix_tellus_admin_updates_position", table_name="tellus_admin_updates")
    op.drop_table("tellus_admin_updates")
