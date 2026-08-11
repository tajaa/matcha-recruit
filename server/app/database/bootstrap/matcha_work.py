"""bootstrap.matcha_work — mw_* tables (24), journal RLS, seeds (verbatim split of app/database.py lines 5185-5912).
"""


async def create_matcha_work(conn):
        # Company-scoped Work permission overrides. Defaults for owners,
        # clients, employees, and external collaborators are resolved by
        # services.matcha_work.work_permissions at request time.
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mw_work_permissions (
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                level VARCHAR(20) NOT NULL
                    CHECK (level IN ('member', 'reviewer', 'operator', 'admin')),
                granted_by UUID REFERENCES users(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (company_id, user_id)
            )
        """)
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mw_work_permissions_user "
            "ON mw_work_permissions(user_id)"
        )

        # Matcha Work tables (chat-driven offer letter generation)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mw_threads (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                created_by UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title VARCHAR(255) NOT NULL DEFAULT 'Untitled Chat',
                task_type VARCHAR(40) NOT NULL DEFAULT 'offer_letter'
                    CHECK (task_type IN ('offer_letter', 'review')),
                status VARCHAR(20) NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'finalized', 'archived')),
                current_state JSONB NOT NULL DEFAULT '{}'::jsonb,
                version INTEGER NOT NULL DEFAULT 0,
                is_pinned BOOLEAN NOT NULL DEFAULT false,
                linked_offer_letter_id UUID REFERENCES offer_letters(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mw_threads_company_id ON mw_threads(company_id)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mw_threads_created_by ON mw_threads(created_by)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mw_threads_company_status ON mw_threads(company_id, status)"
        )
        await conn.execute(
            "ALTER TABLE mw_threads ALTER COLUMN title SET DEFAULT 'Untitled Chat'"
        )
        await conn.execute(
            """
            UPDATE mw_threads
            SET title = 'Untitled Chat'
            WHERE title = 'Untitled Offer Letter'
            """
        )
        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'mw_threads' AND column_name = 'is_pinned'
                ) THEN
                    ALTER TABLE mw_threads ADD COLUMN is_pinned BOOLEAN NOT NULL DEFAULT false;
                END IF;
            END $$;
        """)
        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'mw_threads' AND column_name = 'compliance_mode'
                ) THEN
                    ALTER TABLE mw_threads ADD COLUMN compliance_mode BOOLEAN NOT NULL DEFAULT false;
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'mw_threads' AND column_name = 'payer_mode'
                ) THEN
                    ALTER TABLE mw_threads ADD COLUMN payer_mode BOOLEAN NOT NULL DEFAULT false;
                END IF;
            END $$;
        """)
        # Registry thread modes (matcha_work_modes.THREAD_MODES) — migration mwmodes01
        await conn.execute("""
            ALTER TABLE mw_threads ADD COLUMN IF NOT EXISTS benefits_mode BOOLEAN NOT NULL DEFAULT false;
            ALTER TABLE mw_threads ADD COLUMN IF NOT EXISTS legal_mode BOOLEAN NOT NULL DEFAULT false;
            ALTER TABLE mw_threads ADD COLUMN IF NOT EXISTS risk_mode BOOLEAN NOT NULL DEFAULT false;
            ALTER TABLE mw_threads ADD COLUMN IF NOT EXISTS training_mode BOOLEAN NOT NULL DEFAULT false;
        """)
        # HR Pilot thread mode — migration hrpilot01
        await conn.execute("""
            ALTER TABLE mw_threads ADD COLUMN IF NOT EXISTS hr_pilot_mode BOOLEAN NOT NULL DEFAULT false;
        """)
        # Huume agentic onboarding thread mode — migration huume02
        await conn.execute("""
            ALTER TABLE mw_threads ADD COLUMN IF NOT EXISTS huume_mode BOOLEAN NOT NULL DEFAULT false;
        """)
        # Huume agent run/step audit tables — migration huume03
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS huume_runs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                thread_id UUID NOT NULL REFERENCES mw_threads(id) ON DELETE CASCADE,
                user_id UUID,
                trigger TEXT NOT NULL DEFAULT 'user_turn',
                status TEXT NOT NULL DEFAULT 'running',
                model_calls INTEGER NOT NULL DEFAULT 0,
                token_usage JSONB,
                started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                completed_at TIMESTAMPTZ,
                error TEXT,
                CONSTRAINT huume_runs_trigger_check CHECK (trigger IN ('user_turn', 'plan_execution')),
                CONSTRAINT huume_runs_status_check CHECK (status IN ('running', 'completed', 'force_finished', 'failed'))
            );
            CREATE INDEX IF NOT EXISTS idx_huume_runs_thread ON huume_runs(thread_id, started_at DESC);
            CREATE INDEX IF NOT EXISTS idx_huume_runs_company ON huume_runs(company_id);
            CREATE TABLE IF NOT EXISTS huume_steps (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                run_id UUID NOT NULL REFERENCES huume_runs(id) ON DELETE CASCADE,
                seq INTEGER NOT NULL,
                tool TEXT NOT NULL,
                kind TEXT NOT NULL,
                label TEXT NOT NULL,
                args JSONB,
                result JSONB,
                status TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT huume_steps_kind_check CHECK (kind IN ('read', 'staged', 'write', 'finish')),
                CONSTRAINT huume_steps_status_check CHECK (status IN ('ok', 'rejected', 'error', 'skipped'))
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_huume_steps_run_seq ON huume_steps(run_id, seq);
        """)
        await conn.execute("""
            DO $$
            DECLARE
                c RECORD;
            BEGIN
                FOR c IN
                    SELECT conname
                    FROM pg_constraint
                    WHERE conrelid = 'mw_threads'::regclass
                      AND contype = 'c'
                      AND pg_get_constraintdef(oid) ILIKE '%task_type%'
                LOOP
                    EXECUTE format('ALTER TABLE mw_threads DROP CONSTRAINT %I', c.conname);
                END LOOP;

                ALTER TABLE mw_threads
                ADD CONSTRAINT mw_threads_task_type_check
                CHECK (task_type IN ('offer_letter', 'review'));
            EXCEPTION WHEN duplicate_object THEN
                NULL;
            END $$;
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mw_elements (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                thread_id UUID NOT NULL UNIQUE REFERENCES mw_threads(id) ON DELETE CASCADE,
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                created_by UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                element_type VARCHAR(40) NOT NULL DEFAULT 'offer_letter'
                    CHECK (element_type IN ('offer_letter', 'review')),
                title VARCHAR(255) NOT NULL DEFAULT 'Untitled Chat',
                status VARCHAR(20) NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'finalized', 'archived')),
                state_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                version INTEGER NOT NULL DEFAULT 0,
                linked_offer_letter_id UUID REFERENCES offer_letters(id) ON DELETE SET NULL,
                is_materialized BOOLEAN NOT NULL DEFAULT false,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mw_elements_company_status ON mw_elements(company_id, status)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mw_elements_created_by ON mw_elements(created_by)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mw_elements_thread_id ON mw_elements(thread_id)"
        )
        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'mw_elements' AND column_name = 'is_materialized'
                ) THEN
                    ALTER TABLE mw_elements ADD COLUMN is_materialized BOOLEAN NOT NULL DEFAULT false;
                END IF;
            END $$;
        """)
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mw_elements_company_materialized ON mw_elements(company_id, is_materialized)"
        )
        await conn.execute(
            """
            UPDATE mw_elements
            SET is_materialized = (
                linked_offer_letter_id IS NOT NULL
                OR status = 'finalized'
            )
            WHERE is_materialized = false
            """
        )
        await conn.execute(
            """
            INSERT INTO mw_elements (
                thread_id,
                company_id,
                created_by,
                element_type,
                title,
                status,
                state_json,
                version,
                linked_offer_letter_id,
                is_materialized,
                created_at,
                updated_at
            )
            SELECT
                t.id,
                t.company_id,
                t.created_by,
                t.task_type,
                t.title,
                t.status,
                t.current_state,
                t.version,
                t.linked_offer_letter_id,
                (t.linked_offer_letter_id IS NOT NULL OR t.status = 'finalized'),
                t.created_at,
                t.updated_at
            FROM mw_threads t
            ON CONFLICT (thread_id) DO UPDATE
            SET
                company_id = EXCLUDED.company_id,
                created_by = EXCLUDED.created_by,
                element_type = EXCLUDED.element_type,
                title = EXCLUDED.title,
                status = EXCLUDED.status,
                state_json = EXCLUDED.state_json,
                version = EXCLUDED.version,
                linked_offer_letter_id = EXCLUDED.linked_offer_letter_id,
                is_materialized = EXCLUDED.is_materialized,
                updated_at = EXCLUDED.updated_at
            """
        )
        await conn.execute("""
            DO $$
            DECLARE
                c RECORD;
            BEGIN
                FOR c IN
                    SELECT conname
                    FROM pg_constraint
                    WHERE conrelid = 'mw_elements'::regclass
                      AND contype = 'c'
                      AND pg_get_constraintdef(oid) ILIKE '%element_type%'
                LOOP
                    EXECUTE format('ALTER TABLE mw_elements DROP CONSTRAINT %I', c.conname);
                END LOOP;

                ALTER TABLE mw_elements
                ADD CONSTRAINT mw_elements_element_type_check
                CHECK (element_type IN ('offer_letter', 'review'));
            EXCEPTION WHEN duplicate_object THEN
                NULL;
            END $$;
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mw_messages (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                thread_id UUID NOT NULL REFERENCES mw_threads(id) ON DELETE CASCADE,
                role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
                content TEXT NOT NULL,
                version_created INTEGER,
                metadata JSONB,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mw_messages_thread_id ON mw_messages(thread_id)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mw_messages_thread_created_at ON mw_messages(thread_id, created_at)"
        )
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mw_document_versions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                thread_id UUID NOT NULL REFERENCES mw_threads(id) ON DELETE CASCADE,
                version INTEGER NOT NULL,
                state_json JSONB NOT NULL,
                diff_summary TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(thread_id, version)
            )
        """)
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mw_document_versions_thread_id ON mw_document_versions(thread_id)"
        )
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mw_pdf_cache (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                thread_id UUID NOT NULL REFERENCES mw_threads(id) ON DELETE CASCADE,
                version INTEGER NOT NULL,
                pdf_url TEXT NOT NULL,
                is_draft BOOLEAN NOT NULL DEFAULT true,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(thread_id, version, is_draft)
            )
        """)
        # Backfill/repair uniqueness for existing environments created before is_draft-aware caching.
        await conn.execute("""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'mw_pdf_cache_thread_id_version_key'
                      AND conrelid = 'mw_pdf_cache'::regclass
                ) THEN
                    ALTER TABLE mw_pdf_cache DROP CONSTRAINT mw_pdf_cache_thread_id_version_key;
                END IF;

                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'mw_pdf_cache_thread_id_version_is_draft_key'
                      AND conrelid = 'mw_pdf_cache'::regclass
                ) THEN
                    ALTER TABLE mw_pdf_cache
                    ADD CONSTRAINT mw_pdf_cache_thread_id_version_is_draft_key
                    UNIQUE(thread_id, version, is_draft);
                END IF;
            END $$;
        """)
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mw_pdf_cache_thread_id ON mw_pdf_cache(thread_id)"
        )
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mw_token_usage_events (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                thread_id UUID NOT NULL REFERENCES mw_threads(id) ON DELETE CASCADE,
                model VARCHAR(120) NOT NULL,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                total_tokens INTEGER,
                estimated BOOLEAN NOT NULL DEFAULT false,
                operation VARCHAR(40) NOT NULL DEFAULT 'send_message',
                cost_dollars NUMERIC(10,6),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_mw_token_usage_events_company_user_model_created
            ON mw_token_usage_events(company_id, user_id, model, created_at)
            """
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mw_token_usage_events_thread_id ON mw_token_usage_events(thread_id)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mw_token_usage_events_user_created ON mw_token_usage_events(user_id, created_at)"
        )
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mw_token_quotas (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
                token_limit INTEGER NOT NULL DEFAULT 100000,
                window_hours INTEGER NOT NULL DEFAULT 12,
                is_active BOOLEAN DEFAULT true,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mw_token_quotas_user ON mw_token_quotas(user_id)"
        )
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mw_review_requests (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                thread_id UUID NOT NULL REFERENCES mw_threads(id) ON DELETE CASCADE,
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                recipient_email VARCHAR(320) NOT NULL,
                token VARCHAR(255) NOT NULL UNIQUE,
                status VARCHAR(20) NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'sent', 'failed', 'submitted')),
                feedback TEXT,
                rating INTEGER CHECK (rating >= 1 AND rating <= 5),
                sent_at TIMESTAMPTZ,
                submitted_at TIMESTAMPTZ,
                last_error TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE(thread_id, recipient_email)
            )
        """)
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mw_review_requests_thread_id ON mw_review_requests(thread_id)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mw_review_requests_company_status ON mw_review_requests(company_id, status)"
        )
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mw_review_requests_token ON mw_review_requests(token)"
        )
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mw_credit_balances (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL UNIQUE REFERENCES companies(id) ON DELETE CASCADE,
                credits_remaining NUMERIC(10,6) NOT NULL DEFAULT 0 CHECK (credits_remaining >= 0),
                total_credits_purchased NUMERIC(10,6) NOT NULL DEFAULT 0 CHECK (total_credits_purchased >= 0),
                total_credits_granted NUMERIC(10,6) NOT NULL DEFAULT 0 CHECK (total_credits_granted >= 0),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mw_credit_transactions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                transaction_type VARCHAR(20) NOT NULL
                    CHECK (transaction_type IN ('purchase', 'grant', 'deduction', 'refund', 'adjustment')),
                credits_delta NUMERIC(10,6) NOT NULL,
                credits_after NUMERIC(10,6) NOT NULL CHECK (credits_after >= 0),
                description TEXT,
                reference_id UUID,
                created_by UUID REFERENCES users(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_mw_credit_transactions_company_created
            ON mw_credit_transactions(company_id, created_at DESC)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_mw_credit_transactions_company_type
            ON mw_credit_transactions(company_id, transaction_type)
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mw_stripe_sessions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                stripe_session_id VARCHAR(255) NOT NULL UNIQUE,
                credit_pack_id VARCHAR(50) NOT NULL,
                credits_to_add NUMERIC(10,6) NOT NULL CHECK (credits_to_add > 0),
                amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
                status VARCHAR(20) NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'completed', 'expired')),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                fulfilled_at TIMESTAMPTZ
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_mw_stripe_sessions_company_status
            ON mw_stripe_sessions(company_id, status)
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mw_subscriptions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                stripe_subscription_id VARCHAR(255) NOT NULL UNIQUE,
                stripe_customer_id VARCHAR(255) NOT NULL,
                pack_id VARCHAR(50) NOT NULL,
                credits_per_cycle NUMERIC(10,6) NOT NULL,
                amount_cents INTEGER NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'active',
                current_period_end TIMESTAMPTZ,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                canceled_at TIMESTAMPTZ
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_mw_subscriptions_company_id
            ON mw_subscriptions(company_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_mw_subscriptions_status
            ON mw_subscriptions(status)
        """)
        await conn.execute("""
            INSERT INTO mw_credit_balances (
                company_id,
                credits_remaining,
                total_credits_purchased,
                total_credits_granted
            )
            SELECT
                c.id,
                0,
                0,
                0
            FROM companies c
            ON CONFLICT (company_id) DO NOTHING
        """)

        # ===========================================
        # Token Budgets (token-based billing)
        # ===========================================
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mw_token_budgets (
                company_id UUID PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
                free_tokens_used BIGINT NOT NULL DEFAULT 0,
                free_token_limit BIGINT NOT NULL DEFAULT 1000000,
                subscription_tokens_used BIGINT NOT NULL DEFAULT 0,
                subscription_token_limit BIGINT NOT NULL DEFAULT 0,
                subscription_period_start TIMESTAMPTZ,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute("""
            INSERT INTO mw_token_budgets (company_id, free_tokens_used, free_token_limit)
            SELECT c.id, 0, 1000000
            FROM companies c
            ON CONFLICT (company_id) DO NOTHING
        """)

        # ===========================================
        # Project File Attachments
        # ===========================================
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mw_project_files (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                project_id UUID NOT NULL REFERENCES mw_projects(id) ON DELETE CASCADE,
                uploaded_by UUID NOT NULL REFERENCES users(id),
                filename VARCHAR(500) NOT NULL,
                storage_url TEXT NOT NULL,
                content_type VARCHAR(100),
                file_size BIGINT NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_mw_project_files_project_id ON mw_project_files(project_id)")

        # Folders for manual organization of project Files (migration mwfold0001).
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mw_project_folders (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                project_id UUID NOT NULL REFERENCES mw_projects(id) ON DELETE CASCADE,
                parent_id UUID REFERENCES mw_project_folders(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                created_by UUID,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_mw_project_folders_project_id ON mw_project_folders(project_id)")
        await conn.execute("ALTER TABLE mw_project_files ADD COLUMN IF NOT EXISTS folder_id UUID REFERENCES mw_project_folders(id) ON DELETE SET NULL")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_mw_project_files_folder_id ON mw_project_files(folder_id) WHERE folder_id IS NOT NULL")
        # Partial unique index so the chat->Files sync dedupes root mirrors.
        await conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_mw_project_files_project_url ON mw_project_files(project_id, storage_url) WHERE task_id IS NULL")

        # Checklist items under a kanban task (migration mwsub0001). A complex
        # feature card decomposes into trackable child items; the board shows
        # "done/total" and a reviewer can re-open specific items on send-back.
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mw_subtasks (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                task_id UUID NOT NULL REFERENCES mw_tasks(id) ON DELETE CASCADE,
                project_id UUID NOT NULL,
                company_id UUID NOT NULL,
                title TEXT NOT NULL,
                is_done BOOLEAN NOT NULL DEFAULT false,
                position INTEGER NOT NULL DEFAULT 0,
                round_index INTEGER NOT NULL DEFAULT 1,
                assigned_to UUID,
                created_by UUID,
                completed_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_mw_subtasks_task ON mw_subtasks(task_id, position)")

        # In-app comments on project notes (sections). Sections live in
        # mw_projects.sections JSONB with short hex string ids (not UUIDs), so
        # section_id is TEXT. reply_to_comment_id is reserved for threading
        # (v1 UI renders a flat list). Migration mwseccmt01.
        # anchor_start/anchor_end/quoted_text attach a comment to a highlighted
        # text range (nil = a general, whole-note comment); resolved hides the
        # highlight + tucks the thread away. Migration seccmtanchor01.
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mw_section_comments (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                project_id UUID NOT NULL,
                section_id TEXT NOT NULL,
                company_id UUID NOT NULL,
                user_id UUID NOT NULL,
                content TEXT NOT NULL,
                reply_to_comment_id UUID,
                anchor_start INTEGER,
                anchor_end INTEGER,
                quoted_text TEXT,
                resolved BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_mw_section_comments_section ON mw_section_comments(project_id, section_id, created_at)")

        # Per-user project pin (independent across collaborators)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mw_project_pins (
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                project_id UUID NOT NULL REFERENCES mw_projects(id) ON DELETE CASCADE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (user_id, project_id)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_mw_project_pins_user
            ON mw_project_pins(user_id, created_at DESC)
        """)

        # Free-tier resource pins (templates, glossary, state guides, etc).
        # Generic enough that any tier can pin via the same table.
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS resource_pins (
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                resource_kind VARCHAR(32) NOT NULL
                    CHECK (resource_kind IN ('template','job_description','glossary','state_guide','calculator')),
                resource_id VARCHAR(128) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (user_id, resource_kind, resource_id)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_resource_pins_user
            ON resource_pins(user_id, created_at DESC)
        """)

        # Journals — top-level matcha-work surface for chronological notes
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mw_journals (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                created_by UUID NOT NULL REFERENCES users(id),
                title VARCHAR(255) NOT NULL DEFAULT 'Untitled Journal',
                description TEXT,
                color VARCHAR(20),
                icon VARCHAR(64),
                status VARCHAR(20) NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'archived')),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_mw_journals_created_by ON mw_journals(created_by)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_mw_journals_company_id ON mw_journals(company_id)")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mw_journal_entries (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                journal_id UUID NOT NULL REFERENCES mw_journals(id) ON DELETE CASCADE,
                author_id UUID NOT NULL REFERENCES users(id),
                title VARCHAR(255),
                content TEXT NOT NULL DEFAULT '',
                entry_date DATE NOT NULL DEFAULT CURRENT_DATE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_mw_journal_entries_journal_date
            ON mw_journal_entries(journal_id, entry_date DESC, created_at DESC)
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mw_journal_collaborators (
                journal_id UUID NOT NULL REFERENCES mw_journals(id) ON DELETE CASCADE,
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                invited_by UUID REFERENCES users(id),
                role VARCHAR(20) NOT NULL DEFAULT 'collaborator'
                    CHECK (role IN ('owner', 'collaborator')),
                status VARCHAR(20) NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'pending', 'removed')),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (journal_id, user_id)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_mw_journal_collaborators_user
            ON mw_journal_collaborators(user_id, status)
        """)
        # Obsidian-style folder tree for the Journals hub (adjacency list,
        # company-scoped) + journal folder placement + kind discriminator
        # (note/blog/todo/novel/screenplay) for create-time templates.
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mw_journal_folders (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                parent_id UUID REFERENCES mw_journal_folders(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                created_by UUID REFERENCES users(id),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_mw_journal_folders_company ON mw_journal_folders(company_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_mw_journal_folders_parent ON mw_journal_folders(parent_id)")
        await conn.execute("ALTER TABLE mw_journal_folders ADD COLUMN IF NOT EXISTS color VARCHAR(20)")
        await conn.execute("ALTER TABLE mw_journals ADD COLUMN IF NOT EXISTS folder_id UUID REFERENCES mw_journal_folders(id) ON DELETE SET NULL")
        await conn.execute("ALTER TABLE mw_journals ADD COLUMN IF NOT EXISTS kind VARCHAR(20) NOT NULL DEFAULT 'journal'")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_mw_journals_folder ON mw_journals(folder_id)")

        # ── Per-user RLS on journal tables (dormant under superuser) ──────
        # Journals are PERSONAL: visible to created_by or an active
        # collaborator; folders are strictly per-user. These policies are
        # bypassed while the app connects as the `matcha` SUPERUSER and only
        # enforce once DATABASE_URL is switched to `matcha_app` (NOBYPASSRLS,
        # c9cfac81407a). FORCE is required because matcha_app owns the tables.
        # Mirrors the handbook RLS block above; idempotent. Keep in sync with
        # migration mwjrnlrls01. `mw_journal_collaborators` stays un-RLS'd —
        # the mw_journals policy reads it as the membership oracle.
        _rls_journal_specs = [
            ("mw_journals", "journal_user_isolation",
             "created_by::text = current_setting('app.current_user_id', true) "
             "OR current_setting('app.is_admin', true) = 'true' "
             "OR EXISTS (SELECT 1 FROM mw_journal_collaborators jc "
             "WHERE jc.journal_id = mw_journals.id "
             "AND jc.user_id::text = current_setting('app.current_user_id', true) "
             "AND jc.status = 'active')"),
            ("mw_journal_entries", "entry_user_isolation",
             "current_setting('app.is_admin', true) = 'true' "
             "OR EXISTS (SELECT 1 FROM mw_journals j "
             "WHERE j.id = mw_journal_entries.journal_id)"),
            ("mw_journal_folders", "folder_user_isolation",
             "created_by::text = current_setting('app.current_user_id', true) "
             "OR current_setting('app.is_admin', true) = 'true'"),
        ]
        for _tbl, _policy, _pred in _rls_journal_specs:
            await conn.execute(f"ALTER TABLE IF EXISTS {_tbl} ENABLE ROW LEVEL SECURITY")
            await conn.execute(f"ALTER TABLE IF EXISTS {_tbl} FORCE ROW LEVEL SECURITY")
            await conn.execute(f"""
                DO $$ BEGIN
                    CREATE POLICY {_policy} ON {_tbl}
                        USING ({_pred})
                        WITH CHECK ({_pred});
                EXCEPTION WHEN duplicate_object THEN NULL;
                          WHEN undefined_table THEN NULL;
                END $$
            """)

        # Personal productivity kanban — user-scoped boards + cards (todo /
        # in_progress / done). Cards may back-link to a journal when created
        # from a text selection.
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mw_productivity_boards (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
                title VARCHAR(255) NOT NULL DEFAULT 'My To-Dos',
                is_default BOOLEAN NOT NULL DEFAULT FALSE,
                status VARCHAR(20) NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'archived')),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_mw_prod_boards_user ON mw_productivity_boards(user_id)")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mw_productivity_cards (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                board_id UUID NOT NULL REFERENCES mw_productivity_boards(id) ON DELETE CASCADE,
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                notes TEXT,
                board_column VARCHAR(20) NOT NULL DEFAULT 'todo'
                    CHECK (board_column IN ('todo', 'in_progress', 'done')),
                position INTEGER NOT NULL DEFAULT 0,
                source_journal_id UUID REFERENCES mw_journals(id) ON DELETE SET NULL,
                source_excerpt TEXT,
                completed_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_mw_prod_cards_board ON mw_productivity_cards(board_id, board_column, position)")
        await conn.execute("ALTER TABLE mw_productivity_cards ADD COLUMN IF NOT EXISTS due_date DATE")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_mw_prod_cards_due ON mw_productivity_cards(board_id, due_date)")
