"""Snapshot sales components when an import is committed."""

from alembic import op


revision = "sales02"
down_revision = "invwaste05"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS inventory_sales_line_components (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            sales_line_id UUID NOT NULL REFERENCES inventory_sales_lines(id) ON DELETE CASCADE,
            item_id UUID NOT NULL REFERENCES inventory_items(id),
            quantity_per_sale NUMERIC NOT NULL CHECK (quantity_per_sale > 0),
            unit VARCHAR(50),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (sales_line_id, item_id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_inventory_sales_line_components_item
        ON inventory_sales_line_components (item_id)
    """)


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_inventory_sales_line_components_item")
    op.execute("DROP TABLE IF EXISTS inventory_sales_line_components")
