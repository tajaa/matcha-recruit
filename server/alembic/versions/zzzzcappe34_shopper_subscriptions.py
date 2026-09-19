"""Connected-account recurring storefront orders.

Revision ID: zzzzcappe34
Revises: zzzzcappe33
"""
from alembic import op

revision = "zzzzcappe34"
down_revision = "zzzzcappe33"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE cappe_products ADD COLUMN IF NOT EXISTS subscription_intervals TEXT[] NOT NULL DEFAULT '{}',
            ADD COLUMN IF NOT EXISTS subscription_discount_bps INTEGER NOT NULL DEFAULT 0;
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='cappe_product_subscription_chk') THEN
                ALTER TABLE cappe_products ADD CONSTRAINT cappe_product_subscription_chk
                CHECK (subscription_discount_bps BETWEEN 0 AND 5000
                    AND subscription_intervals <@ ARRAY['week','month']::text[]
                    AND (cardinality(subscription_intervals)=0 OR fulfillment IN ('physical','digital')));
            END IF;
        END $$;
        ALTER TABLE cappe_shoppers ADD COLUMN IF NOT EXISTS deleting BOOLEAN NOT NULL DEFAULT FALSE;
        CREATE TABLE IF NOT EXISTS cappe_shopper_subscriptions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            site_id UUID NOT NULL REFERENCES cappe_sites(id) ON DELETE CASCADE,
            shopper_id UUID REFERENCES cappe_shoppers(id) ON DELETE SET NULL,
            stripe_account_id VARCHAR(255) NOT NULL,
            stripe_checkout_session_id VARCHAR(255) UNIQUE, stripe_subscription_id VARCHAR(255) UNIQUE,
            status VARCHAR(24) NOT NULL DEFAULT 'incomplete',
            interval VARCHAR(8) NOT NULL CHECK (interval IN ('week','month')),
            items JSONB NOT NULL, subtotal_cents INTEGER NOT NULL, tax_cents INTEGER NOT NULL,
            shipping_cents INTEGER NOT NULL, total_cents INTEGER NOT NULL,
            currency VARCHAR(3) NOT NULL, current_period_end TIMESTAMPTZ,
            cancel_at_period_end BOOLEAN NOT NULL DEFAULT FALSE,
            stripe_event_at TIMESTAMPTZ, checkout_token VARCHAR(32) NOT NULL UNIQUE
                DEFAULT replace(gen_random_uuid()::text,'-',''),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS idx_cappe_shopper_subscriptions_shopper ON cappe_shopper_subscriptions(shopper_id,site_id);
        ALTER TABLE cappe_orders ADD COLUMN IF NOT EXISTS subscription_id UUID REFERENCES cappe_shopper_subscriptions(id) ON DELETE SET NULL,
            ADD COLUMN IF NOT EXISTS stripe_invoice_id VARCHAR(255);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_cappe_orders_invoice ON cappe_orders(stripe_invoice_id) WHERE stripe_invoice_id IS NOT NULL;
        UPDATE cappe_billing_products SET features=features || '{"recurring_orders":true}'::jsonb
            WHERE code IN ('business','pro','hosting');
    """)


def downgrade():
    op.execute("""
        UPDATE cappe_billing_products SET features=features-'recurring_orders';
        ALTER TABLE cappe_orders DROP COLUMN IF EXISTS stripe_invoice_id, DROP COLUMN IF EXISTS subscription_id;
        DROP TABLE IF EXISTS cappe_shopper_subscriptions;
        ALTER TABLE cappe_shoppers DROP COLUMN IF EXISTS deleting;
        ALTER TABLE cappe_products DROP CONSTRAINT IF EXISTS cappe_product_subscription_chk;
        ALTER TABLE cappe_products DROP COLUMN IF EXISTS subscription_discount_bps, DROP COLUMN IF EXISTS subscription_intervals;
    """)
