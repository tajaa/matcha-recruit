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

        # Add beta_features column to users table (for beta access control)
        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'users' AND column_name = 'beta_features'
                ) THEN
                    ALTER TABLE users ADD COLUMN beta_features JSONB DEFAULT '{}'::jsonb;
                END IF;
            END $$;
        """)

        # Add interview_prep_tokens column to users table (token system for interview prep)
        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'users' AND column_name = 'interview_prep_tokens'
                ) THEN
                    ALTER TABLE users ADD COLUMN interview_prep_tokens INTEGER DEFAULT 0;
                END IF;
            END $$;
        """)

        # Add allowed_interview_roles column to users table (restrict which roles candidates can practice)
        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'users' AND column_name = 'allowed_interview_roles'
                ) THEN
                    ALTER TABLE users ADD COLUMN allowed_interview_roles JSONB DEFAULT '[]'::jsonb;
                END IF;
            END $$;
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

        # Offer Letters table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS offer_letters (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                candidate_name VARCHAR(255) NOT NULL,
                position_title VARCHAR(255) NOT NULL,
                company_name VARCHAR(255) NOT NULL,
                status VARCHAR(50) DEFAULT 'draft' CHECK (status IN ('draft', 'sent', 'accepted', 'rejected', 'expired')),
                salary VARCHAR(255),
                bonus VARCHAR(255),
                stock_options VARCHAR(255),
                start_date TIMESTAMP,
                employment_type VARCHAR(100),
                location VARCHAR(255),
                benefits TEXT,
                manager_name VARCHAR(255),
                manager_title VARCHAR(255),
                expiration_date TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                sent_at TIMESTAMP
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_offer_letters_status ON offer_letters(status)
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

        # ===========================================
        # Employee Self-Service Portal Tables
        # ===========================================

        # Update users table role constraint to include 'employee'
        await conn.execute("""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'users_role_check'
                ) THEN
                    ALTER TABLE users DROP CONSTRAINT users_role_check;
                    ALTER TABLE users ADD CONSTRAINT users_role_check
                        CHECK (role IN ('admin', 'client', 'candidate', 'employee'));
                END IF;
            END $$;
        """)

        # Employees table (employee profiles linked to auth users)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS employees (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                org_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                user_id UUID UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                email VARCHAR(255) NOT NULL,
                first_name VARCHAR(100) NOT NULL,
                last_name VARCHAR(100) NOT NULL,
                work_state VARCHAR(2),
                employment_type VARCHAR(20) CHECK (employment_type IN ('full_time', 'part_time', 'contractor')),
                start_date DATE,
                termination_date DATE,
                manager_id UUID REFERENCES employees(id) ON DELETE SET NULL,
                phone VARCHAR(50),
                address TEXT,
                emergency_contact JSONB,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_employees_org_id ON employees(org_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_employees_user_id ON employees(user_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_employees_work_state ON employees(work_state)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_employees_manager_id ON employees(manager_id)
        """)

        # PTO Balances table (track PTO accrual per year)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS pto_balances (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
                year INTEGER NOT NULL,
                balance_hours DECIMAL(6,2) DEFAULT 0,
                accrued_hours DECIMAL(6,2) DEFAULT 0,
                used_hours DECIMAL(6,2) DEFAULT 0,
                carryover_hours DECIMAL(6,2) DEFAULT 0,
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(employee_id, year)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_pto_balances_employee_id ON pto_balances(employee_id)
        """)

        # PTO Requests table (track PTO requests and approvals)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS pto_requests (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
                start_date DATE NOT NULL,
                end_date DATE NOT NULL,
                hours DECIMAL(6,2) NOT NULL,
                reason TEXT,
                request_type VARCHAR(20) DEFAULT 'vacation' CHECK (request_type IN ('vacation', 'sick', 'personal', 'other')),
                status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'denied', 'cancelled')),
                approved_by UUID REFERENCES employees(id) ON DELETE SET NULL,
                approved_at TIMESTAMP,
                denial_reason TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_pto_requests_employee_id ON pto_requests(employee_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_pto_requests_status ON pto_requests(status)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_pto_requests_start_date ON pto_requests(start_date)
        """)

        # Employee Documents table (documents assigned to employees)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS employee_documents (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                org_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
                doc_type VARCHAR(50) NOT NULL,
                title VARCHAR(255) NOT NULL,
                description TEXT,
                storage_path VARCHAR(500),
                status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('draft', 'pending_signature', 'signed', 'expired', 'archived')),
                expires_at DATE,
                signed_at TIMESTAMP,
                signature_data TEXT,
                signature_ip VARCHAR(100),
                assigned_by UUID REFERENCES users(id),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_employee_documents_org_id ON employee_documents(org_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_employee_documents_employee_id ON employee_documents(employee_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_employee_documents_status ON employee_documents(status)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_employee_documents_doc_type ON employee_documents(doc_type)
        """)

        # Blog posts table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS blog_posts (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                author_id UUID REFERENCES users(id) ON DELETE SET NULL,
                title VARCHAR(255) NOT NULL,
                slug VARCHAR(255) NOT NULL UNIQUE,
                content TEXT NOT NULL,
                excerpt TEXT,
                cover_image TEXT,
                status VARCHAR(50) DEFAULT 'draft' CHECK (status IN ('draft', 'published', 'archived')),
                tags JSONB DEFAULT '[]',
                meta_title VARCHAR(255),
                meta_description TEXT,
                published_at TIMESTAMP,
                likes_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_blog_posts_slug ON blog_posts(slug)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_blog_posts_status ON blog_posts(status)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_blog_posts_published_at ON blog_posts(published_at)
        """)

        # Add likes_count column if not exists
        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'blog_posts' AND column_name = 'likes_count'
                ) THEN
                    ALTER TABLE blog_posts ADD COLUMN likes_count INTEGER DEFAULT 0;
                END IF;
            END $$;
        """)

        # Blog Likes table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS blog_likes (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                post_id UUID NOT NULL REFERENCES blog_posts(id) ON DELETE CASCADE,
                user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                session_id VARCHAR(255),
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE NULLS NOT DISTINCT (post_id, user_id, session_id)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_blog_likes_post_id ON blog_likes(post_id)
        """)

        # Blog Comments table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS blog_comments (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                post_id UUID NOT NULL REFERENCES blog_posts(id) ON DELETE CASCADE,
                user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                author_name VARCHAR(255),
                content TEXT NOT NULL,
                status VARCHAR(50) DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'spam')),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_blog_comments_post_id ON blog_comments(post_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_blog_comments_status ON blog_comments(status)
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
