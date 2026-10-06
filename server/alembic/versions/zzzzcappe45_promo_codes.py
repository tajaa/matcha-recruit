"""Cappe — promo codes a buyer types at checkout.

`cappe_promo_codes` — a code (per store, stored upper-case), percent or fixed
amount off, an optional minimum spend, date window, total-use cap and
once-per-customer rule. Its own table rather than `cappe_discounts`: that set
is replaced wholesale on every save, so it can't keep a use count.

`cappe_promo_redemptions` — one row per order that used a code. `active`
counts towards the code's cap; an order that is cancelled, declined, expires
unpaid or is refunded in full gives its use back (`released`).

`cappe_orders.promo_code` / `discount_cents` — the code and the amount it
took off. `subtotal_cents` stays what the goods cost after the discount (it
is what every fee and refund is computed from); the order page and receipt
show the discount as its own line.

`cappe_order_items.promo_discount_cents` — each line's share of it, split in
proportion to line totals, so the Stripe page and a refund see exact amounts.

Plan gate: `promo_codes` on creator / business / pro / hosting.

Additive + idempotent.

Revision ID: zzzzcappe45
Revises: zzzzcappe44
"""
from alembic import op

revision = "zzzzcappe45"
down_revision = "zzzzcappe44"
branch_labels = None
depends_on = None

_UPGRADE = [
    """
    CREATE TABLE IF NOT EXISTS cappe_promo_codes (
        id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        site_id            UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
        code               VARCHAR(40) NOT NULL,
        kind               VARCHAR(10) NOT NULL CHECK (kind IN ('percent', 'fixed')),
        percent_off        INTEGER CHECK (percent_off BETWEEN 1 AND 90),
        amount_off_cents   INTEGER CHECK (amount_off_cents > 0),
        min_subtotal_cents INTEGER CHECK (min_subtotal_cents >= 0),
        starts_on          DATE,
        ends_on            DATE,
        max_redemptions    INTEGER CHECK (max_redemptions > 0),
        once_per_customer  BOOLEAN NOT NULL DEFAULT FALSE,
        active             BOOLEAN NOT NULL DEFAULT TRUE,
        redemption_count   INTEGER NOT NULL DEFAULT 0 CHECK (redemption_count >= 0),
        created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CHECK ((kind = 'percent' AND percent_off IS NOT NULL)
            OR (kind = 'fixed' AND amount_off_cents IS NOT NULL))
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_cappe_promo_codes_code ON cappe_promo_codes (site_id, code)",
    """
    CREATE TABLE IF NOT EXISTS cappe_promo_redemptions (
        id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        promo_code_id  UUID NOT NULL REFERENCES cappe_promo_codes(id) ON DELETE CASCADE,
        site_id        UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
        order_id       UUID NOT NULL REFERENCES cappe_orders(id) ON DELETE CASCADE,
        customer_email VARCHAR(320),
        discount_cents INTEGER NOT NULL CHECK (discount_cents >= 0),
        status         VARCHAR(10) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'released')),
        created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_cappe_promo_redemptions_order ON cappe_promo_redemptions (order_id)",
    "CREATE INDEX IF NOT EXISTS idx_cappe_promo_redemptions_customer "
    "ON cappe_promo_redemptions (promo_code_id, lower(customer_email)) WHERE status = 'active'",
    """
    ALTER TABLE cappe_orders
        ADD COLUMN IF NOT EXISTS promo_code     VARCHAR(40),
        ADD COLUMN IF NOT EXISTS discount_cents INTEGER NOT NULL DEFAULT 0
    """,
    "ALTER TABLE cappe_order_items ADD COLUMN IF NOT EXISTS promo_discount_cents INTEGER NOT NULL DEFAULT 0",
    """
    UPDATE cappe_billing_products SET features = features || jsonb_build_object('promo_codes', true)
     WHERE code IN ('creator', 'business', 'pro', 'hosting')
    """,
]

_DOWNGRADE = [
    "UPDATE cappe_billing_products SET features = features - 'promo_codes'",
    "ALTER TABLE cappe_order_items DROP COLUMN IF EXISTS promo_discount_cents",
    "ALTER TABLE cappe_orders DROP COLUMN IF EXISTS discount_cents, DROP COLUMN IF EXISTS promo_code",
    "DROP TABLE IF EXISTS cappe_promo_redemptions",
    "DROP TABLE IF EXISTS cappe_promo_codes",
]


def upgrade() -> None:
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWNGRADE:
        op.execute(statement)
