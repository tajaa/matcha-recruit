"""Add rate_type column for minimum wage variants

Revision ID: g7h8i9j0k1l2
Revises: f6g7h8i9j0k1
Create Date: 2026-02-03

"""
from typing import Sequence, Union

from alembic import op

revision = 'g7h8i9j0k1l2'
down_revision = 'f6g7h8i9j0k1'
branch_labels = None
depends_on = None
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'g7h8i9j0k1l2'
down_revision: Union[str, None] = 'f6g7h8i9j0k1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add rate_type to compliance_requirements (IF NOT EXISTS handled via raw SQL)
    op.execute("""
        ALTER TABLE compliance_requirements
        ADD COLUMN IF NOT EXISTS rate_type VARCHAR(50)
    """)

    # Add rate_type to jurisdiction_requirements
    op.execute("""
        ALTER TABLE jurisdiction_requirements
        ADD COLUMN IF NOT EXISTS rate_type VARCHAR(50)
    """)

    # Add rate_type to compliance_requirement_history
    op.execute("""
        ALTER TABLE compliance_requirement_history
        ADD COLUMN IF NOT EXISTS rate_type VARCHAR(50)
    """)

    # Create indexes for filtering by rate_type (IF NOT EXISTS)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_compliance_requirements_rate_type
        ON compliance_requirements(rate_type)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_jurisdiction_requirements_rate_type
        ON jurisdiction_requirements(rate_type)
    """)


def downgrade() -> None:
    # Drop indexes (IF EXISTS)
    op.execute("DROP INDEX IF EXISTS idx_jurisdiction_requirements_rate_type")
    op.execute("DROP INDEX IF EXISTS idx_compliance_requirements_rate_type")

    # Drop columns (IF EXISTS)
    op.execute("ALTER TABLE compliance_requirement_history DROP COLUMN IF EXISTS rate_type")
    op.execute("ALTER TABLE jurisdiction_requirements DROP COLUMN IF EXISTS rate_type")
    op.execute("ALTER TABLE compliance_requirements DROP COLUMN IF EXISTS rate_type")
