"""bootstrap.er_copilot — ER Copilot tables (incl. CREATE EXTENSION vector — also hoisted to the orchestrator) (verbatim split of app/database.py lines 1641-2041).
"""


async def create_er_copilot(conn):
        # ===========================================
        # ER Copilot Tables (Employee Relations Investigation)
        # ===========================================

        # Enable pgvector extension for embeddings
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")

        # ER Cases table (investigation cases)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS er_cases (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                case_number VARCHAR(50) NOT NULL UNIQUE,
                title VARCHAR(255) NOT NULL,
                description TEXT,
                intake_context JSONB,
                status VARCHAR(50) DEFAULT 'open' CHECK (status IN ('open', 'in_review', 'pending_determination', 'closed')),
                created_by UUID REFERENCES users(id),
                assigned_to UUID REFERENCES users(id),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                closed_at TIMESTAMP,
                category VARCHAR(50),
                outcome VARCHAR(50)
            )
        """)
        await conn.execute("""
            ALTER TABLE er_cases
            ADD COLUMN IF NOT EXISTS intake_context JSONB
        """)
        await conn.execute("""
            ALTER TABLE er_cases
            ADD COLUMN IF NOT EXISTS category VARCHAR(50)
        """)
        await conn.execute("""
            ALTER TABLE er_cases
            ADD COLUMN IF NOT EXISTS outcome VARCHAR(50)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_er_cases_status ON er_cases(status)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_er_cases_created_by ON er_cases(created_by)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_er_cases_category ON er_cases(category)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_er_cases_outcome ON er_cases(outcome)
        """)
        await conn.execute("""
            ALTER TABLE er_cases
            ADD COLUMN IF NOT EXISTS involved_employees JSONB DEFAULT '[]'
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_er_cases_involved_employees
            ON er_cases USING GIN (involved_employees jsonb_path_ops)
        """)

        # Pre-Termination Risk Checks table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS pre_termination_checks (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                initiated_by UUID NOT NULL REFERENCES users(id),
                overall_score INT NOT NULL,
                overall_band VARCHAR(20) NOT NULL CHECK (overall_band IN ('low', 'moderate', 'high', 'critical')),
                dimensions JSONB NOT NULL,
                ai_narrative TEXT,
                recommended_actions JSONB,
                requires_acknowledgment BOOLEAN NOT NULL DEFAULT false,
                acknowledged BOOLEAN NOT NULL DEFAULT false,
                acknowledged_by UUID REFERENCES users(id),
                acknowledged_at TIMESTAMPTZ,
                acknowledgment_notes TEXT,
                outcome VARCHAR(30) CHECK (outcome IN ('proceeded', 'modified', 'abandoned', 'pending')),
                offboarding_case_id UUID,
                separation_reason TEXT,
                is_voluntary BOOLEAN NOT NULL DEFAULT false,
                computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_pre_term_checks_employee
            ON pre_termination_checks(employee_id, computed_at DESC)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_pre_term_checks_company
            ON pre_termination_checks(company_id, computed_at DESC)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_pre_term_checks_band
            ON pre_termination_checks(company_id, overall_band)
        """)
        await conn.execute("""
            ALTER TABLE offboarding_cases
            ADD COLUMN IF NOT EXISTS pre_termination_check_id UUID
        """)

        # Discipline letter templates — created before progressive_discipline
        # so that table's template_id FK can reference it directly.
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS company_discipline_templates (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                name VARCHAR(255) NOT NULL,
                infraction_type VARCHAR(64),
                discipline_type VARCHAR(30),
                body TEXT NOT NULL,
                is_default BOOLEAN NOT NULL DEFAULT FALSE,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_by UUID REFERENCES users(id),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_company_discipline_templates_default
            ON company_discipline_templates(company_id) WHERE is_default AND is_active
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_company_discipline_templates_company
            ON company_discipline_templates(company_id) WHERE is_active
        """)

        # Progressive Discipline table
        # NOTE: this CREATE is the fresh-DB source of truth; it must include
        # every column later migrations added, or a bootstrap-only DB breaks
        # on the first discipline read (discipline_engine.RECORD_COLUMNS
        # selects columns this CREATE used to omit: occurrence_dates,
        # compliance_check, advisory_ack_reason, situation_narrative,
        # remedial_requirement_id — backfilled here alongside the
        # incident-triggered-discipline columns from migration discipapp01).
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS progressive_discipline (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                discipline_type VARCHAR(30) NOT NULL CHECK (discipline_type IN ('verbal_warning', 'written_warning', 'pip', 'final_warning', 'suspension')),
                issued_date DATE NOT NULL,
                issued_by UUID NOT NULL REFERENCES users(id),
                description TEXT,
                expected_improvement TEXT,
                review_date DATE,
                status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (status IN ('draft', 'pending_meeting', 'pending_signature', 'active', 'completed', 'expired', 'escalated', 'denied')),
                outcome_notes TEXT,
                documents JSONB DEFAULT '[]',
                infraction_type VARCHAR(64) NOT NULL DEFAULT 'unspecified',
                severity VARCHAR(20) NOT NULL DEFAULT 'moderate' CHECK (severity IN ('minor', 'moderate', 'severe', 'immediate_written')),
                lookback_months INTEGER NOT NULL DEFAULT 6,
                expires_at TIMESTAMPTZ,
                escalated_from_id UUID REFERENCES progressive_discipline(id) ON DELETE SET NULL,
                override_level BOOLEAN NOT NULL DEFAULT FALSE,
                override_reason TEXT,
                signature_status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (signature_status IN ('pending', 'requested', 'signed', 'refused', 'physical_uploaded')),
                signature_requested_at TIMESTAMPTZ,
                signature_completed_at TIMESTAMPTZ,
                signature_envelope_id VARCHAR(255),
                signed_pdf_storage_path VARCHAR(500),
                meeting_held_at TIMESTAMPTZ,
                -- from discipcomp01 (deterministic leave-overlap compliance gate).
                -- occurrence_dates MUST be DATE[] to match discipcomp01 — the engine
                -- writes a list of date objects through a $n::date[] cast, so a JSONB
                -- column here breaks every discipline write on a bootstrap-only DB.
                occurrence_dates DATE[] NOT NULL DEFAULT '{}',
                compliance_check JSONB,
                advisory_ack_reason TEXT,
                situation_narrative TEXT,
                -- from trainint01 (remedial training provenance)
                -- NOTE: no REFERENCES on the training_requirements / ir_incidents columns
                -- below. create_er_copilot is the 3rd bootstrap module; create_incidents
                -- is the 4th and create_training the 14th (see bootstrap/__init__.py —
                -- the call order is load-bearing), so an inline FK to either table fails
                -- a fresh init_db() with UndefinedTableError. The real FKs are installed
                -- by trainint01 / discipapp01 on any migrated database.
                remedial_requirement_id UUID,
                -- from discipapp01 (incident-triggered discipline + HR approval)
                approval_status VARCHAR(20) NOT NULL DEFAULT 'not_required' CHECK (approval_status IN ('not_required', 'pending', 'approved', 'denied')),
                approval_requested_at TIMESTAMPTZ,
                approved_by UUID REFERENCES users(id),
                approval_decided_at TIMESTAMPTZ,
                denial_reason TEXT,
                source_incident_id UUID,
                template_id UUID REFERENCES company_discipline_templates(id) ON DELETE SET NULL,
                pending_remedial_requirement_id UUID,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_progressive_discipline_employee
            ON progressive_discipline(employee_id, issued_date DESC)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_progressive_discipline_company
            ON progressive_discipline(company_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_progressive_discipline_expires_active
            ON progressive_discipline(expires_at) WHERE status = 'active'
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_progressive_discipline_signature_envelope
            ON progressive_discipline(signature_envelope_id)
            WHERE signature_envelope_id IS NOT NULL
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_progressive_discipline_approval
            ON progressive_discipline(company_id, approval_status) WHERE approval_status = 'pending'
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_progressive_discipline_source_incident
            ON progressive_discipline(source_incident_id) WHERE source_incident_id IS NOT NULL
        """)

        # Discipline Policy Mapping (per-company config powering escalation engine)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS discipline_policy_mapping (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                infraction_type VARCHAR(64) NOT NULL,
                label VARCHAR(255) NOT NULL,
                default_severity VARCHAR(20) NOT NULL DEFAULT 'moderate'
                    CHECK (default_severity IN ('minor', 'moderate', 'severe', 'immediate_written')),
                lookback_months_minor INTEGER NOT NULL DEFAULT 6,
                lookback_months_moderate INTEGER NOT NULL DEFAULT 9,
                lookback_months_severe INTEGER NOT NULL DEFAULT 12,
                auto_to_written BOOLEAN NOT NULL DEFAULT FALSE,
                notify_grandparent_manager BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE (company_id, infraction_type)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_discipline_policy_mapping_company
            ON discipline_policy_mapping(company_id)
        """)

        # Discipline Audit Log
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS discipline_audit_log (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                discipline_id UUID NOT NULL REFERENCES progressive_discipline(id) ON DELETE CASCADE,
                actor_user_id UUID REFERENCES users(id),
                action VARCHAR(40) NOT NULL,
                details JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_discipline_audit_log_discipline
            ON discipline_audit_log(discipline_id, created_at DESC)
        """)

        # Discipline policy sweep dedupe ledger (Celery discipline_policy_sweep task).
        # One row per incident, ever — thread_id NULL means "checked, nothing found",
        # which must also be stamped or a clean incident gets re-Gemini'd every cycle.
        # incident_id carries no FK here for the same ordering reason as above:
        # ir_incidents does not exist yet when this module runs. discipapp01 installs it.
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS discipline_policy_sweep_log (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                incident_id UUID NOT NULL UNIQUE,
                thread_id UUID,
                finding_count INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        # Agency Charges table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS agency_charges (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                charge_type VARCHAR(30) NOT NULL CHECK (charge_type IN ('eeoc', 'nlrb', 'osha', 'state_agency', 'other')),
                charge_number VARCHAR(100),
                filing_date DATE NOT NULL,
                agency_name VARCHAR(255),
                status VARCHAR(30) NOT NULL DEFAULT 'filed' CHECK (status IN ('filed', 'investigating', 'mediation', 'resolved', 'dismissed', 'litigated')),
                description TEXT,
                resolution_amount NUMERIC(12, 2),
                resolution_date DATE,
                resolution_notes TEXT,
                documents JSONB DEFAULT '[]',
                created_by UUID NOT NULL REFERENCES users(id),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_agency_charges_employee
            ON agency_charges(employee_id, filing_date DESC)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_agency_charges_company
            ON agency_charges(company_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_agency_charges_status
            ON agency_charges(company_id, status)
        """)

        # Post-Termination Claims table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS post_termination_claims (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                pre_termination_check_id UUID REFERENCES pre_termination_checks(id) ON DELETE SET NULL,
                offboarding_case_id UUID,
                claim_type VARCHAR(50) NOT NULL,
                filed_date DATE NOT NULL,
                status VARCHAR(30) NOT NULL DEFAULT 'filed' CHECK (status IN ('filed', 'investigating', 'mediation', 'settled', 'dismissed', 'litigated', 'judgment')),
                resolution_amount NUMERIC(12, 2),
                resolution_date DATE,
                description TEXT,
                created_by UUID NOT NULL REFERENCES users(id),
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_post_term_claims_employee
            ON post_termination_claims(employee_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_post_term_claims_company
            ON post_termination_claims(company_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_post_term_claims_check
            ON post_termination_claims(pre_termination_check_id)
        """)

        # Add vesting_schedules column to companies
        await conn.execute("""
            ALTER TABLE companies ADD COLUMN IF NOT EXISTS vesting_schedules JSONB DEFAULT '[]'
        """)

        # ER Case Documents table (uploaded evidence files)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS er_case_documents (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                case_id UUID NOT NULL REFERENCES er_cases(id) ON DELETE CASCADE,
                document_type VARCHAR(50) NOT NULL CHECK (document_type IN ('transcript', 'policy', 'email', 'other')),
                filename VARCHAR(255) NOT NULL,
                file_path VARCHAR(500) NOT NULL,
                mime_type VARCHAR(100),
                file_size INTEGER,
                pii_scrubbed BOOLEAN DEFAULT false,
                original_text TEXT,
                scrubbed_text TEXT,
                processing_status VARCHAR(50) DEFAULT 'pending' CHECK (processing_status IN ('pending', 'processing', 'completed', 'failed')),
                processing_error TEXT,
                parsed_at TIMESTAMP,
                uploaded_by UUID REFERENCES users(id),
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_er_case_documents_case_id ON er_case_documents(case_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_er_case_documents_type ON er_case_documents(document_type)
        """)

        # ER Evidence Chunks table (document chunks with vector embeddings)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS er_evidence_chunks (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                document_id UUID NOT NULL REFERENCES er_case_documents(id) ON DELETE CASCADE,
                case_id UUID NOT NULL REFERENCES er_cases(id) ON DELETE CASCADE,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                speaker VARCHAR(255),
                timestamp_mentioned VARCHAR(100),
                page_number INTEGER,
                line_start INTEGER,
                line_end INTEGER,
                embedding vector(768),
                metadata JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_er_evidence_chunks_case_id ON er_evidence_chunks(case_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_er_evidence_chunks_document_id ON er_evidence_chunks(document_id)
        """)

        # ER Case Analysis table (cached AI analysis results)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS er_case_analysis (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                case_id UUID NOT NULL REFERENCES er_cases(id) ON DELETE CASCADE,
                analysis_type VARCHAR(50) NOT NULL CHECK (analysis_type IN ('timeline', 'discrepancies', 'policy_check', 'summary', 'determination', 'similar_cases')),
                analysis_data JSONB NOT NULL,
                source_documents JSONB,
                generated_by UUID REFERENCES users(id),
                generated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(case_id, analysis_type)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_er_case_analysis_case_id ON er_case_analysis(case_id)
        """)

        # ER Audit Log table (immutable compliance trail)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS er_audit_log (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                case_id UUID REFERENCES er_cases(id) ON DELETE SET NULL,
                user_id UUID REFERENCES users(id),
                action VARCHAR(100) NOT NULL,
                entity_type VARCHAR(50),
                entity_id UUID,
                details JSONB,
                ip_address VARCHAR(50),
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_er_audit_log_case_id ON er_audit_log(case_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_er_audit_log_user_id ON er_audit_log(user_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_er_audit_log_action ON er_audit_log(action)
        """)

        # ER Case Notes table (assistant/user notes and guidance timeline)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS er_case_notes (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                case_id UUID NOT NULL REFERENCES er_cases(id) ON DELETE CASCADE,
                note_type VARCHAR(50) NOT NULL DEFAULT 'general'
                    CHECK (note_type IN ('general', 'question', 'answer', 'guidance', 'system')),
                content TEXT NOT NULL,
                metadata JSONB,
                created_by UUID REFERENCES users(id),
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_er_case_notes_case_id ON er_case_notes(case_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_er_case_notes_created_at ON er_case_notes(created_at DESC)
        """)

        # ER Case Export Links
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS er_case_export_links (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                case_id UUID NOT NULL REFERENCES er_cases(id) ON DELETE CASCADE,
                org_id UUID NOT NULL,
                token VARCHAR(64) NOT NULL UNIQUE,
                password_hash VARCHAR(256) NOT NULL,
                storage_path TEXT NOT NULL,
                filename VARCHAR(256) NOT NULL,
                created_by UUID NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                expires_at TIMESTAMPTZ,
                revoked_at TIMESTAMPTZ,
                download_count INT NOT NULL DEFAULT 0,
                last_downloaded_at TIMESTAMPTZ,
                failed_attempts INT NOT NULL DEFAULT 0,
                last_failed_at TIMESTAMPTZ
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_er_export_links_token ON er_case_export_links(token)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_er_export_links_case_id ON er_case_export_links(case_id)
        """)

