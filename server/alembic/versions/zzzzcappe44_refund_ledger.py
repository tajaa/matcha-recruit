"""Cappe — a record of every refund, part refunds, and the numbers behind them.

`cappe_order_refunds` — one row per refund: how much, which lines went back on
the shelf, why, and where it came from (the dashboard, the Stripe dashboard,
a lost dispute, or an order paid outside Stripe). A refund started from the
dashboard is written `pending` BEFORE Stripe is asked, carrying the owner's
restock choice — so the `charge.refunded` webhook, which can arrive first,
applies that choice instead of guessing. An order used to hold one
`refunded_cents` number and could only be refunded in full.

`cappe_order_items.restocked_quantity` — how many of a line's units have gone
back on the shelf, so a part refund that returned two units and a later full
refund can't credit the same units twice.

Existing refunds are copied into the ledger (source `legacy`) so the finances
page counts them.

Plan gate: `financials_export` (the CSV export) on creator / business / pro /
hosting. The summary itself is on every plan.

Additive + idempotent.

Revision ID: zzzzcappe44
Revises: zzzzcappe43
"""
from alembic import op

revision = "zzzzcappe44"
down_revision = "zzzzcappe43"
branch_labels = None
depends_on = None

_UPGRADE = [
    """
    CREATE TABLE IF NOT EXISTS cappe_order_refunds (
        id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        order_id         UUID NOT NULL REFERENCES cappe_orders(id) ON DELETE CASCADE,
        site_id          UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
        amount_cents     INTEGER NOT NULL CHECK (amount_cents > 0),
        restock          BOOLEAN NOT NULL DEFAULT FALSE,
        lines            JSONB NOT NULL DEFAULT '[]',
        reason           VARCHAR(500),
        status           VARCHAR(20) NOT NULL DEFAULT 'pending'
                         CHECK (status IN ('pending', 'succeeded', 'failed')),
        source           VARCHAR(20) NOT NULL DEFAULT 'dashboard'
                         CHECK (source IN ('dashboard', 'stripe', 'dispute', 'manual', 'legacy')),
        stripe_refund_id VARCHAR(255),
        failure          VARCHAR(500),
        created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_cappe_order_refunds_order ON cappe_order_refunds (order_id, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_cappe_order_refunds_site ON cappe_order_refunds (site_id, created_at) "
    "WHERE status = 'succeeded'",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_cappe_order_refunds_stripe ON cappe_order_refunds (stripe_refund_id) "
    "WHERE stripe_refund_id IS NOT NULL",
    # One refund in flight per order: the second waits for the first to settle.
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_cappe_order_refunds_pending ON cappe_order_refunds (order_id) "
    "WHERE status = 'pending'",
    "ALTER TABLE cappe_order_items ADD COLUMN IF NOT EXISTS restocked_quantity INTEGER NOT NULL DEFAULT 0",
    # The finances page reads paid orders by when they were paid.
    "CREATE INDEX IF NOT EXISTS idx_cappe_orders_site_paid ON cappe_orders "
    "(site_id, (COALESCE(paid_at, created_at))) WHERE status IN ('paid', 'fulfilled', 'refunded')",
    # Refunds recorded before the ledger existed.
    """
    INSERT INTO cappe_order_refunds
        (order_id, site_id, amount_cents, status, source, stripe_refund_id, created_at, updated_at)
    SELECT o.id, o.site_id, o.refunded_cents, 'succeeded', 'legacy', o.stripe_refund_id,
           COALESCE(o.refunded_at, o.updated_at), COALESCE(o.refunded_at, o.updated_at)
      FROM cappe_orders o
     WHERE o.refunded_cents > 0
       AND NOT EXISTS (SELECT 1 FROM cappe_order_refunds r WHERE r.order_id = o.id)
       AND (o.stripe_refund_id IS NULL
            OR NOT EXISTS (SELECT 1 FROM cappe_order_refunds r2 WHERE r2.stripe_refund_id = o.stripe_refund_id))
    """,
    # A fully refunded order's stock went back with the refund.
    """
    UPDATE cappe_order_items i SET restocked_quantity = i.quantity
      FROM cappe_orders o
     WHERE o.id = i.order_id AND o.status IN ('refunded', 'cancelled', 'declined')
       AND i.fulfillment = 'physical' AND i.restocked_quantity = 0
    """,
    """
    UPDATE cappe_billing_products SET features = features || jsonb_build_object('financials_export', true)
     WHERE code IN ('creator', 'business', 'pro', 'hosting')
    """,
]

_DOWNGRADE = [
    "UPDATE cappe_billing_products SET features = features - 'financials_export'",
    "DROP INDEX IF EXISTS idx_cappe_orders_site_paid",
    "ALTER TABLE cappe_order_items DROP COLUMN IF EXISTS restocked_quantity",
    "DROP TABLE IF EXISTS cappe_order_refunds",
]


def upgrade() -> None:
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWNGRADE:
        op.execute(statement)
