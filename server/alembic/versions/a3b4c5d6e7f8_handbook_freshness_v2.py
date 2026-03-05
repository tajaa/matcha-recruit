"""handbook_freshness_v2

Revision ID: a3b4c5d6e7f8
Revises: e72bfad5eca9
Create Date: 2026-03-05 03:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3b4c5d6e7f8'
down_revision: Union[str, Sequence[str], None] = 'e72bfad5eca9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE handbook_freshness_checks
        ADD COLUMN IF NOT EXISTS profile_fingerprint VARCHAR(128)
    """)
    op.execute("""
        ALTER TABLE handbook_sections
        ADD COLUMN IF NOT EXISTS last_reviewed_at TIMESTAMPTZ
    """)
    op.execute("""
        ALTER TABLE handbook_freshness_findings
        ADD COLUMN IF NOT EXISTS age_days INTEGER
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE handbook_freshness_findings
        DROP COLUMN IF EXISTS age_days
    """)
    op.execute("""
        ALTER TABLE handbook_sections
        DROP COLUMN IF EXISTS last_reviewed_at
    """)
    op.execute("""
        ALTER TABLE handbook_freshness_checks
        DROP COLUMN IF EXISTS profile_fingerprint
    """)
