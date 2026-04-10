"""Add paid channels: schema changes for channel subscriptions and inactivity.

Revision ID: zzj0k1l2m3n4
Revises: zzi9j0k1l2m3
Create Date: 2026-04-09
"""
from alembic import op

revision = "zzj0k1l2m3n4"
down_revision = "zzi9j0k1l2m3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── channels table: paid channel settings ──
    op.execute("""
        ALTER TABLE channels
            ADD COLUMN IF NOT EXISTS is_paid boolean NOT NULL DEFAULT false,
            ADD COLUMN IF NOT EXISTS price_cents integer,
            ADD COLUMN IF NOT EXISTS currency text NOT NULL DEFAULT 'usd',
            ADD COLUMN IF NOT EXISTS inactivity_threshold_days integer,
            ADD COLUMN IF NOT EXISTS inactivity_warning_days integer NOT NULL DEFAULT 3,
            ADD COLUMN IF NOT EXISTS stripe_product_id text,
            ADD COLUMN IF NOT EXISTS stripe_price_id text
    """)

    # ── channel_members table: subscription + activity tracking ──
    op.execute("""
        ALTER TABLE channel_members
            ADD COLUMN IF NOT EXISTS last_contributed_at timestamptz,
            ADD COLUMN IF NOT EXISTS stripe_subscription_id text,
            ADD COLUMN IF NOT EXISTS subscription_status text,
            ADD COLUMN IF NOT EXISTS paid_through timestamptz,
            ADD COLUMN IF NOT EXISTS removed_for_inactivity boolean NOT NULL DEFAULT false,
            ADD COLUMN IF NOT EXISTS removal_cooldown_until timestamptz,
            ADD COLUMN IF NOT EXISTS inactivity_warned_at timestamptz
    """)

    # Initialize last_contributed_at for existing members
    op.execute("""
        UPDATE channel_members
        SET last_contributed_at = joined_at
        WHERE last_contributed_at IS NULL
    """)

    # ── channel_payment_events table ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS channel_payment_events (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            channel_id uuid NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            event_type text NOT NULL,
            amount_cents integer DEFAULT 0,
            stripe_event_id text,
            metadata jsonb DEFAULT '{}',
            created_at timestamptz NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_channel_payment_events_channel
        ON channel_payment_events(channel_id, created_at DESC)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_channel_payment_events_user
        ON channel_payment_events(user_id, created_at DESC)
    """)

    # Index for inactivity worker queries
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_channel_members_activity
        ON channel_members(channel_id, last_contributed_at)
        WHERE last_contributed_at IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS channel_payment_events")
    op.execute("""
        ALTER TABLE channel_members
            DROP COLUMN IF EXISTS last_contributed_at,
            DROP COLUMN IF EXISTS stripe_subscription_id,
            DROP COLUMN IF EXISTS subscription_status,
            DROP COLUMN IF EXISTS paid_through,
            DROP COLUMN IF EXISTS removed_for_inactivity,
            DROP COLUMN IF EXISTS removal_cooldown_until,
            DROP COLUMN IF EXISTS inactivity_warned_at
    """)
    op.execute("""
        ALTER TABLE channels
            DROP COLUMN IF EXISTS is_paid,
            DROP COLUMN IF EXISTS price_cents,
            DROP COLUMN IF EXISTS currency,
            DROP COLUMN IF EXISTS inactivity_threshold_days,
            DROP COLUMN IF EXISTS inactivity_warning_days,
            DROP COLUMN IF EXISTS stripe_product_id,
            DROP COLUMN IF EXISTS stripe_price_id
    """)
