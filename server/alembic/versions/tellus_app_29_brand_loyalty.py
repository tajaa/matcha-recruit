"""Tell-Us per-brand loyalty programs.

This is a parallel economy. It deliberately does not alter the global
``tellus_points_*`` tables or marketplace redemption tables.
"""
from alembic import op


revision = "tellus_app_29"
down_revision = "tellus_app_28"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_tellus_stores_id_brand "
        "ON tellus_stores (id, brand_id)"
    )

    op.execute(
        """CREATE TABLE IF NOT EXISTS tellus_loyalty_programs (
            brand_id UUID PRIMARY KEY REFERENCES tellus_brands(id) ON DELETE CASCADE,
            name TEXT NOT NULL DEFAULT 'Rewards',
            point_singular TEXT NOT NULL DEFAULT 'point',
            point_plural TEXT NOT NULL DEFAULT 'points',
            terms TEXT,
            status TEXT NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft', 'active', 'paused')),
            counter_mode TEXT NOT NULL DEFAULT 'purchase'
                CHECK (counter_mode IN ('visit', 'purchase')),
            activated_at TIMESTAMPTZ,
            created_by UUID REFERENCES tellus_accounts(id) ON DELETE SET NULL,
            updated_by UUID REFERENCES tellus_accounts(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_tellus_loyalty_program_activation CHECK (
                (status = 'draft' AND activated_at IS NULL)
                OR (status IN ('active', 'paused') AND activated_at IS NOT NULL)
            )
        )"""
    )

    op.execute(
        """CREATE TABLE IF NOT EXISTS tellus_loyalty_earning_rules (
            brand_id UUID NOT NULL
                REFERENCES tellus_loyalty_programs(brand_id) ON DELETE CASCADE,
            event_key TEXT NOT NULL CHECK (
                event_key IN (
                    'visit', 'purchase', 'review',
                    'board_reply', 'follow', 'social_post'
                )
            ),
            award_type TEXT NOT NULL CHECK (award_type IN ('fixed', 'per_dollar')),
            fixed_points INTEGER,
            points_per_dollar INTEGER,
            min_purchase_cents INTEGER,
            max_points_per_event INTEGER,
            daily_cap INTEGER,
            cooldown_seconds INTEGER,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (brand_id, event_key),
            CONSTRAINT ck_tellus_loyalty_rule_shape CHECK (
                (
                    event_key = 'purchase'
                    AND award_type = 'per_dollar'
                    AND fixed_points IS NULL
                    AND points_per_dollar BETWEEN 1 AND 100
                    AND min_purchase_cents BETWEEN 1 AND 1000000
                    AND max_points_per_event BETWEEN 1 AND 100000
                )
                OR (
                    event_key <> 'purchase'
                    AND award_type = 'fixed'
                    AND fixed_points BETWEEN 1 AND 100000
                    AND points_per_dollar IS NULL
                    AND min_purchase_cents IS NULL
                    AND max_points_per_event IS NULL
                )
            ),
            CONSTRAINT ck_tellus_loyalty_rule_cap
                CHECK (daily_cap IS NULL OR daily_cap BETWEEN 1 AND 1000000),
            CONSTRAINT ck_tellus_loyalty_rule_cooldown
                CHECK (cooldown_seconds IS NULL OR cooldown_seconds BETWEEN 0 AND 2592000)
        )"""
    )

    op.execute(
        """CREATE TABLE IF NOT EXISTS tellus_loyalty_tiers (
            brand_id UUID NOT NULL
                REFERENCES tellus_loyalty_programs(brand_id) ON DELETE CASCADE,
            tier_key TEXT NOT NULL CHECK (tier_key IN ('bronze', 'silver', 'gold')),
            threshold_points INTEGER NOT NULL CHECK (threshold_points >= 0),
            benefits TEXT CHECK (benefits IS NULL OR char_length(benefits) <= 2000),
            sort_order SMALLINT NOT NULL,
            PRIMARY KEY (brand_id, tier_key),
            UNIQUE (brand_id, threshold_points),
            UNIQUE (brand_id, sort_order)
        )"""
    )

    op.execute(
        """CREATE TABLE IF NOT EXISTS tellus_loyalty_balances (
            brand_id UUID NOT NULL
                REFERENCES tellus_loyalty_programs(brand_id) ON DELETE CASCADE,
            account_id UUID NOT NULL
                REFERENCES tellus_accounts(id) ON DELETE CASCADE,
            points_balance INTEGER NOT NULL DEFAULT 0 CHECK (points_balance >= 0),
            lifetime_points INTEGER NOT NULL DEFAULT 0 CHECK (lifetime_points >= 0),
            enrolled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (brand_id, account_id),
            CHECK (points_balance <= lifetime_points)
        )"""
    )
    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_tellus_loyalty_balances_account
           ON tellus_loyalty_balances (account_id, updated_at DESC)"""
    )

    op.execute(
        """CREATE TABLE IF NOT EXISTS tellus_loyalty_member_qr_sessions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            brand_id UUID NOT NULL
                REFERENCES tellus_loyalty_programs(brand_id) ON DELETE CASCADE,
            account_id UUID NOT NULL REFERENCES tellus_accounts(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL UNIQUE CHECK (token_hash ~ '^[0-9a-f]{64}$'),
            expires_at TIMESTAMPTZ NOT NULL,
            consumed_at TIMESTAMPTZ,
            consumed_store_id UUID,
            consumed_event_key TEXT CHECK (consumed_event_key IN ('visit', 'purchase')),
            consumed_by_account_id UUID REFERENCES tellus_accounts(id) ON DELETE SET NULL,
            consumed_scanner_id UUID REFERENCES tellus_scanner_devices(id) ON DELETE SET NULL,
            purchase_amount_cents INTEGER,
            awarded_points INTEGER NOT NULL DEFAULT 0 CHECK (awarded_points >= 0),
            balance_after INTEGER,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_tellus_loyalty_qr_consumption CHECK (
                (consumed_at IS NULL AND consumed_store_id IS NULL
                 AND consumed_event_key IS NULL AND consumed_by_account_id IS NULL
                 AND consumed_scanner_id IS NULL AND purchase_amount_cents IS NULL
                 AND balance_after IS NULL)
                OR
                (consumed_at IS NOT NULL AND consumed_store_id IS NOT NULL
                 AND consumed_event_key IS NOT NULL
                 AND num_nonnulls(consumed_by_account_id, consumed_scanner_id) = 1
                 AND balance_after IS NOT NULL)
            ),
            CONSTRAINT ck_tellus_loyalty_qr_purchase CHECK (
                (consumed_event_key = 'purchase'
                 AND consumed_by_account_id IS NOT NULL
                 AND consumed_scanner_id IS NULL
                 AND purchase_amount_cents BETWEEN 1 AND 1000000)
                OR consumed_event_key IS DISTINCT FROM 'purchase'
            )
        )"""
    )
    op.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS ux_tellus_loyalty_qr_unconsumed
           ON tellus_loyalty_member_qr_sessions (brand_id, account_id)
           WHERE consumed_at IS NULL"""
    )
    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_tellus_loyalty_qr_account_expiry
           ON tellus_loyalty_member_qr_sessions (account_id, expires_at DESC)"""
    )

    op.execute(
        """CREATE TABLE IF NOT EXISTS tellus_loyalty_rewards (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            brand_id UUID NOT NULL
                REFERENCES tellus_loyalty_programs(brand_id) ON DELETE CASCADE,
            title TEXT NOT NULL CHECK (char_length(btrim(title)) BETWEEN 1 AND 255),
            description TEXT CHECK (description IS NULL OR char_length(description) <= 4000),
            terms TEXT CHECK (terms IS NULL OR char_length(terms) <= 4000),
            points_cost INTEGER NOT NULL CHECK (points_cost BETWEEN 1 AND 1000000),
            redemption_expiry_days INTEGER NOT NULL DEFAULT 30
                CHECK (redemption_expiry_days BETWEEN 1 AND 365),
            active_from TIMESTAMPTZ,
            active_to TIMESTAMPTZ,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_by UUID REFERENCES tellus_accounts(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (id, brand_id),
            CHECK (active_to IS NULL OR active_from IS NULL OR active_to > active_from)
        )"""
    )
    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_tellus_loyalty_rewards_brand
           ON tellus_loyalty_rewards (brand_id, is_active, created_at DESC)"""
    )

    op.execute(
        """CREATE TABLE IF NOT EXISTS tellus_loyalty_redemptions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            brand_id UUID NOT NULL,
            account_id UUID NOT NULL REFERENCES tellus_accounts(id) ON DELETE CASCADE,
            reward_id UUID NOT NULL,
            client_request_id UUID NOT NULL,
            token TEXT NOT NULL UNIQUE,
            reward_title TEXT NOT NULL,
            points_spent INTEGER NOT NULL CHECK (points_spent > 0),
            status TEXT NOT NULL DEFAULT 'issued'
                CHECK (status IN ('issued', 'redeemed')),
            issued_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMPTZ NOT NULL,
            redeemed_at TIMESTAMPTZ,
            redeemed_store_id UUID,
            redeemed_by_account_id UUID REFERENCES tellus_accounts(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            FOREIGN KEY (reward_id, brand_id)
                REFERENCES tellus_loyalty_rewards(id, brand_id),
            UNIQUE (brand_id, account_id, client_request_id),
            CHECK (
                (status = 'issued' AND redeemed_at IS NULL)
                OR (status = 'redeemed' AND redeemed_at IS NOT NULL)
            )
        )"""
    )
    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_tellus_loyalty_redemptions_account
           ON tellus_loyalty_redemptions (account_id, created_at DESC)"""
    )
    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_tellus_loyalty_redemptions_brand_status
           ON tellus_loyalty_redemptions (brand_id, status, created_at DESC)"""
    )

    op.execute(
        """CREATE TABLE IF NOT EXISTS tellus_loyalty_social_submissions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            brand_id UUID NOT NULL
                REFERENCES tellus_loyalty_programs(brand_id) ON DELETE CASCADE,
            account_id UUID NOT NULL REFERENCES tellus_accounts(id) ON DELETE CASCADE,
            platform TEXT NOT NULL
                CHECK (platform IN ('instagram', 'tiktok', 'youtube', 'facebook', 'x', 'other')),
            post_url TEXT NOT NULL CHECK (char_length(post_url) <= 2048),
            canonical_url TEXT NOT NULL CHECK (char_length(canonical_url) <= 2048),
            note TEXT CHECK (note IS NULL OR char_length(note) <= 1000),
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'approved', 'rejected', 'withdrawn')),
            decision_note TEXT CHECK (decision_note IS NULL OR char_length(decision_note) <= 1000),
            decided_at TIMESTAMPTZ,
            decided_by UUID REFERENCES tellus_accounts(id) ON DELETE SET NULL,
            awarded_points INTEGER NOT NULL DEFAULT 0 CHECK (awarded_points >= 0),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CHECK (
                (status IN ('approved', 'rejected') AND decided_at IS NOT NULL)
                OR (status IN ('pending', 'withdrawn') AND decided_at IS NULL)
            )
        )"""
    )
    op.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS ux_tellus_loyalty_social_url
           ON tellus_loyalty_social_submissions (brand_id, canonical_url)"""
    )
    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_tellus_loyalty_social_queue
           ON tellus_loyalty_social_submissions (brand_id, status, created_at)"""
    )

    # The ledger is created last because it references balances, stores, and
    # scanner devices. Keeping this table separate from the global ledger is a
    # deliberate product boundary.
    op.execute(
        """CREATE TABLE IF NOT EXISTS tellus_loyalty_ledger (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            brand_id UUID NOT NULL,
            account_id UUID NOT NULL,
            delta INTEGER NOT NULL CHECK (delta <> 0),
            balance_after INTEGER NOT NULL CHECK (balance_after >= 0),
            reason TEXT NOT NULL CHECK (
                reason IN (
                    'earn_visit', 'earn_purchase', 'earn_review',
                    'earn_board_reply', 'earn_follow', 'earn_social_post',
                    'redeem'
                )
            ),
            event_key TEXT,
            reference_type TEXT NOT NULL,
            reference_id TEXT NOT NULL,
            source_store_id UUID,
            actor_account_id UUID REFERENCES tellus_accounts(id) ON DELETE SET NULL,
            scanner_device_id UUID REFERENCES tellus_scanner_devices(id) ON DELETE SET NULL,
            purchase_amount_cents INTEGER,
            description TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            FOREIGN KEY (brand_id, account_id)
                REFERENCES tellus_loyalty_balances(brand_id, account_id)
                ON DELETE CASCADE,
            FOREIGN KEY (source_store_id, brand_id)
                REFERENCES tellus_stores(id, brand_id)
                ON DELETE SET NULL (source_store_id),
            UNIQUE (brand_id, account_id, reason, reference_id)
        )"""
    )
    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_tellus_loyalty_ledger_account
           ON tellus_loyalty_ledger (brand_id, account_id, created_at DESC)"""
    )
    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_tellus_loyalty_ledger_event
           ON tellus_loyalty_ledger (brand_id, account_id, event_key, created_at DESC)
           WHERE event_key IS NOT NULL"""
    )
    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_tellus_loyalty_ledger_store
           ON tellus_loyalty_ledger (brand_id, source_store_id, created_at DESC)
           WHERE source_store_id IS NOT NULL"""
    )
    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_tellus_loyalty_ledger_actor
           ON tellus_loyalty_ledger (brand_id, actor_account_id, created_at DESC)
           WHERE actor_account_id IS NOT NULL"""
    )


def downgrade() -> None:
    for table in (
        "tellus_loyalty_ledger",
        "tellus_loyalty_social_submissions",
        "tellus_loyalty_redemptions",
        "tellus_loyalty_rewards",
        "tellus_loyalty_member_qr_sessions",
        "tellus_loyalty_balances",
        "tellus_loyalty_tiers",
        "tellus_loyalty_earning_rules",
        "tellus_loyalty_programs",
    ):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
    op.execute("DROP INDEX IF EXISTS ux_tellus_stores_id_brand")
