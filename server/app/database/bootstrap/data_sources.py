"""bootstrap.data_sources — structured data sources, posters, rate limits, ai_usage, invitations (verbatim split of app/database.py lines 3837-4185).
"""


async def create_data_sources(conn):
        # ===========================================
        # Tier 1 Structured Data Sources (Phase 4.2)
        # ===========================================

        # Structured data sources registry
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS structured_data_sources (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                source_key VARCHAR(100) NOT NULL UNIQUE,
                source_name VARCHAR(255) NOT NULL,
                source_url VARCHAR(500) NOT NULL,
                source_type VARCHAR(50) NOT NULL,
                domain VARCHAR(100) NOT NULL,
                categories TEXT[] NOT NULL,
                coverage_scope VARCHAR(50) NOT NULL,
                coverage_states TEXT[],
                parser_config JSONB NOT NULL DEFAULT '{}',
                fetch_interval_hours INTEGER DEFAULT 168,
                last_fetched_at TIMESTAMP,
                last_fetch_status VARCHAR(20),
                last_fetch_error TEXT,
                record_count INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_structured_data_sources_active
            ON structured_data_sources(is_active)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_structured_data_sources_domain
            ON structured_data_sources(domain)
        """)

        # Structured data cache - parsed requirement data
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS structured_data_cache (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                source_id UUID NOT NULL REFERENCES structured_data_sources(id) ON DELETE CASCADE,
                jurisdiction_key VARCHAR(100) NOT NULL,
                category VARCHAR(50) NOT NULL,
                rate_type VARCHAR(50),
                jurisdiction_level VARCHAR(20) NOT NULL,
                jurisdiction_name VARCHAR(100) NOT NULL,
                state VARCHAR(2) NOT NULL,
                raw_data JSONB NOT NULL,
                current_value VARCHAR(100),
                numeric_value DECIMAL(10, 4),
                effective_date DATE,
                next_scheduled_date DATE,
                next_scheduled_value VARCHAR(100),
                notes TEXT,
                fetched_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(source_id, jurisdiction_key, category, rate_type)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_structured_data_cache_source
            ON structured_data_cache(source_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_structured_data_cache_jurisdiction
            ON structured_data_cache(jurisdiction_key)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_structured_data_cache_state
            ON structured_data_cache(state)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_structured_data_cache_lookup
            ON structured_data_cache(state, jurisdiction_level, category)
        """)

        # Add sort_order column for manual reordering
        await conn.execute("""
            ALTER TABLE jurisdiction_requirements
            ADD COLUMN IF NOT EXISTS sort_order INTEGER NOT NULL DEFAULT 0
        """)

        # Add source_tier column to jurisdiction_requirements
        # Column was migrated from INTEGER to source_tier_enum via alembic migration 04
        await conn.execute("""
            ALTER TABLE jurisdiction_requirements
            ADD COLUMN IF NOT EXISTS source_tier source_tier_enum DEFAULT 'tier_3_aggregator'
        """)
        await conn.execute("""
            ALTER TABLE jurisdiction_requirements
            ADD COLUMN IF NOT EXISTS structured_source_id UUID REFERENCES structured_data_sources(id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_jurisdiction_requirements_source_tier
            ON jurisdiction_requirements(source_tier)
        """)

        # Seed initial structured data sources
        await conn.execute("""
            INSERT INTO structured_data_sources (source_key, source_name, source_url, source_type, domain, categories, coverage_scope, coverage_states, parser_config, fetch_interval_hours)
            VALUES
                (
                    'berkeley_minwage_csv',
                    'UC Berkeley Labor Center',
                    'https://laborcenter.berkeley.edu/wp-content/uploads/2024/01/Local-Minimum-Wage-Ordinances-Inventory-2024.csv',
                    'csv',
                    'laborcenter.berkeley.edu',
                    ARRAY['minimum_wage'],
                    'city_county',
                    NULL,
                    '{"encoding": "utf-8", "skip_rows": 0, "columns": {"jurisdiction": "Jurisdiction", "state": "State", "current_wage": "Current Minimum Wage", "effective_date": "Effective Date", "next_wage": "Scheduled Increase", "next_date": "Next Increase Date", "notes": "Notes"}}'::jsonb,
                    168
                ),
                (
                    'epi_minwage_tracker',
                    'Economic Policy Institute',
                    'https://www.epi.org/minimum-wage-tracker/',
                    'html_table',
                    'epi.org',
                    ARRAY['minimum_wage'],
                    'state',
                    NULL,
                    '{"table_selector": "table.mw-tracker-table", "rate_type": "general", "columns": {"state": 0, "current_wage": 1, "effective_date": 2, "next_wage": 3, "next_date": 4}}'::jsonb,
                    168
                ),
                (
                    'dol_whd_tipped',
                    'US DOL Wage and Hour Division - Tipped',
                    'https://www.dol.gov/agencies/whd/state/minimum-wage/tipped',
                    'html_table',
                    'dol.gov',
                    ARRAY['minimum_wage'],
                    'state',
                    NULL,
                    '{"table_selector": "table", "rate_type": "tipped", "columns": {"state": 0, "cash_wage": 1, "tip_credit": 2, "total": 3}}'::jsonb,
                    168
                ),
                (
                    'ncsl_minwage_chart',
                    'NCSL State Minimum Wage Chart',
                    'https://www.ncsl.org/labor-and-employment/state-minimum-wages',
                    'html_table',
                    'ncsl.org',
                    ARRAY['minimum_wage'],
                    'state',
                    NULL,
                    '{"table_selector": "table.state-table", "rate_type": "general", "columns": {"state": 0, "current_wage": 1, "future_changes": 2}}'::jsonb,
                    168
                )
            ON CONFLICT (source_key) DO UPDATE SET
                source_url = EXCLUDED.source_url,
                parser_config = EXCLUDED.parser_config
        """)

        # Add scheduler setting for structured data fetch
        await conn.execute("""
            INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
            VALUES
                ('structured_data_fetch', 'Structured Data Fetch', 'Fetch Tier 1 structured data from authoritative sources (Berkeley, DOL, EPI, NCSL).', false, 0)
            ON CONFLICT (task_key) DO NOTHING
        """)

        # Add scheduler setting for project deadline checks
        await conn.execute("""
            INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
            VALUES
                ('project_deadline_checks', 'Project Deadline Checks', 'Auto-close recruiting projects that have passed their closing date, run ranking, and notify top candidates.', false, 0)
            ON CONFLICT (task_key) DO NOTHING
        """)

        # Add scheduler setting for onboarding reminders
        await conn.execute("""
            INSERT INTO scheduler_settings (task_key, enabled, max_per_cycle)
            VALUES ('onboarding_reminders', TRUE, 200)
            ON CONFLICT (task_key) DO NOTHING
        """)

        # Add scheduler setting for compliance action reminders
        await conn.execute("""
            INSERT INTO scheduler_settings (task_key, enabled, max_per_cycle)
            VALUES ('compliance_action_reminders', TRUE, 100)
            ON CONFLICT (task_key) DO NOTHING
        """)

        # Add scheduler setting for handbook freshness checks
        await conn.execute("""
            INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
            VALUES ('handbook_freshness', 'Handbook Freshness Checks',
                    'Automated freshness checks for published handbooks.', false, 5)
            ON CONFLICT (task_key) DO NOTHING
        """)

        # Add scheduler setting for the vertical-coverage sweep. Makes live Gemini
        # calls (industry-specific research), so it is seeded OFF — see
        # workers/tasks/vertical_coverage_sweep.py.
        await conn.execute("""
            INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
            VALUES ('vertical_coverage_sweep', 'Vertical Coverage Sweep',
                    'Reclaims stale in-progress vertical-research cells, drains deferred research calls, and fills industry-specific compliance for tenants whose vertical was never scoped. Default off.',
                    false, 12)
            ON CONFLICT (task_key) DO NOTHING
        """)

        # Add scheduler setting for risk assessments
        await conn.execute("""
            INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
            VALUES ('risk_assessment', 'Risk Assessment',
                    'Automated weekly risk assessment scoring for all companies.', false, 3)
            ON CONFLICT (task_key) DO NOTHING
        """)

        # Add scheduler setting for auto-archive
        await conn.execute("""
            INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
            VALUES ('auto_archive', 'Auto-Archive',
                    'Archives threads and projects idle for 7+ days with no star/pin.', false, 10000)
            ON CONFLICT (task_key) DO NOTHING
        """)

        # ===========================================
        # Compliance Poster Tables
        # ===========================================

        # Poster templates — one per jurisdiction, auto-generated PDF
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS poster_templates (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                jurisdiction_id UUID NOT NULL REFERENCES jurisdictions(id) ON DELETE CASCADE UNIQUE,
                title VARCHAR(500) NOT NULL,
                description TEXT,
                version INTEGER NOT NULL DEFAULT 1,
                pdf_url TEXT,
                pdf_generated_at TIMESTAMP,
                categories_included TEXT[],
                requirement_count INTEGER DEFAULT 0,
                status VARCHAR(20) NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'generated', 'failed')),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Poster orders — company requests for printed posters
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS poster_orders (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                location_id UUID NOT NULL REFERENCES business_locations(id) ON DELETE CASCADE,
                status VARCHAR(20) NOT NULL DEFAULT 'requested'
                    CHECK (status IN ('requested', 'quoted', 'processing', 'shipped', 'delivered', 'cancelled')),
                requested_by UUID REFERENCES users(id) ON DELETE SET NULL,
                admin_notes TEXT,
                quote_amount NUMERIC(10, 2),
                shipping_address TEXT,
                tracking_number VARCHAR(100),
                shipped_at TIMESTAMP,
                delivered_at TIMESTAMP,
                metadata JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_poster_orders_company_id ON poster_orders(company_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_poster_orders_status ON poster_orders(status)
        """)

        # Poster order items — links orders to templates
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS poster_order_items (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                order_id UUID NOT NULL REFERENCES poster_orders(id) ON DELETE CASCADE,
                template_id UUID NOT NULL REFERENCES poster_templates(id) ON DELETE CASCADE,
                quantity INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_poster_order_items_order_id ON poster_order_items(order_id)
        """)

        # ===========================================
        # API Rate Limits Table (for Gemini rate limiting)
        # ===========================================
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS api_rate_limits (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                service_name VARCHAR(50) NOT NULL,
                endpoint VARCHAR(100),
                called_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_rate_limits_called_at ON api_rate_limits(called_at)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_rate_limits_service ON api_rate_limits(service_name)
        """)

        # ===========================================
        # AI Usage Log (provider-general call ledger, see app/core/services/ai_usage.py)
        # ===========================================
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_usage_log (
                id              BIGSERIAL PRIMARY KEY,
                provider        TEXT NOT NULL DEFAULT 'gemini',
                model           TEXT NOT NULL,
                feature         TEXT NOT NULL,
                method          TEXT NOT NULL,
                input_tokens    INTEGER,
                output_tokens   INTEGER,
                thinking_tokens INTEGER,
                cached_tokens   INTEGER,
                cost_usd        NUMERIC(12,6),
                latency_ms      INTEGER,
                status          TEXT NOT NULL DEFAULT 'ok',
                error           TEXT,
                provider_response_id TEXT,
                provider_status TEXT,
                service_tier    TEXT,
                created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS ix_ai_usage_created ON ai_usage_log (created_at)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS ix_ai_usage_feature ON ai_usage_log (feature, created_at)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS ix_ai_usage_model ON ai_usage_log (model, created_at)
        """)

        # Business invitations (admin-generated invite links for auto-approved registration)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS business_invitations (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                token VARCHAR(64) NOT NULL UNIQUE,
                created_by UUID NOT NULL REFERENCES users(id),
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                used_by_company_id UUID REFERENCES companies(id),
                expires_at TIMESTAMP NOT NULL,
                used_at TIMESTAMP,
                note TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_business_invitations_token ON business_invitations(token)
        """)
