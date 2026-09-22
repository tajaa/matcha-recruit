"""Site-scoped storefront shoppers. Existing guest orders remain valid.

Revision ID: zzzzcappe33
Revises: zzzzcappe32
"""
from alembic import op

revision = "zzzzcappe33"
down_revision = "zzzzcappe32"
branch_labels = None
depends_on = None

# One statement per op.execute(): this repo's Alembic runs on asyncpg, which
# prepares every statement and rejects a multi-command string ("cannot insert
# multiple commands into a prepared statement").

_UPGRADE = [
    """
    CREATE TABLE IF NOT EXISTS cappe_shoppers (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
        email VARCHAR(320) NOT NULL CHECK (email = lower(email)),
        name VARCHAR(200), phone VARCHAR(40), stripe_customer_id VARCHAR(255),
        push_order_updates BOOLEAN NOT NULL DEFAULT TRUE,
        tokens_valid_after TIMESTAMPTZ, last_login_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (site_id, email), UNIQUE (id, site_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS cappe_shopper_login_codes (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
        email VARCHAR(320) NOT NULL, code_hash CHAR(64) NOT NULL,
        attempts SMALLINT NOT NULL DEFAULT 0,
        expires_at TIMESTAMPTZ NOT NULL, consumed_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_cappe_shopper_codes
        ON cappe_shopper_login_codes(site_id, email, created_at DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS cappe_shopper_addresses (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        shopper_id UUID NOT NULL, site_id UUID NOT NULL,
        label VARCHAR(60), name VARCHAR(200) NOT NULL,
        line1 VARCHAR(200) NOT NULL, line2 VARCHAR(200),
        city VARCHAR(120) NOT NULL, region VARCHAR(120),
        postal_code VARCHAR(20) NOT NULL, country CHAR(2) NOT NULL DEFAULT 'US',
        phone VARCHAR(40), is_default BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        FOREIGN KEY (shopper_id, site_id) REFERENCES cappe_shoppers(id, site_id) ON DELETE CASCADE
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_cappe_shopper_default_address
        ON cappe_shopper_addresses(shopper_id) WHERE is_default
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_cappe_shopper_addresses_list
        ON cappe_shopper_addresses(shopper_id, site_id, created_at, id)
    """,
    """
    CREATE TABLE IF NOT EXISTS cappe_shopper_favorites (
        shopper_id UUID NOT NULL REFERENCES cappe_shoppers(id) ON DELETE CASCADE,
        product_id UUID NOT NULL REFERENCES cappe_products(id) ON DELETE CASCADE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (shopper_id, product_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_cappe_shopper_favorites_product
        ON cappe_shopper_favorites(product_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS cappe_shopper_devices (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        shopper_id UUID NOT NULL, site_id UUID NOT NULL,
        token VARCHAR(200) NOT NULL,
        bundle_id VARCHAR(155) NOT NULL,
        environment VARCHAR(12) NOT NULL CHECK (environment IN ('sandbox', 'production')),
        app_version VARCHAR(40),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (token, bundle_id, environment),
        FOREIGN KEY (shopper_id, site_id) REFERENCES cappe_shoppers(id, site_id) ON DELETE CASCADE
    )
    """,
    """CREATE INDEX IF NOT EXISTS idx_cappe_shopper_devices_shopper ON cappe_shopper_devices(shopper_id)""",
    """
    CREATE TABLE IF NOT EXISTS cappe_shopper_sessions (
        id UUID PRIMARY KEY,
        shopper_id UUID NOT NULL REFERENCES cappe_shoppers(id) ON DELETE CASCADE,
        refresh_hash CHAR(64) NOT NULL, expires_at TIMESTAMPTZ NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_cappe_shopper_sessions_shopper
        ON cappe_shopper_sessions(shopper_id)
    """,
    """
    ALTER TABLE cappe_orders ADD COLUMN IF NOT EXISTS shopper_id UUID
        REFERENCES cappe_shoppers(id) ON DELETE SET NULL
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_cappe_orders_shopper
        ON cappe_orders(shopper_id, created_at DESC, id DESC) WHERE shopper_id IS NOT NULL
    """,
    """
    ALTER TABLE cappe_sites ADD COLUMN IF NOT EXISTS app_url_scheme VARCHAR(32),
        ADD COLUMN IF NOT EXISTS app_bundle_id VARCHAR(155)
    """,
    """
    UPDATE cappe_billing_products SET features = features || '{"shopper_accounts": true}'::jsonb
        WHERE code IN ('business', 'pro', 'hosting')
    """,
]

_DOWNGRADE = [
    """UPDATE cappe_billing_products SET features = features - 'shopper_accounts'""",
    """ALTER TABLE cappe_sites DROP COLUMN IF EXISTS app_bundle_id, DROP COLUMN IF EXISTS app_url_scheme""",
    """ALTER TABLE cappe_orders DROP COLUMN IF EXISTS shopper_id""",
    """DROP TABLE IF EXISTS cappe_shopper_sessions""",
    """DROP TABLE IF EXISTS cappe_shopper_devices""",
    """DROP TABLE IF EXISTS cappe_shopper_favorites""",
    """DROP TABLE IF EXISTS cappe_shopper_addresses""",
    """DROP TABLE IF EXISTS cappe_shopper_login_codes""",
    """DROP TABLE IF EXISTS cappe_shoppers""",
]


def upgrade():
    for stmt in _UPGRADE:
        op.execute(stmt)


def downgrade():
    for stmt in _DOWNGRADE:
        op.execute(stmt)
