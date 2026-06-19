"""cappe: domain renewals + transfer-out support

- cappe_domains.stripe_customer_id: the Stripe Customer saved at purchase (card
  on file) so the renewal cron can charge off-session.
- cappe_domains.transfer_requested_at: set when a tenant requests transfer-out
  (we provide the auth code manually — Porkbun has no auth-code API).

Both additive + nullable.

Revision ID: zzzzcappe20
Revises: zzzzcappe19
Create Date: 2026-06-18
"""
from alembic import op

revision = "zzzzcappe20"
down_revision = "zzzzcappe19"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE cappe_domains ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT")
    op.execute("ALTER TABLE cappe_domains ADD COLUMN IF NOT EXISTS transfer_requested_at TIMESTAMPTZ")


def downgrade() -> None:
    op.execute("ALTER TABLE cappe_domains DROP COLUMN IF EXISTS transfer_requested_at")
    op.execute("ALTER TABLE cappe_domains DROP COLUMN IF EXISTS stripe_customer_id")
