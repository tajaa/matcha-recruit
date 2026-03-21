"""add credentials category to onboarding + document_type column

Revision ID: zk8l9m0n1o2p
Revises: zt8u9v0w1x2y
Create Date: 2026-03-20
"""
from alembic import op


revision = "zk8l9m0n1o2p"
down_revision = "zt8u9v0w1x2y"
branch_labels = None
depends_on = None


def upgrade():
    # Add 'credentials' to category CHECK constraints
    op.execute("ALTER TABLE onboarding_tasks DROP CONSTRAINT IF EXISTS check_category")
    op.execute(
        """
        ALTER TABLE onboarding_tasks ADD CONSTRAINT check_category CHECK (
            category IN ('documents', 'equipment', 'training', 'admin', 'return_to_work', 'priority', 'credentials')
        )
        """
    )
    op.execute("ALTER TABLE employee_onboarding_tasks DROP CONSTRAINT IF EXISTS check_onboarding_category")
    op.execute(
        """
        ALTER TABLE employee_onboarding_tasks ADD CONSTRAINT check_onboarding_category CHECK (
            category IN ('documents', 'equipment', 'training', 'admin', 'return_to_work', 'priority', 'credentials')
        )
        """
    )

    # Add document_type column for linking credential tasks to credential document types
    op.execute(
        "ALTER TABLE employee_onboarding_tasks ADD COLUMN IF NOT EXISTS document_type VARCHAR(50)"
    )


def downgrade():
    op.execute("ALTER TABLE employee_onboarding_tasks DROP COLUMN IF EXISTS document_type")

    op.execute("ALTER TABLE onboarding_tasks DROP CONSTRAINT IF EXISTS check_category")
    op.execute(
        """
        ALTER TABLE onboarding_tasks ADD CONSTRAINT check_category CHECK (
            category IN ('documents', 'equipment', 'training', 'admin', 'return_to_work', 'priority')
        )
        """
    )
    op.execute("ALTER TABLE employee_onboarding_tasks DROP CONSTRAINT IF EXISTS check_onboarding_category")
    op.execute(
        """
        ALTER TABLE employee_onboarding_tasks ADD CONSTRAINT check_onboarding_category CHECK (
            category IN ('documents', 'equipment', 'training', 'admin', 'return_to_work', 'priority')
        )
        """
    )
