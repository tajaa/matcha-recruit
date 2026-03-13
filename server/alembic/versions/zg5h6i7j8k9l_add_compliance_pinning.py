"""add is_pinned to compliance_requirements

Revision ID: zg5h6i7j8k9l
Revises: zf4g5h6i7j8k
Create Date: 2026-03-13
"""
from alembic import op
import sqlalchemy as sa

revision = "zg5h6i7j8k9l"
down_revision = "zf4g5h6i7j8k"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "compliance_requirements",
        sa.Column("is_pinned", sa.Boolean, server_default=sa.text("false"), nullable=False),
    )


def downgrade():
    op.drop_column("compliance_requirements", "is_pinned")
