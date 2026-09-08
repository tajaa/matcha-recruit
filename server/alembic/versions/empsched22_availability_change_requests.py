"""Employee availability changes become manager-reviewed requests.

An employee editing their own recurring availability used to be an immediate
write: `PUT /v1/portal/me/schedule/availability` replaced the stored windows,
and the very next assignment decision — including one inside an already
published week — was made against the new pattern with nobody having agreed to
it. This turns that edit into a request the manager approves, and gives the
approved change a date it starts applying from.

The request rides on `schedule_requests` rather than a table of its own: the
portal's "my requests" list, the withdraw/cancel endpoints, the manager review
queue and its audit trail already exist there and would otherwise all need a
second, parallel implementation. Three additive columns carry what a shift
request has no place for:

- `proposed_availability` (JSONB) — the whole proposed set, resolved at submit
  time to an explicit state so approval is never re-interpreting legacy
  "empty list means always available" semantics:
      {"availability_state": "windows",
       "windows": [{"weekday": 1, "start_time": "09:00", "end_time": "17:00"}]}
- `availability_effective_on` (DATE) — the date the employee asked it to start.
- `availability_applied_at` — when an approved change actually landed in
  `schedule_employee_availability`. NULL on an approved future-dated row is
  precisely the "still owed" state the promotion sweep looks for, which is why
  it is a timestamp and not a boolean.

The partial unique index keeps an employee to one open availability request:
two pending proposals a manager approves in either order is a coin flip over
which availability the employee ends up with.

Revision ID: empsched22
Revises: schedloc04
Create Date: 2026-09-08
"""

from alembic import op


revision = "empsched22"
down_revision = "schedloc04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE schedule_requests
            ADD COLUMN IF NOT EXISTS proposed_availability JSONB,
            ADD COLUMN IF NOT EXISTS availability_effective_on DATE,
            ADD COLUMN IF NOT EXISTS availability_applied_at TIMESTAMPTZ
        """
    )
    op.execute(
        "ALTER TABLE schedule_requests "
        "DROP CONSTRAINT IF EXISTS schedule_requests_request_type_check"
    )
    op.execute(
        "ALTER TABLE schedule_requests ADD CONSTRAINT schedule_requests_request_type_check "
        "CHECK (request_type IN ('swap', 'drop', 'pickup', 'unavailable', 'availability'))"
    )
    # An availability request must carry both halves of its proposal, and only
    # an availability request may carry either — a shape a route bug cannot
    # quietly violate.
    op.execute(
        """
        ALTER TABLE schedule_requests ADD CONSTRAINT schedule_requests_availability_shape_check
        CHECK (
            CASE WHEN request_type = 'availability'
                 THEN proposed_availability IS NOT NULL
                      AND availability_effective_on IS NOT NULL
                 ELSE proposed_availability IS NULL
                      AND availability_effective_on IS NULL
                      AND availability_applied_at IS NULL
            END
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_schedule_requests_open_availability
        ON schedule_requests (employee_id)
        WHERE request_type = 'availability'
          AND status IN ('pending', 'awaiting_manager')
        """
    )
    # Drives the promotion sweep: approved, dated, not yet written through.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_schedule_requests_availability_due
        ON schedule_requests (company_id, availability_effective_on)
        WHERE request_type = 'availability'
          AND status = 'approved'
          AND availability_applied_at IS NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_schedule_requests_availability_due")
    op.execute("DROP INDEX IF EXISTS uq_schedule_requests_open_availability")
    op.execute(
        "ALTER TABLE schedule_requests "
        "DROP CONSTRAINT IF EXISTS schedule_requests_availability_shape_check"
    )
    # The rows must go before the old constraint is restored, or the ALTER
    # fails validating the very rows this revision made legal.
    op.execute("DELETE FROM schedule_requests WHERE request_type = 'availability'")
    op.execute(
        "ALTER TABLE schedule_requests "
        "DROP CONSTRAINT IF EXISTS schedule_requests_request_type_check"
    )
    op.execute(
        "ALTER TABLE schedule_requests ADD CONSTRAINT schedule_requests_request_type_check "
        "CHECK (request_type IN ('swap', 'drop', 'pickup', 'unavailable'))"
    )
    op.execute(
        """
        ALTER TABLE schedule_requests
            DROP COLUMN IF EXISTS availability_applied_at,
            DROP COLUMN IF EXISTS availability_effective_on,
            DROP COLUMN IF EXISTS proposed_availability
        """
    )
