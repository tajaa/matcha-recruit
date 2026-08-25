"""Add job-scoped credential requirements and grace periods.

Jobs already identify the work an employee may be assigned to.  This revision
lets a company attach credentials to that job, while retaining the existing
company-wide/template requirement path for backwards compatibility.
"""
from alembic import op


revision = "empsched12"
down_revision = "empsched11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE companies
            ADD COLUMN IF NOT EXISTS default_credential_grace_days INTEGER NOT NULL DEFAULT 7
            CHECK (default_credential_grace_days BETWEEN 0 AND 365)
    """)
    op.execute("""
        ALTER TABLE schedule_jobs
            ADD COLUMN IF NOT EXISTS credential_grace_days INTEGER
            CHECK (credential_grace_days BETWEEN 0 AND 365)
    """)
    # Existing rows were created by the jurisdiction/template system and must
    # retain their current company-wide scheduling behavior.
    op.execute("""
        ALTER TABLE employee_credential_requirements
            ADD COLUMN IF NOT EXISTS applies_company_wide BOOLEAN NOT NULL DEFAULT true
    """)
    op.execute("""
        ALTER TABLE schedule_eligibility_cases
            ADD COLUMN IF NOT EXISTS job_id UUID REFERENCES schedule_jobs(id) ON DELETE SET NULL
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS schedule_job_credential_requirements (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            job_id UUID NOT NULL REFERENCES schedule_jobs(id) ON DELETE CASCADE,
            credential_type_id UUID NOT NULL REFERENCES credential_types(id),
            is_required BOOLEAN NOT NULL DEFAULT true,
            schedule_blocking BOOLEAN NOT NULL DEFAULT true,
            effective_from DATE NOT NULL DEFAULT CURRENT_DATE,
            notes TEXT,
            created_by UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (job_id, credential_type_id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_schedule_job_credential_requirements_company_job
        ON schedule_job_credential_requirements(company_id, job_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_schedule_job_credential_requirements_type
        ON schedule_job_credential_requirements(credential_type_id)
    """)
    # Cases are per employee/location/credential/job.  NULLS NOT DISTINCT is
    # required for legacy job-less cases to remain idempotent too.
    op.execute("DROP INDEX IF EXISTS idx_schedule_eligibility_open_by_location")
    op.execute("""
        CREATE UNIQUE INDEX idx_schedule_eligibility_open_by_location
        ON schedule_eligibility_cases(
            company_id, employee_id, location_id, job_id, requirement_type,
            requirement_id, expires_at
        ) NULLS NOT DISTINCT
        WHERE status IN ('warning_open','removal_requested','removal_confirmed','keep_acknowledged')
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_schedule_eligibility_open_by_location")
    # Several active cases may differ only by job_id.  The empsched11 key
    # cannot represent that distinction, so retain the strongest active case
    # before restoring it rather than making rollback fail on real data.
    op.execute("""
        WITH ranked AS (
            SELECT id, ROW_NUMBER() OVER (
                PARTITION BY company_id, employee_id, location_id,
                             requirement_type, requirement_id, expires_at
                ORDER BY CASE status
                    WHEN 'removal_requested' THEN 0
                    WHEN 'removal_confirmed' THEN 1
                    WHEN 'keep_acknowledged' THEN 2
                    ELSE 3
                END, detected_at, id
            ) AS row_number
            FROM schedule_eligibility_cases
            WHERE status IN ('warning_open','removal_requested',
                             'removal_confirmed','keep_acknowledged')
        )
        UPDATE schedule_eligibility_cases c
           SET status='resolved', resolution_reason='job_case_rollback_deduplicated',
               resolved_at=NOW(), updated_at=NOW()
          FROM ranked r
         WHERE c.id=r.id AND r.row_number > 1
    """)
    op.execute("""
        CREATE UNIQUE INDEX idx_schedule_eligibility_open_by_location
        ON schedule_eligibility_cases(
            company_id, employee_id, location_id, requirement_type,
            requirement_id, expires_at
        ) NULLS NOT DISTINCT
        WHERE status IN ('warning_open','removal_requested','removal_confirmed','keep_acknowledged')
    """)
    op.execute("DROP INDEX IF EXISTS idx_schedule_job_credential_requirements_type")
    op.execute("DROP INDEX IF EXISTS idx_schedule_job_credential_requirements_company_job")
    op.execute("DROP TABLE IF EXISTS schedule_job_credential_requirements")
    op.execute("ALTER TABLE schedule_eligibility_cases DROP COLUMN IF EXISTS job_id")
    op.execute("ALTER TABLE employee_credential_requirements DROP COLUMN IF EXISTS applies_company_wide")
    op.execute("ALTER TABLE schedule_jobs DROP COLUMN IF EXISTS credential_grace_days")
    op.execute("ALTER TABLE companies DROP COLUMN IF EXISTS default_credential_grace_days")
