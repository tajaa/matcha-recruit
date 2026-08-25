"""Track verified credential expiry for schedule eligibility.

Revision ID: empsched09
Revises: huumesched01
"""

from alembic import op


revision = "empsched09"
down_revision = "huumesched01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE employee_credential_requirements
        ADD COLUMN IF NOT EXISTS expires_at DATE
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_ecr_schedule_validity
        ON employee_credential_requirements(employee_id, status, expires_at)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_ecr_schedule_validity")
    op.execute("ALTER TABLE employee_credential_requirements DROP COLUMN IF EXISTS expires_at")
