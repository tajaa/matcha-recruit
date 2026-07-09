"""Add details JSONB to lead_captures for the landing qualification wizard.

The wizard collects structured answers (headcount range, location count,
primary needs) that don't fit the existing flat columns. `source` is
varchar(100), so stuffing a note blob in there truncates.

Revision ID: leadqual01
Revises: hnswvec01
Create Date: 2026-07-09 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "leadqual01"
down_revision = "hnswvec01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "lead_captures",
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("lead_captures", "details")
