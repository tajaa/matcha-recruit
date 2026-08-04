"""cappe: creator marketplace — profiles, collab offers, payments

Third Cappe account type ('creator') plus the full brand<->creator collab
pipeline: public creator profiles (socials/portfolio/rate cards), negotiable
offers with immutable per-revision terms snapshots, materialized deliverables
and installment payments, offer chat, and admin-tunable marketplace settings.

Creator-first protections baked into the settings seed: `auto_approve_days`
(brand silence auto-approves a submitted deliverable so the creator still
gets paid) alongside the existing `collab_fee_bps` / `min_offer_cents` knobs.

All DDL IF NOT EXISTS style, matching zzzzcappe10_reviews.py.

Revision ID: zzzzcappe28
Revises: zzzzcappe27
Create Date: 2026-08-03
"""
from alembic import op

revision = "zzzzcappe28"
down_revision = "zzzzcappe27"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Third account type -------------------------------------------------
    op.execute("ALTER TABLE cappe_accounts DROP CONSTRAINT IF EXISTS cappe_accounts_account_type_check")
    op.execute(
        "ALTER TABLE cappe_accounts ADD CONSTRAINT cappe_accounts_account_type_check "
        "CHECK (account_type IN ('business', 'personal', 'creator'))"
    )

    # 2. Creator profile ------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_creator_profiles (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            account_id UUID NOT NULL UNIQUE REFERENCES cappe_accounts(id) ON DELETE CASCADE,
            handle VARCHAR(30) NOT NULL,
            display_name VARCHAR(120) NOT NULL,
            avatar_url TEXT,
            cover_url TEXT,
            bio TEXT,
            location VARCHAR(120),
            niches TEXT[] NOT NULL DEFAULT '{}',
            languages TEXT[] NOT NULL DEFAULT '{}',
            open_to_offers BOOLEAN NOT NULL DEFAULT true,
            status VARCHAR(20) NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft', 'pending_review', 'published', 'rejected', 'suspended')),
            review_note TEXT,
            submitted_at TIMESTAMPTZ,
            reviewed_at TIMESTAMPTZ,
            published_at TIMESTAMPTZ,
            reach_verified BOOLEAN NOT NULL DEFAULT false,
            reach_audited_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_cappe_creator_profiles_handle "
        "ON cappe_creator_profiles (lower(handle))"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_creator_profiles_status "
        "ON cappe_creator_profiles (status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_creator_profiles_niches "
        "ON cappe_creator_profiles USING GIN (niches)"
    )

    # 3. Socials ----------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_creator_socials (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            profile_id UUID NOT NULL REFERENCES cappe_creator_profiles(id) ON DELETE CASCADE,
            platform VARCHAR(20) NOT NULL CHECK (platform IN
                ('instagram', 'tiktok', 'youtube', 'x', 'twitch', 'facebook', 'linkedin', 'other')),
            handle VARCHAR(120) NOT NULL,
            url TEXT NOT NULL,
            follower_count INTEGER CHECK (follower_count IS NULL OR follower_count >= 0),
            engagement_rate NUMERIC(5,2),
            audit_status VARCHAR(16) NOT NULL DEFAULT 'unverified'
                CHECK (audit_status IN ('unverified', 'verified', 'flagged')),
            verified_follower_count INTEGER,
            audited_at TIMESTAMPTZ,
            audited_by VARCHAR(255),
            audit_note TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (profile_id, url)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_creator_socials_profile "
        "ON cappe_creator_socials (profile_id, sort_order)"
    )

    # 4. Portfolio ----------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_creator_portfolio_items (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            profile_id UUID NOT NULL REFERENCES cappe_creator_profiles(id) ON DELETE CASCADE,
            title VARCHAR(200) NOT NULL,
            description TEXT,
            media_url TEXT,
            media_type VARCHAR(10) CHECK (media_type IS NULL OR media_type IN ('image', 'video')),
            external_url TEXT,
            brand_name VARCHAR(120),
            metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_creator_portfolio_profile "
        "ON cappe_creator_portfolio_items (profile_id, sort_order)"
    )

    # 5. Rate cards -----------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_creator_rate_cards (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            profile_id UUID NOT NULL REFERENCES cappe_creator_profiles(id) ON DELETE CASCADE,
            deliverable_type VARCHAR(20) NOT NULL CHECK (deliverable_type IN
                ('post', 'reel', 'story', 'video', 'short', 'stream', 'ugc', 'blog', 'other')),
            platform VARCHAR(20) NOT NULL,
            price_cents INTEGER NOT NULL CHECK (price_cents >= 0),
            currency VARCHAR(8) NOT NULL DEFAULT 'usd',
            negotiable BOOLEAN NOT NULL DEFAULT true,
            notes VARCHAR(500),
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (profile_id, deliverable_type, platform)
        )
        """
    )

    # 6. Campaigns (optional brand grouping) -----------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_collab_campaigns (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            brand_account_id UUID NOT NULL REFERENCES cappe_accounts(id) ON DELETE CASCADE,
            title VARCHAR(200) NOT NULL,
            description TEXT,
            budget_min_cents INTEGER,
            budget_max_cents INTEGER,
            deliverable_notes TEXT,
            status VARCHAR(16) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_collab_campaigns_brand "
        "ON cappe_collab_campaigns (brand_account_id, created_at DESC)"
    )

    # 7. Offers -----------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_collab_offers (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            campaign_id UUID REFERENCES cappe_collab_campaigns(id) ON DELETE SET NULL,
            brand_account_id UUID NOT NULL REFERENCES cappe_accounts(id) ON DELETE CASCADE,
            creator_profile_id UUID NOT NULL REFERENCES cappe_creator_profiles(id) ON DELETE CASCADE,
            title VARCHAR(200) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'sent' CHECK (status IN
                ('sent', 'negotiating', 'accepted', 'active', 'completed',
                 'declined', 'withdrawn', 'cancelled')),
            payment_schedule VARCHAR(20) CHECK (payment_schedule IS NULL OR payment_schedule IN
                ('upfront', 'split_50_50', 'per_deliverable')),
            accepted_revision_id UUID,
            total_cents INTEGER,
            currency VARCHAR(8) NOT NULL DEFAULT 'usd',
            accepted_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            declined_at TIMESTAMPTZ,
            declined_reason TEXT,
            cancelled_at TIMESTAMPTZ,
            cancelled_by VARCHAR(10) CHECK (cancelled_by IS NULL OR cancelled_by IN ('brand', 'creator')),
            cancel_reason TEXT,
            last_action_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_collab_offers_creator "
        "ON cappe_collab_offers (creator_profile_id, status, last_action_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_collab_offers_brand "
        "ON cappe_collab_offers (brand_account_id, status, last_action_at DESC)"
    )

    # 8. Revisions (immutable terms snapshots) -----------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_collab_offer_revisions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            offer_id UUID NOT NULL REFERENCES cappe_collab_offers(id) ON DELETE CASCADE,
            revision_no INTEGER NOT NULL,
            proposed_by VARCHAR(10) NOT NULL CHECK (proposed_by IN ('brand', 'creator')),
            terms JSONB NOT NULL,
            message TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (offer_id, revision_no)
        )
        """
    )
    # FK from offers.accepted_revision_id, added after the revisions table exists.
    op.execute(
        """
        DO $$ BEGIN
            ALTER TABLE cappe_collab_offers
                ADD CONSTRAINT fk_cappe_collab_offers_accepted_revision
                FOREIGN KEY (accepted_revision_id)
                REFERENCES cappe_collab_offer_revisions(id) ON DELETE SET NULL;
        EXCEPTION WHEN duplicate_object THEN NULL; END $$
        """
    )

    # 9. Deliverables (materialized at accept) -----------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_collab_deliverables (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            offer_id UUID NOT NULL REFERENCES cappe_collab_offers(id) ON DELETE CASCADE,
            idx INTEGER NOT NULL,
            type VARCHAR(20) NOT NULL,
            platform VARCHAR(20) NOT NULL,
            spec TEXT,
            due_date DATE,
            status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN
                ('pending', 'submitted', 'revision_requested', 'approved')),
            submission_url TEXT,
            submission_note TEXT,
            proof_media_url TEXT,
            submitted_at TIMESTAMPTZ,
            revision_count INTEGER NOT NULL DEFAULT 0,
            review_note TEXT,
            approved_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (offer_id, idx)
        )
        """
    )

    # 10. Payments (installments, materialized at accept) -------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_collab_payments (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            offer_id UUID NOT NULL REFERENCES cappe_collab_offers(id) ON DELETE CASCADE,
            idx INTEGER NOT NULL,
            label VARCHAR(120) NOT NULL,
            amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
            currency VARCHAR(8) NOT NULL DEFAULT 'usd',
            trigger VARCHAR(20) NOT NULL CHECK (trigger IN
                ('on_accept', 'on_all_approved', 'on_deliverable')),
            deliverable_id UUID REFERENCES cappe_collab_deliverables(id) ON DELETE SET NULL,
            status VARCHAR(16) NOT NULL DEFAULT 'scheduled' CHECK (status IN
                ('scheduled', 'due', 'processing', 'paid', 'failed', 'refunded', 'cancelled')),
            fee_bps_snapshot INTEGER,
            fee_cents INTEGER,
            stripe_checkout_session_id TEXT,
            stripe_payment_intent TEXT,
            due_at TIMESTAMPTZ,
            paid_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (offer_id, idx)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_collab_payments_offer "
        "ON cappe_collab_payments (offer_id, idx)"
    )

    # 11. Offer chat --------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_collab_messages (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            offer_id UUID NOT NULL REFERENCES cappe_collab_offers(id) ON DELETE CASCADE,
            sender VARCHAR(10) NOT NULL CHECK (sender IN ('brand', 'creator')),
            sender_account_id UUID REFERENCES cappe_accounts(id) ON DELETE SET NULL,
            body TEXT NOT NULL,
            revision_id UUID REFERENCES cappe_collab_offer_revisions(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_cappe_collab_messages_offer "
        "ON cappe_collab_messages (offer_id, created_at)"
    )

    # 12. Marketplace settings (admin-editable knobs) ------------------------------
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cappe_marketplace_settings (
            key VARCHAR(64) PRIMARY KEY,
            value JSONB NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        """
        INSERT INTO cappe_marketplace_settings (key, value) VALUES
            ('collab_fee_bps', '{"bps": 1500}'::jsonb),
            ('min_offer_cents', '{"cents": 5000}'::jsonb),
            ('auto_approve_days', '{"days": 14}'::jsonb)
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS cappe_marketplace_settings")
    op.execute("DROP TABLE IF EXISTS cappe_collab_messages")
    op.execute("DROP TABLE IF EXISTS cappe_collab_payments")
    op.execute("DROP TABLE IF EXISTS cappe_collab_deliverables")
    op.execute("ALTER TABLE cappe_collab_offers DROP CONSTRAINT IF EXISTS fk_cappe_collab_offers_accepted_revision")
    op.execute("DROP TABLE IF EXISTS cappe_collab_offer_revisions")
    op.execute("DROP TABLE IF EXISTS cappe_collab_offers")
    op.execute("DROP TABLE IF EXISTS cappe_collab_campaigns")
    op.execute("DROP TABLE IF EXISTS cappe_creator_rate_cards")
    op.execute("DROP TABLE IF EXISTS cappe_creator_portfolio_items")
    op.execute("DROP TABLE IF EXISTS cappe_creator_socials")
    op.execute("DROP TABLE IF EXISTS cappe_creator_profiles")
    # Downgrade of the account_type CHECK fails if any 'creator' rows exist —
    # acceptable; that's the point of the constraint reverting.
    op.execute("ALTER TABLE cappe_accounts DROP CONSTRAINT IF EXISTS cappe_accounts_account_type_check")
    op.execute(
        "ALTER TABLE cappe_accounts ADD CONSTRAINT cappe_accounts_account_type_check "
        "CHECK (account_type IN ('business', 'personal'))"
    )
