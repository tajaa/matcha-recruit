"""cappe: physical-goods shipping — per-site flat rate, order address + tracking

- cappe_sites.shipping_flat_cents / shipping_free_threshold_cents / shipping_label:
  flat per-site shipping applied to carts containing physical lines
  (NULL threshold = no free-shipping threshold).
- cappe_orders.shipping_cents: charged shipping, folded into total_cents.
- cappe_orders.shipping_address: Stripe shipping_details persisted verbatim
  (JSONB; read only for display — nothing filters/joins on it).
- cappe_orders.carrier / tracking_number: fulfillment tracking, owner-edited.

Revision ID: zzzzcappe28
Revises: zzzzcappe27
Create Date: 2026-08-03
"""
from alembic import op

revision = "zzzzcappe28"
down_revision = "zzzzcappe27"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE cappe_sites ADD COLUMN IF NOT EXISTS shipping_flat_cents INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE cappe_sites ADD COLUMN IF NOT EXISTS shipping_free_threshold_cents INTEGER")
    op.execute("ALTER TABLE cappe_sites ADD COLUMN IF NOT EXISTS shipping_label VARCHAR(40) NOT NULL DEFAULT 'Shipping'")
    op.execute("ALTER TABLE cappe_orders ADD COLUMN IF NOT EXISTS shipping_cents INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE cappe_orders ADD COLUMN IF NOT EXISTS shipping_address JSONB")
    op.execute("ALTER TABLE cappe_orders ADD COLUMN IF NOT EXISTS carrier VARCHAR(40)")
    op.execute("ALTER TABLE cappe_orders ADD COLUMN IF NOT EXISTS tracking_number VARCHAR(120)")


def downgrade() -> None:
    op.execute("ALTER TABLE cappe_orders DROP COLUMN IF EXISTS tracking_number")
    op.execute("ALTER TABLE cappe_orders DROP COLUMN IF EXISTS carrier")
    op.execute("ALTER TABLE cappe_orders DROP COLUMN IF EXISTS shipping_address")
    op.execute("ALTER TABLE cappe_orders DROP COLUMN IF EXISTS shipping_cents")
    op.execute("ALTER TABLE cappe_sites DROP COLUMN IF EXISTS shipping_label")
    op.execute("ALTER TABLE cappe_sites DROP COLUMN IF EXISTS shipping_free_threshold_cents")
    op.execute("ALTER TABLE cappe_sites DROP COLUMN IF EXISTS shipping_flat_cents")
