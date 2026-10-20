"""Cappe — product variants: stock, SKU and price for each combination.

Until now a product's options were independent: stock lived on each option
value, so "M + Red" took one unit from M and one from Red, and nothing could
say "we have 3 medium red ones". A variant is one combination of the product's
required single-pick groups (Size × Colour) with its own stock, SKU, price and
picture. Optional groups and add-ons stay plain options.

`cappe_product_variants`
  * `option_ids` — one option id per variant group, sorted (uuid text order) so
    a selection finds its row by equality. UNIQUE per product.
  * `price_cents` — NULL = the product's price plus the options' price changes,
    as before; a number replaces that for this combination.
  * `inventory` — NULL = not tracked on the variant (the product's own stock,
    if any, still applies).
  * `status` — `disabled` is a combination the store doesn't sell.

`cappe_order_items.variant_id` — the variant a line bought; `sku` — the SKU it
sold under (the variant's, else the product's), kept for packing and exports;
`decremented_variant_id` — the variant whose stock the sale took (NULL = none),
read like `decremented_option_ids` by every restock and re-take.

`cappe_inventory_adjustments.variant_id` — which variant a ledger row moved.

Also changes who may sell what (Diego, 2026-10-19): the free plan sells
digital, service and booking offerings only; Creator gains physical and digital
(and a description that says so), so no paid plan sells less than the free one.
On prod (2026-10-19) no free account has a physical product, so nothing that
sells today stops. The catalog is cached for 60 s (entitlements.py).

Additive. The downgrade drops the table and the columns and puts the two plan
rows back as they were.

Revision ID: zzzzcappe50
Revises: zzzzcappe48
Create Date: 2026-10-20
"""
from alembic import op

revision = "zzzzcappe50"
down_revision = "zzzzcappe48"
branch_labels = None
depends_on = None


_UPGRADE = [
    """
    CREATE TABLE IF NOT EXISTS cappe_product_variants (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
        product_id UUID NOT NULL REFERENCES cappe_products(id) ON DELETE CASCADE,
        option_ids UUID[] NOT NULL CHECK (cardinality(option_ids) BETWEEN 1 AND 10),
        sku VARCHAR(120),
        price_cents INTEGER CHECK (price_cents >= 0),
        inventory INTEGER,
        image_url TEXT,
        status VARCHAR(10) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
        sort_order INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (product_id, option_ids)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_cappe_product_variants_site ON cappe_product_variants (site_id)",
    "ALTER TABLE cappe_order_items "
    "ADD COLUMN IF NOT EXISTS variant_id UUID REFERENCES cappe_product_variants(id) ON DELETE SET NULL, "
    "ADD COLUMN IF NOT EXISTS decremented_variant_id UUID, "
    "ADD COLUMN IF NOT EXISTS sku VARCHAR(120)",
    "ALTER TABLE cappe_inventory_adjustments "
    "ADD COLUMN IF NOT EXISTS variant_id UUID REFERENCES cappe_product_variants(id) ON DELETE SET NULL",
    "UPDATE cappe_billing_products SET allowed_fulfillment = ARRAY['digital', 'service', 'booking']::TEXT[], "
    "updated_at = NOW() WHERE code = 'free'",
    "UPDATE cappe_billing_products SET allowed_fulfillment = "
    "ARRAY['physical', 'digital', 'service', 'booking']::TEXT[], "
    "description = 'For solo businesses selling their time and their goods.', "
    "updated_at = NOW() WHERE code = 'creator'",
]

_DOWNGRADE = [
    "UPDATE cappe_billing_products SET allowed_fulfillment = ARRAY['service', 'booking']::TEXT[], "
    "description = 'For solo professionals selling their time.', updated_at = NOW() WHERE code = 'creator'",
    "UPDATE cappe_billing_products SET allowed_fulfillment = "
    "ARRAY['physical', 'digital', 'service', 'booking']::TEXT[], updated_at = NOW() WHERE code = 'free'",
    "ALTER TABLE cappe_inventory_adjustments DROP COLUMN IF EXISTS variant_id",
    "ALTER TABLE cappe_order_items DROP COLUMN IF EXISTS sku, "
    "DROP COLUMN IF EXISTS decremented_variant_id, DROP COLUMN IF EXISTS variant_id",
    "DROP TABLE IF EXISTS cappe_product_variants",
]


def upgrade() -> None:
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWNGRADE:
        op.execute(statement)
