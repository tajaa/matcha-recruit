"""bootstrap.leads_policies — leads agent + policy management (calls _ensure_handbook_tables) (verbatim split of app/database.py lines 2356-2749).
"""
from app.database.handbook import _ensure_handbook_tables


async def create_leads_policies(conn):
        # ===========================================
        # Leads Agent Tables (Executive Lead Generation)
        # ===========================================

        # Executive leads table (positions being tracked)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS executive_leads (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                
                -- Source info
                source_type VARCHAR(50) NOT NULL,
                source_job_id VARCHAR(255),
                source_url TEXT,
                
                -- Position details
                title VARCHAR(255) NOT NULL,
                company_name VARCHAR(255) NOT NULL,
                company_domain VARCHAR(255),
                location VARCHAR(255),
                salary_min INTEGER,
                salary_max INTEGER,
                salary_text VARCHAR(255),
                seniority_level VARCHAR(50),
                job_description TEXT,
                
                -- Gemini analysis
                relevance_score INTEGER,
                gemini_analysis JSONB,
                
                -- Pipeline tracking
                status VARCHAR(50) DEFAULT 'new',
                priority VARCHAR(20) DEFAULT 'medium',
                notes TEXT,
                
                -- Timestamps
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                last_activity_at TIMESTAMP
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_executive_leads_status ON executive_leads(status)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_executive_leads_priority ON executive_leads(priority)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_executive_leads_company ON executive_leads(company_name)
        """)

        # Add unique constraint for deduplication (if not exists)
        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'executive_leads_dedupe'
                ) THEN
                    ALTER TABLE executive_leads ADD CONSTRAINT executive_leads_dedupe
                    UNIQUE (company_name, title, location);
                END IF;
            EXCEPTION WHEN duplicate_table THEN
                NULL;
            END $$;
        """)

        # Lead contacts table (decision-makers)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS lead_contacts (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                lead_id UUID NOT NULL REFERENCES executive_leads(id) ON DELETE CASCADE,
                
                -- Contact info
                name VARCHAR(255) NOT NULL,
                first_name VARCHAR(100),
                last_name VARCHAR(100),
                title VARCHAR(255),
                email VARCHAR(255),
                email_confidence INTEGER,
                phone VARCHAR(50),
                linkedin_url TEXT,
                
                -- Source & ranking
                is_primary BOOLEAN DEFAULT false,
                source VARCHAR(100),
                gemini_ranking_reason TEXT,
                
                -- Outreach tracking
                outreach_status VARCHAR(50) DEFAULT 'pending',
                contacted_at TIMESTAMP,
                opened_at TIMESTAMP,
                replied_at TIMESTAMP,
                
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_lead_contacts_lead_id ON lead_contacts(lead_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_lead_contacts_is_primary ON lead_contacts(is_primary)
        """)

        # Lead emails table (drafts and sent emails)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS lead_emails (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                lead_id UUID NOT NULL REFERENCES executive_leads(id) ON DELETE CASCADE,
                contact_id UUID NOT NULL REFERENCES lead_contacts(id) ON DELETE CASCADE,
                
                -- Email content
                subject VARCHAR(500) NOT NULL,
                body TEXT NOT NULL,
                
                -- Status
                status VARCHAR(50) DEFAULT 'draft',
                
                -- MailerSend tracking
                mailersend_message_id VARCHAR(255),
                sent_at TIMESTAMP,
                delivered_at TIMESTAMP,
                opened_at TIMESTAMP,
                clicked_at TIMESTAMP,
                replied_at TIMESTAMP,
                
                -- Metadata
                created_at TIMESTAMP DEFAULT NOW(),
                approved_at TIMESTAMP,
                approved_by UUID REFERENCES users(id)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_lead_emails_lead_id ON lead_emails(lead_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_lead_emails_status ON lead_emails(status)
        """)

        # Lead search configurations (saved search presets)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS lead_search_configs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name VARCHAR(255) NOT NULL,
                
                -- Search params
                role_types JSONB DEFAULT '[]',
                locations JSONB DEFAULT '[]',
                industries JSONB DEFAULT '[]',
                salary_min INTEGER,
                salary_max INTEGER,
                
                -- Settings
                is_active BOOLEAN DEFAULT true,
                last_run_at TIMESTAMP,
                
                created_by UUID REFERENCES users(id),
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_lead_search_configs_created_by ON lead_search_configs(created_by)
        """)

        # Company enrichment cache (avoid duplicate API calls)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS company_enrichment_cache (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                domain VARCHAR(255) UNIQUE NOT NULL,
                company_name VARCHAR(255),
                industry VARCHAR(100),
                employee_count VARCHAR(50),
                linkedin_url TEXT,
                twitter_handle VARCHAR(100),
                enrichment_data JSONB,
                source VARCHAR(50),
                fetched_at TIMESTAMP DEFAULT NOW(),
                expires_at TIMESTAMP
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_company_enrichment_domain ON company_enrichment_cache(domain)
        """)

        # ===========================================
        # Policy Management Tables
        # ===========================================

        # Policies table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS policies (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                title VARCHAR(500) NOT NULL,
                description TEXT,
                content TEXT NOT NULL DEFAULT '',
                file_url VARCHAR(500),
                version VARCHAR(50) NOT NULL DEFAULT '1.0',
                status VARCHAR(20) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'archived')),
                category VARCHAR(50),
                source_type VARCHAR(20) NOT NULL DEFAULT 'manual',
                effective_date DATE,
                review_date DATE,
                original_filename VARCHAR(500),
                mime_type VARCHAR(100),
                page_count INTEGER,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                created_by UUID REFERENCES users(id)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_policies_company_id ON policies(company_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_policies_status ON policies(status)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_policies_category ON policies(category)
        """)

        # Policy signatures table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS policy_signatures (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                policy_id UUID NOT NULL REFERENCES policies(id) ON DELETE CASCADE,
                signer_type VARCHAR(20) NOT NULL CHECK (signer_type IN ('candidate', 'employee', 'external')),
                signer_id UUID,
                signer_name VARCHAR(500) NOT NULL,
                signer_email VARCHAR(500) NOT NULL,
                token VARCHAR(500) NOT NULL UNIQUE,
                status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'signed', 'declined', 'expired')),
                signed_at TIMESTAMP,
                signature_data TEXT,
                ip_address VARCHAR(100),
                expires_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_policy_signatures_policy_id ON policy_signatures(policy_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_policy_signatures_token ON policy_signatures(token)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_policy_signatures_status ON policy_signatures(status)
        """)

        await _ensure_handbook_tables(conn)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS employee_onboarding_drafts (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                draft_state JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(company_id, user_id)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_employee_onboarding_drafts_company_user
            ON employee_onboarding_drafts(company_id, user_id)
        """)

        # Healthcare employee credentials
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS employee_credentials (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
                org_id UUID NOT NULL,
                license_type VARCHAR(50),
                license_number VARCHAR(100),
                license_state VARCHAR(2),
                license_expiration DATE,
                npi_number VARCHAR(20),
                dea_number VARCHAR(20),
                dea_expiration DATE,
                board_certification VARCHAR(200),
                board_certification_expiration DATE,
                clinical_specialty VARCHAR(100),
                oig_last_checked DATE,
                oig_status VARCHAR(20) DEFAULT 'not_checked',
                malpractice_carrier VARCHAR(200),
                malpractice_policy_number VARCHAR(100),
                malpractice_expiration DATE,
                health_clearances JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(employee_id)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_employee_credentials_org
            ON employee_credentials(org_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_employee_credentials_expiry
            ON employee_credentials(license_expiration)
            WHERE license_expiration IS NOT NULL
        """)

        # Healthcare credential document uploads
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS credential_documents (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL,
                employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
                document_type VARCHAR(50) NOT NULL,
                filename VARCHAR(255) NOT NULL,
                file_path VARCHAR(500) NOT NULL,
                mime_type VARCHAR(100),
                file_size INTEGER,
                extracted_data JSONB,
                extraction_status VARCHAR(20) DEFAULT 'pending',
                review_status VARCHAR(20) DEFAULT 'pending',
                reviewed_by UUID REFERENCES users(id),
                reviewed_at TIMESTAMP,
                review_notes TEXT,
                uploaded_by UUID REFERENCES users(id),
                uploaded_via VARCHAR(20) DEFAULT 'admin',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_cred_docs_employee
            ON credential_documents(employee_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_cred_docs_company
            ON credential_documents(company_id)
        """)

        await conn.execute("""
            DO $$
            BEGIN
                IF to_regclass('employee_documents') IS NOT NULL THEN
                    EXECUTE '
                        CREATE UNIQUE INDEX IF NOT EXISTS idx_employee_documents_active_doc_unique
                        ON employee_documents(employee_id, doc_type)
                        WHERE status IN (''pending_signature'', ''signed'')
                    ';
                END IF;
            END$$;
        """)
        await conn.execute("""
            DO $$
            BEGIN
                IF to_regclass('employees') IS NOT NULL THEN
                    IF NOT EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_name = 'employees'
                          AND column_name = 'personal_email'
                    ) THEN
                        ALTER TABLE employees ADD COLUMN personal_email VARCHAR(255);
                    END IF;
                    EXECUTE 'CREATE INDEX IF NOT EXISTS idx_employees_personal_email ON employees(personal_email)';
                END IF;
            END$$;
        """)
        await conn.execute("""
            DO $$
            BEGIN
                IF to_regclass('employees') IS NOT NULL THEN
                    IF NOT EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_name = 'employees'
                          AND column_name = 'employment_status'
                    ) THEN
                        ALTER TABLE employees ADD COLUMN employment_status VARCHAR(30) DEFAULT 'active';
                    END IF;
                    IF NOT EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_name = 'employees'
                          AND column_name = 'status_changed_at'
                    ) THEN
                        ALTER TABLE employees ADD COLUMN status_changed_at TIMESTAMP;
                    END IF;
                    IF NOT EXISTS (
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_name = 'employees'
                          AND column_name = 'status_reason'
                    ) THEN
                        ALTER TABLE employees ADD COLUMN status_reason TEXT;
                    END IF;
                END IF;
            END$$;
        """)

