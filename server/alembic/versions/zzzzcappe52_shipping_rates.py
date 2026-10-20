"""Cappe — shipping rates: more than one way to get an order, priced by what's in it.

A store used to have one flat rate per destination (plus a free-over
threshold), whatever was in the bag: a pallet of tiles cost what a postcard
did, there was no "express", and a bakery couldn't offer pickup.

`cappe_shipping_rates` — a destination's delivery options (zone_id NULL =
the home country). Each is one of:
  * `ship` — carried to the buyer's address;
  * `pickup` — collected from the store (`instructions` says where and when);
  * `local_delivery` — the store delivers, to the postal codes in
    `postal_codes` (prefixes; empty = anywhere in that destination).
Priced `amount_cents` plus `per_item_cents` for each item after the first,
free over `free_over_cents`, and offered only for an order inside its
`min/max_subtotal_cents` and `min/max_weight_g` bands. `delivery_min/max_days`
is the time in transit. Saved with the zones as one set (zones are replaced
whole, so their ids change; rates go with them).

`cappe_products.weight_g`, `shipping_surcharge_cents` (per unit, on top of
any carried rate), `ships_free` (never adds to the cost, weight or count).

`cappe_sites.handling_days_min/max` — business days to get an order out of
the door, added to each rate's time in transit.

`cappe_orders` — what the buyer chose, kept as it was: `shipping_rate_id`
(no FK: rates are replaced as a set), `shipping_method`, `shipping_rate_label`,
`delivery_min/max_days`, `shipping_instructions`.

No rate rows = a destination keeps its flat rate exactly as before. Additive;
the downgrade drops the table and the columns.

Revision ID: zzzzcappe52
Revises: zzzzcappe51
Create Date: 2026-10-20
"""
from alembic import op

revision = "zzzzcappe52"
down_revision = "zzzzcappe51"
branch_labels = None
depends_on = None


_UPGRADE = [
    """
    CREATE TABLE IF NOT EXISTS cappe_shipping_rates (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
        zone_id UUID REFERENCES cappe_shipping_zones(id) ON DELETE CASCADE,
        name VARCHAR(80) NOT NULL,
        method VARCHAR(16) NOT NULL DEFAULT 'ship' CHECK (method IN ('ship', 'pickup', 'local_delivery')),
        amount_cents INTEGER NOT NULL DEFAULT 0 CHECK (amount_cents >= 0),
        per_item_cents INTEGER NOT NULL DEFAULT 0 CHECK (per_item_cents >= 0),
        min_subtotal_cents INTEGER CHECK (min_subtotal_cents >= 0),
        max_subtotal_cents INTEGER CHECK (max_subtotal_cents >= 0),
        min_weight_g INTEGER CHECK (min_weight_g >= 0),
        max_weight_g INTEGER CHECK (max_weight_g >= 0),
        free_over_cents INTEGER CHECK (free_over_cents >= 0),
        delivery_min_days INTEGER CHECK (delivery_min_days BETWEEN 0 AND 90),
        delivery_max_days INTEGER CHECK (delivery_max_days BETWEEN 0 AND 90),
        postal_codes TEXT[] NOT NULL DEFAULT '{}',
        instructions VARCHAR(500),
        sort_order INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CHECK (delivery_min_days IS NULL OR delivery_max_days IS NULL OR delivery_min_days <= delivery_max_days)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_cappe_shipping_rates_site ON cappe_shipping_rates (site_id, sort_order)",
    "ALTER TABLE cappe_products "
    "ADD COLUMN IF NOT EXISTS weight_g INTEGER CHECK (weight_g >= 0), "
    "ADD COLUMN IF NOT EXISTS shipping_surcharge_cents INTEGER NOT NULL DEFAULT 0 CHECK (shipping_surcharge_cents >= 0), "
    "ADD COLUMN IF NOT EXISTS ships_free BOOLEAN NOT NULL DEFAULT false",
    "ALTER TABLE cappe_sites "
    "ADD COLUMN IF NOT EXISTS handling_days_min INTEGER CHECK (handling_days_min BETWEEN 0 AND 60), "
    "ADD COLUMN IF NOT EXISTS handling_days_max INTEGER CHECK (handling_days_max BETWEEN 0 AND 60)",
    "ALTER TABLE cappe_orders "
    "ADD COLUMN IF NOT EXISTS shipping_rate_id UUID, "
    "ADD COLUMN IF NOT EXISTS shipping_method VARCHAR(16) NOT NULL DEFAULT 'ship', "
    "ADD COLUMN IF NOT EXISTS shipping_rate_label VARCHAR(80), "
    "ADD COLUMN IF NOT EXISTS delivery_min_days INTEGER, "
    "ADD COLUMN IF NOT EXISTS delivery_max_days INTEGER, "
    "ADD COLUMN IF NOT EXISTS shipping_instructions VARCHAR(500)",
]

_DOWNGRADE = [
    "ALTER TABLE cappe_orders DROP COLUMN IF EXISTS shipping_instructions, "
    "DROP COLUMN IF EXISTS delivery_max_days, DROP COLUMN IF EXISTS delivery_min_days, "
    "DROP COLUMN IF EXISTS shipping_rate_label, DROP COLUMN IF EXISTS shipping_method, "
    "DROP COLUMN IF EXISTS shipping_rate_id",
    "ALTER TABLE cappe_sites DROP COLUMN IF EXISTS handling_days_max, DROP COLUMN IF EXISTS handling_days_min",
    "ALTER TABLE cappe_products DROP COLUMN IF EXISTS ships_free, "
    "DROP COLUMN IF EXISTS shipping_surcharge_cents, DROP COLUMN IF EXISTS weight_g",
    "DROP TABLE IF EXISTS cappe_shipping_rates",
]


def upgrade() -> None:
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWNGRADE:
        op.execute(statement)
