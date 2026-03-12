"""Add healthcare_specialties column to companies table.

Revision ID: zc1d2e3f4g5h
Revises: zb1c2d3e4f5g
Create Date: 2025-03-11
"""
from alembic import op
import sqlalchemy as sa

revision = "zc1d2e3f4g5h"
down_revision = "zb1c2d3e4f5g"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column("healthcare_specialties", sa.ARRAY(sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("companies", "healthcare_specialties")
