"""bootstrap.compliance — compliance tracking tables (verbatim split of app/database.py lines 2750-3147).
"""


async def create_compliance(conn):
        # ===========================================
        # Compliance Tracking Tables
        # ===========================================

        # Business locations table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS business_locations (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                name VARCHAR(255),
                address VARCHAR(500),
                city VARCHAR(100) NOT NULL,
                state VARCHAR(2) NOT NULL,
                county VARCHAR(100),
                zipcode VARCHAR(10) NOT NULL,
                is_active BOOLEAN DEFAULT true,
                last_compliance_check TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_business_locations_company_id ON business_locations(company_id)
        """)

        # Auto-check scheduling columns
        await conn.execute("""
            ALTER TABLE business_locations
            ADD COLUMN IF NOT EXISTS auto_check_enabled BOOLEAN DEFAULT true
        """)
        await conn.execute("""
            ALTER TABLE business_locations
            ADD COLUMN IF NOT EXISTS auto_check_interval_days INTEGER DEFAULT 7
        """)
        await conn.execute("""
            ALTER TABLE business_locations
            ADD COLUMN IF NOT EXISTS next_auto_check TIMESTAMP
        """)

        # Per-location anonymous "magic link" tokens backing the public incident
        # intake form (/intake/{token}). Single-use (used_at set on first submit),
        # one current link per (company_id, location_id) — regenerate rotates the
        # token via UPSERT. Distinct from the company-wide anonymous link held in
        # companies.report_email_token.
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ir_report_links (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                location_id UUID NOT NULL REFERENCES business_locations(id) ON DELETE CASCADE,
                token VARCHAR(32) UNIQUE NOT NULL,
                -- Reusable (not single-use): used_at is the LAST-used timestamp,
                -- never blocks. is_active=false is a soft revoke. use_count drives
                -- the optional max_uses cap. See migration irlink0002.
                used_at TIMESTAMPTZ,
                is_active BOOLEAN NOT NULL DEFAULT true,
                revoked_at TIMESTAMPTZ,
                use_count INT NOT NULL DEFAULT 0,
                max_uses INT,
                expires_at TIMESTAMPTZ,
                created_by UUID,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (company_id, location_id)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ir_report_links_company ON ir_report_links(company_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ir_report_links_token ON ir_report_links(token)
        """)
        # Rotation history: every regenerate/revoke retires the old token here so
        # a compromised token stays correlatable to the reports filed through it.
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ir_report_link_history (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                link_id UUID NOT NULL REFERENCES ir_report_links(id) ON DELETE CASCADE,
                company_id UUID NOT NULL,
                location_id UUID NOT NULL,
                token VARCHAR(32) NOT NULL,
                went_live_at TIMESTAMPTZ,
                retired_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                retired_reason TEXT NOT NULL CHECK (retired_reason IN ('rotated', 'revoked')),
                use_count INT NOT NULL DEFAULT 0,
                created_by UUID,
                retired_by UUID
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ir_report_link_history_link ON ir_report_link_history(link_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ir_report_link_history_company ON ir_report_link_history(company_id)
        """)

        # Backfill legacy IR incidents with missing company_id so tenant-scoped
        # dashboard/list queries remain accurate and isolated.
        await conn.execute("""
            UPDATE ir_incidents i
            SET company_id = bl.company_id
            FROM business_locations bl
            WHERE i.company_id IS NULL
              AND i.location_id = bl.id
        """)
        await conn.execute("""
            UPDATE ir_incidents i
            SET company_id = c.company_id
            FROM clients c
            WHERE i.company_id IS NULL
              AND i.created_by = c.user_id
        """)
        await conn.execute("""
            WITH single_company AS (
                SELECT id
                FROM companies
                ORDER BY created_at
                LIMIT 1
            )
            UPDATE ir_incidents i
            SET company_id = sc.id
            FROM single_company sc
            WHERE i.company_id IS NULL
              AND 1 = (SELECT COUNT(*) FROM companies)
        """)
        remaining_ir_without_company = await conn.fetchval(
            "SELECT COUNT(*) FROM ir_incidents WHERE company_id IS NULL"
        )
        if remaining_ir_without_company:
            print(f"[DB] Warning: {remaining_ir_without_company} IR incident(s) still have NULL company_id")

        # Compliance check log table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS compliance_check_log (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                location_id UUID NOT NULL REFERENCES business_locations(id) ON DELETE CASCADE,
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                check_type VARCHAR(30) NOT NULL DEFAULT 'manual' CHECK (check_type IN ('manual', 'scheduled', 'proactive')),
                status VARCHAR(20) NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed')),
                started_at TIMESTAMP NOT NULL DEFAULT NOW(),
                completed_at TIMESTAMP,
                new_count INTEGER DEFAULT 0,
                updated_count INTEGER DEFAULT 0,
                alert_count INTEGER DEFAULT 0,
                error_message TEXT
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_compliance_check_log_location
            ON compliance_check_log(location_id, started_at DESC)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_compliance_check_log_company
            ON compliance_check_log(company_id, started_at DESC)
        """)

        # Compliance requirements table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS compliance_requirements (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                location_id UUID NOT NULL REFERENCES business_locations(id) ON DELETE CASCADE,
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
                last_changed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_compliance_requirements_location_id ON compliance_requirements(location_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_compliance_requirements_category ON compliance_requirements(category)
        """)
        await conn.execute("""
            ALTER TABLE compliance_requirements
            ADD COLUMN IF NOT EXISTS requirement_key TEXT
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_compliance_requirements_location_key
            ON compliance_requirements(location_id, requirement_key)
        """)
        # Add rate_type column for minimum wage variants
        await conn.execute("""
            ALTER TABLE compliance_requirements
            ADD COLUMN IF NOT EXISTS rate_type VARCHAR(50)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_compliance_requirements_rate_type
            ON compliance_requirements(rate_type)
        """)
        # Add applicable_industries for industry-specific filtering at sync time
        await conn.execute("""
            ALTER TABLE compliance_requirements
            ADD COLUMN IF NOT EXISTS applicable_industries TEXT[]
        """)
        # Add is_pinned for dashboard pinning
        await conn.execute("""
            ALTER TABLE compliance_requirements
            ADD COLUMN IF NOT EXISTS is_pinned BOOLEAN NOT NULL DEFAULT false
        """)
        # Provenance of the row. Known values:
        #   not_evaluated | precedence_rule | default_local | admin_override
        #   | onboarding_wizard | employee_sync
        # (historically only set by migration zp4q5r6s7t8u_05 — mirrored here for fresh DBs)
        await conn.execute("""
            ALTER TABLE compliance_requirements
            ADD COLUMN IF NOT EXISTS governance_source VARCHAR(20) NOT NULL DEFAULT 'not_evaluated'
        """)
        # Match jurisdiction_requirements.current_value (widened to VARCHAR(500)
        # for international reqs). The scan + projector copy jr.current_value into
        # this column, so a narrower type truncate-errors on long values.
        await conn.execute("""
            ALTER TABLE compliance_requirements
            ALTER COLUMN current_value TYPE VARCHAR(500)
        """)
        # NOTE: the jurisdiction_requirement_id FK column (which REFERENCES
        # jurisdiction_requirements) is added further below, AFTER that table is
        # created — see "compliance_requirements → catalog link" block.

        # Compliance alerts table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS compliance_alerts (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                location_id UUID NOT NULL REFERENCES business_locations(id) ON DELETE CASCADE,
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                requirement_id UUID REFERENCES compliance_requirements(id) ON DELETE SET NULL,
                title VARCHAR(500) NOT NULL,
                message TEXT NOT NULL,
                severity VARCHAR(20) NOT NULL DEFAULT 'info' CHECK (severity IN ('info', 'warning', 'critical')),
                status VARCHAR(20) NOT NULL DEFAULT 'unread' CHECK (status IN ('unread', 'read', 'dismissed', 'actioned')),
                category VARCHAR(50),
                action_required TEXT,
                source_url VARCHAR(500),
                source_name VARCHAR(100),
                deadline DATE,
                created_at TIMESTAMP DEFAULT NOW(),
                read_at TIMESTAMP,
                dismissed_at TIMESTAMP
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_compliance_alerts_company_id ON compliance_alerts(company_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_compliance_alerts_location_id ON compliance_alerts(location_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_compliance_alerts_status ON compliance_alerts(status)
        """)
        await conn.execute("""
            ALTER TABLE compliance_alerts
            ADD COLUMN IF NOT EXISTS source_url VARCHAR(500)
        """)
        await conn.execute("""
            ALTER TABLE compliance_alerts
            ADD COLUMN IF NOT EXISTS source_name VARCHAR(100)
        """)

        # Agentic compliance columns on alerts
        await conn.execute("""
            ALTER TABLE compliance_alerts
            ADD COLUMN IF NOT EXISTS confidence_score DECIMAL(3,2)
        """)
        await conn.execute("""
            ALTER TABLE compliance_alerts
            ADD COLUMN IF NOT EXISTS verification_sources JSONB
        """)
        await conn.execute("""
            ALTER TABLE compliance_alerts
            ADD COLUMN IF NOT EXISTS alert_type VARCHAR(30) DEFAULT 'change'
        """)
        await conn.execute("""
            ALTER TABLE compliance_alerts
            ADD COLUMN IF NOT EXISTS effective_date DATE
        """)
        await conn.execute("""
            ALTER TABLE compliance_alerts
            ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'
        """)
        await conn.execute("""
            ALTER TABLE compliance_alerts
            ADD COLUMN IF NOT EXISTS impact_summary TEXT
        """)

        # Compliance requirement history (stateful updates)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS compliance_requirement_history (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                requirement_id UUID NOT NULL REFERENCES compliance_requirements(id) ON DELETE CASCADE,
                location_id UUID NOT NULL REFERENCES business_locations(id) ON DELETE CASCADE,
                category VARCHAR(50),
                jurisdiction_level VARCHAR(20),
                jurisdiction_name VARCHAR(200),
                title VARCHAR(500),
                description TEXT,
                current_value TEXT,
                numeric_value NUMERIC,
                source_url TEXT,
                source_name TEXT,
                effective_date DATE,
                captured_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_compliance_requirement_history_requirement
            ON compliance_requirement_history(requirement_id, captured_at)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_compliance_requirement_history_location
            ON compliance_requirement_history(location_id, captured_at)
        """)
        # Add rate_type column for minimum wage variants history
        await conn.execute("""
            ALTER TABLE compliance_requirement_history
            ADD COLUMN IF NOT EXISTS rate_type VARCHAR(50)
        """)

        # Verification outcomes for confidence calibration (Phase 1.2)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS verification_outcomes (
                id SERIAL PRIMARY KEY,
                jurisdiction_id UUID REFERENCES jurisdictions(id) ON DELETE SET NULL,
                alert_id UUID REFERENCES compliance_alerts(id) ON DELETE SET NULL,
                requirement_key TEXT NOT NULL,
                category VARCHAR(50),
                predicted_confidence DECIMAL(3,2) NOT NULL,
                predicted_is_change BOOLEAN NOT NULL,
                verification_sources JSONB,
                actual_is_change BOOLEAN,
                reviewed_by UUID REFERENCES users(id) ON DELETE SET NULL,
                reviewed_at TIMESTAMP,
                admin_notes TEXT,
                correction_reason VARCHAR(100),
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_verification_outcomes_jurisdiction_id
            ON verification_outcomes(jurisdiction_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_verification_outcomes_category
            ON verification_outcomes(category)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_verification_outcomes_predicted_confidence
            ON verification_outcomes(predicted_confidence)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_verification_outcomes_actual_is_change
            ON verification_outcomes(actual_is_change)
        """)

        # Upcoming legislation tracking table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS upcoming_legislation (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                location_id UUID NOT NULL REFERENCES business_locations(id) ON DELETE CASCADE,
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                category VARCHAR(50),
                title VARCHAR(500) NOT NULL,
                description TEXT,
                current_status VARCHAR(30) NOT NULL DEFAULT 'proposed'
                    CHECK (current_status IN ('proposed', 'passed', 'signed', 'effective_soon', 'effective', 'dismissed')),
                expected_effective_date DATE,
                impact_summary TEXT,
                source_url TEXT,
                source_name VARCHAR(200),
                confidence DECIMAL(3,2),
                legislation_key TEXT,
                alert_id UUID REFERENCES compliance_alerts(id) ON DELETE SET NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_upcoming_legislation_location
            ON upcoming_legislation(location_id, current_status)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_upcoming_legislation_company
            ON upcoming_legislation(company_id, expected_effective_date)
        """)
        await conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_upcoming_legislation_key
            ON upcoming_legislation(location_id, legislation_key)
            WHERE legislation_key IS NOT NULL
        """)

