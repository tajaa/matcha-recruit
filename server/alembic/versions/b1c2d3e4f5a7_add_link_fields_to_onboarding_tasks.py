"""add link fields to onboarding tasks for priority attachments

Revision ID: b1c2d3e4f5a7
Revises: a1b2c3d4e5f7
Create Date: 2026-02-26
"""

from alembic import op


revision = "b1c2d3e4f5a7"
down_revision = "a1b2c3d4e5f7"
branch_labels = None
depends_on = None


def upgrade():
    # Add link fields to template table
    op.execute("ALTER TABLE onboarding_tasks ADD COLUMN IF NOT EXISTS link_type VARCHAR(30)")
    op.execute("ALTER TABLE onboarding_tasks ADD COLUMN IF NOT EXISTS link_id UUID")
    op.execute("ALTER TABLE onboarding_tasks ADD COLUMN IF NOT EXISTS link_label TEXT")
    op.execute("ALTER TABLE onboarding_tasks ADD COLUMN IF NOT EXISTS link_url TEXT")

    # Propagate to per-employee assigned tasks
    op.execute("ALTER TABLE employee_onboarding_tasks ADD COLUMN IF NOT EXISTS link_type VARCHAR(30)")
    op.execute("ALTER TABLE employee_onboarding_tasks ADD COLUMN IF NOT EXISTS link_id UUID")
    op.execute("ALTER TABLE employee_onboarding_tasks ADD COLUMN IF NOT EXISTS link_label TEXT")
    op.execute("ALTER TABLE employee_onboarding_tasks ADD COLUMN IF NOT EXISTS link_url TEXT")


def downgrade():
    op.execute("ALTER TABLE onboarding_tasks DROP COLUMN IF EXISTS link_type")
    op.execute("ALTER TABLE onboarding_tasks DROP COLUMN IF EXISTS link_id")
    op.execute("ALTER TABLE onboarding_tasks DROP COLUMN IF EXISTS link_label")
    op.execute("ALTER TABLE onboarding_tasks DROP COLUMN IF EXISTS link_url")
    op.execute("ALTER TABLE employee_onboarding_tasks DROP COLUMN IF EXISTS link_type")
    op.execute("ALTER TABLE employee_onboarding_tasks DROP COLUMN IF EXISTS link_id")
    op.execute("ALTER TABLE employee_onboarding_tasks DROP COLUMN IF EXISTS link_label")
    op.execute("ALTER TABLE employee_onboarding_tasks DROP COLUMN IF EXISTS link_url")
