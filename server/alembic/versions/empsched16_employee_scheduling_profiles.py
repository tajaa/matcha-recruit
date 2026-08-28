"""Add explicit employee scheduling inputs and qualified-job metadata.

Revision ID: empsched16
Revises: empsched15
"""
from alembic import op


revision = "empsched16"
down_revision = "empsched15"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE schedule_job_employees
            ADD COLUMN is_primary BOOLEAN NOT NULL DEFAULT FALSE,
            ADD COLUMN qualification_status VARCHAR(20) NOT NULL DEFAULT 'active',
            ADD COLUMN qualified_from DATE,
            ADD COLUMN qualified_until DATE,
            ADD COLUMN notes TEXT,
            ADD CONSTRAINT schedule_job_employees_status_check
                CHECK (qualification_status IN ('active', 'training', 'suspended')),
            ADD CONSTRAINT schedule_job_employees_dates_check
                CHECK (qualified_until IS NULL OR qualified_from IS NULL OR qualified_until >= qualified_from)
    """)
    op.execute("""
        CREATE UNIQUE INDEX uniq_schedule_job_employee_primary
            ON schedule_job_employees(company_id, employee_id)
            WHERE is_primary AND qualification_status = 'active'
    """)
    op.execute("""
        CREATE TABLE employee_schedule_profiles (
            employee_id UUID PRIMARY KEY REFERENCES employees(id) ON DELETE CASCADE,
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            availability_state VARCHAR(24) NOT NULL DEFAULT 'unconfirmed',
            availability_confirmed_at TIMESTAMPTZ,
            availability_confirmed_by UUID REFERENCES users(id) ON DELETE SET NULL,
            min_weekly_minutes INTEGER CHECK (min_weekly_minutes BETWEEN 0 AND 10080),
            target_weekly_minutes INTEGER CHECK (target_weekly_minutes BETWEEN 0 AND 10080),
            max_weekly_minutes INTEGER CHECK (max_weekly_minutes BETWEEN 0 AND 10080),
            max_consecutive_days SMALLINT,
            allow_overtime BOOLEAN NOT NULL DEFAULT FALSE,
            prefer_extra_hours BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_employee_schedule_profile_availability_state
                CHECK (availability_state IN ('unconfirmed', 'always_available', 'windows')),
            CONSTRAINT ck_employee_schedule_profile_weekly_minutes
                CHECK (
                    (min_weekly_minutes IS NULL OR target_weekly_minutes IS NULL OR min_weekly_minutes <= target_weekly_minutes) AND
                    (target_weekly_minutes IS NULL OR max_weekly_minutes IS NULL OR target_weekly_minutes <= max_weekly_minutes) AND
                    (min_weekly_minutes IS NULL OR max_weekly_minutes IS NULL OR min_weekly_minutes <= max_weekly_minutes)
                ),
            CONSTRAINT ck_employee_schedule_profile_max_consecutive_days
                CHECK (max_consecutive_days IS NULL OR max_consecutive_days BETWEEN 1 AND 14),
            UNIQUE (company_id, employee_id)
        )
    """)
    op.execute("""
        CREATE INDEX idx_employee_schedule_profiles_company
            ON employee_schedule_profiles(company_id)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS employee_schedule_profiles")
    op.execute("DROP INDEX IF EXISTS uniq_schedule_job_employee_primary")
    op.execute("""
        ALTER TABLE schedule_job_employees
            DROP CONSTRAINT IF EXISTS schedule_job_employees_dates_check,
            DROP CONSTRAINT IF EXISTS schedule_job_employees_status_check,
            DROP COLUMN IF EXISTS notes,
            DROP COLUMN IF EXISTS qualified_until,
            DROP COLUMN IF EXISTS qualified_from,
            DROP COLUMN IF EXISTS qualification_status,
            DROP COLUMN IF EXISTS is_primary
    """)
