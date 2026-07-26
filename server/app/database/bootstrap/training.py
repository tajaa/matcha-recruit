"""bootstrap.training — training, i9, cobra, benefits, separation (verbatim split of app/database.py lines 5913-6194).
"""


async def create_training(conn):
        # Training compliance tables
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS training_requirements (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                title VARCHAR(255) NOT NULL,
                description TEXT,
                training_type VARCHAR(50) NOT NULL,
                jurisdiction VARCHAR(50),
                frequency_months INTEGER,
                applies_to VARCHAR(50) DEFAULT 'all',
                is_active BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_training_requirements_company
            ON training_requirements(company_id)
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS training_records (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
                requirement_id UUID REFERENCES training_requirements(id) ON DELETE SET NULL,
                title VARCHAR(255) NOT NULL,
                training_type VARCHAR(50) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'assigned',
                assigned_date DATE NOT NULL DEFAULT CURRENT_DATE,
                due_date DATE,
                completed_date DATE,
                expiration_date DATE,
                provider VARCHAR(255),
                certificate_number VARCHAR(100),
                score DECIMAL(5,2),
                notes TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_training_records_company
            ON training_records(company_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_training_records_employee
            ON training_records(employee_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_training_records_status
            ON training_records(status)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_training_records_due_date
            ON training_records(due_date)
        """)
        await conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_training_records_active_assignment
            ON training_records(employee_id, requirement_id)
            WHERE status IN ('assigned', 'in_progress')
        """)

        # -- I-9 Employment Eligibility Records --
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS i9_records (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
                status VARCHAR(30) NOT NULL DEFAULT 'pending_section1',
                section1_completed_date DATE,
                section2_completed_date DATE,
                section2_completed_by UUID REFERENCES users(id),
                document_title VARCHAR(100),
                list_used VARCHAR(10),
                document_number VARCHAR(100),
                issuing_authority VARCHAR(100),
                expiration_date DATE,
                reverification_date DATE,
                reverification_document VARCHAR(100),
                reverification_expiration DATE,
                reverification_by UUID REFERENCES users(id),
                everify_case_number VARCHAR(50),
                everify_status VARCHAR(30),
                notes TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(employee_id)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_i9_records_company ON i9_records(company_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_i9_records_expiration ON i9_records(expiration_date)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_i9_records_status ON i9_records(status)
        """)

        # COBRA qualifying events
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS cobra_qualifying_events (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
                event_type VARCHAR(50) NOT NULL,
                event_date DATE NOT NULL,
                employer_notice_deadline DATE NOT NULL,
                administrator_notice_deadline DATE NOT NULL,
                election_deadline DATE NOT NULL,
                continuation_months INTEGER NOT NULL DEFAULT 18,
                continuation_end_date DATE NOT NULL,
                employer_notice_sent BOOLEAN DEFAULT false,
                employer_notice_sent_date DATE,
                administrator_notified BOOLEAN DEFAULT false,
                administrator_notified_date DATE,
                election_received BOOLEAN,
                election_received_date DATE,
                status VARCHAR(30) NOT NULL DEFAULT 'pending_notice',
                beneficiary_count INTEGER DEFAULT 1,
                notes TEXT,
                offboarding_case_id UUID,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_cobra_events_company
            ON cobra_qualifying_events(company_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_cobra_events_employee
            ON cobra_qualifying_events(employee_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_cobra_events_deadline
            ON cobra_qualifying_events(employer_notice_deadline)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_cobra_events_status
            ON cobra_qualifying_events(status)
        """)

        # ===========================================
        # Employee-benefits broker feature (Scopes 1 & 2)
        # ===========================================
        # Source-agnostic roster snapshot (Finch sync OR CSV upload feed it).
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS benefit_roster_entries (
                id                              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id                      UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                source                          VARCHAR(20) NOT NULL,
                external_id                     VARCHAR(160) NOT NULL,
                employee_id                     UUID REFERENCES employees(id) ON DELETE SET NULL,
                first_name                      VARCHAR(160),
                last_name                       VARCHAR(160),
                email                           VARCHAR(320),
                department                      VARCHAR(160),
                location                        VARCHAR(160),
                start_date                      DATE,
                termination_date                DATE,
                employment_status               VARCHAR(20) NOT NULL DEFAULT 'active',
                has_benefits_enrollment         BOOLEAN,
                employer_health_premium_monthly NUMERIC(12,2),
                gross_pay_period                NUMERIC(14,2),
                benefit_line_items              JSONB NOT NULL DEFAULT '[]'::jsonb,
                snapshot_date                   DATE NOT NULL DEFAULT CURRENT_DATE,
                created_at                      TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at                      TIMESTAMP NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_benefit_roster_entry UNIQUE (company_id, source, external_id)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_benefit_roster_company
            ON benefit_roster_entries(company_id)
        """)
        # Scope 1 — eligibility exceptions (new-hire gaps + termination leaks).
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS benefit_eligibility_exceptions (
                id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id             UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                dedup_key              VARCHAR(220) NOT NULL,
                roster_entry_id        UUID REFERENCES benefit_roster_entries(id) ON DELETE SET NULL,
                employee_id            UUID REFERENCES employees(id) ON DELETE SET NULL,
                employee_name          VARCHAR(320),
                exception_type         VARCHAR(40) NOT NULL,
                reference_date         DATE NOT NULL,
                days_elapsed           INTEGER,
                days_remaining         INTEGER,
                estimated_monthly_leak NUMERIC(12,2),
                status                 VARCHAR(20) NOT NULL DEFAULT 'open',
                source                 VARCHAR(20),
                detected_at            TIMESTAMP NOT NULL DEFAULT NOW(),
                last_seen_at           TIMESTAMP NOT NULL DEFAULT NOW(),
                resolved_at            TIMESTAMP,
                resolution_note        TEXT,
                last_nudge_sent_at     TIMESTAMP,
                metadata               JSONB NOT NULL DEFAULT '{}'::jsonb,
                CONSTRAINT uq_benefit_exception UNIQUE (company_id, dedup_key)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_benefit_exception_company_status
            ON benefit_eligibility_exceptions(company_id, status)
        """)
        # Scope 2 — renewal-risk rows (company + per-department + per-location).
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS benefit_renewal_risk (
                id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id               UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                dimension_type           VARCHAR(20) NOT NULL DEFAULT 'company',
                dimension_value          VARCHAR(200) NOT NULL DEFAULT '',
                risk_band                VARCHAR(16) NOT NULL DEFAULT 'stable',
                turnover_pct             NUMERIC,
                turnover_baseline_pct    NUMERIC,
                turnover_delta_pct       NUMERIC,
                lost_workdays            INTEGER NOT NULL DEFAULT 0,
                lost_workdays_baseline   NUMERIC,
                lost_workdays_delta_pct  NUMERIC,
                near_misses              INTEGER NOT NULL DEFAULT 0,
                behavioral_incidents     INTEGER NOT NULL DEFAULT 0,
                headcount                INTEGER NOT NULL DEFAULT 0,
                gross_payroll            NUMERIC(16,2),
                policy_month             INTEGER,
                triggers                 JSONB NOT NULL DEFAULT '[]'::jsonb,
                computed_at              TIMESTAMP NOT NULL DEFAULT NOW(),
                created_at               TIMESTAMP NOT NULL DEFAULT NOW(),
                updated_at               TIMESTAMP NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_benefit_renewal_risk UNIQUE (company_id, dimension_type, dimension_value)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_benefit_renewal_risk_company
            ON benefit_renewal_risk(company_id)
        """)

        # Separation agreements (ADEA period tracking)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS separation_agreements (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
                offboarding_case_id UUID,
                pre_term_check_id UUID,
                status VARCHAR(30) NOT NULL DEFAULT 'draft',
                severance_amount DECIMAL(12,2),
                severance_weeks INTEGER,
                severance_description TEXT,
                additional_terms JSONB,
                employee_age_at_separation INTEGER,
                is_adea_applicable BOOLEAN DEFAULT false,
                is_group_layoff BOOLEAN DEFAULT false,
                presented_date DATE,
                consideration_period_days INTEGER,
                consideration_deadline DATE,
                signed_date DATE,
                revocation_period_days INTEGER DEFAULT 7,
                revocation_deadline DATE,
                effective_date DATE,
                revoked_date DATE,
                decisional_unit TEXT,
                group_disclosure JSONB,
                created_by UUID REFERENCES users(id),
                notes TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_separation_agreements_company
            ON separation_agreements(company_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_separation_agreements_employee
            ON separation_agreements(employee_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_separation_agreements_status
            ON separation_agreements(status)
        """)

