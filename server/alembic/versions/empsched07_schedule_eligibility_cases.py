"""Add manager-mediated schedule eligibility cases.

Revision ID: empsched07
Revises: empsched06
"""
from alembic import op

revision = "empsched07"
down_revision = "empsched06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE credential_requirement_templates
            ADD COLUMN IF NOT EXISTS schedule_blocking BOOLEAN NOT NULL DEFAULT false,
            ADD COLUMN IF NOT EXISTS warning_days INTEGER NOT NULL DEFAULT 14,
            ADD COLUMN IF NOT EXISTS legal_basis JSONB NOT NULL DEFAULT '{}'::jsonb
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS employee_work_permits (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            expires_at DATE NOT NULL,
            schedule_blocking BOOLEAN NOT NULL DEFAULT true,
            legal_basis JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS schedule_eligibility_cases (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            location_id UUID REFERENCES business_locations(id) ON DELETE SET NULL,
            requirement_type VARCHAR(40) NOT NULL CHECK (requirement_type IN ('credential','minor_work_permit')),
            requirement_id UUID,
            blocking_reason_code VARCHAR(100) NOT NULL,
            status VARCHAR(40) NOT NULL CHECK (status IN ('warning_open','removal_requested','removal_confirmed','removal_completed','keep_acknowledged','resolved')),
            detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at DATE,
            legal_basis JSONB NOT NULL DEFAULT '{}'::jsonb,
            manager_decision_by UUID REFERENCES users(id), manager_decision_at TIMESTAMPTZ,
            manager_acknowledged_by UUID REFERENCES users(id), manager_acknowledged_at TIMESTAMPTZ,
            acknowledgement_note TEXT, resolved_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS schedule_eligibility_case_assignments (
            case_id UUID NOT NULL REFERENCES schedule_eligibility_cases(id) ON DELETE CASCADE,
            shift_id UUID NOT NULL REFERENCES schedule_shifts(id) ON DELETE CASCADE,
            employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            shift_starts_at TIMESTAMPTZ NOT NULL,
            action_status VARCHAR(30) NOT NULL DEFAULT 'pending' CHECK (action_status IN ('pending','removed','retained','no_longer_assigned')),
            acted_at TIMESTAMPTZ,
            PRIMARY KEY (case_id, shift_id, employee_id)
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_schedule_eligibility_open
        ON schedule_eligibility_cases(company_id, employee_id, requirement_type, requirement_id, expires_at)
        WHERE status IN ('warning_open','removal_requested','removal_confirmed','keep_acknowledged')
    """)
    op.execute("""
        INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
        VALUES ('schedule_eligibility', 'Schedule eligibility', 'Opens manager decisions for expired schedule-blocking credentials and work permits.', false, 200)
        ON CONFLICT (task_key) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_schedule_eligibility_open")
    op.execute("DROP TABLE IF EXISTS schedule_eligibility_case_assignments")
    op.execute("DROP TABLE IF EXISTS schedule_eligibility_cases")
    op.execute("DROP TABLE IF EXISTS employee_work_permits")
    op.execute("ALTER TABLE credential_requirement_templates DROP COLUMN IF EXISTS legal_basis, DROP COLUMN IF EXISTS warning_days, DROP COLUMN IF EXISTS schedule_blocking")
    op.execute("DELETE FROM scheduler_settings WHERE task_key = 'schedule_eligibility'")
