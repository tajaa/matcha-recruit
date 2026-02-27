"""add priority category to onboarding tables

Revision ID: a1b2c3d4e5f7
Revises: a1b2c3d4e5f8
Create Date: 2026-02-26
"""

from alembic import op


revision = "a1b2c3d4e5f7"
down_revision = "a1b2c3d4e5f8"
branch_labels = None
depends_on = None


def upgrade():
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


def downgrade():
    op.execute("ALTER TABLE onboarding_tasks DROP CONSTRAINT IF EXISTS check_category")
    op.execute(
        """
        ALTER TABLE onboarding_tasks ADD CONSTRAINT check_category CHECK (
            category IN ('documents', 'equipment', 'training', 'admin', 'return_to_work')
        )
        """
    )
    op.execute("ALTER TABLE employee_onboarding_tasks DROP CONSTRAINT IF EXISTS check_onboarding_category")
    op.execute(
        """
        ALTER TABLE employee_onboarding_tasks ADD CONSTRAINT check_onboarding_category CHECK (
            category IN ('documents', 'equipment', 'training', 'admin', 'return_to_work')
        )
        """
    )
