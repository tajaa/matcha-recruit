"""bootstrap.incidents — IR core/CAPA/OSHA/people + IR<->ER bridge ALTERs (verbatim split of app/database.py lines 2042-2355).
"""


async def create_incidents(conn):
        # ===========================================
        # IR (Incident Report) Tables
        # ===========================================

        # IR Incidents table (main incident records)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ir_incidents (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                incident_number VARCHAR(50) NOT NULL UNIQUE,
                title VARCHAR(255) NOT NULL,
                description TEXT,
                incident_type VARCHAR(50) NOT NULL CHECK (incident_type IN ('safety', 'behavioral', 'property', 'near_miss', 'other')),
                severity VARCHAR(20) DEFAULT 'medium' CHECK (severity IN ('critical', 'high', 'medium', 'low')),
                status VARCHAR(50) DEFAULT 'reported' CHECK (status IN ('reported', 'investigating', 'action_required', 'resolved', 'closed')),
                occurred_at TIMESTAMP NOT NULL,
                location VARCHAR(255),
                reported_by_name VARCHAR(255) NOT NULL,
                reported_by_email VARCHAR(255),
                reported_at TIMESTAMP DEFAULT NOW(),
                assigned_to UUID REFERENCES users(id),
                witnesses JSONB DEFAULT '[]',
                category_data JSONB DEFAULT '{}',
                root_cause TEXT,
                corrective_actions TEXT,
                involved_employee_ids UUID[] DEFAULT '{}',
                company_id UUID REFERENCES companies(id) ON DELETE SET NULL,
                location_id UUID REFERENCES business_locations(id) ON DELETE SET NULL,
                created_by UUID REFERENCES users(id),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                resolved_at TIMESTAMP
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ir_incidents_status ON ir_incidents(status)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ir_incidents_type ON ir_incidents(incident_type)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ir_incidents_severity ON ir_incidents(severity)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ir_incidents_occurred_at ON ir_incidents(occurred_at)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ir_incidents_location ON ir_incidents(location)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ir_incidents_company_id ON ir_incidents(company_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ir_incidents_location_id ON ir_incidents(location_id)
        """)

        # IR Incident Documents table (photos, forms, attachments)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ir_incident_documents (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                incident_id UUID NOT NULL REFERENCES ir_incidents(id) ON DELETE CASCADE,
                document_type VARCHAR(50) NOT NULL CHECK (document_type IN ('photo', 'form', 'statement', 'other', 'disciplinary')),
                filename VARCHAR(255) NOT NULL,
                file_path VARCHAR(500) NOT NULL,
                mime_type VARCHAR(100),
                file_size INTEGER,
                uploaded_by UUID REFERENCES users(id),
                -- 'authed' | 'magic_link' | NULL (legacy). Anonymous magic-link
                -- attachments have no uploaded_by, so this is what tells them
                -- apart from a row whose uploader is simply unknown.
                uploaded_via VARCHAR(30),
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ir_incident_documents_incident_id ON ir_incident_documents(incident_id)
        """)

        # IR Incident Analysis table (cached AI analysis)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ir_incident_analysis (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                incident_id UUID NOT NULL REFERENCES ir_incidents(id) ON DELETE CASCADE,
                analysis_type VARCHAR(50) NOT NULL CHECK (analysis_type IN ('categorization', 'severity', 'root_cause', 'recommendations', 'similar', 'consistency', 'company_consistency', 'policy_mapping', 'training_mapping')),
                analysis_data JSONB NOT NULL,
                generated_by UUID REFERENCES users(id),
                generated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(incident_id, analysis_type)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ir_incident_analysis_incident_id ON ir_incident_analysis(incident_id)
        """)

        # IR Audit Log table (compliance trail)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ir_audit_log (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                incident_id UUID REFERENCES ir_incidents(id) ON DELETE SET NULL,
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
            CREATE INDEX IF NOT EXISTS idx_ir_audit_log_incident_id ON ir_audit_log(incident_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ir_audit_log_user_id ON ir_audit_log(user_id)
        """)

        # ===========================================
        # IR Corrective Actions (CAPA) — structured follow-through
        # ===========================================
        # The accountable layer over the free-text ir_incidents.corrective_actions
        # notes column: one row per corrective/preventive action, each with its
        # own owner, due date, status lifecycle, and effectiveness verification.
        # See alembic migration ircapa01.
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ir_corrective_actions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                incident_id UUID NOT NULL REFERENCES ir_incidents(id) ON DELETE CASCADE,
                company_id UUID NOT NULL,
                description TEXT NOT NULL,
                action_type VARCHAR(20) NOT NULL DEFAULT 'corrective'
                    CHECK (action_type IN ('corrective', 'preventive')),
                priority VARCHAR(20) NOT NULL DEFAULT 'short_term'
                    CHECK (priority IN ('immediate', 'short_term', 'long_term')),
                assigned_to UUID,
                assignee_name TEXT,
                due_date DATE,
                status VARCHAR(20) NOT NULL DEFAULT 'open'
                    CHECK (status IN ('open', 'in_progress', 'completed', 'verified', 'cancelled')),
                completed_at TIMESTAMPTZ,
                verified_by UUID,
                verified_at TIMESTAMPTZ,
                effectiveness VARCHAR(20)
                    CHECK (effectiveness IN ('effective', 'ineffective', 'pending')),
                reminder_sent_at DATE,
                created_by UUID,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ir_corrective_actions_incident
            ON ir_corrective_actions(incident_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ir_corrective_actions_company_status_due
            ON ir_corrective_actions(company_id, status, due_date)
        """)

        # ir_deadline_alert_log — idempotency ledger for the IR deadline worker's
        # incident-scoped sweeps (stale critical, unclassified recordable, OSHA
        # emergency countdown). CAPA nudges dedupe on reminder_sent_at instead.
        # See alembic migration irdl01.
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ir_deadline_alert_log (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                incident_id UUID NOT NULL REFERENCES ir_incidents(id) ON DELETE CASCADE,
                company_id UUID NOT NULL,
                alert_kind VARCHAR(40) NOT NULL,
                sent_on DATE NOT NULL DEFAULT CURRENT_DATE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (incident_id, alert_kind, sent_on)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ir_deadline_alert_log_company
            ON ir_deadline_alert_log(company_id, sent_on)
        """)

        # ===========================================
        # OSHA ITA direct electronic filing
        # ===========================================
        # osha_ita_credentials holds the company's ITA API token (encrypted at
        # rest via app.core.services.secret_crypto); osha_ita_submissions is the
        # auditable filing history. See alembic migration ita01.
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS osha_ita_credentials (
                company_id UUID PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
                api_token TEXT NOT NULL,
                created_by UUID,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS osha_ita_submissions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                location_id UUID,
                year INTEGER NOT NULL,
                status VARCHAR(30) NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'submitted', 'accepted', 'rejected',
                                      'error', 'not_configured')),
                ita_submission_id TEXT,
                establishment_count INTEGER NOT NULL DEFAULT 0,
                response_payload JSONB,
                error_detail TEXT,
                submitted_by UUID,
                submitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_osha_ita_submissions_company_year
            ON osha_ita_submissions(company_id, year DESC)
        """)

        # ===========================================
        # IR People registry (matcha-lite per-person tracking, no roster)
        # ===========================================
        # Lightweight, auto-built identity for people named in incidents.
        # Stable id derived from the typed name (normalized for dedup) so
        # per-person history works on the IR feature alone — distinct from
        # involved_employee_ids, which targets the real `employees` roster.
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ir_people (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                display_name TEXT NOT NULL,
                normalized_name TEXT NOT NULL,
                email TEXT,
                verified BOOLEAN NOT NULL DEFAULT false,
                first_seen TIMESTAMP DEFAULT NOW(),
                last_seen TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_ir_people_company_norm
            ON ir_people (company_id, normalized_name)
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ir_incident_people (
                incident_id UUID NOT NULL REFERENCES ir_incidents(id) ON DELETE CASCADE,
                person_id UUID NOT NULL REFERENCES ir_people(id) ON DELETE CASCADE,
                role TEXT NOT NULL CHECK (role IN ('reporter', 'involved', 'witness', 'interviewee')),
                created_at TIMESTAMP DEFAULT NOW(),
                PRIMARY KEY (incident_id, person_id, role)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ir_incident_people_person
            ON ir_incident_people (person_id)
        """)

        # ===========================================
        # IR Investigation Interviews (bridge IR → ER)
        # ===========================================

        # Add investigation interview columns to interviews table
        # (placed here because FKs reference ir_incidents and er_cases created above)
        await conn.execute("""
            ALTER TABLE interviews ADD COLUMN IF NOT EXISTS incident_id UUID REFERENCES ir_incidents(id) ON DELETE SET NULL
        """)
        await conn.execute("""
            ALTER TABLE interviews ADD COLUMN IF NOT EXISTS er_case_id UUID REFERENCES er_cases(id) ON DELETE SET NULL
        """)
        await conn.execute("""
            ALTER TABLE interviews ADD COLUMN IF NOT EXISTS interviewee_role VARCHAR(50)
        """)
        await conn.execute("""
            ALTER TABLE interviews ADD COLUMN IF NOT EXISTS investigation_analysis JSONB
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_interviews_incident_id ON interviews(incident_id) WHERE incident_id IS NOT NULL
        """)

        # Add er_case_id to ir_incidents for ER linking
        await conn.execute("""
            ALTER TABLE ir_incidents ADD COLUMN IF NOT EXISTS er_case_id UUID REFERENCES er_cases(id) ON DELETE SET NULL
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ir_incidents_er_case_id ON ir_incidents(er_case_id) WHERE er_case_id IS NOT NULL
        """)

        # Junction table for investigation interviews
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ir_investigation_interviews (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                incident_id UUID NOT NULL REFERENCES ir_incidents(id) ON DELETE CASCADE,
                interview_id UUID NOT NULL REFERENCES interviews(id) ON DELETE CASCADE,
                er_case_id UUID REFERENCES er_cases(id) ON DELETE SET NULL,
                interviewee_role VARCHAR(50),
                interviewee_name VARCHAR(255),
                interviewee_email VARCHAR(255),
                questions_generated JSONB,
                status VARCHAR(50) DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT NOW(),
                completed_at TIMESTAMP
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_irii_incident_id ON ir_investigation_interviews(incident_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_irii_interview_id ON ir_investigation_interviews(interview_id)
        """)
        await conn.execute("""
            ALTER TABLE ir_investigation_interviews ADD COLUMN IF NOT EXISTS invite_token VARCHAR(64)
        """)
        await conn.execute("""
            ALTER TABLE ir_investigation_interviews ADD COLUMN IF NOT EXISTS invite_sent_at TIMESTAMP
        """)
        await conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_irii_invite_token
            ON ir_investigation_interviews(invite_token)
            WHERE invite_token IS NOT NULL
        """)

