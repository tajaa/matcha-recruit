"""Recurring weekly employee availability for the scheduling module.

Semantics (enforced by services/scheduling/schedule_rules.availability_violations):
- employee with ZERO rows = fully available (back-compat: nothing changes
  for existing tenants until someone logs availability);
- employee with >=1 row: a weekday with no rows is unavailable; a weekday
  with rows is available only inside those windows.

NOTE: the alembic history on this branch has multiple leaves; down_revision
is set to `offthread01`, a verified leaf at authoring time (no other
migration's down_revision points to it as of 2026-08-02). Confirm the
correct head for your environment before `alembic upgrade` if time has
passed.

Revision ID: empavail01
Revises: offthread01
Create Date: 2026-08-02
"""

from alembic import op

revision = "empavail01"
down_revision = "offthread01"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS schedule_employee_availability (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
            weekday SMALLINT NOT NULL CHECK (weekday BETWEEN 0 AND 6),
            start_time TIME NOT NULL,
            end_time TIME NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW(),
            CHECK (end_time > start_time)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_sched_avail_employee "
        "ON schedule_employee_availability(employee_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_sched_avail_company "
        "ON schedule_employee_availability(company_id)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS schedule_employee_availability")
