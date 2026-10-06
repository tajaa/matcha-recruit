"""Cappe payments hardening — a record of what happens AFTER money moves.

The storefront could take a payment correctly and then lose track of it: a
"refunded" status with no refund behind it, refunds and disputes made in the
Stripe dashboard that never came back, a domain renewal that had no card to
charge, a failed refund that existed only as a log line. These columns are
where those facts now live.

`cappe_orders`
  * `refunded_at` / `refunded_cents` / `stripe_refund_id` — a refund is an
    event with an amount and a Stripe id, not just a status word. A partial
    refund records its amount without changing the status.
  * `dispute_status` / `disputed_at` — a chargeback opened against the order.

`cappe_collab_payments`
  * `refunded_at` / `stripe_refund_id` — the `refunded` status has been in the
    CHECK since zzzzcappe28 but nothing ever wrote it.

`cappe_domains`
  * `stripe_payment_method_id` — the card a renewal charges. A PaymentIntent
    does not fall back to "the customer's card"; without this id an
    off-session renewal has nothing to charge.
  * `refund_status` ('owed' | 'refunded') / `stripe_refund_id` / `refunded_at`
    — a refund that failed after a failed registration is now a row the
    reconciler retries, not a log line.
  * `renewal_attempted_at` / `renewal_failed_at` / `renewal_notified_at` /
    `renewal_error` — dunning state, so a failed renewal is retried on a
    schedule and the customer is told once, not hourly and not never.

Additive + idempotent. Nothing is backfilled: every column's absence means
"nothing recorded", which is the truth for existing rows.

Revision ID: zzzzcappe38
Revises: zzzzcappe37
"""
from alembic import op

revision = "zzzzcappe38"
down_revision = "zzzzcappe37"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE cappe_orders
            ADD COLUMN IF NOT EXISTS refunded_at      TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS refunded_cents   INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS stripe_refund_id VARCHAR(255),
            ADD COLUMN IF NOT EXISTS dispute_status   VARCHAR(40),
            ADD COLUMN IF NOT EXISTS disputed_at      TIMESTAMPTZ
        """
    )
    # Refund and dispute events arrive keyed on the payment intent.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_orders_payment_intent "
        "ON cappe_orders (stripe_payment_intent) WHERE stripe_payment_intent IS NOT NULL"
    )
    op.execute(
        """
        ALTER TABLE cappe_collab_payments
            ADD COLUMN IF NOT EXISTS refunded_at      TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS stripe_refund_id TEXT
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_collab_payments_intent "
        "ON cappe_collab_payments (stripe_payment_intent) WHERE stripe_payment_intent IS NOT NULL"
    )
    op.execute(
        """
        ALTER TABLE cappe_domains
            ADD COLUMN IF NOT EXISTS stripe_payment_method_id TEXT,
            ADD COLUMN IF NOT EXISTS refund_status            VARCHAR(16),
            ADD COLUMN IF NOT EXISTS stripe_refund_id         TEXT,
            ADD COLUMN IF NOT EXISTS refunded_at              TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS renewal_attempted_at     TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS renewal_failed_at        TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS renewal_notified_at      TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS renewal_error            TEXT
        """
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'cappe_domains_refund_status_check'
            ) THEN
                ALTER TABLE cappe_domains ADD CONSTRAINT cappe_domains_refund_status_check
                CHECK (refund_status IS NULL OR refund_status IN ('owed', 'refunded'));
            END IF;
        END $$
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_domains_refund_owed "
        "ON cappe_domains (updated_at) WHERE refund_status = 'owed'"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_domains_payment_intent "
        "ON cappe_domains (stripe_payment_intent) WHERE stripe_payment_intent IS NOT NULL"
    )
    # The renewal sweep now also finds domains with auto-renew OFF (to lapse
    # them at expiry instead of leaving them active for ever), so the partial
    # index that required `auto_renew` no longer covers its predicate.
    op.execute("DROP INDEX IF EXISTS idx_cappe_domains_renewal")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_domains_renewal "
        "ON cappe_domains (expires_at) WHERE status = 'active' AND kind = 'register'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_cappe_domains_renewal")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_domains_renewal "
        "ON cappe_domains (expires_at) WHERE status = 'active' AND auto_renew"
    )
    op.execute("DROP INDEX IF EXISTS idx_cappe_domains_payment_intent")
    op.execute("DROP INDEX IF EXISTS idx_cappe_domains_refund_owed")
    op.execute(
        "ALTER TABLE cappe_domains DROP CONSTRAINT IF EXISTS cappe_domains_refund_status_check"
    )
    op.execute(
        """
        ALTER TABLE cappe_domains
            DROP COLUMN IF EXISTS renewal_error,
            DROP COLUMN IF EXISTS renewal_notified_at,
            DROP COLUMN IF EXISTS renewal_failed_at,
            DROP COLUMN IF EXISTS renewal_attempted_at,
            DROP COLUMN IF EXISTS refunded_at,
            DROP COLUMN IF EXISTS stripe_refund_id,
            DROP COLUMN IF EXISTS refund_status,
            DROP COLUMN IF EXISTS stripe_payment_method_id
        """
    )
    op.execute("DROP INDEX IF EXISTS idx_cappe_collab_payments_intent")
    op.execute(
        """
        ALTER TABLE cappe_collab_payments
            DROP COLUMN IF EXISTS stripe_refund_id,
            DROP COLUMN IF EXISTS refunded_at
        """
    )
    op.execute("DROP INDEX IF EXISTS idx_cappe_orders_payment_intent")
    op.execute(
        """
        ALTER TABLE cappe_orders
            DROP COLUMN IF EXISTS disputed_at,
            DROP COLUMN IF EXISTS dispute_status,
            DROP COLUMN IF EXISTS stripe_refund_id,
            DROP COLUMN IF EXISTS refunded_cents,
            DROP COLUMN IF EXISTS refunded_at
        """
    )
