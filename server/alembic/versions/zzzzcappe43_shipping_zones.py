"""Cappe — ship beyond the home country, and a currency per store.

`cappe_sites`
  * `home_country` — where the store is based. The store's existing flat rate,
    free-shipping threshold and tax rate are its rates for THIS country (they
    were the US rates, with Stripe told to accept US addresses only).
  * `currency` — what the store charges in. Products, booking prices and
    shipping amounts are all in it. It was a free three-letter string per
    product with no way to set it, and bookings were hard-coded to USD.
    Backfilled from each store's own products so nothing changes meaning.

`cappe_shipping_zones` — extra destinations, each with its own flat rate,
free-shipping threshold and "charge tax here" switch. One zone may be "the
rest of the world". No zones = the home country only, which is today.

`cappe_orders.ship_country` — where a physical order was priced to ship, so
the payment page accepts an address in that country only.

Plan gate: `shipping_zones` on business / pro / hosting.

Additive + idempotent.

Revision ID: zzzzcappe43
Revises: zzzzcappe42
"""
from alembic import op

revision = "zzzzcappe43"
down_revision = "zzzzcappe42"
branch_labels = None
depends_on = None

# Two-decimal currencies only: a price is stored in hundredths, so a
# zero-decimal currency (JPY) would charge 100x what the store shows. Keep in
# sync with `services/shipping.SITE_CURRENCIES`.
_CURRENCIES = "'USD','CAD','EUR','GBP','AUD','NZD','CHF','SEK','NOK','DKK','PLN','MXN','SGD','HKD'"

_UPGRADE = [
    """
    ALTER TABLE cappe_sites
        ADD COLUMN IF NOT EXISTS home_country VARCHAR(2) NOT NULL DEFAULT 'US',
        ADD COLUMN IF NOT EXISTS currency     VARCHAR(3) NOT NULL DEFAULT 'USD'
    """,
    # The currency a store's products are already priced in, where they agree
    # on a supported one. Anything else keeps USD (what checkout assumed).
    f"""
    UPDATE cappe_sites s SET currency = p.cur
      FROM (SELECT site_id, MIN(UPPER(currency)) AS cur
              FROM cappe_products
             GROUP BY site_id
            HAVING COUNT(DISTINCT UPPER(currency)) = 1) p
     WHERE p.site_id = s.id AND p.cur IN ({_CURRENCIES}) AND s.currency <> p.cur
    """,
    """
    CREATE TABLE IF NOT EXISTS cappe_shipping_zones (
        id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        site_id              UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
        name                 VARCHAR(80) NOT NULL,
        countries            VARCHAR(2)[] NOT NULL DEFAULT '{}',
        rest_of_world        BOOLEAN NOT NULL DEFAULT FALSE,
        flat_cents           INTEGER NOT NULL DEFAULT 0 CHECK (flat_cents >= 0),
        free_threshold_cents INTEGER CHECK (free_threshold_cents >= 0),
        charge_tax           BOOLEAN NOT NULL DEFAULT FALSE,
        sort_order           INTEGER NOT NULL DEFAULT 0,
        created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_cappe_shipping_zones_site ON cappe_shipping_zones (site_id, sort_order)",
    # At most one "everywhere else" zone per store.
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_cappe_shipping_zones_row "
    "ON cappe_shipping_zones (site_id) WHERE rest_of_world",
    "ALTER TABLE cappe_orders ADD COLUMN IF NOT EXISTS ship_country VARCHAR(2)",
    # jsonb_build_object, not a JSON literal: op.execute wraps the string in
    # sqlalchemy.text(), which reads ":true" as a bind parameter.
    """
    UPDATE cappe_billing_products SET features = features || jsonb_build_object('shipping_zones', true)
     WHERE code IN ('business', 'pro', 'hosting')
    """,
]

_DOWNGRADE = [
    "UPDATE cappe_billing_products SET features = features - 'shipping_zones'",
    "ALTER TABLE cappe_orders DROP COLUMN IF EXISTS ship_country",
    "DROP TABLE IF EXISTS cappe_shipping_zones",
    "ALTER TABLE cappe_sites DROP COLUMN IF EXISTS currency, DROP COLUMN IF EXISTS home_country",
]


def upgrade() -> None:
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWNGRADE:
        op.execute(statement)
