"""Cappe magazines, PR 6 — paid subscriptions for readers.

A magazine can charge its readers a monthly price. The subscription lives on
the writer's own Stripe account (Connect, direct charges), and Gummfit keeps
`magazine_fee_bps` of each payment (30% unless an admin changes it), whatever
the writer's plan.

  * `cappe_shopper_subscriptions.kind` — `goods` (a store's recurring order,
    every row so far) or `magazine` (a reader's subscription). A magazine
    invoice never becomes an order: it goes to `cappe_magazine_payments`;
  * `cappe_magazines` gains the paid settings: `paid_enabled`, `price_cents`
    ($1–$1,000 a month), `paid_pitch`, `preview_blocks` (how many blocks a
    paid story shows when it has no paywall marker) and `lapsed_at` (when paid
    subscriptions were stopped — by the writer, or because the plan no longer
    includes them; readers keep what they paid for);
  * `cappe_magazine_payments` — one row per paid invoice, unique on the
    invoice, with the fee Stripe took and what was refunded;
  * `cappe_magazine_comps` — free subscriptions a writer gives; at most one
    live comp per reader and magazine;
  * the `magazine_fee_bps` setting (3000) and the `magazine_paid` plan feature
    on Writer, Creator, Business and Pro.

The downgrade refuses while any magazine subscription, payment or comp exists.

Revision ID: cappemag05
Revises: cappemag04
Create Date: 2026-10-21
"""
from alembic import op

revision = "cappemag05"
down_revision = "cappemag04"
branch_labels = None
depends_on = None

_UPGRADE = [
    "ALTER TABLE cappe_shopper_subscriptions ADD COLUMN IF NOT EXISTS kind VARCHAR(10) NOT NULL DEFAULT 'goods'",
    """
    DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_cappe_shopper_subscriptions_kind') THEN
            ALTER TABLE cappe_shopper_subscriptions ADD CONSTRAINT ck_cappe_shopper_subscriptions_kind
                CHECK (kind IN ('goods', 'magazine'));
        END IF;
    END $$
    """,
    "CREATE INDEX IF NOT EXISTS idx_cappe_shopper_subscriptions_magazine "
    "ON cappe_shopper_subscriptions (site_id, shopper_id) WHERE kind = 'magazine'",
    "ALTER TABLE cappe_magazines ADD COLUMN IF NOT EXISTS paid_enabled BOOLEAN NOT NULL DEFAULT false",
    "ALTER TABLE cappe_magazines ADD COLUMN IF NOT EXISTS price_cents INTEGER",
    "ALTER TABLE cappe_magazines ADD COLUMN IF NOT EXISTS paid_pitch TEXT",
    "ALTER TABLE cappe_magazines ADD COLUMN IF NOT EXISTS preview_blocks SMALLINT NOT NULL DEFAULT 3",
    "ALTER TABLE cappe_magazines ADD COLUMN IF NOT EXISTS lapsed_at TIMESTAMPTZ",
    """
    DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_cappe_magazines_paid') THEN
            ALTER TABLE cappe_magazines ADD CONSTRAINT ck_cappe_magazines_paid CHECK (
                (price_cents IS NULL OR price_cents BETWEEN 100 AND 100000)
                AND preview_blocks BETWEEN 1 AND 20
                AND (NOT paid_enabled OR price_cents IS NOT NULL));
        END IF;
    END $$
    """,
    """
    CREATE TABLE IF NOT EXISTS cappe_magazine_payments (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
        subscription_id UUID REFERENCES cappe_shopper_subscriptions(id) ON DELETE SET NULL,
        shopper_id UUID REFERENCES cappe_shoppers(id) ON DELETE SET NULL,
        stripe_account_id VARCHAR(255) NOT NULL,
        stripe_invoice_id VARCHAR(255) NOT NULL UNIQUE,
        stripe_payment_intent VARCHAR(255),
        amount_cents INTEGER NOT NULL CHECK (amount_cents >= 0),
        fee_cents INTEGER CHECK (fee_cents >= 0),
        refunded_cents INTEGER NOT NULL DEFAULT 0 CHECK (refunded_cents >= 0),
        currency VARCHAR(3) NOT NULL,
        billing_reason VARCHAR(40),
        paid_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_cappe_magazine_payments_site ON cappe_magazine_payments (site_id, paid_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_cappe_magazine_payments_intent ON cappe_magazine_payments (stripe_payment_intent) "
    "WHERE stripe_payment_intent IS NOT NULL",
    """
    CREATE TABLE IF NOT EXISTS cappe_magazine_comps (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
        shopper_id UUID NOT NULL REFERENCES cappe_shoppers(id) ON DELETE CASCADE,
        note VARCHAR(200),
        expires_at TIMESTAMPTZ,
        revoked_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_cappe_magazine_comps_live ON cappe_magazine_comps (site_id, shopper_id) "
    "WHERE revoked_at IS NULL",
    # jsonb_build_object, never a JSON literal: op.execute reads ":3000"-style
    # text as a bind parameter (zzzzcappe34).
    "INSERT INTO cappe_marketplace_settings (key, value) VALUES ('magazine_fee_bps', jsonb_build_object('bps', 3000)) "
    "ON CONFLICT (key) DO NOTHING",
    "UPDATE cappe_billing_products SET features = features || jsonb_build_object('magazine_paid', true) "
    "WHERE code IN ('writer', 'creator', 'business', 'pro')",
]

_DOWNGRADE = [
    """
    DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM cappe_shopper_subscriptions WHERE kind = 'magazine')
           OR EXISTS (SELECT 1 FROM cappe_magazine_payments)
           OR EXISTS (SELECT 1 FROM cappe_magazine_comps) THEN
            RAISE EXCEPTION 'cappemag05 downgrade: magazine subscriptions, payments or comps exist';
        END IF;
    END $$
    """,
    "UPDATE cappe_billing_products SET features = features - 'magazine_paid' "
    "WHERE features ->> 'magazine_paid' IS NOT NULL",
    "DELETE FROM cappe_marketplace_settings WHERE key = 'magazine_fee_bps'",
    "DROP TABLE IF EXISTS cappe_magazine_comps",
    "DROP TABLE IF EXISTS cappe_magazine_payments",
    "ALTER TABLE cappe_magazines DROP CONSTRAINT IF EXISTS ck_cappe_magazines_paid",
    "ALTER TABLE cappe_magazines DROP COLUMN IF EXISTS lapsed_at",
    "ALTER TABLE cappe_magazines DROP COLUMN IF EXISTS preview_blocks",
    "ALTER TABLE cappe_magazines DROP COLUMN IF EXISTS paid_pitch",
    "ALTER TABLE cappe_magazines DROP COLUMN IF EXISTS price_cents",
    "ALTER TABLE cappe_magazines DROP COLUMN IF EXISTS paid_enabled",
    "DROP INDEX IF EXISTS idx_cappe_shopper_subscriptions_magazine",
    "ALTER TABLE cappe_shopper_subscriptions DROP CONSTRAINT IF EXISTS ck_cappe_shopper_subscriptions_kind",
    "ALTER TABLE cappe_shopper_subscriptions DROP COLUMN IF EXISTS kind",
]


def upgrade() -> None:
    for statement in _UPGRADE:
        op.execute(statement)


def downgrade() -> None:
    for statement in _DOWNGRADE:
        op.execute(statement)
