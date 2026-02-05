from contextlib import asynccontextmanager
from typing import Optional

import asyncpg

_pool: Optional[asyncpg.Pool] = None


async def init_pool(database_url: str):
    """Initialize the connection pool."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(database_url, min_size=2, max_size=10)
    return _pool


async def get_pool() -> asyncpg.Pool:
    """Get the existing connection pool."""
    global _pool
    if _pool is None:
        raise RuntimeError("Database pool not initialized. Call init_pool first.")
    return _pool


async def close_pool():
    """Close the connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def get_connection():
    """Get a database connection from the pool."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn


async def init_db():
    """Initialize gummfit-specific database tables."""
    async with get_connection() as conn:
        # Ensure users table role constraint includes gummfit roles
        await conn.execute("""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'users_role_check'
                ) THEN
                    ALTER TABLE users DROP CONSTRAINT users_role_check;
                END IF;
                ALTER TABLE users ADD CONSTRAINT users_role_check
                    CHECK (role IN ('admin', 'client', 'candidate', 'employee', 'creator', 'agency', 'gumfit_admin'));
            EXCEPTION WHEN others THEN
                NULL;
            END $$;
        """)

        # ===========================================
        # Creator Platform Tables
        # ===========================================

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS creators (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                display_name VARCHAR(255) NOT NULL,
                bio TEXT,
                profile_image_url TEXT,
                niches JSONB DEFAULT '[]',
                social_handles JSONB DEFAULT '{}',
                audience_demographics JSONB DEFAULT '{}',
                metrics JSONB DEFAULT '{}',
                is_verified BOOLEAN DEFAULT false,
                is_public BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_creators_user_id ON creators(user_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_creators_is_public ON creators(is_public)")

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS creator_platform_connections (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                creator_id UUID NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
                platform VARCHAR(50) NOT NULL CHECK (platform IN ('youtube', 'patreon', 'tiktok', 'instagram', 'twitch', 'twitter', 'spotify')),
                platform_user_id VARCHAR(255),
                platform_username VARCHAR(255),
                access_token_encrypted TEXT,
                refresh_token_encrypted TEXT,
                token_expires_at TIMESTAMP,
                scopes JSONB DEFAULT '[]',
                last_synced_at TIMESTAMP,
                sync_status VARCHAR(50) DEFAULT 'pending' CHECK (sync_status IN ('pending', 'syncing', 'synced', 'failed')),
                sync_error TEXT,
                platform_data JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(creator_id, platform)
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_creator_platform_connections_creator_id ON creator_platform_connections(creator_id)")

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS revenue_streams (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                creator_id UUID NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
                name VARCHAR(255) NOT NULL,
                category VARCHAR(100) NOT NULL CHECK (category IN ('adsense', 'sponsorship', 'affiliate', 'merch', 'subscription', 'tips', 'licensing', 'services', 'other')),
                platform VARCHAR(100),
                description TEXT,
                is_active BOOLEAN DEFAULT true,
                tax_category VARCHAR(100),
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_revenue_streams_creator_id ON revenue_streams(creator_id)")

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS revenue_entries (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                creator_id UUID NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
                stream_id UUID REFERENCES revenue_streams(id) ON DELETE SET NULL,
                amount DECIMAL(12, 2) NOT NULL,
                currency VARCHAR(10) DEFAULT 'USD',
                date DATE NOT NULL,
                description TEXT,
                source VARCHAR(255),
                is_recurring BOOLEAN DEFAULT false,
                tax_category VARCHAR(100),
                metadata JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_revenue_entries_creator_id ON revenue_entries(creator_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_revenue_entries_date ON revenue_entries(date)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_revenue_entries_stream_id ON revenue_entries(stream_id)")

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS creator_expenses (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                creator_id UUID NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
                amount DECIMAL(12, 2) NOT NULL,
                currency VARCHAR(10) DEFAULT 'USD',
                date DATE NOT NULL,
                category VARCHAR(100) NOT NULL CHECK (category IN ('equipment', 'software', 'travel', 'marketing', 'contractors', 'office', 'education', 'legal', 'other')),
                description TEXT NOT NULL,
                vendor VARCHAR(255),
                receipt_url TEXT,
                is_deductible BOOLEAN DEFAULT true,
                tax_category VARCHAR(100),
                metadata JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_creator_expenses_creator_id ON creator_expenses(creator_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_creator_expenses_date ON creator_expenses(date)")

        # ===========================================
        # Agency Tables
        # ===========================================

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS agencies (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name VARCHAR(255) NOT NULL,
                slug VARCHAR(255) NOT NULL UNIQUE,
                agency_type VARCHAR(50) NOT NULL CHECK (agency_type IN ('talent', 'brand', 'hybrid')),
                description TEXT,
                logo_url TEXT,
                website_url TEXT,
                is_verified BOOLEAN DEFAULT false,
                verification_status VARCHAR(50) DEFAULT 'pending' CHECK (verification_status IN ('pending', 'in_review', 'verified', 'rejected')),
                contact_email VARCHAR(255),
                industries JSONB DEFAULT '[]',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_agencies_slug ON agencies(slug)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_agencies_agency_type ON agencies(agency_type)")

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS agency_members (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                agency_id UUID NOT NULL REFERENCES agencies(id) ON DELETE CASCADE,
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                role VARCHAR(50) NOT NULL CHECK (role IN ('owner', 'admin', 'member')),
                title VARCHAR(255),
                permissions JSONB DEFAULT '{}',
                invited_at TIMESTAMP DEFAULT NOW(),
                joined_at TIMESTAMP,
                is_active BOOLEAN DEFAULT true,
                UNIQUE(agency_id, user_id)
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_agency_members_agency_id ON agency_members(agency_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_agency_members_user_id ON agency_members(user_id)")

        # ===========================================
        # GumFit Admin Tables
        # ===========================================

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS gumfit_invites (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                email VARCHAR(255) NOT NULL,
                invite_type VARCHAR(20) NOT NULL CHECK (invite_type IN ('creator', 'agency')),
                token VARCHAR(255) NOT NULL UNIQUE,
                message TEXT,
                status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'expired')),
                created_by UUID REFERENCES users(id),
                created_at TIMESTAMP DEFAULT NOW(),
                expires_at TIMESTAMP NOT NULL,
                accepted_at TIMESTAMP,
                accepted_by UUID REFERENCES users(id)
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_gumfit_invites_email ON gumfit_invites(email)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_gumfit_invites_token ON gumfit_invites(token)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_gumfit_invites_status ON gumfit_invites(status)")

        # ===========================================
        # Marketplace Tables (Brand Deals)
        # ===========================================

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS brand_deals (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                agency_id UUID NOT NULL REFERENCES agencies(id) ON DELETE CASCADE,
                title VARCHAR(500) NOT NULL,
                brand_name VARCHAR(255) NOT NULL,
                description TEXT NOT NULL,
                requirements JSONB DEFAULT '{}',
                deliverables JSONB DEFAULT '[]',
                compensation_type VARCHAR(50) NOT NULL CHECK (compensation_type IN ('fixed', 'per_deliverable', 'revenue_share', 'product_only', 'negotiable')),
                compensation_min DECIMAL(12, 2),
                compensation_max DECIMAL(12, 2),
                compensation_currency VARCHAR(10) DEFAULT 'USD',
                compensation_details TEXT,
                niches JSONB DEFAULT '[]',
                min_followers INTEGER,
                max_followers INTEGER,
                preferred_platforms JSONB DEFAULT '[]',
                audience_requirements JSONB DEFAULT '{}',
                timeline_start DATE,
                timeline_end DATE,
                application_deadline DATE,
                status VARCHAR(50) DEFAULT 'draft' CHECK (status IN ('draft', 'open', 'closed', 'filled', 'cancelled')),
                visibility VARCHAR(50) DEFAULT 'public' CHECK (visibility IN ('public', 'invite_only', 'private')),
                applications_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_brand_deals_agency_id ON brand_deals(agency_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_brand_deals_status ON brand_deals(status)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_brand_deals_visibility ON brand_deals(visibility)")

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS deal_applications (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                deal_id UUID NOT NULL REFERENCES brand_deals(id) ON DELETE CASCADE,
                creator_id UUID NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
                pitch TEXT NOT NULL,
                proposed_rate DECIMAL(12, 2),
                proposed_currency VARCHAR(10) DEFAULT 'USD',
                proposed_deliverables JSONB DEFAULT '[]',
                portfolio_links JSONB DEFAULT '[]',
                availability_notes TEXT,
                status VARCHAR(50) DEFAULT 'pending' CHECK (status IN ('pending', 'under_review', 'shortlisted', 'accepted', 'rejected', 'withdrawn')),
                agency_notes TEXT,
                match_score FLOAT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(deal_id, creator_id)
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_deal_applications_deal_id ON deal_applications(deal_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_deal_applications_creator_id ON deal_applications(creator_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_deal_applications_status ON deal_applications(status)")

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS deal_contracts (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                deal_id UUID NOT NULL REFERENCES brand_deals(id) ON DELETE CASCADE,
                application_id UUID NOT NULL REFERENCES deal_applications(id) ON DELETE CASCADE,
                creator_id UUID NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
                agency_id UUID NOT NULL REFERENCES agencies(id) ON DELETE CASCADE,
                agreed_rate DECIMAL(12, 2) NOT NULL,
                agreed_currency VARCHAR(10) DEFAULT 'USD',
                agreed_deliverables JSONB DEFAULT '[]',
                terms TEXT,
                contract_document_url TEXT,
                start_date DATE,
                end_date DATE,
                status VARCHAR(50) DEFAULT 'pending' CHECK (status IN ('pending', 'active', 'completed', 'cancelled', 'disputed')),
                total_paid DECIMAL(12, 2) DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_deal_contracts_deal_id ON deal_contracts(deal_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_deal_contracts_creator_id ON deal_contracts(creator_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_deal_contracts_agency_id ON deal_contracts(agency_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_deal_contracts_status ON deal_contracts(status)")

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS contract_payments (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                contract_id UUID NOT NULL REFERENCES deal_contracts(id) ON DELETE CASCADE,
                amount DECIMAL(12, 2) NOT NULL,
                currency VARCHAR(10) DEFAULT 'USD',
                milestone_name VARCHAR(255),
                due_date DATE,
                paid_date DATE,
                status VARCHAR(50) DEFAULT 'pending' CHECK (status IN ('pending', 'invoiced', 'paid', 'overdue', 'cancelled')),
                payment_method VARCHAR(100),
                transaction_reference VARCHAR(255),
                notes TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_contract_payments_contract_id ON contract_payments(contract_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_contract_payments_status ON contract_payments(status)")

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS creator_deal_matches (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                deal_id UUID NOT NULL REFERENCES brand_deals(id) ON DELETE CASCADE,
                creator_id UUID NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
                overall_score FLOAT NOT NULL,
                niche_score FLOAT,
                audience_score FLOAT,
                engagement_score FLOAT,
                budget_fit_score FLOAT,
                match_reasoning TEXT,
                breakdown JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(deal_id, creator_id)
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_creator_deal_matches_deal_id ON creator_deal_matches(deal_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_creator_deal_matches_creator_id ON creator_deal_matches(creator_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_creator_deal_matches_overall_score ON creator_deal_matches(overall_score DESC)")

        # ===========================================
        # Campaign Platform Tables (Limit Order System)
        # ===========================================

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS contract_templates (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                agency_id UUID REFERENCES agencies(id) ON DELETE CASCADE,
                name VARCHAR(255) NOT NULL,
                template_type VARCHAR(50) CHECK (template_type IN ('sponsorship', 'affiliate', 'content', 'ambassador', 'custom')),
                content TEXT NOT NULL,
                variables JSONB DEFAULT '[]',
                is_default BOOLEAN DEFAULT false,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_contract_templates_agency_id ON contract_templates(agency_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_contract_templates_type ON contract_templates(template_type)")

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS campaigns (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                agency_id UUID NOT NULL REFERENCES agencies(id) ON DELETE CASCADE,
                brand_name VARCHAR(255) NOT NULL,
                title VARCHAR(255) NOT NULL,
                description TEXT,
                deliverables JSONB NOT NULL DEFAULT '[]',
                timeline JSONB DEFAULT '{}',
                total_budget DECIMAL(12, 2) NOT NULL,
                upfront_percent INTEGER DEFAULT 30,
                completion_percent INTEGER DEFAULT 70,
                platform_fee_percent DECIMAL(5, 2) DEFAULT 10,
                max_creators INTEGER DEFAULT 1,
                accepted_count INTEGER DEFAULT 0,
                status VARCHAR(20) DEFAULT 'draft' CHECK (status IN ('draft', 'open', 'active', 'completed', 'cancelled')),
                contract_template_id UUID REFERENCES contract_templates(id) ON DELETE SET NULL,
                expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_campaigns_agency_id ON campaigns(agency_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_campaigns_status ON campaigns(status)")

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS campaign_offers (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                campaign_id UUID NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
                creator_id UUID NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
                offered_amount DECIMAL(12, 2) NOT NULL,
                custom_message TEXT,
                status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'viewed', 'accepted', 'declined', 'expired', 'taken')),
                creator_counter_amount DECIMAL(12, 2),
                creator_notes TEXT,
                viewed_at TIMESTAMP,
                responded_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(campaign_id, creator_id)
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_campaign_offers_campaign_id ON campaign_offers(campaign_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_campaign_offers_creator_id ON campaign_offers(creator_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_campaign_offers_status ON campaign_offers(status)")

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS campaign_payments (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                campaign_id UUID NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
                creator_id UUID NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
                payment_type VARCHAR(20) CHECK (payment_type IN ('upfront', 'completion', 'milestone', 'affiliate')),
                amount DECIMAL(12, 2) NOT NULL,
                platform_fee DECIMAL(12, 2),
                status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'held', 'released', 'refunded', 'failed')),
                stripe_payment_intent_id VARCHAR(255),
                stripe_transfer_id VARCHAR(255),
                charged_at TIMESTAMP,
                released_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_campaign_payments_campaign_id ON campaign_payments(campaign_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_campaign_payments_creator_id ON campaign_payments(creator_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_campaign_payments_status ON campaign_payments(status)")

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS affiliate_links (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                campaign_id UUID REFERENCES campaigns(id) ON DELETE SET NULL,
                creator_id UUID NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
                agency_id UUID NOT NULL REFERENCES agencies(id) ON DELETE CASCADE,
                short_code VARCHAR(20) UNIQUE NOT NULL,
                destination_url TEXT NOT NULL,
                product_name VARCHAR(255),
                commission_percent DECIMAL(5, 2) DEFAULT 10,
                platform_percent DECIMAL(5, 2) DEFAULT 5,
                click_count INTEGER DEFAULT 0,
                conversion_count INTEGER DEFAULT 0,
                total_sales DECIMAL(12, 2) DEFAULT 0,
                total_commission DECIMAL(12, 2) DEFAULT 0,
                is_active BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_affiliate_links_short_code ON affiliate_links(short_code)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_affiliate_links_creator_id ON affiliate_links(creator_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_affiliate_links_agency_id ON affiliate_links(agency_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_affiliate_links_campaign_id ON affiliate_links(campaign_id)")

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS affiliate_events (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                link_id UUID NOT NULL REFERENCES affiliate_links(id) ON DELETE CASCADE,
                event_type VARCHAR(20) CHECK (event_type IN ('click', 'conversion')),
                sale_amount DECIMAL(12, 2),
                commission_amount DECIMAL(12, 2),
                ip_address VARCHAR(45),
                user_agent TEXT,
                referrer TEXT,
                metadata JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_affiliate_events_link_id ON affiliate_events(link_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_affiliate_events_type ON affiliate_events(event_type)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_affiliate_events_created_at ON affiliate_events(created_at)")

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS creator_valuations (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                creator_id UUID NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
                estimated_value_min DECIMAL(12, 2),
                estimated_value_max DECIMAL(12, 2),
                factors JSONB DEFAULT '{}',
                data_sources JSONB DEFAULT '[]',
                confidence_score FLOAT,
                calculated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(creator_id)
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_creator_valuations_creator_id ON creator_valuations(creator_id)")

        # Add Stripe columns to creators table
        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'creators' AND column_name = 'stripe_account_id'
                ) THEN
                    ALTER TABLE creators ADD COLUMN stripe_account_id VARCHAR(255);
                    ALTER TABLE creators ADD COLUMN stripe_onboarding_complete BOOLEAN DEFAULT false;
                    ALTER TABLE creators ADD COLUMN stripe_payouts_enabled BOOLEAN DEFAULT false;
                END IF;
            END $$;
        """)

        # Add Stripe customer column to agencies table
        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'agencies' AND column_name = 'stripe_customer_id'
                ) THEN
                    ALTER TABLE agencies ADD COLUMN stripe_customer_id VARCHAR(255);
                END IF;
            END $$;
        """)

        # GumFit assets table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS gumfit_assets (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name VARCHAR(255) NOT NULL,
                url TEXT NOT NULL,
                category VARCHAR(50) DEFAULT 'general',
                file_type VARCHAR(50),
                file_size INTEGER,
                width INTEGER,
                height INTEGER,
                alt_text TEXT,
                uploaded_by UUID REFERENCES users(id),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_gumfit_assets_category ON gumfit_assets(category)")

        print("[DB] Gummfit tables initialized")
