from contextlib import asynccontextmanager
from typing import Optional

import asyncpg

_pool: Optional[asyncpg.Pool] = None


async def init_pool(database_url: str):
    """Initialize the connection pool."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(database_url, min_size=2, max_size=10)
    return _pool


async def get_pool() -> asyncpg.Pool:
    """Get the existing connection pool."""
    global _pool
    if _pool is None:
        raise RuntimeError("Database pool not initialized. Call init_pool first.")
    return _pool


async def close_pool():
    """Close the connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def get_connection():
    """Get a database connection from the pool."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn


async def init_db():
    """Create tables if they don't exist."""
    async with get_connection() as conn:
        # Users table (auth)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                email VARCHAR(255) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL,
                role VARCHAR(20) NOT NULL CHECK (role IN ('admin', 'client', 'candidate')),
                is_active BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                last_login TIMESTAMP
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_role ON users(role)
        """)

        # Admins table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                name VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_admins_user_id ON admins(user_id)
        """)

        # Companies table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS companies (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name VARCHAR(255) NOT NULL,
                industry VARCHAR(100),
                size VARCHAR(50),
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Clients table (linked to companies)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS clients (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                name VARCHAR(255) NOT NULL,
                phone VARCHAR(50),
                job_title VARCHAR(100),
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_clients_user_id ON clients(user_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_clients_company_id ON clients(company_id)
        """)

        # Interviews table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS interviews (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
                interviewer_name VARCHAR(255),
                interviewer_role VARCHAR(255),
                interview_type VARCHAR(50) DEFAULT 'culture',
                transcript TEXT,
                raw_culture_data JSONB,
                status VARCHAR(50) DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT NOW(),
                completed_at TIMESTAMP
            )
        """)

        # Add interview_type column if not exists (migration for existing tables)
        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'interviews' AND column_name = 'interview_type'
                ) THEN
                    ALTER TABLE interviews ADD COLUMN interview_type VARCHAR(50) DEFAULT 'culture';
                END IF;
            END $$;
        """)

        # Add conversation_analysis column if not exists (for interview quality analysis)
        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'interviews' AND column_name = 'conversation_analysis'
                ) THEN
                    ALTER TABLE interviews ADD COLUMN conversation_analysis JSONB;
                END IF;
            END $$;
        """)

        # Add screening_analysis column if not exists (for screening interview analysis)
        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'interviews' AND column_name = 'screening_analysis'
                ) THEN
                    ALTER TABLE interviews ADD COLUMN screening_analysis JSONB;
                END IF;
            END $$;
        """)

        # Add tutor_analysis column if not exists (for tutor session metrics)
        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'interviews' AND column_name = 'tutor_analysis'
                ) THEN
                    ALTER TABLE interviews ADD COLUMN tutor_analysis JSONB;
                END IF;
            END $$;
        """)

        # Tutor vocabulary tracking table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS tutor_vocabulary (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                session_id UUID NOT NULL REFERENCES interviews(id) ON DELETE CASCADE,
                language VARCHAR(10) NOT NULL,
                word VARCHAR(255) NOT NULL,
                usage_context TEXT,
                used_correctly BOOLEAN,
                correction TEXT,
                category VARCHAR(50),
                difficulty VARCHAR(20),
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_tutor_vocabulary_session ON tutor_vocabulary(session_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_tutor_vocabulary_language ON tutor_vocabulary(language)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_tutor_vocabulary_word ON tutor_vocabulary(word)
        """)

        # Culture profiles table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS culture_profiles (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID UNIQUE REFERENCES companies(id) ON DELETE CASCADE,
                profile_data JSONB NOT NULL,
                last_updated TIMESTAMP DEFAULT NOW()
            )
        """)

        # Candidates table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS candidates (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name VARCHAR(255),
                email VARCHAR(255),
                phone VARCHAR(50),
                resume_text TEXT,
                resume_file_path VARCHAR(500),
                skills JSONB,
                experience_years INTEGER,
                education JSONB,
                parsed_data JSONB,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Add user_id to candidates table if not exists
        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'candidates' AND column_name = 'user_id'
                ) THEN
                    ALTER TABLE candidates ADD COLUMN user_id UUID UNIQUE REFERENCES users(id) ON DELETE SET NULL;
                END IF;
            END $$;
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_candidates_user_id ON candidates(user_id)
        """)

        # Add resume_hash column for duplicate detection
        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'candidates' AND column_name = 'resume_hash'
                ) THEN
                    ALTER TABLE candidates ADD COLUMN resume_hash VARCHAR(64) UNIQUE;
                END IF;
            END $$;
        """)

        # Match results table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS match_results (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
                candidate_id UUID REFERENCES candidates(id) ON DELETE CASCADE,
                match_score FLOAT,
                match_reasoning TEXT,
                culture_fit_breakdown JSONB,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(company_id, candidate_id)
            )
        """)

        # Positions table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
                title VARCHAR(255) NOT NULL,
                salary_min INTEGER,
                salary_max INTEGER,
                salary_currency VARCHAR(10) DEFAULT 'USD',
                location VARCHAR(255),
                employment_type VARCHAR(50),
                requirements JSONB,
                responsibilities JSONB,
                required_skills JSONB,
                preferred_skills JSONB,
                experience_level VARCHAR(50),
                benefits JSONB,
                department VARCHAR(100),
                reporting_to VARCHAR(255),
                remote_policy VARCHAR(50),
                visa_sponsorship BOOLEAN DEFAULT false,
                status VARCHAR(50) DEFAULT 'active',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Position match results table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS position_match_results (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                position_id UUID REFERENCES positions(id) ON DELETE CASCADE,
                candidate_id UUID REFERENCES candidates(id) ON DELETE CASCADE,
                overall_score FLOAT,
                skills_match_score FLOAT,
                experience_match_score FLOAT,
                culture_fit_score FLOAT,
                match_reasoning TEXT,
                skills_breakdown JSONB,
                experience_breakdown JSONB,
                culture_fit_breakdown JSONB,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(position_id, candidate_id)
            )
        """)

        # Create indexes for positions
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_positions_company_id ON positions(company_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_positions_status ON positions(status)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_position_match_results_position_id ON position_match_results(position_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_position_match_results_candidate_id ON position_match_results(candidate_id)
        """)

        # Add show_on_job_board column to positions table
        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'positions' AND column_name = 'show_on_job_board'
                ) THEN
                    ALTER TABLE positions ADD COLUMN show_on_job_board BOOLEAN DEFAULT false;
                END IF;
            END $$;
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_positions_show_on_job_board ON positions(show_on_job_board)
        """)

        # Saved jobs table (external jobs from SearchAPI)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS saved_jobs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                job_id VARCHAR(255),
                title VARCHAR(255) NOT NULL,
                company_name VARCHAR(255) NOT NULL,
                location VARCHAR(255),
                description TEXT,
                salary VARCHAR(255),
                schedule_type VARCHAR(100),
                work_from_home BOOLEAN DEFAULT false,
                posted_at VARCHAR(100),
                apply_link TEXT,
                thumbnail TEXT,
                extensions JSONB,
                job_highlights JSONB,
                apply_links JSONB,
                notes TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(job_id)
            )
        """)

        # Migrate existing saved_jobs table if columns are VARCHAR
        await conn.execute("""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'saved_jobs' AND column_name = 'apply_link'
                    AND data_type = 'character varying'
                ) THEN
                    ALTER TABLE saved_jobs ALTER COLUMN apply_link TYPE TEXT;
                    ALTER TABLE saved_jobs ALTER COLUMN thumbnail TYPE TEXT;
                END IF;
            END $$;
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_saved_jobs_company_name ON saved_jobs(company_name)
        """)

        # Saved openings table (scraped from career pages)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS saved_openings (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                title VARCHAR(255) NOT NULL,
                company_name VARCHAR(255) NOT NULL,
                location VARCHAR(255),
                department VARCHAR(255),
                apply_url TEXT NOT NULL,
                source_url TEXT,
                industry VARCHAR(100),
                notes TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(apply_url)
            )
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_saved_openings_company ON saved_openings(company_name)
        """)

        # Add show_on_job_board column to saved_jobs table
        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'saved_jobs' AND column_name = 'show_on_job_board'
                ) THEN
                    ALTER TABLE saved_jobs ADD COLUMN show_on_job_board BOOLEAN DEFAULT false;
                END IF;
            END $$;
        """)

        # Add show_on_job_board column to saved_openings table
        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'saved_openings' AND column_name = 'show_on_job_board'
                ) THEN
                    ALTER TABLE saved_openings ADD COLUMN show_on_job_board BOOLEAN DEFAULT false;
                END IF;
            END $$;
        """)

        # Tracked companies table (company watchlist)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS tracked_companies (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name VARCHAR(255) NOT NULL,
                career_url TEXT NOT NULL UNIQUE,
                logo_url TEXT,
                industry VARCHAR(100),
                last_scraped_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_tracked_companies_name ON tracked_companies(name)
        """)

        # Tracked company jobs table (jobs found from tracked companies)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS tracked_company_jobs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES tracked_companies(id) ON DELETE CASCADE,
                title VARCHAR(255) NOT NULL,
                location VARCHAR(255),
                department VARCHAR(255),
                apply_url TEXT NOT NULL UNIQUE,
                first_seen_at TIMESTAMP DEFAULT NOW(),
                is_new BOOLEAN DEFAULT true
            )
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_tracked_company_jobs_company_id ON tracked_company_jobs(company_id)
        """)

        # Projects table (for recruitment project management)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_name VARCHAR(255) NOT NULL,
                name VARCHAR(255) NOT NULL,
                position_title VARCHAR(255),
                location VARCHAR(255),
                salary_min INTEGER,
                salary_max INTEGER,
                benefits TEXT,
                requirements TEXT,
                status VARCHAR(50) DEFAULT 'draft',
                notes TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status)
        """)

        # Project candidates junction table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS project_candidates (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                candidate_id UUID NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
                stage VARCHAR(50) DEFAULT 'initial',
                notes TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(project_id, candidate_id)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_project_candidates_project_id ON project_candidates(project_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_project_candidates_candidate_id ON project_candidates(candidate_id)
        """)

        # Project outreach table (for sending screening invites to candidates)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS project_outreach (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                candidate_id UUID NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
                token VARCHAR(64) UNIQUE NOT NULL,
                status VARCHAR(50) DEFAULT 'sent',
                email_sent_at TIMESTAMP,
                interest_response_at TIMESTAMP,
                interview_id UUID REFERENCES interviews(id) ON DELETE SET NULL,
                screening_score FLOAT,
                screening_recommendation VARCHAR(50),
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(project_id, candidate_id)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_project_outreach_project_id ON project_outreach(project_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_project_outreach_token ON project_outreach(token)
        """)

        # Job applications table (for public job board applications)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS job_applications (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                position_id UUID NOT NULL REFERENCES positions(id) ON DELETE CASCADE,
                candidate_id UUID NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
                source VARCHAR(100),
                cover_letter TEXT,
                status VARCHAR(50) DEFAULT 'new',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(position_id, candidate_id)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_job_applications_position_id ON job_applications(position_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_job_applications_candidate_id ON job_applications(candidate_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_job_applications_status ON job_applications(status)
        """)

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
                status VARCHAR(50) DEFAULT 'open' CHECK (status IN ('open', 'in_review', 'pending_determination', 'closed')),
                created_by UUID REFERENCES users(id),
                assigned_to UUID REFERENCES users(id),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                closed_at TIMESTAMP
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_er_cases_status ON er_cases(status)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_er_cases_created_by ON er_cases(created_by)
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
                analysis_type VARCHAR(50) NOT NULL CHECK (analysis_type IN ('timeline', 'discrepancies', 'policy_check', 'summary', 'determination')),
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

        # IR Incident Documents table (photos, forms, attachments)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ir_incident_documents (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                incident_id UUID NOT NULL REFERENCES ir_incidents(id) ON DELETE CASCADE,
                document_type VARCHAR(50) NOT NULL CHECK (document_type IN ('photo', 'form', 'statement', 'other')),
                filename VARCHAR(255) NOT NULL,
                file_path VARCHAR(500) NOT NULL,
                mime_type VARCHAR(100),
                file_size INTEGER,
                uploaded_by UUID REFERENCES users(id),
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
                analysis_type VARCHAR(50) NOT NULL CHECK (analysis_type IN ('categorization', 'severity', 'root_cause', 'recommendations', 'similar')),
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

        # Create default admin if no admins exist
        admin_exists = await conn.fetchval("SELECT COUNT(*) FROM users WHERE role = 'admin'")
        if admin_exists == 0:
            import os
            from .services.auth import hash_password
            default_password = os.getenv("DEFAULT_ADMIN_PASSWORD", "changeme123")
            user_row = await conn.fetchrow(
                """
                INSERT INTO users (email, password_hash, role)
                VALUES ('admin@matcha.local', $1, 'admin')
                RETURNING id
                """,
                hash_password(default_password)
            )
            await conn.execute(
                "INSERT INTO admins (user_id, name) VALUES ($1, 'System Admin')",
                user_row["id"]
            )
            print("[DB] Created default admin user (admin@matcha.local)")

        print("[DB] Tables initialized")
