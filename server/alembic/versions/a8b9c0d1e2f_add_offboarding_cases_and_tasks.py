"""add offboarding cases and tasks

Revision ID: a8b9c0d1e2f
Revises: z7a8b9c0d1e
Create Date: 2026-02-18
"""

from alembic import op


revision = "a8b9c0d1e2f"
down_revision = "z7a8b9c0d1e"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS offboarding_cases (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            status VARCHAR(20) NOT NULL DEFAULT 'in_progress'
                CHECK (status IN ('in_progress', 'completed', 'cancelled')),
            reason TEXT,
            is_voluntary BOOLEAN NOT NULL DEFAULT true,
            last_day DATE NOT NULL,
            started_at TIMESTAMP NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMP,
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_offboarding_cases_org_id
            ON offboarding_cases(org_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_offboarding_cases_employee_id
            ON offboarding_cases(employee_id)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_offboarding_cases_employee_active_unique
            ON offboarding_cases(employee_id)
            WHERE status = 'in_progress'
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS offboarding_tasks (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            case_id UUID NOT NULL REFERENCES offboarding_cases(id) ON DELETE CASCADE,
            employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            title VARCHAR(500) NOT NULL,
            description TEXT,
            category VARCHAR(50) NOT NULL DEFAULT 'other'
                CHECK (
                    category IN (
                        'access_revocation',
                        'equipment_return',
                        'knowledge_transfer',
                        'exit_interview',
                        'final_payroll',
                        'benefits_termination',
                        'other'
                    )
                ),
            assignee_type VARCHAR(20) NOT NULL DEFAULT 'hr'
                CHECK (assignee_type IN ('hr', 'it', 'manager', 'employee', 'payroll')),
            due_date DATE,
            status VARCHAR(20) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'completed', 'skipped')),
            completed_at TIMESTAMP,
            completed_by UUID REFERENCES users(id) ON DELETE SET NULL,
            notes TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_offboarding_tasks_case_id
            ON offboarding_tasks(case_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_offboarding_tasks_employee_id
            ON offboarding_tasks(employee_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_offboarding_tasks_status
            ON offboarding_tasks(status)
        """
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_offboarding_tasks_status")
    op.execute("DROP INDEX IF EXISTS idx_offboarding_tasks_employee_id")
    op.execute("DROP INDEX IF EXISTS idx_offboarding_tasks_case_id")
    op.execute("DROP TABLE IF EXISTS offboarding_tasks")

    op.execute("DROP INDEX IF EXISTS idx_offboarding_cases_employee_active_unique")
    op.execute("DROP INDEX IF EXISTS idx_offboarding_cases_employee_id")
    op.execute("DROP INDEX IF EXISTS idx_offboarding_cases_org_id")
    op.execute("DROP TABLE IF EXISTS offboarding_cases")
