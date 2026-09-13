"""Add schedule_jobs.default_hourly_rate — the rate an OPEN seat costs at.

Scheduled labor cost prices assigned shifts from `employees.pay_rate`. An
unfilled seat has no employee, so without a per-job rate a draft week's total
silently understates the finished schedule — the projection is worth least
exactly when the week is least full. This column is what an open Barista seat
costs; NULL means "not set", and the cost engine reports those seats as
unpriced rather than free (same rule as an employee with no pay_rate).

Additive and nullable: every existing job keeps working, unpriced.

Revision ID: laborcost01
Revises: empsched24
"""

from alembic import op

revision = "laborcost01"
down_revision = "empsched24"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE schedule_jobs "
        "ADD COLUMN IF NOT EXISTS default_hourly_rate DECIMAL(12, 2)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE schedule_jobs DROP COLUMN IF EXISTS default_hourly_rate")
