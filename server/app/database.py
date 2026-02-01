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

        # Update users role constraint to include creator and agency roles
        await conn.execute("""
            DO $$
            BEGIN
                -- Drop the old constraint if it exists and recreate with new values
                IF EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'users_role_check'
                ) THEN
                    ALTER TABLE users DROP CONSTRAINT users_role_check;
                    ALTER TABLE users ADD CONSTRAINT users_role_check
                        CHECK (role IN ('admin', 'client', 'candidate', 'employee', 'creator', 'agency', 'gumfit_admin'));
                END IF;
            EXCEPTION WHEN undefined_object THEN
                -- Constraint doesn't exist, add it
                ALTER TABLE users ADD CONSTRAINT users_role_check
                    CHECK (role IN ('admin', 'client', 'candidate', 'employee', 'creator', 'agency', 'gumfit_admin'));
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
                owner_id UUID REFERENCES users(id),
                status VARCHAR(20) DEFAULT 'approved',
                approved_at TIMESTAMPTZ,
                approved_by UUID REFERENCES users(id),
                rejection_reason TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Add status columns for existing companies tables (migration)
        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'companies' AND column_name = 'status') THEN
                    ALTER TABLE companies ADD COLUMN status VARCHAR(20) DEFAULT 'approved';
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'companies' AND column_name = 'approved_at') THEN
                    ALTER TABLE companies ADD COLUMN approved_at TIMESTAMPTZ;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'companies' AND column_name = 'approved_by') THEN
                    ALTER TABLE companies ADD COLUMN approved_by UUID REFERENCES users(id);
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'companies' AND column_name = 'rejection_reason') THEN
                    ALTER TABLE companies ADD COLUMN rejection_reason TEXT;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'companies' AND column_name = 'owner_id') THEN
                    ALTER TABLE companies ADD COLUMN owner_id UUID REFERENCES users(id);
                END IF;
            END $$;
        """)

        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_companies_status ON companies(status)
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
                sent_at TIMESTAMP,
                -- Structured benefits
                benefits_medical BOOLEAN DEFAULT false,
                benefits_medical_coverage INTEGER,
                benefits_medical_waiting_days INTEGER DEFAULT 0,
                benefits_dental BOOLEAN DEFAULT false,
                benefits_vision BOOLEAN DEFAULT false,
                benefits_401k BOOLEAN DEFAULT false,
                benefits_401k_match VARCHAR(255),
                benefits_wellness VARCHAR(255),
                benefits_pto_vacation BOOLEAN DEFAULT false,
                benefits_pto_sick BOOLEAN DEFAULT false,
                benefits_holidays BOOLEAN DEFAULT false,
                benefits_other VARCHAR(500),
                -- Contingencies
                contingency_background_check BOOLEAN DEFAULT false,
                contingency_credit_check BOOLEAN DEFAULT false,
                contingency_drug_screening BOOLEAN DEFAULT false,
                -- Company logo
                company_logo_url TEXT
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_offer_letters_status ON offer_letters(status)
        """)

        # Migration: Add new columns to offer_letters if they don't exist
        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'offer_letters' AND column_name = 'benefits_medical') THEN
                    ALTER TABLE offer_letters ADD COLUMN benefits_medical BOOLEAN DEFAULT false;
                    ALTER TABLE offer_letters ADD COLUMN benefits_medical_coverage INTEGER;
                    ALTER TABLE offer_letters ADD COLUMN benefits_medical_waiting_days INTEGER DEFAULT 0;
                    ALTER TABLE offer_letters ADD COLUMN benefits_dental BOOLEAN DEFAULT false;
                    ALTER TABLE offer_letters ADD COLUMN benefits_vision BOOLEAN DEFAULT false;
                    ALTER TABLE offer_letters ADD COLUMN benefits_401k BOOLEAN DEFAULT false;
                    ALTER TABLE offer_letters ADD COLUMN benefits_401k_match VARCHAR(255);
                    ALTER TABLE offer_letters ADD COLUMN benefits_wellness VARCHAR(255);
                    ALTER TABLE offer_letters ADD COLUMN benefits_pto_vacation BOOLEAN DEFAULT false;
                    ALTER TABLE offer_letters ADD COLUMN benefits_pto_sick BOOLEAN DEFAULT false;
                    ALTER TABLE offer_letters ADD COLUMN benefits_holidays BOOLEAN DEFAULT false;
                    ALTER TABLE offer_letters ADD COLUMN benefits_other VARCHAR(500);
                    ALTER TABLE offer_letters ADD COLUMN contingency_background_check BOOLEAN DEFAULT false;
                    ALTER TABLE offer_letters ADD COLUMN contingency_credit_check BOOLEAN DEFAULT false;
                    ALTER TABLE offer_letters ADD COLUMN contingency_drug_screening BOOLEAN DEFAULT false;
                    ALTER TABLE offer_letters ADD COLUMN company_logo_url TEXT;
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
                last_changed_at TIMESTAMP,
                last_verified_at TIMESTAMP NOT NULL DEFAULT NOW(),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(jurisdiction_id, requirement_key)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_jurisdiction_requirements_jurisdiction
            ON jurisdiction_requirements(jurisdiction_id)
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
            INSERT INTO jurisdictions (city, state, county)
            SELECT DISTINCT LOWER(city), UPPER(state), county
            FROM business_locations WHERE is_active = true
            ON CONFLICT (city, state) DO NOTHING
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

        # ===========================================
        # Employee Self-Service Portal Tables
        # ===========================================
        # NOTE: Employee portal tables are now managed via Alembic migrations
        # See: alembic/versions/7c1de748641e_add_employee_portal_tables.py
        # See: alembic/versions/6e4ad940b98b_update_users_role_constraint_for_.py

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

        # ===========================================
        # Chat System Tables (Standalone Community Chat)
        # ===========================================

        # Chat Users table (completely separate from main users)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_users (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                email VARCHAR(255) UNIQUE NOT NULL,
                first_name VARCHAR(100) NOT NULL,
                last_name VARCHAR(100) NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                avatar_url VARCHAR(500),
                bio TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_users_email ON chat_users(email)
        """)

        # Chat Rooms table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_rooms (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name VARCHAR(100) NOT NULL,
                slug VARCHAR(100) UNIQUE NOT NULL,
                description TEXT,
                icon VARCHAR(10),
                is_default BOOLEAN DEFAULT FALSE,
                created_by UUID REFERENCES chat_users(id) ON DELETE SET NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_rooms_slug ON chat_rooms(slug)
        """)

        # Chat Room Memberships
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_room_members (
                room_id UUID REFERENCES chat_rooms(id) ON DELETE CASCADE,
                user_id UUID REFERENCES chat_users(id) ON DELETE CASCADE,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_read_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (room_id, user_id)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_room_members_user ON chat_room_members(user_id)
        """)

        # Chat Messages table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                room_id UUID REFERENCES chat_rooms(id) ON DELETE CASCADE,
                user_id UUID REFERENCES chat_users(id) ON DELETE SET NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                edited_at TIMESTAMP
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_messages_room ON chat_messages(room_id, created_at DESC)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_messages_user ON chat_messages(user_id)
        """)

        # ===========================================
        # Creator Platform Tables
        # ===========================================

        # Creators table (creator profiles linked to users)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS creators (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                user_id UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
                display_name VARCHAR(255) NOT NULL,
                bio TEXT,
                profile_image_url TEXT,
                niches JSONB DEFAULT '[]',
                social_handles JSONB DEFAULT '{}',
                audience_demographics JSONB DEFAULT '{}',
                metrics JSONB DEFAULT '{}',
                is_verified BOOLEAN DEFAULT false,
                is_public BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_creators_user_id ON creators(user_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_creators_is_public ON creators(is_public)
        """)

        # Creator platform connections (OAuth tokens)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS creator_platform_connections (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                creator_id UUID NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
                platform VARCHAR(50) NOT NULL CHECK (platform IN ('youtube', 'patreon', 'tiktok', 'instagram', 'twitch', 'twitter', 'spotify')),
                platform_user_id VARCHAR(255),
                platform_username VARCHAR(255),
                access_token_encrypted TEXT,
                refresh_token_encrypted TEXT,
                token_expires_at TIMESTAMP,
                scopes JSONB DEFAULT '[]',
                last_synced_at TIMESTAMP,
                sync_status VARCHAR(50) DEFAULT 'pending' CHECK (sync_status IN ('pending', 'syncing', 'synced', 'failed')),
                sync_error TEXT,
                platform_data JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(creator_id, platform)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_creator_platform_connections_creator_id ON creator_platform_connections(creator_id)
        """)

        # Revenue streams (categories of income)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS revenue_streams (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                creator_id UUID NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
                name VARCHAR(255) NOT NULL,
                category VARCHAR(100) NOT NULL CHECK (category IN ('adsense', 'sponsorship', 'affiliate', 'merch', 'subscription', 'tips', 'licensing', 'services', 'other')),
                platform VARCHAR(100),
                description TEXT,
                is_active BOOLEAN DEFAULT true,
                tax_category VARCHAR(100),
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_revenue_streams_creator_id ON revenue_streams(creator_id)
        """)

        # Revenue entries (individual transactions)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS revenue_entries (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                creator_id UUID NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
                stream_id UUID REFERENCES revenue_streams(id) ON DELETE SET NULL,
                amount DECIMAL(12, 2) NOT NULL,
                currency VARCHAR(10) DEFAULT 'USD',
                date DATE NOT NULL,
                description TEXT,
                source VARCHAR(255),
                is_recurring BOOLEAN DEFAULT false,
                tax_category VARCHAR(100),
                metadata JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_revenue_entries_creator_id ON revenue_entries(creator_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_revenue_entries_date ON revenue_entries(date)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_revenue_entries_stream_id ON revenue_entries(stream_id)
        """)

        # Creator expenses (for tax tracking)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS creator_expenses (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                creator_id UUID NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
                amount DECIMAL(12, 2) NOT NULL,
                currency VARCHAR(10) DEFAULT 'USD',
                date DATE NOT NULL,
                category VARCHAR(100) NOT NULL CHECK (category IN ('equipment', 'software', 'travel', 'marketing', 'contractors', 'office', 'education', 'legal', 'other')),
                description TEXT NOT NULL,
                vendor VARCHAR(255),
                receipt_url TEXT,
                is_deductible BOOLEAN DEFAULT true,
                tax_category VARCHAR(100),
                metadata JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_creator_expenses_creator_id ON creator_expenses(creator_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_creator_expenses_date ON creator_expenses(date)
        """)

        # ===========================================
        # Agency Tables
        # ===========================================

        # Agencies table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS agencies (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name VARCHAR(255) NOT NULL,
                slug VARCHAR(255) NOT NULL UNIQUE,
                agency_type VARCHAR(50) NOT NULL CHECK (agency_type IN ('talent', 'brand', 'hybrid')),
                description TEXT,
                logo_url TEXT,
                website_url TEXT,
                is_verified BOOLEAN DEFAULT false,
                verification_status VARCHAR(50) DEFAULT 'pending' CHECK (verification_status IN ('pending', 'in_review', 'verified', 'rejected')),
                contact_email VARCHAR(255),
                industries JSONB DEFAULT '[]',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_agencies_slug ON agencies(slug)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_agencies_agency_type ON agencies(agency_type)
        """)

        # Agency members (team members)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS agency_members (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                agency_id UUID NOT NULL REFERENCES agencies(id) ON DELETE CASCADE,
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                role VARCHAR(50) NOT NULL CHECK (role IN ('owner', 'admin', 'member')),
                title VARCHAR(255),
                permissions JSONB DEFAULT '{}',
                invited_at TIMESTAMP DEFAULT NOW(),
                joined_at TIMESTAMP,
                is_active BOOLEAN DEFAULT true,
                UNIQUE(agency_id, user_id)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_agency_members_agency_id ON agency_members(agency_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_agency_members_user_id ON agency_members(user_id)
        """)

        # ===========================================
        # GumFit Admin Tables
        # ===========================================

        # GumFit invites (platform invitations to creators/agencies)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS gumfit_invites (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                email VARCHAR(255) NOT NULL,
                invite_type VARCHAR(20) NOT NULL CHECK (invite_type IN ('creator', 'agency')),
                token VARCHAR(255) NOT NULL UNIQUE,
                message TEXT,
                status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'expired')),
                created_by UUID REFERENCES users(id),
                created_at TIMESTAMP DEFAULT NOW(),
                expires_at TIMESTAMP NOT NULL,
                accepted_at TIMESTAMP,
                accepted_by UUID REFERENCES users(id)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_gumfit_invites_email ON gumfit_invites(email)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_gumfit_invites_token ON gumfit_invites(token)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_gumfit_invites_status ON gumfit_invites(status)
        """)

        # ===========================================
        # Marketplace Tables (Brand Deals)
        # ===========================================

        # Brand deals (opportunities posted by agencies)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS brand_deals (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                agency_id UUID NOT NULL REFERENCES agencies(id) ON DELETE CASCADE,
                title VARCHAR(500) NOT NULL,
                brand_name VARCHAR(255) NOT NULL,
                description TEXT NOT NULL,
                requirements JSONB DEFAULT '{}',
                deliverables JSONB DEFAULT '[]',
                compensation_type VARCHAR(50) NOT NULL CHECK (compensation_type IN ('fixed', 'per_deliverable', 'revenue_share', 'product_only', 'negotiable')),
                compensation_min DECIMAL(12, 2),
                compensation_max DECIMAL(12, 2),
                compensation_currency VARCHAR(10) DEFAULT 'USD',
                compensation_details TEXT,
                niches JSONB DEFAULT '[]',
                min_followers INTEGER,
                max_followers INTEGER,
                preferred_platforms JSONB DEFAULT '[]',
                audience_requirements JSONB DEFAULT '{}',
                timeline_start DATE,
                timeline_end DATE,
                application_deadline DATE,
                status VARCHAR(50) DEFAULT 'draft' CHECK (status IN ('draft', 'open', 'closed', 'filled', 'cancelled')),
                visibility VARCHAR(50) DEFAULT 'public' CHECK (visibility IN ('public', 'invite_only', 'private')),
                applications_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_brand_deals_agency_id ON brand_deals(agency_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_brand_deals_status ON brand_deals(status)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_brand_deals_visibility ON brand_deals(visibility)
        """)

        # Deal applications (creators applying to deals)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS deal_applications (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                deal_id UUID NOT NULL REFERENCES brand_deals(id) ON DELETE CASCADE,
                creator_id UUID NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
                pitch TEXT NOT NULL,
                proposed_rate DECIMAL(12, 2),
                proposed_currency VARCHAR(10) DEFAULT 'USD',
                proposed_deliverables JSONB DEFAULT '[]',
                portfolio_links JSONB DEFAULT '[]',
                availability_notes TEXT,
                status VARCHAR(50) DEFAULT 'pending' CHECK (status IN ('pending', 'under_review', 'shortlisted', 'accepted', 'rejected', 'withdrawn')),
                agency_notes TEXT,
                match_score FLOAT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(deal_id, creator_id)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_deal_applications_deal_id ON deal_applications(deal_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_deal_applications_creator_id ON deal_applications(creator_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_deal_applications_status ON deal_applications(status)
        """)

        # Deal contracts (accepted deals)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS deal_contracts (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                deal_id UUID NOT NULL REFERENCES brand_deals(id) ON DELETE CASCADE,
                application_id UUID NOT NULL REFERENCES deal_applications(id) ON DELETE CASCADE,
                creator_id UUID NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
                agency_id UUID NOT NULL REFERENCES agencies(id) ON DELETE CASCADE,
                agreed_rate DECIMAL(12, 2) NOT NULL,
                agreed_currency VARCHAR(10) DEFAULT 'USD',
                agreed_deliverables JSONB DEFAULT '[]',
                terms TEXT,
                contract_document_url TEXT,
                start_date DATE,
                end_date DATE,
                status VARCHAR(50) DEFAULT 'pending' CHECK (status IN ('pending', 'active', 'completed', 'cancelled', 'disputed')),
                total_paid DECIMAL(12, 2) DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_deal_contracts_deal_id ON deal_contracts(deal_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_deal_contracts_creator_id ON deal_contracts(creator_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_deal_contracts_agency_id ON deal_contracts(agency_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_deal_contracts_status ON deal_contracts(status)
        """)

        # Contract payments (payment milestones)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS contract_payments (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                contract_id UUID NOT NULL REFERENCES deal_contracts(id) ON DELETE CASCADE,
                amount DECIMAL(12, 2) NOT NULL,
                currency VARCHAR(10) DEFAULT 'USD',
                milestone_name VARCHAR(255),
                due_date DATE,
                paid_date DATE,
                status VARCHAR(50) DEFAULT 'pending' CHECK (status IN ('pending', 'invoiced', 'paid', 'overdue', 'cancelled')),
                payment_method VARCHAR(100),
                transaction_reference VARCHAR(255),
                notes TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_contract_payments_contract_id ON contract_payments(contract_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_contract_payments_status ON contract_payments(status)
        """)

        # Creator-Deal matches (AI-generated match scores)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS creator_deal_matches (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                deal_id UUID NOT NULL REFERENCES brand_deals(id) ON DELETE CASCADE,
                creator_id UUID NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
                overall_score FLOAT NOT NULL,
                niche_score FLOAT,
                audience_score FLOAT,
                engagement_score FLOAT,
                budget_fit_score FLOAT,
                match_reasoning TEXT,
                breakdown JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(deal_id, creator_id)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_creator_deal_matches_deal_id ON creator_deal_matches(deal_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_creator_deal_matches_creator_id ON creator_deal_matches(creator_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_creator_deal_matches_overall_score ON creator_deal_matches(overall_score DESC)
        """)

        print("[DB] Creator/Agency tables initialized")

        # ===========================================
        # Campaign Platform Tables (Limit Order System)
        # ===========================================

        # Contract templates (for generating agreements)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS contract_templates (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                agency_id UUID REFERENCES agencies(id) ON DELETE CASCADE,
                name VARCHAR(255) NOT NULL,
                template_type VARCHAR(50) CHECK (template_type IN ('sponsorship', 'affiliate', 'content', 'ambassador', 'custom')),
                content TEXT NOT NULL,
                variables JSONB DEFAULT '[]',
                is_default BOOLEAN DEFAULT false,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_contract_templates_agency_id ON contract_templates(agency_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_contract_templates_type ON contract_templates(template_type)
        """)

        # Campaigns (the "limit order" system)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS campaigns (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                agency_id UUID NOT NULL REFERENCES agencies(id) ON DELETE CASCADE,
                brand_name VARCHAR(255) NOT NULL,
                title VARCHAR(255) NOT NULL,
                description TEXT,
                deliverables JSONB NOT NULL DEFAULT '[]',
                timeline JSONB DEFAULT '{}',
                total_budget DECIMAL(12, 2) NOT NULL,
                upfront_percent INTEGER DEFAULT 30,
                completion_percent INTEGER DEFAULT 70,
                platform_fee_percent DECIMAL(5, 2) DEFAULT 10,
                max_creators INTEGER DEFAULT 1,
                accepted_count INTEGER DEFAULT 0,
                status VARCHAR(20) DEFAULT 'draft' CHECK (status IN ('draft', 'open', 'active', 'completed', 'cancelled')),
                contract_template_id UUID REFERENCES contract_templates(id) ON DELETE SET NULL,
                expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_campaigns_agency_id ON campaigns(agency_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_campaigns_status ON campaigns(status)
        """)

        # Campaign offers to specific creators
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS campaign_offers (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                campaign_id UUID NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
                creator_id UUID NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
                offered_amount DECIMAL(12, 2) NOT NULL,
                custom_message TEXT,
                status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'viewed', 'accepted', 'declined', 'expired', 'taken')),
                creator_counter_amount DECIMAL(12, 2),
                creator_notes TEXT,
                viewed_at TIMESTAMP,
                responded_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(campaign_id, creator_id)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_campaign_offers_campaign_id ON campaign_offers(campaign_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_campaign_offers_creator_id ON campaign_offers(creator_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_campaign_offers_status ON campaign_offers(status)
        """)

        # Campaign payments (escrow tracking)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS campaign_payments (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                campaign_id UUID NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
                creator_id UUID NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
                payment_type VARCHAR(20) CHECK (payment_type IN ('upfront', 'completion', 'milestone', 'affiliate')),
                amount DECIMAL(12, 2) NOT NULL,
                platform_fee DECIMAL(12, 2),
                status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'held', 'released', 'refunded', 'failed')),
                stripe_payment_intent_id VARCHAR(255),
                stripe_transfer_id VARCHAR(255),
                charged_at TIMESTAMP,
                released_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_campaign_payments_campaign_id ON campaign_payments(campaign_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_campaign_payments_creator_id ON campaign_payments(creator_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_campaign_payments_status ON campaign_payments(status)
        """)

        # Affiliate tracking links
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS affiliate_links (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                campaign_id UUID REFERENCES campaigns(id) ON DELETE SET NULL,
                creator_id UUID NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
                agency_id UUID NOT NULL REFERENCES agencies(id) ON DELETE CASCADE,
                short_code VARCHAR(20) UNIQUE NOT NULL,
                destination_url TEXT NOT NULL,
                product_name VARCHAR(255),
                commission_percent DECIMAL(5, 2) DEFAULT 10,
                platform_percent DECIMAL(5, 2) DEFAULT 5,
                click_count INTEGER DEFAULT 0,
                conversion_count INTEGER DEFAULT 0,
                total_sales DECIMAL(12, 2) DEFAULT 0,
                total_commission DECIMAL(12, 2) DEFAULT 0,
                is_active BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_affiliate_links_short_code ON affiliate_links(short_code)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_affiliate_links_creator_id ON affiliate_links(creator_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_affiliate_links_agency_id ON affiliate_links(agency_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_affiliate_links_campaign_id ON affiliate_links(campaign_id)
        """)

        # Affiliate click/conversion events
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS affiliate_events (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                link_id UUID NOT NULL REFERENCES affiliate_links(id) ON DELETE CASCADE,
                event_type VARCHAR(20) CHECK (event_type IN ('click', 'conversion')),
                sale_amount DECIMAL(12, 2),
                commission_amount DECIMAL(12, 2),
                ip_address VARCHAR(45),
                user_agent TEXT,
                referrer TEXT,
                metadata JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_affiliate_events_link_id ON affiliate_events(link_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_affiliate_events_type ON affiliate_events(event_type)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_affiliate_events_created_at ON affiliate_events(created_at)
        """)

        # Creator valuations (cached worth estimates)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS creator_valuations (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                creator_id UUID NOT NULL REFERENCES creators(id) ON DELETE CASCADE,
                estimated_value_min DECIMAL(12, 2),
                estimated_value_max DECIMAL(12, 2),
                factors JSONB DEFAULT '{}',
                data_sources JSONB DEFAULT '[]',
                confidence_score FLOAT,
                calculated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(creator_id)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_creator_valuations_creator_id ON creator_valuations(creator_id)
        """)

        # AI Chat tables
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_conversations (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id),
                user_id UUID NOT NULL REFERENCES users(id),
                title TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ai_conversations_company_user
            ON ai_conversations(company_id, user_id)
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ai_messages (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                conversation_id UUID NOT NULL REFERENCES ai_conversations(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ai_messages_conversation
            ON ai_messages(conversation_id, created_at)
        """)

        # Add attachments column to ai_messages
        await conn.execute("""
            ALTER TABLE ai_messages
            ADD COLUMN IF NOT EXISTS attachments JSONB DEFAULT '[]'
        """)

        # Add Stripe columns to creators table
        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'creators' AND column_name = 'stripe_account_id'
                ) THEN
                    ALTER TABLE creators ADD COLUMN stripe_account_id VARCHAR(255);
                    ALTER TABLE creators ADD COLUMN stripe_onboarding_complete BOOLEAN DEFAULT false;
                    ALTER TABLE creators ADD COLUMN stripe_payouts_enabled BOOLEAN DEFAULT false;
                END IF;
            END $$;
        """)

        # Add Stripe customer column to agencies table
        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'agencies' AND column_name = 'stripe_customer_id'
                ) THEN
                    ALTER TABLE agencies ADD COLUMN stripe_customer_id VARCHAR(255);
                END IF;
            END $$;
        """)

        # Create default contract templates if none exist
        template_exists = await conn.fetchval("SELECT COUNT(*) FROM contract_templates WHERE agency_id IS NULL")
        if template_exists == 0:
            await conn.execute("""
                INSERT INTO contract_templates (agency_id, name, template_type, content, variables, is_default) VALUES
                (NULL, 'Standard Sponsorship Agreement', 'sponsorship',
                 'SPONSORSHIP AGREEMENT

This Sponsorship Agreement ("Agreement") is entered into as of {{effective_date}} by and between:

BRAND: {{brand_name}} ("Brand")
CREATOR: {{creator_name}} ("Creator")

1. CAMPAIGN DETAILS
Campaign Title: {{campaign_title}}
Campaign Description: {{campaign_description}}

2. DELIVERABLES
{{deliverables}}

3. COMPENSATION
Total Compensation: {{total_amount}} {{currency}}
- Upfront Payment ({{upfront_percent}}%): {{upfront_amount}} {{currency}}
- Completion Payment ({{completion_percent}}%): {{completion_amount}} {{currency}}

4. TIMELINE
Start Date: {{start_date}}
End Date: {{end_date}}

5. CONTENT GUIDELINES
- Creator will follow all brand guidelines provided
- All content must be approved before posting
- Creator must disclose sponsored content per FTC guidelines

6. INTELLECTUAL PROPERTY
Brand grants Creator limited license to use brand assets for the campaign.
Creator grants Brand license to repurpose campaign content.

7. TERMINATION
Either party may terminate with 14 days written notice.

Agreed and accepted:

Brand Representative: ___________________ Date: ___________
Creator: ___________________ Date: ___________',
                 '["effective_date", "brand_name", "creator_name", "campaign_title", "campaign_description", "deliverables", "total_amount", "currency", "upfront_percent", "upfront_amount", "completion_percent", "completion_amount", "start_date", "end_date"]',
                 true),
                (NULL, 'Affiliate Partnership Agreement', 'affiliate',
                 'AFFILIATE PARTNERSHIP AGREEMENT

This Affiliate Partnership Agreement ("Agreement") is entered into as of {{effective_date}}.

PARTIES:
Brand/Agency: {{brand_name}}
Affiliate/Creator: {{creator_name}}

1. PROGRAM DETAILS
The Brand appoints Creator as a non-exclusive affiliate to promote:
Product/Service: {{product_name}}

2. COMMISSION STRUCTURE
Commission Rate: {{commission_percent}}%
Payment Terms: Monthly, net 30 days
Minimum Payout: $50

3. AFFILIATE LINKS
Creator will receive unique tracking link(s) for all promotions.
Tracking URL: {{affiliate_url}}

4. CREATOR OBLIGATIONS
- Promote products in good faith
- Disclose affiliate relationship per FTC guidelines
- Not engage in misleading advertising
- Not use paid ads on brand terms without approval

5. TERMINATION
Either party may terminate with 7 days notice.
Pending commissions will be paid within 30 days of termination.

Agreed and accepted:

Brand Representative: ___________________ Date: ___________
Creator: ___________________ Date: ___________',
                 '["effective_date", "brand_name", "creator_name", "product_name", "commission_percent", "affiliate_url"]',
                 true)
            """)
            print("[DB] Created default contract templates")

        print("[DB] Campaign platform tables initialized")

        # ===========================================
        # Scheduler Settings Table
        # ===========================================
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS scheduler_settings (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                task_key VARCHAR(100) UNIQUE NOT NULL,
                display_name VARCHAR(255) NOT NULL,
                description TEXT,
                enabled BOOLEAN DEFAULT true,
                max_per_cycle INTEGER DEFAULT 2,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Seed scheduler settings
        await conn.execute("""
            INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
            VALUES
                ('compliance_checks', 'Compliance Auto-Checks', 'Automated compliance checks for business locations on a recurring schedule.', true, 2),
                ('deadline_escalation', 'Deadline Escalation', 'Re-evaluate deadline severities for upcoming legislation based on proximity to effective dates.', true, 0)
            ON CONFLICT (task_key) DO NOTHING
        """)

        # Create default chat rooms if none exist
        room_exists = await conn.fetchval("SELECT COUNT(*) FROM chat_rooms")
        if room_exists == 0:
            await conn.execute("""
                INSERT INTO chat_rooms (name, slug, description, icon, is_default) VALUES
                    ('General', 'general', 'General discussion and introductions', '💬', TRUE),
                    ('Job Hunting', 'job-hunting', 'Share tips and experiences about the job search', '🔍', TRUE),
                    ('Interview Prep', 'interview-prep', 'Practice and prepare for interviews together', '🎯', TRUE),
                    ('Career Advice', 'career-advice', 'Get and give career guidance', '📈', TRUE),
                    ('Off Topic', 'off-topic', 'Anything goes (within reason)', '🎲', TRUE)
            """)
            print("[DB] Created default chat rooms")

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
