"""Add policy_suggestions_dismissed to companies.

Revision ID: zu9v0w1x2y3z
Revises: zt8u9v0w1x2y
Create Date: 2025-03-25
"""
from alembic import op

revision = "zu9v0w1x2y3z"
down_revision = "zt8u9v0w1x2y"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE companies
        ADD COLUMN IF NOT EXISTS policy_suggestions_dismissed JSONB DEFAULT '[]'::jsonb
    """)


def downgrade():
    op.execute("""
        ALTER TABLE companies
        DROP COLUMN IF EXISTS policy_suggestions_dismissed
    """)
