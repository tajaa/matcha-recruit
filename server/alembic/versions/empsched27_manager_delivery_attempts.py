"""Dead-letter manager request notifications; one open pickup/swap per shift.

Manager-ready email deliveries deleted their claim row on a failed send, so a
permanently bouncing reviewer address was retried by every sweep and could
fill the sweep's LIMIT, starving newer requests. They now count attempts and
park at a cap, like the employee delivery table (empsched26).

Pickup and swap offers had no duplicate guard, so a double tap created two
offers coworkers could accept. The partial unique indexes mirror empsched25's
claim/drop/unavailable ones, over the three statuses in which an offer is
still open. Existing duplicates are collapsed first (newest kept, older
cancelled) or the index build would fail.

Revision ID: empsched27
Revises: empsched26
"""

from alembic import op


revision = "empsched27"
down_revision = "empsched26"
branch_labels = None
depends_on = None


_OPEN = "('pending', 'awaiting_counterparty', 'awaiting_manager')"


def upgrade() -> None:
    op.execute("""
        ALTER TABLE schedule_request_notification_deliveries
            ADD COLUMN IF NOT EXISTS attempts INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS failed_at TIMESTAMPTZ
    """)
    for request_type in ("pickup", "swap"):
        # Set-based dedupe: keep the newest open offer per (employee, shift).
        op.execute(f"""
            WITH ranked AS (
                SELECT id, ROW_NUMBER() OVER (
                           PARTITION BY employee_id, shift_id
                           ORDER BY created_at DESC, id DESC
                       ) AS rn
                FROM schedule_requests
                WHERE request_type = '{request_type}' AND status IN {_OPEN}
            )
            UPDATE schedule_requests r
               SET status = 'cancelled', updated_at = NOW()
              FROM ranked
             WHERE r.id = ranked.id AND ranked.rn > 1
        """)
        op.execute(f"""
            CREATE UNIQUE INDEX uq_schedule_requests_open_{request_type}
            ON schedule_requests(employee_id, shift_id)
            WHERE request_type = '{request_type}' AND status IN {_OPEN}
        """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_schedule_requests_open_swap")
    op.execute("DROP INDEX IF EXISTS uq_schedule_requests_open_pickup")
    op.execute("""
        ALTER TABLE schedule_request_notification_deliveries
            DROP COLUMN IF EXISTS failed_at,
            DROP COLUMN IF EXISTS attempts
    """)
