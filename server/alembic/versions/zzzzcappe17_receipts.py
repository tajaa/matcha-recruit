"""cappe: receipts — tax, totals, sequential numbering

Adds the data a real receipt needs:
- per-site tax config (rate in basis points + a label like "Sales tax") and a
  per-site receipt counter + prefix for human-readable numbers (e.g. LUM-00042).
- per-order tax_cents, total_cents (subtotal + tax), and the assigned
  receipt_number (set when the order is paid).

Tax is computed at checkout on PHYSICAL lines and added as a line item to the
Stripe Checkout Session, so the charged amount matches the receipt total. All
additive; tax defaults to 0 (no behavior change for existing sites).

Revision ID: zzzzcappe17
Revises: zzzzcappe16
Create Date: 2026-06-16
"""
from alembic import op

revision = "zzzzcappe17"
down_revision = "zzzzcappe16"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE cappe_sites ADD COLUMN IF NOT EXISTS tax_rate_bps INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE cappe_sites ADD COLUMN IF NOT EXISTS tax_label VARCHAR(40) NOT NULL DEFAULT 'Tax'")
    op.execute("ALTER TABLE cappe_sites ADD COLUMN IF NOT EXISTS receipt_prefix VARCHAR(12)")
    op.execute("ALTER TABLE cappe_sites ADD COLUMN IF NOT EXISTS receipt_seq INTEGER NOT NULL DEFAULT 0")

    op.execute("ALTER TABLE cappe_orders ADD COLUMN IF NOT EXISTS tax_cents INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE cappe_orders ADD COLUMN IF NOT EXISTS total_cents INTEGER")
    op.execute("ALTER TABLE cappe_orders ADD COLUMN IF NOT EXISTS receipt_number VARCHAR(40)")


def downgrade() -> None:
    op.execute("ALTER TABLE cappe_orders DROP COLUMN IF EXISTS receipt_number")
    op.execute("ALTER TABLE cappe_orders DROP COLUMN IF EXISTS total_cents")
    op.execute("ALTER TABLE cappe_orders DROP COLUMN IF EXISTS tax_cents")
    op.execute("ALTER TABLE cappe_sites DROP COLUMN IF EXISTS receipt_seq")
    op.execute("ALTER TABLE cappe_sites DROP COLUMN IF EXISTS receipt_prefix")
    op.execute("ALTER TABLE cappe_sites DROP COLUMN IF EXISTS tax_label")
    op.execute("ALTER TABLE cappe_sites DROP COLUMN IF EXISTS tax_rate_bps")
