"""Partial UNIQUE indexes on Stripe IDs for paid channels.

Catches double-create orphans:
- channels.stripe_product_id  — re-running create_stripe_product_and_price
  (e.g. failure between Stripe call and DB UPDATE) leaves an orphan Stripe
  product. UNIQUE prevents the DB-side overwrite from masking the issue.
- channel_members.stripe_subscription_id — one subscription per (channel,
  member). Prevents the activation handler from silently overwriting an
  existing sub-id when the same user re-subscribes during cancel period
  (defense in depth — the route gate at channels.py blocks this case too).
- channel_job_postings.stripe_subscription_id — same logic for postings.

All three columns are nullable; partial UNIQUE on `WHERE col IS NOT NULL`
keeps the constraint compatible with rows that haven't been activated yet.

Revision ID: zzzv8w9x0y1z2
Revises: zzzu7v8w9x0y1
Create Date: 2026-05-03

"""
from alembic import op


revision = "zzzv8w9x0y1z2"
down_revision = "zzzu7v8w9x0y1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_channels_stripe_product_id_unique
          ON channels(stripe_product_id)
          WHERE stripe_product_id IS NOT NULL;
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_channel_members_stripe_subscription_id_unique
          ON channel_members(stripe_subscription_id)
          WHERE stripe_subscription_id IS NOT NULL;
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_channel_job_postings_stripe_subscription_id_unique
          ON channel_job_postings(stripe_subscription_id)
          WHERE stripe_subscription_id IS NOT NULL;
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_channel_job_postings_stripe_subscription_id_unique")
    op.execute("DROP INDEX IF EXISTS idx_channel_members_stripe_subscription_id_unique")
    op.execute("DROP INDEX IF EXISTS idx_channels_stripe_product_id_unique")
