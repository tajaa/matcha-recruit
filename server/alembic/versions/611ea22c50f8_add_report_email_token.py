"""add report_email_token to companies

Revision ID: 611ea22c50f8
Revises: b4c5d6e7f8a9
Create Date: 2026-03-03
"""

from alembic import op


revision = "611ea22c50f8"
down_revision = "b4c5d6e7f8a9"
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
        CREATE UNIQUE INDEX IF NOT EXISTS uq_companies_report_email_token
        ON companies (report_email_token);
        """
    )
    op.execute(
        """
        ALTER TABLE companies
        ADD COLUMN IF NOT EXISTS report_token_used_at TIMESTAMPTZ;
        """
    )


def downgrade():
    op.execute(
        """
        ALTER TABLE companies DROP COLUMN IF EXISTS report_token_used_at;
        """
    )
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
