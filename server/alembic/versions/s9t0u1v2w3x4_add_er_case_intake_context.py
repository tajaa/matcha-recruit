"""add intake_context to er_cases

Revision ID: s9t0u1v2w3x4
Revises: r8s9t0u1v2w3
Create Date: 2026-02-16
"""

from alembic import op
import sqlalchemy as sa


revision = "s9t0u1v2w3x4"
down_revision = "r8s9t0u1v2w3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("er_cases", sa.Column("intake_context", sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade():
    op.drop_column("er_cases", "intake_context")
