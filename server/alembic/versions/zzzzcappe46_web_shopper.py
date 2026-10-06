"""Cappe — shopper accounts and subscriptions on the web storefront.

Shopper sign-in and subscriptions existed only in the white-label iOS app.
The storefront now has an `/account` page and a "Subscribe" button; nothing
about shoppers, sessions or subscriptions changes shape for that.

`cappe_accounts.stripe_portal_config_id` — the Stripe customer-portal
configuration created on a store's connected account the first time one of
its shoppers asks to update their card (card updates and invoices only;
cancelling stays on our own endpoints so our records stay authoritative).
Created once and reused, rather than one per visit.

Additive + idempotent.

Revision ID: zzzzcappe46
Revises: zzzzcappe45
"""
from alembic import op

revision = "zzzzcappe46"
down_revision = "zzzzcappe45"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE cappe_accounts ADD COLUMN IF NOT EXISTS stripe_portal_config_id VARCHAR(255)")


def downgrade() -> None:
    op.execute("ALTER TABLE cappe_accounts DROP COLUMN IF EXISTS stripe_portal_config_id")
