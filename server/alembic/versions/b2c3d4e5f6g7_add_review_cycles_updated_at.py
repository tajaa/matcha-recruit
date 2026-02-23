"""add_review_cycles_updated_at

Revision ID: b2c3d4e5f6g7
Revises: a1b2c3d4e5f6
Create Date: 2026-01-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision = 'b2c3d4e5f6g7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6g7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add updated_at column to review_cycles table."""
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'review_cycles' AND column_name = 'updated_at'
            ) THEN
                ALTER TABLE review_cycles
                ADD COLUMN updated_at TIMESTAMP DEFAULT NOW();
            END IF;
        END $$;
    """)


def downgrade() -> None:
    """Remove updated_at column from review_cycles table."""
    op.drop_column('review_cycles', 'updated_at')
