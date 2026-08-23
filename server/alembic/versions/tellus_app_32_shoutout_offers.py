"""Tell-Us shoutout offers layered onto the radar mention queue."""
from alembic import op


revision = "tellus_app_32"
down_revision = "tellus_app_31"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE tellus_shoutout_configs ADD COLUMN IF NOT EXISTS require_app_install BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("ALTER TABLE tellus_promo_campaigns DROP CONSTRAINT IF EXISTS tellus_promo_campaigns_campaign_type_check")
    op.execute("""ALTER TABLE tellus_promo_campaigns ADD CONSTRAINT tellus_promo_campaigns_campaign_type_check
        CHECK (campaign_type IN ('qr', 'location', 'shoutout'))""")
    op.execute("""CREATE TABLE IF NOT EXISTS tellus_shoutout_offers (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        brand_id UUID NOT NULL REFERENCES tellus_brands(id) ON DELETE CASCADE,
        mention_id UUID NOT NULL REFERENCES tellus_shoutout_mentions(id) ON DELETE CASCADE,
        campaign_id UUID NOT NULL REFERENCES tellus_promo_campaigns(id) ON DELETE CASCADE,
        store_id UUID REFERENCES tellus_stores(id) ON DELETE SET NULL,
        offer_token TEXT NOT NULL UNIQUE,
        short_code TEXT NOT NULL UNIQUE,
        reward_text TEXT NOT NULL,
        offer_terms TEXT,
        status TEXT NOT NULL DEFAULT 'sent' CHECK (status IN ('sent', 'claimed', 'revoked')),
        claim_expires_at TIMESTAMPTZ NOT NULL,
        claimed_account_id UUID REFERENCES tellus_accounts(id) ON DELETE SET NULL,
        claimed_at TIMESTAMPTZ,
        card_token TEXT,
        client_request_id UUID NOT NULL,
        created_by UUID REFERENCES tellus_accounts(id) ON DELETE SET NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")
    op.execute("""ALTER TABLE tellus_shoutout_mentions
        ADD CONSTRAINT fk_tellus_shoutout_mentions_offer
        FOREIGN KEY (offer_id) REFERENCES tellus_shoutout_offers(id) ON DELETE SET NULL""")
    op.execute("""CREATE INDEX IF NOT EXISTS ix_tellus_shoutout_offers_brand
        ON tellus_shoutout_offers (brand_id, created_at DESC)""")
    op.execute("""CREATE UNIQUE INDEX IF NOT EXISTS ux_tellus_shoutout_offer_mention_live
        ON tellus_shoutout_offers (mention_id) WHERE status <> 'revoked'""")
    op.execute("""CREATE UNIQUE INDEX IF NOT EXISTS ux_tellus_shoutout_offer_request
        ON tellus_shoutout_offers (brand_id, client_request_id)""")


def downgrade() -> None:
    op.execute("ALTER TABLE tellus_shoutout_mentions DROP CONSTRAINT IF EXISTS fk_tellus_shoutout_mentions_offer")
    op.execute("DROP INDEX IF EXISTS ux_tellus_shoutout_offer_request")
    op.execute("DROP INDEX IF EXISTS ux_tellus_shoutout_offer_mention_live")
    op.execute("DROP TABLE IF EXISTS tellus_shoutout_offers")
    op.execute("UPDATE tellus_promo_campaigns SET campaign_type='qr' WHERE campaign_type='shoutout'")
    op.execute("ALTER TABLE tellus_promo_campaigns DROP CONSTRAINT IF EXISTS tellus_promo_campaigns_campaign_type_check")
    op.execute("""ALTER TABLE tellus_promo_campaigns ADD CONSTRAINT tellus_promo_campaigns_campaign_type_check
        CHECK (campaign_type IN ('qr', 'location'))""")
    op.execute("ALTER TABLE tellus_shoutout_configs DROP COLUMN IF EXISTS require_app_install")
