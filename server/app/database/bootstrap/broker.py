"""bootstrap.broker — broker channel tables (incl. EXECUTE format() constraint churn) (verbatim split of app/database.py lines 4186-4782).
"""


async def create_broker(conn):
        # ===========================================
        # Broker Channel Tables
        # ===========================================
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS brokers (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name VARCHAR(255) NOT NULL,
                slug VARCHAR(120) NOT NULL UNIQUE,
                status VARCHAR(20) NOT NULL DEFAULT 'active'
                    CHECK (status IN ('pending', 'active', 'suspended', 'terminated')),
                support_routing VARCHAR(20) NOT NULL DEFAULT 'shared'
                    CHECK (support_routing IN ('broker_first', 'matcha_first', 'shared')),
                billing_mode VARCHAR(20) NOT NULL DEFAULT 'direct'
                    CHECK (billing_mode IN ('direct', 'reseller', 'hybrid')),
                invoice_owner VARCHAR(20) NOT NULL DEFAULT 'matcha'
                    CHECK (invoice_owner IN ('matcha', 'broker')),
                terms_required_version VARCHAR(50) NOT NULL DEFAULT 'v1',
                created_by UUID REFERENCES users(id),
                terminated_at TIMESTAMPTZ,
                grace_until TIMESTAMPTZ,
                post_termination_mode VARCHAR(30)
                    CHECK (post_termination_mode IN ('convert_to_direct', 'transfer_to_broker', 'sunset', 'matcha_managed')),
                allocated_seats INTEGER NOT NULL DEFAULT 0,
                metadata JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_brokers_status ON brokers(status)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_brokers_created_at ON brokers(created_at DESC)
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS broker_members (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                broker_id UUID NOT NULL REFERENCES brokers(id) ON DELETE CASCADE,
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                role VARCHAR(20) NOT NULL DEFAULT 'member'
                    CHECK (role IN ('owner', 'admin', 'member')),
                permissions JSONB DEFAULT '{}'::jsonb,
                is_active BOOLEAN NOT NULL DEFAULT true,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE (broker_id, user_id)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_broker_members_user_id ON broker_members(user_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_broker_members_broker_id ON broker_members(broker_id)
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS broker_company_links (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                broker_id UUID NOT NULL REFERENCES brokers(id) ON DELETE CASCADE,
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                status VARCHAR(20) NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'active', 'suspending', 'grace', 'terminated', 'transferred')),
                permissions JSONB DEFAULT '{}'::jsonb,
                linked_at TIMESTAMPTZ DEFAULT NOW(),
                activated_at TIMESTAMPTZ,
                terminated_at TIMESTAMPTZ,
                grace_until TIMESTAMPTZ,
                renewal_date DATE,
                post_termination_mode VARCHAR(30)
                    CHECK (post_termination_mode IN ('convert_to_direct', 'transfer_to_broker', 'sunset', 'matcha_managed')),
                transition_state VARCHAR(20) DEFAULT 'none'
                    CHECK (transition_state IN ('none', 'planned', 'in_progress', 'matcha_managed', 'completed')),
                transition_updated_at TIMESTAMPTZ,
                data_handoff_status VARCHAR(20) DEFAULT 'not_required'
                    CHECK (data_handoff_status IN ('not_required', 'pending', 'in_progress', 'completed')),
                data_handoff_notes TEXT,
                current_transition_id UUID,
                created_by UUID REFERENCES users(id),
                metadata JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE (broker_id, company_id)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_broker_company_links_company_id ON broker_company_links(company_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_broker_company_links_status ON broker_company_links(status)
        """)

        # Broker↔company chat (migration brokerchat01). Private messaging between
        # a broker and one of its linked client companies. Threads may anchor to a
        # specific shared record (claim / loss run / document / incident).
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS broker_company_conversations (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                broker_id UUID NOT NULL REFERENCES brokers(id) ON DELETE CASCADE,
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                subject TEXT,
                status VARCHAR(20) NOT NULL DEFAULT 'open'
                    CHECK (status IN ('open', 'archived')),
                reference_type VARCHAR(40),
                reference_id UUID,
                reference_label TEXT,
                created_by UUID REFERENCES users(id) ON DELETE SET NULL,
                created_by_side VARCHAR(10) NOT NULL
                    CHECK (created_by_side IN ('broker', 'company')),
                last_message_at TIMESTAMPTZ,
                last_message_preview TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_bc_conversations_broker
            ON broker_company_conversations(broker_id, last_message_at DESC)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_bc_conversations_company
            ON broker_company_conversations(company_id, last_message_at DESC)
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS broker_company_messages (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                conversation_id UUID NOT NULL
                    REFERENCES broker_company_conversations(id) ON DELETE CASCADE,
                sender_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                sender_side VARCHAR(10) NOT NULL
                    CHECK (sender_side IN ('broker', 'company')),
                body TEXT NOT NULL,
                reference_type VARCHAR(40),
                reference_id UUID,
                reference_label TEXT,
                client_message_id UUID,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                edited_at TIMESTAMPTZ,
                deleted_at TIMESTAMPTZ
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_bc_messages_conversation
            ON broker_company_messages(conversation_id, created_at)
        """)
        # Idempotent send, scoped per conversation: a sender-wide key would make
        # a client_message_id reused across threads collapse onto the other
        # thread's row and silently drop the new message.
        await conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_bc_messages_conv_sender_cmid
            ON broker_company_messages(conversation_id, sender_user_id, client_message_id)
            WHERE client_message_id IS NOT NULL
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS broker_company_conversation_reads (
                conversation_id UUID NOT NULL
                    REFERENCES broker_company_conversations(id) ON DELETE CASCADE,
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                last_read_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                last_read_message_id UUID,
                PRIMARY KEY (conversation_id, user_id)
            )
        """)
        # Client-controlled grants: a broker sees an incident's defense file only
        # where the client shared THAT incident with THAT broker (migration
        # irshare01). Access additionally requires a live broker_company_links row.
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS broker_incident_shares (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                incident_id UUID NOT NULL REFERENCES ir_incidents(id) ON DELETE CASCADE,
                broker_id UUID NOT NULL REFERENCES brokers(id) ON DELETE CASCADE,
                shared_by UUID REFERENCES users(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (incident_id, broker_id)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_broker_incident_shares_broker_company
            ON broker_incident_shares(broker_id, company_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_broker_incident_shares_incident
            ON broker_incident_shares(incident_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_broker_company_links_broker_status ON broker_company_links(broker_id, status)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_broker_company_links_transition_state ON broker_company_links(transition_state)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_broker_company_links_current_transition ON broker_company_links(current_transition_id)
        """)

        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'broker_company_links' AND column_name = 'transition_state'
                ) THEN
                    ALTER TABLE broker_company_links ADD COLUMN transition_state VARCHAR(20) DEFAULT 'none';
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'broker_company_links' AND column_name = 'transition_updated_at'
                ) THEN
                    ALTER TABLE broker_company_links ADD COLUMN transition_updated_at TIMESTAMPTZ;
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'broker_company_links' AND column_name = 'data_handoff_status'
                ) THEN
                    ALTER TABLE broker_company_links ADD COLUMN data_handoff_status VARCHAR(20) DEFAULT 'not_required';
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'broker_company_links' AND column_name = 'data_handoff_notes'
                ) THEN
                    ALTER TABLE broker_company_links ADD COLUMN data_handoff_notes TEXT;
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'broker_company_links' AND column_name = 'current_transition_id'
                ) THEN
                    ALTER TABLE broker_company_links ADD COLUMN current_transition_id UUID;
                END IF;
            END $$;
        """)

        await conn.execute("""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'broker_company_links_transition_state_check') THEN
                    ALTER TABLE broker_company_links DROP CONSTRAINT broker_company_links_transition_state_check;
                END IF;
                ALTER TABLE broker_company_links
                    ADD CONSTRAINT broker_company_links_transition_state_check
                    CHECK (transition_state IN ('none', 'planned', 'in_progress', 'matcha_managed', 'completed'));

                IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'broker_company_links_data_handoff_status_check') THEN
                    ALTER TABLE broker_company_links DROP CONSTRAINT broker_company_links_data_handoff_status_check;
                END IF;
                ALTER TABLE broker_company_links
                    ADD CONSTRAINT broker_company_links_data_handoff_status_check
                    CHECK (data_handoff_status IN ('not_required', 'pending', 'in_progress', 'completed'));
            EXCEPTION WHEN undefined_column THEN
                NULL;
            END $$;
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS broker_contracts (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                broker_id UUID NOT NULL REFERENCES brokers(id) ON DELETE CASCADE,
                status VARCHAR(20) NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'active', 'suspended', 'terminated')),
                billing_mode VARCHAR(20) NOT NULL
                    CHECK (billing_mode IN ('direct', 'reseller', 'hybrid')),
                invoice_owner VARCHAR(20) NOT NULL
                    CHECK (invoice_owner IN ('matcha', 'broker')),
                currency VARCHAR(3) NOT NULL DEFAULT 'USD',
                base_platform_fee NUMERIC(12, 2) NOT NULL DEFAULT 0,
                pepm_rate NUMERIC(12, 2) NOT NULL DEFAULT 0,
                minimum_monthly_commit NUMERIC(12, 2) NOT NULL DEFAULT 0,
                pricing_rules JSONB DEFAULT '{}'::jsonb,
                effective_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                expires_at TIMESTAMPTZ,
                created_by UUID REFERENCES users(id),
                metadata JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_broker_contracts_broker_id ON broker_contracts(broker_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_broker_contracts_status ON broker_contracts(status)
        """)

        # --- Fractional HR (internal master-admin engagement tooling) ---
        # company_id nullable: a fractional client may have no platform tenant.
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS fractional_clients (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name VARCHAR(255) NOT NULL,
                company_id UUID REFERENCES companies(id) ON DELETE SET NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'prospect'
                    CHECK (status IN ('prospect', 'active', 'paused', 'offboarded')),
                billing_model VARCHAR(20) NOT NULL DEFAULT 'monthly_retainer'
                    CHECK (billing_model IN ('monthly_retainer', 'hours_block', 'project_fixed', 'hourly')),
                retainer_hours NUMERIC(8, 2),
                retainer_period VARCHAR(12) NOT NULL DEFAULT 'monthly'
                    CHECK (retainer_period IN ('weekly', 'monthly', 'quarterly')),
                rollover_unused BOOLEAN NOT NULL DEFAULT false,
                billing_rate NUMERIC(10, 2),
                project_fee NUMERIC(12, 2),
                currency VARCHAR(3) NOT NULL DEFAULT 'USD',
                industry VARCHAR(100),
                headcount INTEGER,
                jurisdictions JSONB NOT NULL DEFAULT '[]'::jsonb,
                contact_name VARCHAR(255),
                contact_email VARCHAR(320),
                contact_phone VARCHAR(50),
                lead_pro_id UUID REFERENCES users(id) ON DELETE SET NULL,
                start_date DATE,
                notes TEXT,
                created_by UUID REFERENCES users(id),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_fractional_clients_status ON fractional_clients(status)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_fractional_clients_company_id ON fractional_clients(company_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_fractional_clients_lead_pro ON fractional_clients(lead_pro_id)")

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS fractional_assignments (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                client_id UUID NOT NULL REFERENCES fractional_clients(id) ON DELETE CASCADE,
                pro_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                role VARCHAR(20) NOT NULL DEFAULT 'consultant'
                    CHECK (role IN ('lead', 'consultant', 'jr')),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (client_id, pro_user_id)
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_fractional_assignments_client ON fractional_assignments(client_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_fractional_assignments_pro ON fractional_assignments(pro_user_id)")

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS fractional_scope_items (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                client_id UUID NOT NULL REFERENCES fractional_clients(id) ON DELETE CASCADE,
                service_category VARCHAR(40) NOT NULL DEFAULT 'other',
                title VARCHAR(255) NOT NULL,
                description TEXT,
                status VARCHAR(20) NOT NULL DEFAULT 'planned'
                    CHECK (status IN ('planned', 'active', 'on_hold', 'done')),
                priority VARCHAR(10) NOT NULL DEFAULT 'medium'
                    CHECK (priority IN ('low', 'medium', 'high')),
                created_by UUID REFERENCES users(id),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_fractional_scope_client ON fractional_scope_items(client_id, status)")

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS fractional_tasks (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                client_id UUID NOT NULL REFERENCES fractional_clients(id) ON DELETE CASCADE,
                scope_item_id UUID REFERENCES fractional_scope_items(id) ON DELETE SET NULL,
                title VARCHAR(255) NOT NULL,
                description TEXT,
                service_category VARCHAR(40) NOT NULL DEFAULT 'other',
                status VARCHAR(20) NOT NULL DEFAULT 'todo'
                    CHECK (status IN ('todo', 'in_progress', 'blocked', 'review', 'done')),
                priority VARCHAR(10) NOT NULL DEFAULT 'medium'
                    CHECK (priority IN ('low', 'medium', 'high')),
                assignee_pro_id UUID REFERENCES users(id) ON DELETE SET NULL,
                due_date DATE,
                estimated_hours NUMERIC(6, 2),
                billable BOOLEAN NOT NULL DEFAULT true,
                created_by UUID REFERENCES users(id),
                completed_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_fractional_tasks_client_status ON fractional_tasks(client_id, status)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_fractional_tasks_assignee ON fractional_tasks(assignee_pro_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_fractional_tasks_due ON fractional_tasks(due_date)")

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS fractional_time_entries (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                client_id UUID NOT NULL REFERENCES fractional_clients(id) ON DELETE CASCADE,
                task_id UUID REFERENCES fractional_tasks(id) ON DELETE SET NULL,
                pro_id UUID NOT NULL REFERENCES users(id),
                hours NUMERIC(6, 2) NOT NULL,
                entry_date DATE NOT NULL DEFAULT CURRENT_DATE,
                note TEXT,
                billable BOOLEAN NOT NULL DEFAULT true,
                service_category VARCHAR(40),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_fractional_time_client_date ON fractional_time_entries(client_id, entry_date)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_fractional_time_task ON fractional_time_entries(task_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_fractional_time_pro ON fractional_time_entries(pro_id)")

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS fractional_audit_log (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                client_id UUID REFERENCES fractional_clients(id) ON DELETE SET NULL,
                actor_id UUID REFERENCES users(id),
                action VARCHAR(64) NOT NULL,
                detail JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_fractional_audit_client ON fractional_audit_log(client_id, created_at DESC)")

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS broker_terms_acceptances (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                broker_id UUID NOT NULL REFERENCES brokers(id) ON DELETE CASCADE,
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                terms_version VARCHAR(50) NOT NULL,
                accepted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                ip_address VARCHAR(64),
                user_agent TEXT,
                UNIQUE (broker_id, user_id, terms_version)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_broker_terms_acceptances_lookup
            ON broker_terms_acceptances(broker_id, user_id, terms_version)
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS broker_branding_configs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                broker_id UUID NOT NULL UNIQUE REFERENCES brokers(id) ON DELETE CASCADE,
                branding_mode VARCHAR(20) NOT NULL DEFAULT 'direct'
                    CHECK (branding_mode IN ('direct', 'co_branded', 'white_label')),
                brand_display_name VARCHAR(255),
                brand_legal_name VARCHAR(255),
                logo_url TEXT,
                favicon_url TEXT,
                primary_color VARCHAR(20),
                secondary_color VARCHAR(20),
                login_subdomain VARCHAR(120) UNIQUE,
                custom_login_url TEXT,
                support_email VARCHAR(320),
                support_phone VARCHAR(50),
                support_url TEXT,
                email_from_name VARCHAR(255),
                email_from_address VARCHAR(320),
                powered_by_badge BOOLEAN NOT NULL DEFAULT true,
                hide_matcha_identity BOOLEAN NOT NULL DEFAULT false,
                mobile_branding_enabled BOOLEAN NOT NULL DEFAULT false,
                theme JSONB DEFAULT '{}'::jsonb,
                metadata JSONB DEFAULT '{}'::jsonb,
                created_by UUID REFERENCES users(id),
                updated_by UUID REFERENCES users(id),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_broker_branding_mode ON broker_branding_configs(branding_mode)
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS broker_company_transitions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                broker_id UUID NOT NULL REFERENCES brokers(id) ON DELETE CASCADE,
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                source_link_id UUID REFERENCES broker_company_links(id) ON DELETE SET NULL,
                mode VARCHAR(30) NOT NULL
                    CHECK (mode IN ('convert_to_direct', 'transfer_to_broker', 'sunset', 'matcha_managed')),
                status VARCHAR(20) NOT NULL DEFAULT 'planned'
                    CHECK (status IN ('planned', 'in_progress', 'completed', 'cancelled')),
                transfer_target_broker_id UUID REFERENCES brokers(id),
                grace_until TIMESTAMPTZ,
                matcha_managed_until TIMESTAMPTZ,
                data_handoff_status VARCHAR(20) NOT NULL DEFAULT 'not_required'
                    CHECK (data_handoff_status IN ('not_required', 'pending', 'in_progress', 'completed')),
                data_handoff_notes TEXT,
                started_at TIMESTAMPTZ,
                completed_at TIMESTAMPTZ,
                metadata JSONB DEFAULT '{}'::jsonb,
                created_by UUID REFERENCES users(id),
                updated_by UUID REFERENCES users(id),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_broker_company_transitions_broker_company
            ON broker_company_transitions(broker_id, company_id, status)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_broker_company_transitions_transfer_target
            ON broker_company_transitions(transfer_target_broker_id)
        """)
        await conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_broker_company_transitions_active_single
            ON broker_company_transitions(broker_id, company_id)
            WHERE status IN ('planned', 'in_progress')
        """)

        await conn.execute("""
            DO $$
            DECLARE existing_constraint TEXT;
            BEGIN
                SELECT c.conname INTO existing_constraint
                FROM pg_constraint c
                WHERE c.conrelid = 'brokers'::regclass
                  AND c.contype = 'c'
                  AND pg_get_constraintdef(c.oid) ILIKE '%post_termination_mode%';
                IF existing_constraint IS NOT NULL THEN
                    EXECUTE format('ALTER TABLE brokers DROP CONSTRAINT %I', existing_constraint);
                END IF;
                ALTER TABLE brokers
                    ADD CONSTRAINT brokers_post_termination_mode_check
                    CHECK (post_termination_mode IS NULL OR post_termination_mode IN ('convert_to_direct', 'transfer_to_broker', 'sunset', 'matcha_managed'));
            EXCEPTION WHEN undefined_table THEN
                NULL;
            END $$;
        """)

        await conn.execute("""
            DO $$
            DECLARE existing_constraint TEXT;
            BEGIN
                SELECT c.conname INTO existing_constraint
                FROM pg_constraint c
                WHERE c.conrelid = 'broker_company_links'::regclass
                  AND c.contype = 'c'
                  AND pg_get_constraintdef(c.oid) ILIKE '%post_termination_mode%';
                IF existing_constraint IS NOT NULL THEN
                    EXECUTE format('ALTER TABLE broker_company_links DROP CONSTRAINT %I', existing_constraint);
                END IF;
                ALTER TABLE broker_company_links
                    ADD CONSTRAINT broker_company_links_post_termination_mode_check
                    CHECK (post_termination_mode IS NULL OR post_termination_mode IN ('convert_to_direct', 'transfer_to_broker', 'sunset', 'matcha_managed'));
            EXCEPTION WHEN undefined_table THEN
                NULL;
            END $$;
        """)

        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'broker_company_links_current_transition_id_fkey'
                ) THEN
                    ALTER TABLE broker_company_links
                        ADD CONSTRAINT broker_company_links_current_transition_id_fkey
                        FOREIGN KEY (current_transition_id)
                        REFERENCES broker_company_transitions(id)
                        ON DELETE SET NULL;
                END IF;
            EXCEPTION WHEN undefined_table THEN
                NULL;
            END $$;
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS broker_client_setups (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                broker_id UUID NOT NULL REFERENCES brokers(id) ON DELETE CASCADE,
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                status VARCHAR(20) NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'invited', 'activated', 'expired', 'cancelled')),
                contact_name VARCHAR(255),
                contact_email VARCHAR(320),
                contact_phone VARCHAR(50),
                company_size_hint VARCHAR(50),
                headcount_hint INTEGER,
                preconfigured_features JSONB DEFAULT '{}'::jsonb,
                onboarding_template JSONB DEFAULT '{}'::jsonb,
                invite_token VARCHAR(128) UNIQUE,
                invite_expires_at TIMESTAMPTZ,
                invited_at TIMESTAMPTZ,
                activated_at TIMESTAMPTZ,
                expired_at TIMESTAMPTZ,
                cancelled_at TIMESTAMPTZ,
                created_by UUID REFERENCES users(id),
                updated_by UUID REFERENCES users(id),
                notes TEXT,
                locations JSONB DEFAULT '[]'::jsonb,
                onboarding_stage VARCHAR(30) DEFAULT 'submitted'
                    CHECK (onboarding_stage IN ('submitted', 'under_review', 'configuring', 'live')),
                metadata JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE (broker_id, company_id)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_broker_client_setups_broker_status
            ON broker_client_setups(broker_id, status)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_broker_client_setups_invite_token
            ON broker_client_setups(invite_token)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_broker_client_setups_invite_expires_at
            ON broker_client_setups(invite_expires_at)
        """)

