"""add report_email_token to companies

Revision ID: a1b2c3d4e5f6
Revises: z7a8b9c0d1e
Create Date: 2026-03-03
"""

from alembic import op


revision = "a1b2c3d4e5f6"
down_revision = "z7a8b9c0d1e"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        ALTER TABLE companies
        ADD COLUMN IF NOT EXISTS report_email_token VARCHAR(32);
        """
    )
    op.execute(
        """
        ALTER TABLE companies
        ADD CONSTRAINT uq_companies_report_email_token UNIQUE (report_email_token);
        """
    )


def downgrade():
    op.execute(
        """
        ALTER TABLE companies DROP CONSTRAINT IF EXISTS uq_companies_report_email_token;
        """
    )
    op.execute(
        """
        ALTER TABLE companies DROP COLUMN IF EXISTS report_email_token;
        """
    )
