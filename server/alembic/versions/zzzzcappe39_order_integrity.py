"""Cappe order integrity — remember what a sale actually took off the shelf.

A restock used to credit whatever a line's product and options track *now*.
A product sold while it was not tracking stock, then switched to tracking,
gained units when that old order was cancelled or refunded: stock that was
never taken came "back".

`cappe_order_items`
  * `stock_decremented` — whether the sale decremented the PRODUCT's stock.
  * `decremented_option_ids` — the selected options whose own stock it
    decremented (a subset of `selected_option_ids`).

Both are NULL on every existing row, and NULL means "not recorded": the
restock falls back to the old behaviour for those, which is the best that can
be known about them. Nothing is backfilled.

Additive + idempotent.

Revision ID: zzzzcappe39
Revises: zzzzcappe38
"""
from alembic import op

revision = "zzzzcappe39"
down_revision = "zzzzcappe38"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE cappe_order_items
            ADD COLUMN IF NOT EXISTS stock_decremented      BOOLEAN,
            ADD COLUMN IF NOT EXISTS decremented_option_ids UUID[]
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE cappe_order_items
            DROP COLUMN IF EXISTS decremented_option_ids,
            DROP COLUMN IF EXISTS stock_decremented
        """
    )
