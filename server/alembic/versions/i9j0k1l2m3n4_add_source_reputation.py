"""Add source reputation tracking columns to jurisdiction_sources

Revision ID: i9j0k1l2m3n4
Revises: h8i9j0k1l2m3
Create Date: 2026-02-03

"""
from typing import Sequence, Union

from alembic import op

revision = 'i9j0k1l2m3n4'
down_revision = 'h8i9j0k1l2m3'
branch_labels = None
depends_on = None
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'i9j0k1l2m3n4'
down_revision: Union[str, None] = 'h8i9j0k1l2m3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add reputation tracking columns to jurisdiction_sources
    op.execute("""
        ALTER TABLE jurisdiction_sources
        ADD COLUMN IF NOT EXISTS accurate_count INTEGER DEFAULT 0,
        ADD COLUMN IF NOT EXISTS inaccurate_count INTEGER DEFAULT 0,
        ADD COLUMN IF NOT EXISTS last_accuracy_update TIMESTAMP
    """)

    # Create index for accuracy-based queries
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_jurisdiction_sources_accuracy
        ON jurisdiction_sources(jurisdiction_id, accurate_count, inaccurate_count)
    """)


def downgrade() -> None:
    # Drop index
    op.execute("DROP INDEX IF EXISTS idx_jurisdiction_sources_accuracy")

    # Remove columns
    op.execute("""
        ALTER TABLE jurisdiction_sources
        DROP COLUMN IF EXISTS accurate_count,
        DROP COLUMN IF EXISTS inaccurate_count,
        DROP COLUMN IF EXISTS last_accuracy_update
    """)
