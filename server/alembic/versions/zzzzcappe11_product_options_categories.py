"""Cappe product options + categories.

Products gain a free-text `category` for storefront grouping (Drinks / Pastries /
Beans), and option groups (Size, Milk, Add-ons) — each group is single- or
multi-select, optionally required, and each option carries a SIGNED
price_delta_cents (Large +$1.00, Small -$0.50). order_items snapshot the chosen
options so a receipt/admin shows "Latte — Large, Oat milk" forever even if the
option rows are later edited or deleted. All additive — legacy single-price
products are unchanged.

Revision ID: zzzzcappe11
Revises: zzzzcappe10
"""
from alembic import op

revision = "zzzzcappe11"
down_revision = "zzzzcappe10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE cappe_products ADD COLUMN IF NOT EXISTS category VARCHAR(120)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_product_option_groups (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
            product_id UUID NOT NULL REFERENCES cappe_products(id) ON DELETE CASCADE,
            name VARCHAR(120) NOT NULL,
            select_type VARCHAR(10) NOT NULL DEFAULT 'single'
                CHECK (select_type IN ('single', 'multi')),
            required BOOLEAN NOT NULL DEFAULT false,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_option_groups_product "
        "ON cappe_product_option_groups(product_id, sort_order)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_product_options (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
            group_id UUID NOT NULL REFERENCES cappe_product_option_groups(id) ON DELETE CASCADE,
            name VARCHAR(120) NOT NULL,
            price_delta_cents INTEGER NOT NULL DEFAULT 0,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_product_options_group "
        "ON cappe_product_options(group_id, sort_order)"
    )

    op.execute(
        "ALTER TABLE cappe_order_items "
        "ADD COLUMN IF NOT EXISTS selected_options JSONB NOT NULL DEFAULT '[]'::jsonb"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE cappe_order_items DROP COLUMN IF EXISTS selected_options")
    op.execute("DROP TABLE IF EXISTS cappe_product_options")
    op.execute("DROP TABLE IF EXISTS cappe_product_option_groups")
    op.execute("ALTER TABLE cappe_products DROP COLUMN IF EXISTS category")
