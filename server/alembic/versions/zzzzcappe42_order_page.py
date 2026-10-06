"""Cappe orders — pay after approval, and tell the buyer when it ships.

`cappe_orders`
  * `checkout_opened_at` — when the order's CURRENT Stripe payment page was
    opened. An order approved days after it was placed opens its page then,
    so "abandoned" is measured from here, not from `created_at` (the reaper
    would otherwise close a page the buyer had just opened).
  * `pay_by` — set when the owner accepts an order that is paid by card: the
    buyer has until then to pay from the link they are emailed, after which
    the order is released and its stock returned.
  * `shipped_notified_at` — when the buyer was emailed that the order shipped
    (or is ready). Shipping used to be an app push only; guests heard nothing.

Additive + idempotent; NULL on existing rows means "not recorded".

Revision ID: zzzzcappe42
Revises: zzzzcappe41
"""
from alembic import op

revision = "zzzzcappe42"
down_revision = "zzzzcappe41"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE cappe_orders
            ADD COLUMN IF NOT EXISTS checkout_opened_at  TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS pay_by              TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS shipped_notified_at TIMESTAMPTZ
        """
    )
    # The reaper's sweep for approved orders nobody paid for.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_orders_pay_by "
        "ON cappe_orders (pay_by) WHERE status = 'pending' AND pay_by IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_cappe_orders_pay_by")
    op.execute(
        """
        ALTER TABLE cappe_orders
            DROP COLUMN IF EXISTS shipped_notified_at,
            DROP COLUMN IF EXISTS pay_by,
            DROP COLUMN IF EXISTS checkout_opened_at
        """
    )
