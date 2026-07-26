"""bootstrap.provisioning — provisioning/HRIS, inbox, reset tokens, beta invitations, hr-news (verbatim split of app/database.py lines 4783-5081).
"""


async def create_provisioning(conn):
        # ===========================================
        # Provisioning and Integrations Tables
        # ===========================================
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS integration_connections (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                provider VARCHAR(50) NOT NULL
                    CHECK (provider IN ('google_workspace', 'slack', 'hris')),
                status VARCHAR(20) NOT NULL DEFAULT 'disconnected'
                    CHECK (status IN ('disconnected', 'connected', 'error', 'needs_action')),
                config JSONB DEFAULT '{}'::jsonb,
                secrets JSONB DEFAULT '{}'::jsonb,
                last_tested_at TIMESTAMPTZ,
                last_error TEXT,
                created_by UUID REFERENCES users(id),
                updated_by UUID REFERENCES users(id),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE (company_id, provider)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_integration_connections_company_provider
            ON integration_connections(company_id, provider)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_integration_connections_status
            ON integration_connections(status)
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS onboarding_runs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
                provider VARCHAR(50) NOT NULL
                    CHECK (provider IN ('google_workspace', 'slack', 'hris')),
                status VARCHAR(20) NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'running', 'completed', 'failed', 'needs_action', 'rolled_back', 'cancelled')),
                trigger_source VARCHAR(30) NOT NULL DEFAULT 'manual'
                    CHECK (trigger_source IN ('manual', 'employee_create', 'scheduled', 'retry', 'api')),
                triggered_by UUID REFERENCES users(id),
                started_at TIMESTAMPTZ,
                completed_at TIMESTAMPTZ,
                last_error TEXT,
                metadata JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_onboarding_runs_company_provider_status
            ON onboarding_runs(company_id, provider, status)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_onboarding_runs_employee_provider
            ON onboarding_runs(employee_id, provider, created_at DESC)
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS onboarding_steps (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                run_id UUID NOT NULL REFERENCES onboarding_runs(id) ON DELETE CASCADE,
                step_key VARCHAR(100) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'running', 'completed', 'failed', 'needs_action', 'rolled_back', 'cancelled')),
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                last_response JSONB DEFAULT '{}'::jsonb,
                started_at TIMESTAMPTZ,
                completed_at TIMESTAMPTZ,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE (run_id, step_key)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_onboarding_steps_run_status
            ON onboarding_steps(run_id, status)
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS external_identities (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
                provider VARCHAR(50) NOT NULL
                    CHECK (provider IN ('google_workspace', 'slack', 'hris')),
                external_user_id VARCHAR(255),
                external_email VARCHAR(320),
                status VARCHAR(20) NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'suspended', 'deprovisioned', 'error')),
                raw_profile JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE (employee_id, provider)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_external_identities_company_provider
            ON external_identities(company_id, provider)
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS provisioning_audit_logs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                employee_id UUID REFERENCES employees(id) ON DELETE SET NULL,
                run_id UUID REFERENCES onboarding_runs(id) ON DELETE SET NULL,
                step_id UUID REFERENCES onboarding_steps(id) ON DELETE SET NULL,
                actor_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                provider VARCHAR(50) NOT NULL
                    CHECK (provider IN ('google_workspace', 'slack', 'hris')),
                action VARCHAR(100) NOT NULL,
                status VARCHAR(20) NOT NULL
                    CHECK (status IN ('success', 'error', 'info')),
                error_code VARCHAR(80),
                detail TEXT,
                payload JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_provisioning_audit_logs_company_created
            ON provisioning_audit_logs(company_id, created_at DESC)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_provisioning_audit_logs_run
            ON provisioning_audit_logs(run_id)
        """)

        # ===========================================
        # HRIS Sync Runs Table
        # ===========================================
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS hris_sync_runs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                connection_id UUID NOT NULL REFERENCES integration_connections(id) ON DELETE CASCADE,
                status VARCHAR(20) NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'running', 'completed', 'failed', 'partial')),
                trigger_source VARCHAR(30) NOT NULL DEFAULT 'manual'
                    CHECK (trigger_source IN ('manual', 'scheduled', 'api')),
                triggered_by UUID REFERENCES users(id),
                started_at TIMESTAMPTZ,
                completed_at TIMESTAMPTZ,
                total_records INTEGER DEFAULT 0,
                created_count INTEGER DEFAULT 0,
                updated_count INTEGER DEFAULT 0,
                skipped_count INTEGER DEFAULT 0,
                error_count INTEGER DEFAULT 0,
                errors JSONB DEFAULT '[]'::jsonb,
                last_error TEXT,
                metadata JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_hris_sync_runs_company
            ON hris_sync_runs(company_id, created_at DESC)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_hris_sync_runs_status
            ON hris_sync_runs(status)
        """)

        # ===========================================
        # Inbox Messaging Tables
        # ===========================================
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS inbox_conversations (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                title VARCHAR(255),
                is_group BOOLEAN DEFAULT false,
                created_by UUID NOT NULL REFERENCES users(id),
                last_message_at TIMESTAMPTZ,
                last_message_preview TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_inbox_conversations_last_message
            ON inbox_conversations(last_message_at DESC)
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS inbox_participants (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                conversation_id UUID NOT NULL REFERENCES inbox_conversations(id) ON DELETE CASCADE,
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                last_read_at TIMESTAMPTZ,
                is_muted BOOLEAN DEFAULT false,
                joined_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(conversation_id, user_id)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_inbox_participants_user
            ON inbox_participants(user_id, last_read_at)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_inbox_participants_conversation
            ON inbox_participants(conversation_id)
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS inbox_messages (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                conversation_id UUID NOT NULL REFERENCES inbox_conversations(id) ON DELETE CASCADE,
                sender_id UUID NOT NULL REFERENCES users(id),
                content TEXT NOT NULL,
                attachments JSONB DEFAULT '[]',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                edited_at TIMESTAMPTZ
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_inbox_messages_conversation
            ON inbox_messages(conversation_id, created_at DESC)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_inbox_messages_sender
            ON inbox_messages(sender_id)
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS inbox_email_batches (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                recipient_id UUID NOT NULL REFERENCES users(id),
                sender_id UUID NOT NULL REFERENCES users(id),
                last_sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(recipient_id, sender_id)
            )
        """)

        # ===========================================
        # Password Reset Tokens Table
        # ===========================================
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID NOT NULL REFERENCES users(id),
                token VARCHAR(128) NOT NULL UNIQUE,
                expires_at TIMESTAMPTZ NOT NULL,
                used_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_token ON password_reset_tokens(token)")

        # ===========================================
        # Beta Invitations Table
        # ===========================================
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS beta_invitations (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                email VARCHAR(255) NOT NULL,
                token VARCHAR(64) NOT NULL UNIQUE,
                status VARCHAR(20) DEFAULT 'pending',
                invited_by UUID REFERENCES users(id),
                created_at TIMESTAMPTZ DEFAULT NOW(),
                registered_at TIMESTAMPTZ,
                user_id UUID REFERENCES users(id)
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_beta_invitations_token ON beta_invitations(token)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_beta_invitations_email ON beta_invitations(email)")

        # ===========================================
        # HR News Articles Table
        # ===========================================
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS hr_news_articles (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                item_hash VARCHAR(64) NOT NULL UNIQUE,
                title TEXT NOT NULL,
                description TEXT,
                link TEXT,
                author VARCHAR(255),
                pub_date TIMESTAMP,
                source_name VARCHAR(100),
                source_feed_url TEXT,
                image_url TEXT,
                full_content TEXT,
                content_fetched_at TIMESTAMP,
                content_error TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_hr_news_articles_pub_date ON hr_news_articles(pub_date DESC)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_hr_news_articles_source_name ON hr_news_articles(source_name)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_hr_news_articles_created_at ON hr_news_articles(created_at DESC)
        """)

