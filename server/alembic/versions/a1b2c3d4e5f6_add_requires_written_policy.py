"""Add requires_written_policy column to jurisdiction_requirements

Revision ID: a1b2c3d4e5f6
Revises: z7a8b9c0d1e
Create Date: 2026-03-08
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "z7a8b9c0d1e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "jurisdiction_requirements",
        sa.Column("requires_written_policy", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("jurisdiction_requirements", "requires_written_policy")
