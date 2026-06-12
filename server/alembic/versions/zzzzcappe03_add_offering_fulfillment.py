"""Generalize Cappe products into offerings: fulfillment + deliverables + bookings.

Additive on top of zzzzcappe02. A "product" becomes any sellable offering whose
`fulfillment` decides how it's delivered:
  physical  - shipped good (today's behavior; uses inventory)
  digital   - buyer downloads `digital_file_url`
  service   - seller delivers a result; buyer answers `intake_fields`; seller
              uploads the result onto the order item (`deliverable_url`)
  booking   - buying schedules a session against `booking_type_id`

Order items snapshot `fulfillment` and carry the per-line intake answers, the
seller deliverable, and a link to any booking created. Orders gain an
unguessable `access_token` (same pattern as cappe_subscribers.unsubscribe_token)
so a buyer can view their receipt / downloads without an account.

Everything is additive with defaults, so existing rows + flows are unchanged
(every legacy product/order item is `fulfillment='physical'`).

Revision ID: zzzzcappe03
Revises: zzzzcappe02
Create Date: 2026-06-11
"""
from alembic import op


revision = "zzzzcappe03"
down_revision = "zzzzcappe02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- products -> offerings --------------------------------------------
    op.execute("""
        ALTER TABLE cappe_products
            ADD COLUMN IF NOT EXISTS fulfillment VARCHAR(20) NOT NULL DEFAULT 'physical'
                CHECK (fulfillment IN ('physical', 'digital', 'service', 'booking')),
            ADD COLUMN IF NOT EXISTS digital_file_url TEXT,
            ADD COLUMN IF NOT EXISTS booking_type_id UUID
                REFERENCES cappe_booking_types(id) ON DELETE SET NULL,
            ADD COLUMN IF NOT EXISTS intake_fields JSONB NOT NULL DEFAULT '[]'::jsonb
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_products_booking_type "
        "ON cappe_products(booking_type_id)"
    )

    # --- order items carry fulfillment context ----------------------------
    op.execute("""
        ALTER TABLE cappe_order_items
            ADD COLUMN IF NOT EXISTS fulfillment VARCHAR(20) NOT NULL DEFAULT 'physical'
                CHECK (fulfillment IN ('physical', 'digital', 'service', 'booking')),
            ADD COLUMN IF NOT EXISTS intake_answers JSONB NOT NULL DEFAULT '{}'::jsonb,
            ADD COLUMN IF NOT EXISTS deliverable_url TEXT,
            ADD COLUMN IF NOT EXISTS booking_id UUID
                REFERENCES cappe_bookings(id) ON DELETE SET NULL
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_order_items_booking "
        "ON cappe_order_items(booking_id)"
    )

    # --- orders get an unguessable buyer access token ---------------------
    op.execute("""
        ALTER TABLE cappe_orders
            ADD COLUMN IF NOT EXISTS access_token VARCHAR(64)
                DEFAULT replace(gen_random_uuid()::text, '-', '')
    """)
    # Backfill any pre-existing rows (DEFAULT only applies to new inserts).
    op.execute(
        "UPDATE cappe_orders SET access_token = replace(gen_random_uuid()::text, '-', '') "
        "WHERE access_token IS NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_cappe_orders_access_token "
        "ON cappe_orders(access_token)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_cappe_orders_access_token")
    op.execute("ALTER TABLE cappe_orders DROP COLUMN IF EXISTS access_token")

    op.execute("DROP INDEX IF EXISTS idx_cappe_order_items_booking")
    op.execute("""
        ALTER TABLE cappe_order_items
            DROP COLUMN IF EXISTS booking_id,
            DROP COLUMN IF EXISTS deliverable_url,
            DROP COLUMN IF EXISTS intake_answers,
            DROP COLUMN IF EXISTS fulfillment
    """)

    op.execute("DROP INDEX IF EXISTS idx_cappe_products_booking_type")
    op.execute("""
        ALTER TABLE cappe_products
            DROP COLUMN IF EXISTS intake_fields,
            DROP COLUMN IF EXISTS booking_type_id,
            DROP COLUMN IF EXISTS digital_file_url,
            DROP COLUMN IF EXISTS fulfillment
    """)
