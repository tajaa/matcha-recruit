"""Add requires_written_policy column to jurisdiction_requirements

Revision ID: a1b2c3d4e5f9
Revises: z7a8b9c0d1e
Create Date: 2026-03-08
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "a1b2c3d4e5f9"
down_revision: Union[str, None] = "z7a8b9c0d1e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE jurisdiction_requirements ADD COLUMN IF NOT EXISTS requires_written_policy BOOLEAN"
    )


def downgrade() -> None:
    op.drop_column("jurisdiction_requirements", "requires_written_policy")
