"""bootstrap.jurisdictions — jurisdiction compliance repository (late FK into compliance tables) (verbatim split of app/database.py lines 3148-3496).
"""


async def create_jurisdictions(conn):
        # ===========================================
        # Jurisdiction Compliance Repository Tables
        # ===========================================

        # Jurisdictions table — first-class entity for a city+state
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS jurisdictions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                city VARCHAR(100) NOT NULL,
                state VARCHAR(2) NOT NULL,
                county VARCHAR(100),
                last_verified_at TIMESTAMP,
                requirement_count INTEGER DEFAULT 0,
                legislation_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(city, state)
            )
        """)

        # Jurisdiction requirements — growing repository of employment requirements per jurisdiction
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS jurisdiction_requirements (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                jurisdiction_id UUID NOT NULL REFERENCES jurisdictions(id) ON DELETE CASCADE,
                requirement_key TEXT NOT NULL,
                category VARCHAR(50) NOT NULL,
                jurisdiction_level VARCHAR(20) NOT NULL,
                jurisdiction_name VARCHAR(100) NOT NULL,
                title VARCHAR(500) NOT NULL,
                description TEXT,
                current_value VARCHAR(100),
                numeric_value DECIMAL(10, 4),
                source_url VARCHAR(500),
                source_name VARCHAR(100),
                effective_date DATE,
                expiration_date DATE,
                previous_value VARCHAR(100),
                previous_description TEXT,
                change_status VARCHAR(20) DEFAULT 'new',
                last_changed_at TIMESTAMP,
                last_verified_at TIMESTAMP NOT NULL DEFAULT NOW(),
                is_bookmarked BOOLEAN NOT NULL DEFAULT false,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(jurisdiction_id, requirement_key)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_jurisdiction_requirements_jurisdiction
            ON jurisdiction_requirements(jurisdiction_id)
        """)
        # Add rate_type column for minimum wage variants
        await conn.execute("""
            ALTER TABLE jurisdiction_requirements
            ADD COLUMN IF NOT EXISTS rate_type VARCHAR(50)
        """)
        # Add is_bookmarked column for accuracy review flagging
        await conn.execute("""
            ALTER TABLE jurisdiction_requirements
            ADD COLUMN IF NOT EXISTS is_bookmarked BOOLEAN NOT NULL DEFAULT false
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_jurisdiction_requirements_rate_type
            ON jurisdiction_requirements(rate_type)
        """)
        # Add requires_written_policy column for handbook injection filtering
        await conn.execute("""
            ALTER TABLE jurisdiction_requirements
            ADD COLUMN IF NOT EXISTS requires_written_policy BOOLEAN
        """)
        # Add applicable_industries for industry-specific filtering at sync time
        await conn.execute("""
            ALTER TABLE jurisdiction_requirements
            ADD COLUMN IF NOT EXISTS applicable_industries TEXT[]
        """)
        # Add implementation_steps (JSONB array of "how to comply" steps from research)
        await conn.execute("""
            ALTER TABLE jurisdiction_requirements
            ADD COLUMN IF NOT EXISTS implementation_steps JSONB
        """)
        # Source-liveness tracking: flag a dead source_url instead of erasing it
        # (the URL is the re-check pointer to the authority). See
        # compliance_service._validate_source_urls.
        await conn.execute("""
            ALTER TABLE jurisdiction_requirements
            ADD COLUMN IF NOT EXISTS source_url_status VARCHAR(20) DEFAULT 'unchecked'
        """)
        await conn.execute("""
            ALTER TABLE jurisdiction_requirements
            ADD COLUMN IF NOT EXISTS source_checked_at TIMESTAMP
        """)

        # compliance_requirements → catalog link. Added here (not in the
        # compliance_requirements block above) because the FK REFERENCES
        # jurisdiction_requirements, which is only created at this point.
        # Null for hand-authored rows; the dedup identity for catalog-derived rows.
        await conn.execute("""
            ALTER TABLE compliance_requirements
            ADD COLUMN IF NOT EXISTS jurisdiction_requirement_id UUID
                REFERENCES jurisdiction_requirements(id) ON DELETE SET NULL
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_compliance_requirements_jr_id
            ON compliance_requirements(jurisdiction_requirement_id)
        """)
        await conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_compliance_requirements_loc_jr
            ON compliance_requirements(location_id, jurisdiction_requirement_id)
            WHERE jurisdiction_requirement_id IS NOT NULL
        """)

        # Compliance embeddings — vectorized jurisdiction_requirements for RAG Q&A
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS compliance_embeddings (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                requirement_id UUID NOT NULL REFERENCES jurisdiction_requirements(id) ON DELETE CASCADE,
                jurisdiction_id UUID NOT NULL REFERENCES jurisdictions(id) ON DELETE CASCADE,
                content TEXT NOT NULL,
                embedding vector(768) NOT NULL,
                category VARCHAR(50),
                jurisdiction_level VARCHAR(20),
                jurisdiction_name VARCHAR(100),
                applicable_industries TEXT[],
                metadata JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(requirement_id)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_compliance_embeddings_jurisdiction
            ON compliance_embeddings(jurisdiction_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_compliance_embeddings_category
            ON compliance_embeddings(category)
        """)

        # Policy change log — granular per-field change tracking
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS policy_change_log (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                requirement_id UUID NOT NULL REFERENCES jurisdiction_requirements(id) ON DELETE CASCADE,
                field_changed VARCHAR(100) NOT NULL,
                old_value TEXT,
                new_value TEXT,
                changed_at TIMESTAMP DEFAULT NOW(),
                change_source VARCHAR(50),
                change_reason TEXT
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_policy_change_log_requirement
            ON policy_change_log(requirement_id, changed_at)
        """)

        # Payer medical policies — coverage criteria keyed by (payer, procedure)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS payer_medical_policies (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                payer_name VARCHAR(100) NOT NULL,
                payer_type VARCHAR(50),
                policy_number VARCHAR(100),
                policy_title TEXT,
                procedure_codes TEXT[],
                diagnosis_codes TEXT[],
                procedure_description TEXT,
                coverage_status VARCHAR(30) NOT NULL DEFAULT 'conditional',
                requires_prior_auth BOOLEAN DEFAULT false,
                clinical_criteria TEXT,
                documentation_requirements TEXT,
                medical_necessity_criteria TEXT,
                age_restrictions VARCHAR(100),
                frequency_limits VARCHAR(200),
                place_of_service TEXT[],
                effective_date DATE,
                last_reviewed DATE,
                source_url TEXT,
                source_document TEXT,
                research_source VARCHAR(30) DEFAULT 'gemini',
                cms_document_id INTEGER,
                cms_document_type VARCHAR(10),
                cms_document_version INTEGER,
                metadata JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(payer_name, policy_number)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_payer_policies_payer_name
            ON payer_medical_policies(payer_name)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_payer_policies_procedure_codes
            ON payer_medical_policies USING GIN(procedure_codes)
        """)

        # Payer policy embeddings — vectorized payer policies for RAG search
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS payer_policy_embeddings (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                policy_id UUID NOT NULL REFERENCES payer_medical_policies(id) ON DELETE CASCADE,
                payer_name VARCHAR(100) NOT NULL,
                content TEXT NOT NULL,
                embedding vector(768) NOT NULL,
                metadata JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(policy_id)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_payer_policy_embeddings_payer
            ON payer_policy_embeddings(payer_name)
        """)

        # Jurisdiction legislation — upcoming/pending legislation per jurisdiction
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS jurisdiction_legislation (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                jurisdiction_id UUID NOT NULL REFERENCES jurisdictions(id) ON DELETE CASCADE,
                legislation_key TEXT NOT NULL,
                category VARCHAR(50),
                title VARCHAR(500) NOT NULL,
                description TEXT,
                current_status VARCHAR(30) NOT NULL DEFAULT 'proposed',
                expected_effective_date DATE,
                impact_summary TEXT,
                source_url TEXT,
                source_name VARCHAR(200),
                confidence DECIMAL(3,2),
                last_verified_at TIMESTAMP NOT NULL DEFAULT NOW(),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(jurisdiction_id, legislation_key)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_jurisdiction_legislation_jurisdiction
            ON jurisdiction_legislation(jurisdiction_id)
        """)

        # Jurisdiction sources — learned authoritative sources per jurisdiction
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS jurisdiction_sources (
                id SERIAL PRIMARY KEY,
                jurisdiction_id UUID NOT NULL REFERENCES jurisdictions(id) ON DELETE CASCADE,
                domain TEXT NOT NULL,
                source_name TEXT,
                categories TEXT[],
                success_count INTEGER DEFAULT 1 NOT NULL,
                last_seen_at TIMESTAMP DEFAULT NOW() NOT NULL,
                created_at TIMESTAMP DEFAULT NOW() NOT NULL,
                accurate_count INTEGER DEFAULT 0,
                inaccurate_count INTEGER DEFAULT 0,
                last_accuracy_update TIMESTAMP,
                UNIQUE(jurisdiction_id, domain)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_jurisdiction_sources_jurisdiction_id
            ON jurisdiction_sources(jurisdiction_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_jurisdiction_sources_domain
            ON jurisdiction_sources(domain)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_jurisdiction_sources_accuracy
            ON jurisdiction_sources(jurisdiction_id, accurate_count, inaccurate_count)
        """)

        # Add parent_id self-referencing FK on jurisdictions
        await conn.execute("""
            ALTER TABLE jurisdictions
            ADD COLUMN IF NOT EXISTS parent_id UUID REFERENCES jurisdictions(id) ON DELETE SET NULL
        """)

        # Add jurisdiction_id FK on business_locations
        await conn.execute("""
            ALTER TABLE business_locations
            ADD COLUMN IF NOT EXISTS jurisdiction_id UUID REFERENCES jurisdictions(id)
        """)

        # Backfill: create jurisdictions from existing locations
        await conn.execute("""
            INSERT INTO jurisdictions (city, state, county, display_name, level)
            SELECT DISTINCT LOWER(city), UPPER(state), county,
                   city || ', ' || UPPER(state), 'city'
            FROM business_locations WHERE is_active = true
            ON CONFLICT DO NOTHING
        """)

        # Backfill: link existing locations to jurisdictions
        await conn.execute("""
            UPDATE business_locations bl
            SET jurisdiction_id = j.id
            FROM jurisdictions j
            WHERE LOWER(bl.city) = j.city AND UPPER(bl.state) = j.state
              AND bl.jurisdiction_id IS NULL
        """)

        # Backfill: seed jurisdiction_requirements from existing per-location data
        await conn.execute("""
            INSERT INTO jurisdiction_requirements
                (jurisdiction_id, requirement_key, category, jurisdiction_level, jurisdiction_name,
                 title, description, current_value, numeric_value, source_url, source_name,
                 effective_date, expiration_date, previous_value, last_changed_at, last_verified_at)
            SELECT DISTINCT ON (j.id, cr.requirement_key)
                j.id, cr.requirement_key, cr.category, cr.jurisdiction_level, cr.jurisdiction_name,
                cr.title, cr.description, cr.current_value, cr.numeric_value,
                cr.source_url, cr.source_name, cr.effective_date, cr.expiration_date,
                cr.previous_value, cr.last_changed_at, cr.updated_at
            FROM compliance_requirements cr
            JOIN business_locations bl ON cr.location_id = bl.id
            JOIN jurisdictions j ON LOWER(bl.city) = j.city AND UPPER(bl.state) = j.state
            WHERE cr.requirement_key IS NOT NULL
            ORDER BY j.id, cr.requirement_key, cr.updated_at DESC
            ON CONFLICT (jurisdiction_id, requirement_key) DO NOTHING
        """)

        # Employee hours log (needed by leave eligibility checks)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS employee_hours_log (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
                org_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                period_start DATE NOT NULL,
                period_end DATE NOT NULL,
                hours_worked DECIMAL(8,2) NOT NULL,
                source VARCHAR(30) DEFAULT 'manual',
                created_at TIMESTAMP DEFAULT NOW(),
                CONSTRAINT check_hours_source CHECK (
                    source IN ('manual', 'payroll_import', 'time_clock')
                ),
                CONSTRAINT uq_hours_log_employee_period
                    UNIQUE(employee_id, period_start, period_end)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_employee_hours_log_employee_id
                ON employee_hours_log(employee_id)
        """)

        # Leave backfill from leave_jurisdiction_rules is handled by Alembic migration
        # y7z8a9b0c1d2_backfill_leave_jurisdiction_requirements.py

