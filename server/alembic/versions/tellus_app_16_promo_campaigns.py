"""tellus_app_16 — promo campaigns, single-use QR reward cards, per-store
scanner devices.

Brand mints a campaign with a global claim cap (tellus_links'
max_uses/use_count shape, renamed claim_count here since it's issuance not a
generic use counter). A consumer scanning the campaign QR claims exactly one
card (partial-unique (campaign_id, account_id) — one card per account per
campaign, race-safe at the DB). Staff redeem a card at the counter through a
per-store scanner device token (tellus_scanner_devices — no staff account
model exists in Tell-Us, so the device token IS the auth, same shape as
tellus_links authenticating a public intake flow rather than a person).

Deliberately NOT layered onto tellus_redemptions/tellus_reward_listings:
these cards are free (no points_cost), must never touch
tellus_points_ledger/tellus_points_balances, and reclaim_expired_redemptions'
"restore quantity_claimed on expiry" behavior is wrong here — claim_count is
a monotone issuance counter, never decremented by expiry or cancellation.

Table order matters: tellus_scanner_devices before tellus_promo_cards (the
cards table FK-references scanner devices for redeemed_scanner_id).

Revision ID: tellus_app_16
Revises: oceanlab_app_01
"""
from alembic import op

revision = "tellus_app_16"
down_revision = "oceanlab_app_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE TABLE IF NOT EXISTS tellus_promo_campaigns (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            brand_id UUID NOT NULL REFERENCES tellus_brands(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            description TEXT,
            reward_text TEXT NOT NULL,
            claim_token TEXT NOT NULL UNIQUE,
            max_claims INT NOT NULL CHECK (max_claims BETWEEN 1 AND 10000),
            claim_count INT NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','paused','cancelled')),
            card_expiry_days INT NOT NULL DEFAULT 30 CHECK (card_expiry_days BETWEEN 1 AND 365),
            starts_at TIMESTAMPTZ,
            ends_at TIMESTAMPTZ,
            design_json JSONB,
            flyer_image_url TEXT,
            cancelled_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )"""
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tellus_promo_campaigns_brand "
        "ON tellus_promo_campaigns (brand_id, created_at DESC)"
    )

    op.execute(
        """CREATE TABLE IF NOT EXISTS tellus_scanner_devices (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            brand_id UUID NOT NULL REFERENCES tellus_brands(id) ON DELETE CASCADE,
            store_id UUID NOT NULL REFERENCES tellus_stores(id) ON DELETE CASCADE,
            token TEXT NOT NULL UNIQUE,
            label TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            revoked_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )"""
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tellus_scanner_devices_brand "
        "ON tellus_scanner_devices (brand_id)"
    )

    op.execute(
        """CREATE TABLE IF NOT EXISTS tellus_promo_cards (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            campaign_id UUID NOT NULL REFERENCES tellus_promo_campaigns(id) ON DELETE CASCADE,
            account_id UUID NOT NULL REFERENCES tellus_accounts(id) ON DELETE CASCADE,
            card_token TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'issued' CHECK (status IN ('issued','redeemed','cancelled')),
            issued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMPTZ NOT NULL,
            redeemed_at TIMESTAMPTZ,
            redeemed_store_id UUID REFERENCES tellus_stores(id) ON DELETE SET NULL,
            redeemed_scanner_id UUID REFERENCES tellus_scanner_devices(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT ux_tellus_promo_cards_one_per_account UNIQUE (campaign_id, account_id)
        )"""
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tellus_promo_cards_account "
        "ON tellus_promo_cards (account_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tellus_promo_cards_campaign_status "
        "ON tellus_promo_cards (campaign_id, status)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS tellus_promo_cards")
    op.execute("DROP TABLE IF EXISTS tellus_scanner_devices")
    op.execute("DROP TABLE IF EXISTS tellus_promo_campaigns")
