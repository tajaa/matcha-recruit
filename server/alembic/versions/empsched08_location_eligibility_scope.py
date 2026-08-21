"""Scope eligibility cases and recipients to locations.

Revision ID: empsched08
Revises: empsched07
"""
from alembic import op

revision = "empsched08"
down_revision = "empsched07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""ALTER TABLE employee_work_permits
        ADD COLUMN IF NOT EXISTS location_id UUID REFERENCES business_locations(id),
        ADD COLUMN IF NOT EXISTS issued_at DATE,
        ADD COLUMN IF NOT EXISTS status VARCHAR(30) NOT NULL DEFAULT 'active',
        ADD COLUMN IF NOT EXISTS confirmed_on_file BOOLEAN NOT NULL DEFAULT false,
        ADD COLUMN IF NOT EXISTS confirmed_by UUID REFERENCES users(id),
        ADD COLUMN IF NOT EXISTS confirmed_at TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS supersedes_id UUID REFERENCES employee_work_permits(id)""")
    op.execute("""ALTER TABLE schedule_eligibility_cases
        ADD COLUMN IF NOT EXISTS next_escalation_at TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS last_escalated_at TIMESTAMPTZ,
        ADD COLUMN IF NOT EXISTS escalation_count INTEGER NOT NULL DEFAULT 0,
        ADD COLUMN IF NOT EXISTS resolution_reason VARCHAR(60)""")
    op.execute("""CREATE TABLE IF NOT EXISTS schedule_location_notification_recipients (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
        location_id UUID NOT NULL REFERENCES business_locations(id) ON DELETE CASCADE,
        email VARCHAR(320) NOT NULL, display_name VARCHAR(255),
        recipient_type VARCHAR(30) NOT NULL CHECK (recipient_type IN ('operational_mailbox','additional_manager')),
        is_active BOOLEAN NOT NULL DEFAULT true,
        created_by UUID NOT NULL REFERENCES users(id),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")
    op.execute("""CREATE UNIQUE INDEX IF NOT EXISTS idx_schedule_location_recipient_active
        ON schedule_location_notification_recipients(location_id, LOWER(email)) WHERE is_active""")
    op.execute("DROP INDEX IF EXISTS idx_schedule_eligibility_open")
    op.execute("""CREATE UNIQUE INDEX IF NOT EXISTS idx_schedule_eligibility_open_by_location
        ON schedule_eligibility_cases(company_id, employee_id, location_id, requirement_type, requirement_id, expires_at)
        WHERE status IN ('warning_open','removal_requested','removal_confirmed','keep_acknowledged')""")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_schedule_eligibility_open_by_location")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_schedule_eligibility_open ON schedule_eligibility_cases(company_id, employee_id, requirement_type, requirement_id, expires_at) WHERE status IN ('warning_open','removal_requested','removal_confirmed','removal_completed','keep_acknowledged')")
    op.execute("DROP INDEX IF EXISTS idx_schedule_location_recipient_active")
    op.execute("DROP TABLE IF EXISTS schedule_location_notification_recipients")
    op.execute("""ALTER TABLE employee_work_permits
        DROP COLUMN IF EXISTS supersedes_id, DROP COLUMN IF EXISTS confirmed_at,
        DROP COLUMN IF EXISTS confirmed_by, DROP COLUMN IF EXISTS confirmed_on_file,
        DROP COLUMN IF EXISTS status, DROP COLUMN IF EXISTS issued_at,
        DROP COLUMN IF EXISTS location_id""")
    op.execute("ALTER TABLE schedule_eligibility_cases DROP COLUMN IF EXISTS resolution_reason, DROP COLUMN IF EXISTS escalation_count, DROP COLUMN IF EXISTS last_escalated_at, DROP COLUMN IF EXISTS next_escalation_at")
