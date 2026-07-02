"""Tell-Us standalone app — all tellus_* tables.

Tell-Us is its own app (rewards-for-feedback marketplace) running on the matcha
stack but with its OWN identity table + JWT scope, exactly like Cappe. Nothing
here touches matcha's tenant model; every row scopes by tellus account / brand.

Rooted on the matcha-line head (mlpricing04). The history has two permanent
branch heads (matcha + cappe); apply with `alembic upgrade heads`.

Revision ID: tellus_app_01
Revises: mlpricing04
Create Date: 2026-07-01
"""
from alembic import op


revision = "tellus_app_01"
down_revision = "mlpricing04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Identity & brands ───────────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tellus_accounts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            account_type TEXT NOT NULL DEFAULT 'consumer'
                CHECK (account_type IN ('consumer', 'brand')),
            display_name TEXT,
            city TEXT,
            state TEXT,
            latitude DOUBLE PRECISION,
            longitude DOUBLE PRECISION,
            county TEXT,
            geo_updated_at TIMESTAMPTZ,
            status TEXT NOT NULL DEFAULT 'active',
            -- Email-confirmation gate (mirrors cappe_accounts).
            email_verified_at TIMESTAMPTZ,
            verification_token UUID,
            verification_sent_at TIMESTAMPTZ,
            -- Session revocation watermark (server-side logout).
            tokens_valid_after TIMESTAMPTZ,
            leaderboard_opt_in BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_tellus_accounts_city ON tellus_accounts (lower(city), lower(state))")
    op.execute("CREATE INDEX IF NOT EXISTS ix_tellus_accounts_verif ON tellus_accounts (verification_token)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tellus_brands (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_account_id UUID NOT NULL REFERENCES tellus_accounts(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            logo_url TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_tellus_brands_owner ON tellus_brands (owner_account_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tellus_stores (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            brand_id UUID NOT NULL REFERENCES tellus_brands(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            address TEXT,
            city TEXT,
            state TEXT,
            zipcode TEXT,
            lat DOUBLE PRECISION,
            lng DOUBLE PRECISION,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_tellus_stores_brand ON tellus_stores (brand_id)")

    # ── Feedback + media ────────────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tellus_links (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            brand_id UUID NOT NULL REFERENCES tellus_brands(id) ON DELETE CASCADE,
            store_id UUID REFERENCES tellus_stores(id) ON DELETE CASCADE,
            token TEXT NOT NULL UNIQUE,
            label TEXT,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            revoked_at TIMESTAMPTZ,
            use_count INTEGER NOT NULL DEFAULT 0,
            max_uses INTEGER,
            expires_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_tellus_links_brand ON tellus_links (brand_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_tellus_links_store ON tellus_links (store_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tellus_link_history (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            link_id UUID NOT NULL REFERENCES tellus_links(id) ON DELETE CASCADE,
            action TEXT NOT NULL,
            actor_account_id UUID REFERENCES tellus_accounts(id) ON DELETE SET NULL,
            actor_ip TEXT,
            detail TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_tellus_link_history_link ON tellus_link_history (link_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tellus_reports (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            brand_id UUID NOT NULL REFERENCES tellus_brands(id) ON DELETE CASCADE,
            store_id UUID REFERENCES tellus_stores(id) ON DELETE SET NULL,
            link_id UUID REFERENCES tellus_links(id) ON DELETE SET NULL,
            report_number TEXT,
            category TEXT NOT NULL DEFAULT 'other'
                CHECK (category IN ('service', 'cleanliness', 'facilities', 'safety', 'compliment', 'other')),
            sentiment TEXT NOT NULL DEFAULT 'neutral'
                CHECK (sentiment IN ('positive', 'neutral', 'negative')),
            title TEXT,
            description TEXT,
            occurred_at TIMESTAMPTZ,
            reporter_account_id UUID REFERENCES tellus_accounts(id) ON DELETE SET NULL,
            reporter_contact TEXT,
            usefulness_score INTEGER NOT NULL DEFAULT 0,
            points_awarded INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'new'
                CHECK (status IN ('new', 'reviewing', 'resolved', 'archived')),
            ai_summary TEXT,
            ai_category TEXT,
            ai_sentiment TEXT,
            -- Moderation (review finding G): hide abusive UGC pending takedown.
            moderation_status TEXT NOT NULL DEFAULT 'visible'
                CHECK (moderation_status IN ('visible', 'flagged', 'removed')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_tellus_reports_brand ON tellus_reports (brand_id, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_tellus_reports_store ON tellus_reports (store_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_tellus_reports_reporter ON tellus_reports (reporter_account_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tellus_report_media (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            report_id UUID NOT NULL REFERENCES tellus_reports(id) ON DELETE CASCADE,
            media_type TEXT NOT NULL CHECK (media_type IN ('photo', 'video')),
            storage_path TEXT NOT NULL,
            mime_type TEXT,
            file_size BIGINT,
            original_filename TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_tellus_report_media_report ON tellus_report_media (report_id)")

    # ── Rewards economy ─────────────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tellus_points_balances (
            account_id UUID PRIMARY KEY REFERENCES tellus_accounts(id) ON DELETE CASCADE,
            points_balance INTEGER NOT NULL DEFAULT 0,
            lifetime_points INTEGER NOT NULL DEFAULT 0,
            level INTEGER NOT NULL DEFAULT 1,
            current_streak INTEGER NOT NULL DEFAULT 0,
            longest_streak INTEGER NOT NULL DEFAULT 0,
            last_activity_date DATE,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tellus_points_ledger (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            account_id UUID NOT NULL REFERENCES tellus_accounts(id) ON DELETE CASCADE,
            delta INTEGER NOT NULL,
            balance_after INTEGER NOT NULL,
            reason TEXT NOT NULL
                CHECK (reason IN ('earn_feedback', 'earn_engagement', 'earn_grant',
                                  'redeem', 'swap', 'adjustment', 'expire')),
            reference_type TEXT,
            reference_id TEXT,
            description TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_tellus_ledger_account ON tellus_points_ledger (account_id, created_at DESC)")
    # Idempotency: one credit per (account, reason, reference) — replaying the
    # same feedback/redemption can't double-credit. NULL reference_id rows
    # (manual adjustments) are exempt (Postgres treats NULLs as distinct).
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_tellus_ledger_idem "
        "ON tellus_points_ledger (account_id, reason, reference_id) "
        "WHERE reference_id IS NOT NULL"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tellus_earning_rules (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            event_key TEXT NOT NULL UNIQUE,
            points INTEGER NOT NULL DEFAULT 0,
            daily_cap INTEGER,
            cooldown_seconds INTEGER,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tellus_badge_definitions (
            key TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            icon TEXT,
            criteria JSONB NOT NULL DEFAULT '{}'::jsonb,
            sort_order INTEGER NOT NULL DEFAULT 0
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tellus_user_badges (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            account_id UUID NOT NULL REFERENCES tellus_accounts(id) ON DELETE CASCADE,
            badge_key TEXT NOT NULL REFERENCES tellus_badge_definitions(key) ON DELETE CASCADE,
            awarded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (account_id, badge_key)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_tellus_user_badges_account ON tellus_user_badges (account_id)")

    # ── City marketplace ────────────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tellus_reward_listings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            brand_id UUID REFERENCES tellus_brands(id) ON DELETE CASCADE,
            city TEXT,
            state TEXT,
            title TEXT NOT NULL,
            description TEXT,
            image_url TEXT,
            points_cost INTEGER NOT NULL CHECK (points_cost >= 0),
            quantity_total INTEGER,
            quantity_claimed INTEGER NOT NULL DEFAULT 0,
            redemption_type TEXT NOT NULL DEFAULT 'code'
                CHECK (redemption_type IN ('code', 'qr', 'manual')),
            terms TEXT,
            active_from TIMESTAMPTZ,
            active_to TIMESTAMPTZ,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_tellus_listings_city ON tellus_reward_listings (lower(city), lower(state)) WHERE is_active")
    op.execute("CREATE INDEX IF NOT EXISTS ix_tellus_listings_brand ON tellus_reward_listings (brand_id)")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tellus_redemptions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            account_id UUID NOT NULL REFERENCES tellus_accounts(id) ON DELETE CASCADE,
            listing_id UUID NOT NULL REFERENCES tellus_reward_listings(id) ON DELETE CASCADE,
            points_spent INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'issued'
                CHECK (status IN ('pending', 'issued', 'redeemed', 'expired', 'cancelled')),
            code TEXT,
            issued_at TIMESTAMPTZ,
            redeemed_at TIMESTAMPTZ,
            expires_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_tellus_redemptions_account ON tellus_redemptions (account_id, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_tellus_redemptions_listing ON tellus_redemptions (listing_id)")

    # ── In-app notifications (tellus-native — matcha's mw_notifications FK users)
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tellus_notifications (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            account_id UUID NOT NULL REFERENCES tellus_accounts(id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT,
            reference_type TEXT,
            reference_id TEXT,
            is_read BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_tellus_notifications_account ON tellus_notifications (account_id, is_read, created_at DESC)")

    # ── Seed earning rules + badges (idempotent) ────────────────────────────
    op.execute(
        """
        INSERT INTO tellus_earning_rules (event_key, points, daily_cap, cooldown_seconds, is_active)
        VALUES
            ('useful_feedback', 50, 500, 60, TRUE),
            ('feedback_with_media', 25, 250, 60, TRUE),
            ('first_feedback', 100, NULL, NULL, TRUE),
            ('daily_login', 10, 10, 72000, TRUE)
        ON CONFLICT (event_key) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO tellus_badge_definitions (key, name, description, icon, criteria, sort_order)
        VALUES
            ('first_feedback', 'First Word', 'Submitted your first piece of feedback.', 'message-circle',
             '{"type": "feedback_count", "threshold": 1}'::jsonb, 1),
            ('feedback_10', 'Regular', 'Submitted 10 pieces of feedback.', 'messages-square',
             '{"type": "feedback_count", "threshold": 10}'::jsonb, 2),
            ('feedback_50', 'Voice of the City', 'Submitted 50 pieces of feedback.', 'megaphone',
             '{"type": "feedback_count", "threshold": 50}'::jsonb, 3),
            ('streak_7', 'On a Roll', 'Kept a 7-day feedback streak.', 'flame',
             '{"type": "streak", "threshold": 7}'::jsonb, 4),
            ('streak_30', 'Unstoppable', 'Kept a 30-day feedback streak.', 'zap',
             '{"type": "streak", "threshold": 30}'::jsonb, 5),
            ('first_redeem', 'Treat Yourself', 'Redeemed your first reward.', 'gift',
             '{"type": "redeem_count", "threshold": 1}'::jsonb, 6),
            ('level_5', 'Rising Star', 'Reached level 5.', 'star',
             '{"type": "level", "threshold": 5}'::jsonb, 7),
            ('level_10', 'Local Legend', 'Reached level 10.', 'crown',
             '{"type": "level", "threshold": 10}'::jsonb, 8)
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade() -> None:
    for tbl in (
        "tellus_notifications",
        "tellus_redemptions",
        "tellus_reward_listings",
        "tellus_user_badges",
        "tellus_badge_definitions",
        "tellus_earning_rules",
        "tellus_points_ledger",
        "tellus_points_balances",
        "tellus_report_media",
        "tellus_reports",
        "tellus_link_history",
        "tellus_links",
        "tellus_stores",
        "tellus_brands",
        "tellus_accounts",
    ):
        op.execute(f"DROP TABLE IF EXISTS {tbl} CASCADE")
