"""Add applicable_industries column to jurisdiction and compliance requirements

Revision ID: z8a9b0c1d2e3
Revises: y7z8a9b0c1d2
Create Date: 2026-03-09
"""
from alembic import op

revision = "z8a9b0c1d2e3"
down_revision = "y7z8a9b0c1d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE jurisdiction_requirements
        ADD COLUMN IF NOT EXISTS applicable_industries TEXT[]
    """)
    op.execute("""
        ALTER TABLE compliance_requirements
        ADD COLUMN IF NOT EXISTS applicable_industries TEXT[]
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE compliance_requirements
        DROP COLUMN IF EXISTS applicable_industries
    """)
    op.execute("""
        ALTER TABLE jurisdiction_requirements
        DROP COLUMN IF EXISTS applicable_industries
    """)
