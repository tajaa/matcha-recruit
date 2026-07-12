"""add employee-schedule tables — shifts, assignments, templates, requests

Employee scheduling as a paid, per-company feature (flag `employee_schedule`).
Builds on the existing roster (`employees`, keyed on org_id) and work sites
(`business_locations`, keyed on company_id). Five tables:

  - schedule_shift_templates: reusable shift definitions (role/location/time-of-
    day/staffing + a days-of-week mask) that generate concrete shifts for a date
    range in one call.
  - schedule_shifts: concrete dated shifts with a draft → published → cancelled
    lifecycle. `series_id` groups shifts generated from one template run so they
    can be managed as a set; `template_id` records provenance.
  - schedule_shift_assignments: which employees are on a shift (a shift can carry
    up to `required_staff` assignees). Unique per (shift, employee).
  - schedule_requests: employee-initiated swap / drop / unavailability requests
    that an admin reviews (pending → approved/denied). Kept separate from the
    PTO/time_off subsystem so scheduling is self-contained.
  - schedule_audit_log: per-company audit trail for schedule mutations.

All tenant-scoped by company_id (FK → companies, ON DELETE CASCADE), mirroring
the other feature tables. Idempotent DDL; additive only.

Revision ID: empsched01
Revises: ita01
Create Date: 2026-07-12
"""

from alembic import op


revision = "empsched01"
down_revision = "ita01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS schedule_shift_templates (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            name VARCHAR(150) NOT NULL,
            role VARCHAR(150),
            department VARCHAR(100),
            location_id UUID REFERENCES business_locations(id) ON DELETE SET NULL,
            start_time TIME NOT NULL,
            end_time TIME NOT NULL,
            break_minutes INTEGER NOT NULL DEFAULT 0,
            required_staff INTEGER NOT NULL DEFAULT 1,
            -- weekday mask, ISO-ish 0=Sunday .. 6=Saturday, e.g. [1,2,3,4,5]
            days_of_week JSONB NOT NULL DEFAULT '[]',
            color VARCHAR(20),
            notes TEXT,
            created_by UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_schedule_shift_templates_company "
        "ON schedule_shift_templates(company_id);"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS schedule_shifts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            location_id UUID REFERENCES business_locations(id) ON DELETE SET NULL,
            template_id UUID REFERENCES schedule_shift_templates(id) ON DELETE SET NULL,
            series_id UUID,
            role VARCHAR(150),
            department VARCHAR(100),
            starts_at TIMESTAMPTZ NOT NULL,
            ends_at TIMESTAMPTZ NOT NULL,
            break_minutes INTEGER NOT NULL DEFAULT 0,
            required_staff INTEGER NOT NULL DEFAULT 1,
            color VARCHAR(20),
            notes TEXT,
            status VARCHAR(20) NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft', 'published', 'cancelled')),
            published_at TIMESTAMPTZ,
            created_by UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_schedule_shifts_company_start "
        "ON schedule_shifts(company_id, starts_at);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_schedule_shifts_series "
        "ON schedule_shifts(series_id);"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS schedule_shift_assignments (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            shift_id UUID NOT NULL REFERENCES schedule_shifts(id) ON DELETE CASCADE,
            employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            status VARCHAR(20) NOT NULL DEFAULT 'assigned'
                CHECK (status IN ('assigned', 'confirmed', 'declined')),
            assigned_by UUID,
            assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (shift_id, employee_id)
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_schedule_assignments_shift "
        "ON schedule_shift_assignments(shift_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_schedule_assignments_employee "
        "ON schedule_shift_assignments(employee_id);"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS schedule_requests (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            request_type VARCHAR(20) NOT NULL
                CHECK (request_type IN ('swap', 'drop', 'unavailable')),
            shift_id UUID REFERENCES schedule_shifts(id) ON DELETE CASCADE,
            target_employee_id UUID REFERENCES employees(id) ON DELETE SET NULL,
            unavailable_start DATE,
            unavailable_end DATE,
            reason TEXT,
            status VARCHAR(20) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'approved', 'denied', 'cancelled')),
            reviewed_by UUID,
            reviewed_at TIMESTAMPTZ,
            review_notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_schedule_requests_company_status "
        "ON schedule_requests(company_id, status);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_schedule_requests_employee "
        "ON schedule_requests(employee_id);"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS schedule_audit_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL,
            entity_type VARCHAR(40) NOT NULL,
            entity_id UUID,
            actor_user_id UUID,
            action VARCHAR(60) NOT NULL,
            details JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_schedule_audit_company "
        "ON schedule_audit_log(company_id, created_at DESC);"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS schedule_audit_log")
    op.execute("DROP TABLE IF EXISTS schedule_requests")
    op.execute("DROP TABLE IF EXISTS schedule_shift_assignments")
    op.execute("DROP TABLE IF EXISTS schedule_shifts")
    op.execute("DROP TABLE IF EXISTS schedule_shift_templates")
