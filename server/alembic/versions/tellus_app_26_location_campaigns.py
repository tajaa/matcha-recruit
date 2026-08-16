"""tellus_app_26 — location-scoped promo campaigns.

Location campaigns use a store's geocoded coordinates as their anchor. They
are pushed explicitly to followers whose recently reported device location is
inside the configured radius, and the same radius is enforced when claiming.
"""
from alembic import op


revision = "tellus_app_26"
down_revision = "tellus_app_25"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """ALTER TABLE tellus_promo_campaigns
           ADD COLUMN IF NOT EXISTS campaign_type TEXT NOT NULL DEFAULT 'qr'
             CHECK (campaign_type IN ('qr', 'location'))"""
    )
    op.execute(
        """ALTER TABLE tellus_promo_campaigns
           ADD COLUMN IF NOT EXISTS store_id UUID
             REFERENCES tellus_stores(id) ON DELETE SET NULL"""
    )
    op.execute(
        """ALTER TABLE tellus_promo_campaigns
           ADD COLUMN IF NOT EXISTS radius_miles DOUBLE PRECISION
             CHECK (radius_miles IS NULL OR radius_miles > 0 AND radius_miles <= 10)"""
    )
    op.execute(
        """ALTER TABLE tellus_promo_campaigns
           ADD COLUMN IF NOT EXISTS push_sent_at TIMESTAMPTZ"""
    )
    op.execute(
        """ALTER TABLE tellus_promo_campaigns
           ADD COLUMN IF NOT EXISTS push_sent_count INTEGER NOT NULL DEFAULT 0
             CHECK (push_sent_count >= 0)"""
    )
    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_tellus_promo_campaigns_store
           ON tellus_promo_campaigns (store_id)
           WHERE store_id IS NOT NULL"""
    )

    op.execute(
        """ALTER TABLE tellus_device_tokens
           ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION,
           ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION,
           ADD COLUMN IF NOT EXISTS location_updated_at TIMESTAMPTZ"""
    )
    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_tellus_device_tokens_location
           ON tellus_device_tokens (account_id, location_updated_at DESC)
           WHERE latitude IS NOT NULL AND longitude IS NOT NULL"""
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_tellus_device_tokens_location")
    op.execute(
        """ALTER TABLE tellus_device_tokens
           DROP COLUMN IF EXISTS location_updated_at,
           DROP COLUMN IF EXISTS longitude,
           DROP COLUMN IF EXISTS latitude"""
    )
    op.execute("DROP INDEX IF EXISTS ix_tellus_promo_campaigns_store")
    op.execute(
        """ALTER TABLE tellus_promo_campaigns
           DROP COLUMN IF EXISTS push_sent_count,
           DROP COLUMN IF EXISTS push_sent_at,
           DROP COLUMN IF EXISTS radius_miles,
           DROP COLUMN IF EXISTS store_id,
           DROP COLUMN IF EXISTS campaign_type"""
    )
