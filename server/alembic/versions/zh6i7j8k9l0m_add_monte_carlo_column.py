"""add monte_carlo JSONB column to risk_assessment_snapshots

Revision ID: zh6i7j8k9l0m
Revises: zg5h6i7j8k9l
Create Date: 2026-03-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "zh6i7j8k9l0m"
down_revision = "zg5h6i7j8k9l"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "risk_assessment_snapshots",
        sa.Column("monte_carlo", JSONB, nullable=True),
    )


def downgrade():
    op.drop_column("risk_assessment_snapshots", "monte_carlo")
