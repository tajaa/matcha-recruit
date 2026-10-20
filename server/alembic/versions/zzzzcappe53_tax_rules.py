"""Cappe — tax rules: prices that include tax, tax on shipping, a rate per zone.

A store had one tax rate, added on top of the goods only: never on shipping,
the same rate in every zone that charged tax (no VAT per country), and no way
to say "my prices already include tax" — which is how every EU/UK/AU seller
prices.

`cappe_sites.prices_include_tax` — the listed prices already contain the tax:
the buyer pays the listed price, and the tax inside it is shown ("Includes
VAT") rather than added. `cappe_sites.tax_on_shipping` — shipping is taxed at
the same rate as the goods.

`cappe_shipping_zones.tax_rate_bps` — the rate a zone that charges tax uses;
NULL = the store's own rate, as before.

`cappe_orders.tax_included`, `shipping_tax_cents` (and the same on
`cappe_shopper_subscriptions`, whose renewals become orders): what the order
was priced with, kept as it was. With `tax_included`, `tax_cents` is inside
`subtotal_cents` (its goods part) and `shipping_cents` (`shipping_tax_cents`)
instead of on top, so the total is subtotal + shipping; without it, as before,
subtotal + tax + shipping. Either way the goods net of tax are
`subtotal - (tax - shipping_tax if tax_included else 0)`, which is what the
platform fee is taken on.

Country-level only (the bag knows the country before Stripe collects an
address). All defaults keep today's behaviour. Additive; the downgrade drops
the columns.

Revision ID: zzzzcappe53
Revises: zzzzcappe52
Create Date: 2026-10-20
"""
from alembic import op

revision = "zzzzcappe53"
down_revision = "zzzzcappe52"
branch_labels = None
depends_on = None


_UPGRADE = [
    "ALTER TABLE cappe_sites "
    "ADD COLUMN IF NOT EXISTS prices_include_tax BOOLEAN NOT NULL DEFAULT false, "
    "ADD COLUMN IF NOT EXISTS tax_on_shipping BOOLEAN NOT NULL DEFAULT false",
    "ALTER TABLE cappe_shipping_zones "
    "ADD COLUMN IF NOT EXISTS tax_rate_bps INTEGER CHECK (tax_rate_bps BETWEEN 0 AND 10000)",
    "ALTER TABLE cappe_orders "
    "ADD COLUMN IF NOT EXISTS tax_included BOOLEAN NOT NULL DEFAULT false, "
    "ADD COLUMN IF NOT EXISTS shipping_tax_cents INTEGER NOT NULL DEFAULT 0 CHECK (shipping_tax_cents >= 0)",
    "ALTER TABLE cappe_shopper_subscriptions "
    "ADD COLUMN IF NOT EXISTS tax_included BOOLEAN NOT NULL DEFAULT false, "
    "ADD COLUMN IF NOT EXISTS shipping_tax_cents INTEGER NOT NULL DEFAULT 0 CHECK (shipping_tax_cents >= 0)",
]

_DOWNGRADE = [
    "ALTER TABLE cappe_shopper_subscriptions DROP COLUMN IF EXISTS shipping_tax_cents, "
    "DROP COLUMN IF EXISTS tax_included",
    "ALTER TABLE cappe_orders DROP COLUMN IF EXISTS shipping_tax_cents, DROP COLUMN IF EXISTS tax_included",
    "ALTER TABLE cappe_shipping_zones DROP COLUMN IF EXISTS tax_rate_bps",
    "ALTER TABLE cappe_sites DROP COLUMN IF EXISTS tax_on_shipping, DROP COLUMN IF EXISTS prices_include_tax",
]


def upgrade() -> None:
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWNGRADE:
        op.execute(statement)
