"""cappe: sophisticated inventory — per-variant stock, thresholds, audit log

- cappe_product_options.inventory: per-variant stock (NULL = untracked); decremented
  alongside product stock at checkout, restocked on decline.
- cappe_products.low_stock_threshold: owner gets an alert/badge when stock <= this.
- cappe_order_items.selected_option_ids: the chosen option UUIDs (so a declined
  order can restock the exact variant rows, not just the product).
- cappe_inventory_adjustments: append-only audit of every stock change (sale,
  manual, restock, decline_restock, damage, return) with the resulting balance.

All additive; tracking is opt-in per product/option (NULL stock = unlimited).

Revision ID: zzzzcappe18
Revises: zzzzcappe17
Create Date: 2026-06-16
"""
from alembic import op

revision = "zzzzcappe18"
down_revision = "zzzzcappe17"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE cappe_products ADD COLUMN IF NOT EXISTS low_stock_threshold INTEGER")
    op.execute("ALTER TABLE cappe_product_options ADD COLUMN IF NOT EXISTS inventory INTEGER")
    op.execute(
        "ALTER TABLE cappe_order_items "
        "ADD COLUMN IF NOT EXISTS selected_option_ids UUID[] NOT NULL DEFAULT '{}'"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_inventory_adjustments (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
            product_id UUID NOT NULL REFERENCES cappe_products(id) ON DELETE CASCADE,
            option_id UUID REFERENCES cappe_product_options(id) ON DELETE SET NULL,
            delta INTEGER NOT NULL,
            balance_after INTEGER,
            reason VARCHAR(40) NOT NULL DEFAULT 'manual'
                CHECK (reason IN ('sale','manual','restock','decline_restock','damage','return','adjustment')),
            note TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_inv_adj_product "
        "ON cappe_inventory_adjustments(product_id, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS cappe_inventory_adjustments")
    op.execute("ALTER TABLE cappe_order_items DROP COLUMN IF EXISTS selected_option_ids")
    op.execute("ALTER TABLE cappe_product_options DROP COLUMN IF EXISTS inventory")
    op.execute("ALTER TABLE cappe_products DROP COLUMN IF EXISTS low_stock_threshold")
