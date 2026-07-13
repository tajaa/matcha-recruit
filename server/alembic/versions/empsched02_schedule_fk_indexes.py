"""Index the employee-schedule FKs that cascade on delete.

empsched01 indexed the read paths (company+start, assignments by shift/employee)
but not the two FKs Postgres has to scan on a parent delete:

* schedule_requests.shift_id  — ON DELETE CASCADE. Deleting a shift (a one-click
  UI action) seq-scans schedule_requests to find rows to cascade.
* schedule_shifts.template_id — ON DELETE SET NULL. Deleting a template
  seq-scans every shift the company has ever had.

The requests index also serves the swap-review LEFT JOIN on r.shift_id.

Revision ID: empsched02
Revises: empsched01
"""

from alembic import op

revision = "empsched02"
down_revision = "empsched01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_schedule_requests_shift "
        "ON schedule_requests(shift_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_schedule_shifts_template "
        "ON schedule_shifts(template_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_schedule_shifts_template")
    op.execute("DROP INDEX IF EXISTS idx_schedule_requests_shift")
