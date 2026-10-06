"""Cappe shopper subscriptions — remember which emails were sent.

Stripe retries a failed renewal invoice several times and repeats events, so
the shopper emails a subscription owes need a once-only record.

`cappe_shopper_subscriptions`
  * `failure_notified_invoice_id` — the invoice the shopper was last told
    failed. A new failing invoice notifies again; a retry of the same one
    does not.
  * `cancel_notified_at` — when the shopper was told the subscription ended.

Additive + idempotent. NULL on existing rows means "not sent", which is true.

Revision ID: zzzzcappe41
Revises: zzzzcappe40
"""
from alembic import op

revision = "zzzzcappe41"
down_revision = "zzzzcappe40"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE cappe_shopper_subscriptions
            ADD COLUMN IF NOT EXISTS failure_notified_invoice_id VARCHAR(255),
            ADD COLUMN IF NOT EXISTS cancel_notified_at          TIMESTAMPTZ
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE cappe_shopper_subscriptions
            DROP COLUMN IF EXISTS cancel_notified_at,
            DROP COLUMN IF EXISTS failure_notified_invoice_id
        """
    )
