"""Cappe booking integrity — find a booking's order without a table scan.

Cancelling, declining or rescheduling a booking now looks up the shop order it
was bought through, so the owner is told when the booking's money has not been
refunded, and the bookings list shows each booking's order. Both look order
lines up by `booking_id`, which nothing indexed.

Partial: almost every order line is not a booking.

Additive + idempotent. `CREATE INDEX` (not CONCURRENTLY): migrations run in a
transaction, and `cappe_order_items` is small.

Revision ID: zzzzcappe40
Revises: zzzzcappe39
"""
from alembic import op

revision = "zzzzcappe40"
down_revision = "zzzzcappe39"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_order_items_booking "
        "ON cappe_order_items (booking_id) WHERE booking_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_cappe_order_items_booking")
