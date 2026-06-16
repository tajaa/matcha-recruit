"""cappe: Stripe Connect for storefront sales

Wires real payments for physical-product (and any priced) storefront orders.
Each business connects its OWN Stripe account (Connect Standard); customer card
payments are DIRECT charges on that connected account, with a 2% platform fee
(`application_fee_amount`) routed to the Gummfit platform account. Orders move to
`paid` via the Connect webhook (`checkout.session.completed`).

- cappe_accounts gains the connected-account id + capability flags.
- cappe_orders gains the Stripe session/payment-intent refs, the platform fee
  taken, and a paid timestamp.

All additive; existing manual/pending orders are unaffected.

Revision ID: zzzzcappe16
Revises: zzzzcappe15
Create Date: 2026-06-16
"""
from alembic import op

revision = "zzzzcappe16"
down_revision = "zzzzcappe15"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Connected-account identity + capability flags (kept in sync from
    # account.updated webhooks + the /payments/status poll).
    op.execute("ALTER TABLE cappe_accounts ADD COLUMN IF NOT EXISTS stripe_account_id VARCHAR(255)")
    op.execute(
        "ALTER TABLE cappe_accounts "
        "ADD COLUMN IF NOT EXISTS stripe_charges_enabled BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute(
        "ALTER TABLE cappe_accounts "
        "ADD COLUMN IF NOT EXISTS stripe_details_submitted BOOLEAN NOT NULL DEFAULT false"
    )

    # Payment refs on the order. payment_ref already exists (legacy/manual);
    # these capture the Stripe Checkout flow specifically.
    op.execute("ALTER TABLE cappe_orders ADD COLUMN IF NOT EXISTS stripe_session_id VARCHAR(255)")
    op.execute("ALTER TABLE cappe_orders ADD COLUMN IF NOT EXISTS stripe_payment_intent VARCHAR(255)")
    op.execute("ALTER TABLE cappe_orders ADD COLUMN IF NOT EXISTS platform_fee_cents INTEGER")
    op.execute("ALTER TABLE cappe_orders ADD COLUMN IF NOT EXISTS paid_at TIMESTAMPTZ")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_orders_session "
        "ON cappe_orders(stripe_session_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_cappe_orders_session")
    op.execute("ALTER TABLE cappe_orders DROP COLUMN IF EXISTS paid_at")
    op.execute("ALTER TABLE cappe_orders DROP COLUMN IF EXISTS platform_fee_cents")
    op.execute("ALTER TABLE cappe_orders DROP COLUMN IF EXISTS stripe_payment_intent")
    op.execute("ALTER TABLE cappe_orders DROP COLUMN IF EXISTS stripe_session_id")
    op.execute("ALTER TABLE cappe_accounts DROP COLUMN IF EXISTS stripe_details_submitted")
    op.execute("ALTER TABLE cappe_accounts DROP COLUMN IF EXISTS stripe_charges_enabled")
    op.execute("ALTER TABLE cappe_accounts DROP COLUMN IF EXISTS stripe_account_id")
