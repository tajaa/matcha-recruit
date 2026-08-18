"""add schedule jobs — tie a shift/block to a job, gate assignment on skill

Real usage: a movie theatre schedules Box Office, Concessions, and Ushers —
distinct jobs, and not every employee is trained in every one. Adds
schedule_jobs (a named job, company- or location-scoped) and
schedule_job_employees (the qualified-employee list per job), then points
schedule_shifts and schedule_shift_templates at a job via a nullable job_id.

NULL job_id = ungated (every existing row, and any new shift with no job
picked) — assignment is unrestricted, same as today. NOT NULL = only
employees on that job's qualified list should be assigned (enforced,
forceable, in the route layer — not by this migration).

Revision ID: empsched04
Revises: empsched03
Create Date: 2026-08-18
"""

from alembic import op

revision = "empsched04"
down_revision = "empsched03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS schedule_jobs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            location_id UUID REFERENCES business_locations(id) ON DELETE SET NULL,
            name VARCHAR(150) NOT NULL,
            color VARCHAR(20),
            notes TEXT,
            created_by UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_schedule_jobs_company ON schedule_jobs(company_id);"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS schedule_job_employees (
            job_id UUID NOT NULL REFERENCES schedule_jobs(id) ON DELETE CASCADE,
            employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            created_by UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (job_id, employee_id)
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_schedule_job_employees_employee "
        "ON schedule_job_employees(employee_id);"
    )

    for table in ("schedule_shifts", "schedule_shift_templates"):
        op.execute(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS job_id UUID "
            f"REFERENCES schedule_jobs(id) ON DELETE SET NULL"
        )
        op.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{table}_job ON {table}(job_id);"
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_schedule_shift_templates_job")
    op.execute("ALTER TABLE schedule_shift_templates DROP COLUMN IF EXISTS job_id")
    op.execute("DROP INDEX IF EXISTS idx_schedule_shifts_job")
    op.execute("ALTER TABLE schedule_shifts DROP COLUMN IF EXISTS job_id")
    op.execute("DROP INDEX IF EXISTS idx_schedule_job_employees_employee")
    op.execute("DROP TABLE IF EXISTS schedule_job_employees")
    op.execute("DROP INDEX IF EXISTS idx_schedule_jobs_company")
    op.execute("DROP TABLE IF EXISTS schedule_jobs")
