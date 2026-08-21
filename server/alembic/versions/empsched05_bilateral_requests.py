"""Require bilateral confirmation before employee shift requests reach managers.

Offers and swaps are staged in ``awaiting_counterparty`` until the other
employee accepts them.  Only then do they enter the manager's approval queue;
the schedule remains unchanged throughout both stages.
"""

from alembic import op


revision = "empsched05"
down_revision = "schedwarn01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE schedule_requests ALTER COLUMN status TYPE VARCHAR(32)")
    # The original checks were generated without explicit names by PostgreSQL;
    # this is the conventional name for the table/column pair.
    op.execute(
        "ALTER TABLE schedule_requests DROP CONSTRAINT IF EXISTS "
        "schedule_requests_request_type_check"
    )
    op.execute(
        "ALTER TABLE schedule_requests ADD CONSTRAINT schedule_requests_request_type_check "
        "CHECK (request_type IN ('swap', 'drop', 'pickup', 'unavailable'))"
    )
    op.execute(
        "ALTER TABLE schedule_requests DROP CONSTRAINT IF EXISTS "
        "schedule_requests_status_check"
    )
    op.execute(
        "ALTER TABLE schedule_requests ADD CONSTRAINT schedule_requests_status_check "
        "CHECK (status IN ('pending', 'awaiting_counterparty', 'awaiting_manager', "
        "'approved', 'denied', 'cancelled'))"
    )
    op.execute(
        "ALTER TABLE schedule_requests ADD COLUMN IF NOT EXISTS counter_shift_id UUID "
        "REFERENCES schedule_shifts(id) ON DELETE SET NULL"
    )
    op.execute(
        "ALTER TABLE schedule_requests ADD COLUMN IF NOT EXISTS counterparty_confirmed_at "
        "TIMESTAMPTZ"
    )
    # Existing requests were already visible to managers and are therefore
    # treated as manager-ready legacy requests rather than being re-paired.
    op.execute(
        "UPDATE schedule_requests SET status = 'awaiting_manager' "
        "WHERE status = 'pending'"
    )
    op.execute(
        "UPDATE schedule_requests SET counterparty_confirmed_at = COALESCE(counterparty_confirmed_at, created_at) "
        "WHERE status = 'awaiting_manager' AND request_type = 'swap' "
        "AND counterparty_confirmed_at IS NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_schedule_requests_counterparty_status "
        "ON schedule_requests(company_id, target_employee_id, status)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_schedule_requests_counterparty_status")
    op.execute(
        "UPDATE schedule_requests SET status = 'pending' "
        "WHERE status IN ('awaiting_counterparty', 'awaiting_manager')"
    )
    op.execute("ALTER TABLE schedule_requests DROP COLUMN IF EXISTS counterparty_confirmed_at")
    op.execute("ALTER TABLE schedule_requests DROP COLUMN IF EXISTS counter_shift_id")
    op.execute(
        "ALTER TABLE schedule_requests DROP CONSTRAINT IF EXISTS "
        "schedule_requests_status_check"
    )
    op.execute(
        "ALTER TABLE schedule_requests ADD CONSTRAINT schedule_requests_status_check "
        "CHECK (status IN ('pending', 'approved', 'denied', 'cancelled'))"
    )
    op.execute(
        "ALTER TABLE schedule_requests DROP CONSTRAINT IF EXISTS "
        "schedule_requests_request_type_check"
    )
    op.execute(
        "ALTER TABLE schedule_requests ADD CONSTRAINT schedule_requests_request_type_check "
        "CHECK (request_type IN ('swap', 'drop', 'unavailable'))"
    )
    op.execute("ALTER TABLE schedule_requests ALTER COLUMN status TYPE VARCHAR(20)")
