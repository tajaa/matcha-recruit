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
                role VARCHAR(20) NOT NULL CHECK (role IN ('admin', 'client', 'candidate', 'broker')),
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

        # Update users role constraint
        await conn.execute("""
            DO $$
            DECLARE
                normalized_count INTEGER := 0;
                downgraded_count INTEGER := 0;
            BEGIN
                -- Normalize known legacy role typos before enforcing the constraint.
                UPDATE users
                SET role = 'gumfit_admin'
                WHERE role IN ('gummfit_admin', 'gumfit-admin', 'gumfit admin');
                GET DIAGNOSTICS normalized_count = ROW_COUNT;

                -- Fail closed: unknown roles are downgraded to least-privileged default.
                UPDATE users
                SET role = 'candidate'
                WHERE role NOT IN ('admin', 'client', 'candidate', 'employee', 'broker', 'creator', 'agency', 'gumfit_admin');
                GET DIAGNOSTICS downgraded_count = ROW_COUNT;

                IF normalized_count > 0 OR downgraded_count > 0 THEN
                    RAISE NOTICE 'users.role normalized: % typo fixes, % downgraded to candidate',
                        normalized_count, downgraded_count;
                END IF;

                IF EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'users_role_check'
                      AND conrelid = 'users'::regclass
                ) THEN
                    ALTER TABLE users DROP CONSTRAINT users_role_check;
                END IF;

                ALTER TABLE users ADD CONSTRAINT users_role_check
                    CHECK (role IN ('admin', 'client', 'candidate', 'employee', 'broker', 'creator', 'agency', 'gumfit_admin'));
            EXCEPTION WHEN duplicate_object THEN
                NULL;
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
                ir_guidance_blurb TEXT,
                logo_url TEXT,
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
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'companies' AND column_name = 'logo_url') THEN
                    ALTER TABLE companies ADD COLUMN logo_url TEXT;
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

        # Add candidate_id FK to interviews now that candidates table exists
        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'interviews' AND column_name = 'candidate_id'
                ) THEN
                    ALTER TABLE interviews ADD COLUMN candidate_id UUID REFERENCES candidates(id) ON DELETE SET NULL;
                END IF;
            END $$;
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_interviews_candidate_id ON interviews(candidate_id)
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

        # Ranked results table (multi-signal scoring)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ranked_results (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
                candidate_id UUID REFERENCES candidates(id) ON DELETE CASCADE,
                overall_rank_score FLOAT,
                screening_score FLOAT,
                conversation_score FLOAT,
                culture_alignment_score FLOAT,
                signal_breakdown JSONB,
                has_interview_data BOOLEAN DEFAULT false,
                interview_ids JSONB,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(company_id, candidate_id)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ranked_results_company_id ON ranked_results(company_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_ranked_results_candidate_id ON ranked_results(candidate_id)
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
                company_id UUID REFERENCES companies(id) ON DELETE SET NULL,
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

        # Add new columns to projects table (idempotent)
        await conn.execute("""
            DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'projects' AND column_name = 'closing_date')
                THEN ALTER TABLE projects ADD COLUMN closing_date TIMESTAMP; END IF;
            END$$;
        """)
        await conn.execute("""
            DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'projects' AND column_name = 'salary_hidden')
                THEN ALTER TABLE projects ADD COLUMN salary_hidden BOOLEAN DEFAULT false; END IF;
            END$$;
        """)
        await conn.execute("""
            DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'projects' AND column_name = 'is_public')
                THEN ALTER TABLE projects ADD COLUMN is_public BOOLEAN DEFAULT false; END IF;
            END$$;
        """)
        await conn.execute("""
            DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'projects' AND column_name = 'description')
                THEN ALTER TABLE projects ADD COLUMN description TEXT; END IF;
            END$$;
        """)
        await conn.execute("""
            DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'projects' AND column_name = 'currency')
                THEN ALTER TABLE projects ADD COLUMN currency VARCHAR(10) DEFAULT 'USD'; END IF;
            END$$;
        """)

        # Project applications table (public applications linked to a project)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS project_applications (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                candidate_id UUID NOT NULL REFERENCES candidates(id) ON DELETE CASCADE,
                status VARCHAR(50) DEFAULT 'new',
                ai_score FLOAT,
                ai_recommendation VARCHAR(50),
                ai_notes TEXT,
                source VARCHAR(100) DEFAULT 'direct',
                cover_letter TEXT,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(project_id, candidate_id)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_project_applications_project_id ON project_applications(project_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_project_applications_status ON project_applications(status)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_project_applications_candidate_id ON project_applications(candidate_id)
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
                intake_context JSONB,
                status VARCHAR(50) DEFAULT 'open' CHECK (status IN ('open', 'in_review', 'pending_determination', 'closed')),
                created_by UUID REFERENCES users(id),
                assigned_to UUID REFERENCES users(id),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                closed_at TIMESTAMP
            )
        """)
        await conn.execute("""
            ALTER TABLE er_cases
            ADD COLUMN IF NOT EXISTS intake_context JSONB
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
        # Handbook Management Tables
        # ===========================================

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS company_handbook_profiles (
                company_id UUID PRIMARY KEY REFERENCES companies(id) ON DELETE CASCADE,
                legal_name VARCHAR(255) NOT NULL,
                dba VARCHAR(255),
                ceo_or_president VARCHAR(255) NOT NULL,
                headcount INTEGER,
                remote_workers BOOLEAN NOT NULL DEFAULT false,
                minors BOOLEAN NOT NULL DEFAULT false,
                tipped_employees BOOLEAN NOT NULL DEFAULT false,
                union_employees BOOLEAN NOT NULL DEFAULT false,
                federal_contracts BOOLEAN NOT NULL DEFAULT false,
                group_health_insurance BOOLEAN NOT NULL DEFAULT false,
                background_checks BOOLEAN NOT NULL DEFAULT false,
                hourly_employees BOOLEAN NOT NULL DEFAULT true,
                salaried_employees BOOLEAN NOT NULL DEFAULT false,
                commissioned_employees BOOLEAN NOT NULL DEFAULT false,
                tip_pooling BOOLEAN NOT NULL DEFAULT false,
                updated_by UUID REFERENCES users(id),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            ALTER TABLE company_handbook_profiles
            ADD COLUMN IF NOT EXISTS legal_name VARCHAR(255)
        """)
        await conn.execute("""
            ALTER TABLE company_handbook_profiles
            ADD COLUMN IF NOT EXISTS dba VARCHAR(255)
        """)
        await conn.execute("""
            ALTER TABLE company_handbook_profiles
            ADD COLUMN IF NOT EXISTS ceo_or_president VARCHAR(255)
        """)
        await conn.execute("""
            ALTER TABLE company_handbook_profiles
            ADD COLUMN IF NOT EXISTS headcount INTEGER
        """)
        await conn.execute("""
            ALTER TABLE company_handbook_profiles
            ADD COLUMN IF NOT EXISTS remote_workers BOOLEAN NOT NULL DEFAULT false
        """)
        await conn.execute("""
            ALTER TABLE company_handbook_profiles
            ADD COLUMN IF NOT EXISTS minors BOOLEAN NOT NULL DEFAULT false
        """)
        await conn.execute("""
            ALTER TABLE company_handbook_profiles
            ADD COLUMN IF NOT EXISTS tipped_employees BOOLEAN NOT NULL DEFAULT false
        """)
        await conn.execute("""
            ALTER TABLE company_handbook_profiles
            ADD COLUMN IF NOT EXISTS union_employees BOOLEAN NOT NULL DEFAULT false
        """)
        await conn.execute("""
            ALTER TABLE company_handbook_profiles
            ADD COLUMN IF NOT EXISTS federal_contracts BOOLEAN NOT NULL DEFAULT false
        """)
        await conn.execute("""
            ALTER TABLE company_handbook_profiles
            ADD COLUMN IF NOT EXISTS group_health_insurance BOOLEAN NOT NULL DEFAULT false
        """)
        await conn.execute("""
            ALTER TABLE company_handbook_profiles
            ADD COLUMN IF NOT EXISTS background_checks BOOLEAN NOT NULL DEFAULT false
        """)
        await conn.execute("""
            ALTER TABLE company_handbook_profiles
            ADD COLUMN IF NOT EXISTS hourly_employees BOOLEAN NOT NULL DEFAULT true
        """)
        await conn.execute("""
            ALTER TABLE company_handbook_profiles
            ADD COLUMN IF NOT EXISTS salaried_employees BOOLEAN NOT NULL DEFAULT false
        """)
        await conn.execute("""
            ALTER TABLE company_handbook_profiles
            ADD COLUMN IF NOT EXISTS commissioned_employees BOOLEAN NOT NULL DEFAULT false
        """)
        await conn.execute("""
            ALTER TABLE company_handbook_profiles
            ADD COLUMN IF NOT EXISTS tip_pooling BOOLEAN NOT NULL DEFAULT false
        """)
        await conn.execute("""
            ALTER TABLE company_handbook_profiles
            ADD COLUMN IF NOT EXISTS updated_by UUID REFERENCES users(id)
        """)
        await conn.execute("""
            ALTER TABLE company_handbook_profiles
            ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW()
        """)
        await conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_company_handbook_profiles_company_id
            ON company_handbook_profiles(company_id)
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS handbooks (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                title VARCHAR(500) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'active', 'archived')),
                mode VARCHAR(20) NOT NULL DEFAULT 'single_state'
                    CHECK (mode IN ('single_state', 'multi_state')),
                source_type VARCHAR(20) NOT NULL DEFAULT 'template'
                    CHECK (source_type IN ('template', 'upload')),
                active_version INTEGER NOT NULL DEFAULT 1,
                file_url VARCHAR(1000),
                file_name VARCHAR(255),
                created_by UUID REFERENCES users(id),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                published_at TIMESTAMP
            )
        """)
        await conn.execute("""
            ALTER TABLE handbooks
            ADD COLUMN IF NOT EXISTS mode VARCHAR(20) NOT NULL DEFAULT 'single_state'
        """)
        await conn.execute("""
            ALTER TABLE handbooks
            ADD COLUMN IF NOT EXISTS source_type VARCHAR(20) NOT NULL DEFAULT 'template'
        """)
        await conn.execute("""
            ALTER TABLE handbooks
            ADD COLUMN IF NOT EXISTS active_version INTEGER NOT NULL DEFAULT 1
        """)
        await conn.execute("""
            ALTER TABLE handbooks
            ADD COLUMN IF NOT EXISTS file_url VARCHAR(1000)
        """)
        await conn.execute("""
            ALTER TABLE handbooks
            ADD COLUMN IF NOT EXISTS file_name VARCHAR(255)
        """)
        await conn.execute("""
            ALTER TABLE handbooks
            ADD COLUMN IF NOT EXISTS created_by UUID REFERENCES users(id)
        """)
        await conn.execute("""
            ALTER TABLE handbooks
            ADD COLUMN IF NOT EXISTS published_at TIMESTAMP
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_handbooks_company_id ON handbooks(company_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_handbooks_status ON handbooks(status)
        """)
        await conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_handbooks_company_active
            ON handbooks(company_id)
            WHERE status = 'active'
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS handbook_versions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                handbook_id UUID NOT NULL REFERENCES handbooks(id) ON DELETE CASCADE,
                version_number INTEGER NOT NULL,
                summary TEXT,
                is_published BOOLEAN NOT NULL DEFAULT false,
                created_by UUID REFERENCES users(id),
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(handbook_id, version_number)
            )
        """)
        await conn.execute("""
            ALTER TABLE handbook_versions
            ADD COLUMN IF NOT EXISTS summary TEXT
        """)
        await conn.execute("""
            ALTER TABLE handbook_versions
            ADD COLUMN IF NOT EXISTS is_published BOOLEAN NOT NULL DEFAULT false
        """)
        await conn.execute("""
            ALTER TABLE handbook_versions
            ADD COLUMN IF NOT EXISTS created_by UUID REFERENCES users(id)
        """)
        await conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_handbook_versions_unique_version
            ON handbook_versions(handbook_id, version_number)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_handbook_versions_handbook_id
            ON handbook_versions(handbook_id)
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS handbook_scopes (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                handbook_id UUID NOT NULL REFERENCES handbooks(id) ON DELETE CASCADE,
                state VARCHAR(2) NOT NULL,
                city VARCHAR(100),
                zipcode VARCHAR(10),
                location_id UUID,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            ALTER TABLE handbook_scopes
            ADD COLUMN IF NOT EXISTS city VARCHAR(100)
        """)
        await conn.execute("""
            ALTER TABLE handbook_scopes
            ADD COLUMN IF NOT EXISTS zipcode VARCHAR(10)
        """)
        await conn.execute("""
            ALTER TABLE handbook_scopes
            ADD COLUMN IF NOT EXISTS location_id UUID
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_handbook_scopes_handbook_id
            ON handbook_scopes(handbook_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_handbook_scopes_state
            ON handbook_scopes(state)
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS handbook_sections (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                handbook_version_id UUID NOT NULL REFERENCES handbook_versions(id) ON DELETE CASCADE,
                section_key VARCHAR(120) NOT NULL,
                title VARCHAR(255) NOT NULL,
                section_order INTEGER NOT NULL DEFAULT 0,
                section_type VARCHAR(20) NOT NULL DEFAULT 'core'
                    CHECK (section_type IN ('core', 'state', 'custom', 'uploaded')),
                jurisdiction_scope JSONB DEFAULT '{}'::jsonb,
                content TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(handbook_version_id, section_key)
            )
        """)
        await conn.execute("""
            ALTER TABLE handbook_sections
            ADD COLUMN IF NOT EXISTS section_order INTEGER NOT NULL DEFAULT 0
        """)
        await conn.execute("""
            ALTER TABLE handbook_sections
            ADD COLUMN IF NOT EXISTS section_type VARCHAR(20) NOT NULL DEFAULT 'core'
        """)
        await conn.execute("""
            ALTER TABLE handbook_sections
            ADD COLUMN IF NOT EXISTS jurisdiction_scope JSONB DEFAULT '{}'::jsonb
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_handbook_sections_version_id
            ON handbook_sections(handbook_version_id)
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS handbook_change_requests (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                handbook_id UUID NOT NULL REFERENCES handbooks(id) ON DELETE CASCADE,
                handbook_version_id UUID NOT NULL REFERENCES handbook_versions(id) ON DELETE CASCADE,
                alert_id UUID,
                section_key VARCHAR(120),
                old_content TEXT,
                proposed_content TEXT NOT NULL,
                rationale TEXT,
                source_url VARCHAR(1000),
                effective_date DATE,
                status VARCHAR(20) NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'accepted', 'rejected')),
                resolved_by UUID REFERENCES users(id),
                resolved_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_handbook_change_requests_handbook_id
            ON handbook_change_requests(handbook_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_handbook_change_requests_status
            ON handbook_change_requests(status)
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS handbook_distribution_runs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                handbook_id UUID NOT NULL REFERENCES handbooks(id) ON DELETE CASCADE,
                handbook_version_id UUID NOT NULL REFERENCES handbook_versions(id) ON DELETE CASCADE,
                distributed_by UUID REFERENCES users(id),
                distributed_at TIMESTAMP DEFAULT NOW(),
                employee_count INTEGER NOT NULL DEFAULT 0
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_handbook_distribution_runs_handbook_id
            ON handbook_distribution_runs(handbook_id)
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
        # Add rate_type column for minimum wage variants
        await conn.execute("""
            ALTER TABLE jurisdiction_requirements
            ADD COLUMN IF NOT EXISTS rate_type VARCHAR(50)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_jurisdiction_requirements_rate_type
            ON jurisdiction_requirements(rate_type)
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

        # (Gummfit creator/agency/deal/campaign tables removed — still in DB, just not bootstrapped here)

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

        # Seed scheduler settings (disabled by default for safety)
        await conn.execute("""
            INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
            VALUES
                ('compliance_checks', 'Compliance Auto-Checks', 'Automated compliance checks for business locations on a recurring schedule.', false, 2),
                ('deadline_escalation', 'Deadline Escalation', 'Re-evaluate deadline severities for upcoming legislation based on proximity to effective dates.', false, 0),
                ('legislation_watch', 'Legislation Watch (RSS)', 'Monitor RSS feeds from state DOL/legislature sites for upcoming legislation.', false, 0),
                ('pattern_recognition', 'Pattern Recognition', 'Detect coordinated legislative changes across jurisdictions.', false, 0)
            ON CONFLICT (task_key) DO NOTHING
        """)

        # ===========================================
        # RSS Feed Sources Table (Phase 4.1)
        # ===========================================
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS rss_feed_sources (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                state VARCHAR(2) NOT NULL,
                feed_url TEXT NOT NULL UNIQUE,
                feed_name VARCHAR(255) NOT NULL,
                feed_type VARCHAR(50) DEFAULT 'dol',
                categories TEXT[],
                is_active BOOLEAN DEFAULT true,
                last_fetched_at TIMESTAMP,
                last_item_hash VARCHAR(64),
                error_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_rss_feed_sources_state ON rss_feed_sources(state)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_rss_feed_sources_active ON rss_feed_sources(is_active)
        """)

        # RSS Feed Items table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS rss_feed_items (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                feed_id UUID NOT NULL REFERENCES rss_feed_sources(id) ON DELETE CASCADE,
                item_hash VARCHAR(64) NOT NULL,
                title TEXT NOT NULL,
                link TEXT,
                pub_date TIMESTAMP,
                description TEXT,
                processed BOOLEAN DEFAULT false,
                gemini_triggered BOOLEAN DEFAULT false,
                relevance_score DECIMAL(3,2),
                detected_category VARCHAR(50),
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(feed_id, item_hash)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_rss_feed_items_feed_id ON rss_feed_items(feed_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_rss_feed_items_processed ON rss_feed_items(processed)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_rss_feed_items_relevance ON rss_feed_items(relevance_score)
        """)

        # Seed initial RSS feeds for major states
        await conn.execute("""
            INSERT INTO rss_feed_sources (state, feed_url, feed_name, feed_type, categories)
            VALUES
                ('CA', 'https://www.dir.ca.gov/rss/news.xml', 'CA DIR News', 'dol', ARRAY['minimum_wage', 'sick_leave', 'overtime', 'meal_breaks']),
                ('NY', 'https://dol.ny.gov/rss.xml', 'NY DOL News', 'dol', ARRAY['minimum_wage', 'sick_leave', 'pay_frequency']),
                ('WA', 'https://lni.wa.gov/news/rss.xml', 'WA L&I News', 'dol', ARRAY['minimum_wage', 'sick_leave', 'overtime'])
            ON CONFLICT (feed_url) DO NOTHING
        """)

        # ===========================================
        # Pattern Recognition Tables (Phase 3.3)
        # ===========================================
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS legislative_patterns (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                pattern_key VARCHAR(100) NOT NULL UNIQUE,
                display_name VARCHAR(255) NOT NULL,
                category VARCHAR(50),
                trigger_month INTEGER,
                trigger_day INTEGER,
                lookback_days INTEGER DEFAULT 30,
                min_jurisdictions INTEGER DEFAULT 3,
                is_active BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Pattern Detections table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS pattern_detections (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                pattern_id UUID REFERENCES legislative_patterns(id) ON DELETE CASCADE,
                detection_year INTEGER NOT NULL,
                jurisdictions_matched JSONB NOT NULL,
                jurisdictions_flagged JSONB,
                detection_date TIMESTAMP DEFAULT NOW(),
                alerts_created INTEGER DEFAULT 0,
                UNIQUE(pattern_id, detection_year)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_pattern_detections_year ON pattern_detections(detection_year)
        """)

        # Seed known legislative patterns
        await conn.execute("""
            INSERT INTO legislative_patterns (pattern_key, display_name, category, trigger_month, trigger_day, lookback_days, min_jurisdictions)
            VALUES
                ('jan_1_wage_update', 'January 1st Minimum Wage Update', 'minimum_wage', 1, 1, 60, 3),
                ('july_1_fiscal_year', 'July 1st Fiscal Year Updates', NULL, 7, 1, 30, 2),
                ('jan_1_sick_leave', 'January 1st Sick Leave Update', 'sick_leave', 1, 1, 45, 2)
            ON CONFLICT (pattern_key) DO NOTHING
        """)

        # ===========================================
        # Tier 1 Structured Data Sources (Phase 4.2)
        # ===========================================

        # Structured data sources registry
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS structured_data_sources (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                source_key VARCHAR(100) NOT NULL UNIQUE,
                source_name VARCHAR(255) NOT NULL,
                source_url VARCHAR(500) NOT NULL,
                source_type VARCHAR(50) NOT NULL,
                domain VARCHAR(100) NOT NULL,
                categories TEXT[] NOT NULL,
                coverage_scope VARCHAR(50) NOT NULL,
                coverage_states TEXT[],
                parser_config JSONB NOT NULL DEFAULT '{}',
                fetch_interval_hours INTEGER DEFAULT 168,
                last_fetched_at TIMESTAMP,
                last_fetch_status VARCHAR(20),
                last_fetch_error TEXT,
                record_count INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_structured_data_sources_active
            ON structured_data_sources(is_active)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_structured_data_sources_domain
            ON structured_data_sources(domain)
        """)

        # Structured data cache - parsed requirement data
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS structured_data_cache (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                source_id UUID NOT NULL REFERENCES structured_data_sources(id) ON DELETE CASCADE,
                jurisdiction_key VARCHAR(100) NOT NULL,
                category VARCHAR(50) NOT NULL,
                rate_type VARCHAR(50),
                jurisdiction_level VARCHAR(20) NOT NULL,
                jurisdiction_name VARCHAR(100) NOT NULL,
                state VARCHAR(2) NOT NULL,
                raw_data JSONB NOT NULL,
                current_value VARCHAR(100),
                numeric_value DECIMAL(10, 4),
                effective_date DATE,
                next_scheduled_date DATE,
                next_scheduled_value VARCHAR(100),
                notes TEXT,
                fetched_at TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE(source_id, jurisdiction_key, category, rate_type)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_structured_data_cache_source
            ON structured_data_cache(source_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_structured_data_cache_jurisdiction
            ON structured_data_cache(jurisdiction_key)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_structured_data_cache_state
            ON structured_data_cache(state)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_structured_data_cache_lookup
            ON structured_data_cache(state, jurisdiction_level, category)
        """)

        # Add source_tier column to jurisdiction_requirements
        await conn.execute("""
            ALTER TABLE jurisdiction_requirements
            ADD COLUMN IF NOT EXISTS source_tier INTEGER DEFAULT 3
        """)
        await conn.execute("""
            ALTER TABLE jurisdiction_requirements
            ADD COLUMN IF NOT EXISTS structured_source_id UUID REFERENCES structured_data_sources(id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_jurisdiction_requirements_source_tier
            ON jurisdiction_requirements(source_tier)
        """)

        # Seed initial structured data sources
        await conn.execute("""
            INSERT INTO structured_data_sources (source_key, source_name, source_url, source_type, domain, categories, coverage_scope, coverage_states, parser_config, fetch_interval_hours)
            VALUES
                (
                    'berkeley_minwage_csv',
                    'UC Berkeley Labor Center',
                    'https://laborcenter.berkeley.edu/wp-content/uploads/2024/01/Local-Minimum-Wage-Ordinances-Inventory-2024.csv',
                    'csv',
                    'laborcenter.berkeley.edu',
                    ARRAY['minimum_wage'],
                    'city_county',
                    NULL,
                    '{"encoding": "utf-8", "skip_rows": 0, "columns": {"jurisdiction": "Jurisdiction", "state": "State", "current_wage": "Current Minimum Wage", "effective_date": "Effective Date", "next_wage": "Scheduled Increase", "next_date": "Next Increase Date", "notes": "Notes"}}'::jsonb,
                    168
                ),
                (
                    'epi_minwage_tracker',
                    'Economic Policy Institute',
                    'https://www.epi.org/minimum-wage-tracker/',
                    'html_table',
                    'epi.org',
                    ARRAY['minimum_wage'],
                    'state',
                    NULL,
                    '{"table_selector": "table.mw-tracker-table", "rate_type": "general", "columns": {"state": 0, "current_wage": 1, "effective_date": 2, "next_wage": 3, "next_date": 4}}'::jsonb,
                    168
                ),
                (
                    'dol_whd_tipped',
                    'US DOL Wage and Hour Division - Tipped',
                    'https://www.dol.gov/agencies/whd/state/minimum-wage/tipped',
                    'html_table',
                    'dol.gov',
                    ARRAY['minimum_wage'],
                    'state',
                    NULL,
                    '{"table_selector": "table", "rate_type": "tipped", "columns": {"state": 0, "cash_wage": 1, "tip_credit": 2, "total": 3}}'::jsonb,
                    168
                ),
                (
                    'ncsl_minwage_chart',
                    'NCSL State Minimum Wage Chart',
                    'https://www.ncsl.org/labor-and-employment/state-minimum-wages',
                    'html_table',
                    'ncsl.org',
                    ARRAY['minimum_wage'],
                    'state',
                    NULL,
                    '{"table_selector": "table.state-table", "rate_type": "general", "columns": {"state": 0, "current_wage": 1, "future_changes": 2}}'::jsonb,
                    168
                )
            ON CONFLICT (source_key) DO UPDATE SET
                source_url = EXCLUDED.source_url,
                parser_config = EXCLUDED.parser_config
        """)

        # Add scheduler setting for structured data fetch
        await conn.execute("""
            INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
            VALUES
                ('structured_data_fetch', 'Structured Data Fetch', 'Fetch Tier 1 structured data from authoritative sources (Berkeley, DOL, EPI, NCSL).', false, 0)
            ON CONFLICT (task_key) DO NOTHING
        """)

        # Add scheduler setting for project deadline checks
        await conn.execute("""
            INSERT INTO scheduler_settings (task_key, display_name, description, enabled, max_per_cycle)
            VALUES
                ('project_deadline_checks', 'Project Deadline Checks', 'Auto-close recruiting projects that have passed their closing date, run ranking, and notify top candidates.', false, 0)
            ON CONFLICT (task_key) DO NOTHING
        """)

        # ===========================================
        # Compliance Poster Tables
        # ===========================================

        # Poster templates — one per jurisdiction, auto-generated PDF
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS poster_templates (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                jurisdiction_id UUID NOT NULL REFERENCES jurisdictions(id) ON DELETE CASCADE UNIQUE,
                title VARCHAR(500) NOT NULL,
                description TEXT,
                version INTEGER NOT NULL DEFAULT 1,
                pdf_url TEXT,
                pdf_generated_at TIMESTAMP,
                categories_included TEXT[],
                requirement_count INTEGER DEFAULT 0,
                status VARCHAR(20) NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'generated', 'failed')),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Poster orders — company requests for printed posters
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS poster_orders (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                location_id UUID NOT NULL REFERENCES business_locations(id) ON DELETE CASCADE,
                status VARCHAR(20) NOT NULL DEFAULT 'requested'
                    CHECK (status IN ('requested', 'quoted', 'processing', 'shipped', 'delivered', 'cancelled')),
                requested_by UUID REFERENCES users(id) ON DELETE SET NULL,
                admin_notes TEXT,
                quote_amount NUMERIC(10, 2),
                shipping_address TEXT,
                tracking_number VARCHAR(100),
                shipped_at TIMESTAMP,
                delivered_at TIMESTAMP,
                metadata JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_poster_orders_company_id ON poster_orders(company_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_poster_orders_status ON poster_orders(status)
        """)

        # Poster order items — links orders to templates
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS poster_order_items (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                order_id UUID NOT NULL REFERENCES poster_orders(id) ON DELETE CASCADE,
                template_id UUID NOT NULL REFERENCES poster_templates(id) ON DELETE CASCADE,
                quantity INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_poster_order_items_order_id ON poster_order_items(order_id)
        """)

        # ===========================================
        # API Rate Limits Table (for Gemini rate limiting)
        # ===========================================
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS api_rate_limits (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                service_name VARCHAR(50) NOT NULL,
                endpoint VARCHAR(100),
                called_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_rate_limits_called_at ON api_rate_limits(called_at)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_rate_limits_service ON api_rate_limits(service_name)
        """)

        # Business invitations (admin-generated invite links for auto-approved registration)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS business_invitations (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                token VARCHAR(64) NOT NULL UNIQUE,
                created_by UUID NOT NULL REFERENCES users(id),
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                used_by_company_id UUID REFERENCES companies(id),
                expires_at TIMESTAMP NOT NULL,
                used_at TIMESTAMP,
                note TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_business_invitations_token ON business_invitations(token)
        """)

        # ===========================================
        # Broker Channel Tables
        # ===========================================
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS brokers (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name VARCHAR(255) NOT NULL,
                slug VARCHAR(120) NOT NULL UNIQUE,
                status VARCHAR(20) NOT NULL DEFAULT 'active'
                    CHECK (status IN ('pending', 'active', 'suspended', 'terminated')),
                support_routing VARCHAR(20) NOT NULL DEFAULT 'shared'
                    CHECK (support_routing IN ('broker_first', 'matcha_first', 'shared')),
                billing_mode VARCHAR(20) NOT NULL DEFAULT 'direct'
                    CHECK (billing_mode IN ('direct', 'reseller', 'hybrid')),
                invoice_owner VARCHAR(20) NOT NULL DEFAULT 'matcha'
                    CHECK (invoice_owner IN ('matcha', 'broker')),
                terms_required_version VARCHAR(50) NOT NULL DEFAULT 'v1',
                created_by UUID REFERENCES users(id),
                terminated_at TIMESTAMPTZ,
                grace_until TIMESTAMPTZ,
                post_termination_mode VARCHAR(30)
                    CHECK (post_termination_mode IN ('convert_to_direct', 'transfer_to_broker', 'sunset', 'matcha_managed')),
                metadata JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_brokers_status ON brokers(status)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_brokers_created_at ON brokers(created_at DESC)
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS broker_members (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                broker_id UUID NOT NULL REFERENCES brokers(id) ON DELETE CASCADE,
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                role VARCHAR(20) NOT NULL DEFAULT 'member'
                    CHECK (role IN ('owner', 'admin', 'member')),
                permissions JSONB DEFAULT '{}'::jsonb,
                is_active BOOLEAN NOT NULL DEFAULT true,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE (broker_id, user_id)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_broker_members_user_id ON broker_members(user_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_broker_members_broker_id ON broker_members(broker_id)
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS broker_company_links (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                broker_id UUID NOT NULL REFERENCES brokers(id) ON DELETE CASCADE,
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                status VARCHAR(20) NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'active', 'suspending', 'grace', 'terminated', 'transferred')),
                permissions JSONB DEFAULT '{}'::jsonb,
                linked_at TIMESTAMPTZ DEFAULT NOW(),
                activated_at TIMESTAMPTZ,
                terminated_at TIMESTAMPTZ,
                grace_until TIMESTAMPTZ,
                post_termination_mode VARCHAR(30)
                    CHECK (post_termination_mode IN ('convert_to_direct', 'transfer_to_broker', 'sunset', 'matcha_managed')),
                transition_state VARCHAR(20) DEFAULT 'none'
                    CHECK (transition_state IN ('none', 'planned', 'in_progress', 'matcha_managed', 'completed')),
                transition_updated_at TIMESTAMPTZ,
                data_handoff_status VARCHAR(20) DEFAULT 'not_required'
                    CHECK (data_handoff_status IN ('not_required', 'pending', 'in_progress', 'completed')),
                data_handoff_notes TEXT,
                current_transition_id UUID,
                created_by UUID REFERENCES users(id),
                metadata JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE (broker_id, company_id)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_broker_company_links_company_id ON broker_company_links(company_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_broker_company_links_status ON broker_company_links(status)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_broker_company_links_broker_status ON broker_company_links(broker_id, status)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_broker_company_links_transition_state ON broker_company_links(transition_state)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_broker_company_links_current_transition ON broker_company_links(current_transition_id)
        """)

        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'broker_company_links' AND column_name = 'transition_state'
                ) THEN
                    ALTER TABLE broker_company_links ADD COLUMN transition_state VARCHAR(20) DEFAULT 'none';
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'broker_company_links' AND column_name = 'transition_updated_at'
                ) THEN
                    ALTER TABLE broker_company_links ADD COLUMN transition_updated_at TIMESTAMPTZ;
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'broker_company_links' AND column_name = 'data_handoff_status'
                ) THEN
                    ALTER TABLE broker_company_links ADD COLUMN data_handoff_status VARCHAR(20) DEFAULT 'not_required';
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'broker_company_links' AND column_name = 'data_handoff_notes'
                ) THEN
                    ALTER TABLE broker_company_links ADD COLUMN data_handoff_notes TEXT;
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'broker_company_links' AND column_name = 'current_transition_id'
                ) THEN
                    ALTER TABLE broker_company_links ADD COLUMN current_transition_id UUID;
                END IF;
            END $$;
        """)

        await conn.execute("""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'broker_company_links_transition_state_check') THEN
                    ALTER TABLE broker_company_links DROP CONSTRAINT broker_company_links_transition_state_check;
                END IF;
                ALTER TABLE broker_company_links
                    ADD CONSTRAINT broker_company_links_transition_state_check
                    CHECK (transition_state IN ('none', 'planned', 'in_progress', 'matcha_managed', 'completed'));

                IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'broker_company_links_data_handoff_status_check') THEN
                    ALTER TABLE broker_company_links DROP CONSTRAINT broker_company_links_data_handoff_status_check;
                END IF;
                ALTER TABLE broker_company_links
                    ADD CONSTRAINT broker_company_links_data_handoff_status_check
                    CHECK (data_handoff_status IN ('not_required', 'pending', 'in_progress', 'completed'));
            EXCEPTION WHEN undefined_column THEN
                NULL;
            END $$;
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS broker_contracts (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                broker_id UUID NOT NULL REFERENCES brokers(id) ON DELETE CASCADE,
                status VARCHAR(20) NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'active', 'suspended', 'terminated')),
                billing_mode VARCHAR(20) NOT NULL
                    CHECK (billing_mode IN ('direct', 'reseller', 'hybrid')),
                invoice_owner VARCHAR(20) NOT NULL
                    CHECK (invoice_owner IN ('matcha', 'broker')),
                currency VARCHAR(3) NOT NULL DEFAULT 'USD',
                base_platform_fee NUMERIC(12, 2) NOT NULL DEFAULT 0,
                pepm_rate NUMERIC(12, 2) NOT NULL DEFAULT 0,
                minimum_monthly_commit NUMERIC(12, 2) NOT NULL DEFAULT 0,
                pricing_rules JSONB DEFAULT '{}'::jsonb,
                effective_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                expires_at TIMESTAMPTZ,
                created_by UUID REFERENCES users(id),
                metadata JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_broker_contracts_broker_id ON broker_contracts(broker_id)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_broker_contracts_status ON broker_contracts(status)
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS broker_terms_acceptances (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                broker_id UUID NOT NULL REFERENCES brokers(id) ON DELETE CASCADE,
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                terms_version VARCHAR(50) NOT NULL,
                accepted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                ip_address VARCHAR(64),
                user_agent TEXT,
                UNIQUE (broker_id, user_id, terms_version)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_broker_terms_acceptances_lookup
            ON broker_terms_acceptances(broker_id, user_id, terms_version)
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS broker_branding_configs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                broker_id UUID NOT NULL UNIQUE REFERENCES brokers(id) ON DELETE CASCADE,
                branding_mode VARCHAR(20) NOT NULL DEFAULT 'direct'
                    CHECK (branding_mode IN ('direct', 'co_branded', 'white_label')),
                brand_display_name VARCHAR(255),
                brand_legal_name VARCHAR(255),
                logo_url TEXT,
                favicon_url TEXT,
                primary_color VARCHAR(20),
                secondary_color VARCHAR(20),
                login_subdomain VARCHAR(120) UNIQUE,
                custom_login_url TEXT,
                support_email VARCHAR(320),
                support_phone VARCHAR(50),
                support_url TEXT,
                email_from_name VARCHAR(255),
                email_from_address VARCHAR(320),
                powered_by_badge BOOLEAN NOT NULL DEFAULT true,
                hide_matcha_identity BOOLEAN NOT NULL DEFAULT false,
                mobile_branding_enabled BOOLEAN NOT NULL DEFAULT false,
                theme JSONB DEFAULT '{}'::jsonb,
                metadata JSONB DEFAULT '{}'::jsonb,
                created_by UUID REFERENCES users(id),
                updated_by UUID REFERENCES users(id),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_broker_branding_mode ON broker_branding_configs(branding_mode)
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS broker_company_transitions (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                broker_id UUID NOT NULL REFERENCES brokers(id) ON DELETE CASCADE,
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                source_link_id UUID REFERENCES broker_company_links(id) ON DELETE SET NULL,
                mode VARCHAR(30) NOT NULL
                    CHECK (mode IN ('convert_to_direct', 'transfer_to_broker', 'sunset', 'matcha_managed')),
                status VARCHAR(20) NOT NULL DEFAULT 'planned'
                    CHECK (status IN ('planned', 'in_progress', 'completed', 'cancelled')),
                transfer_target_broker_id UUID REFERENCES brokers(id),
                grace_until TIMESTAMPTZ,
                matcha_managed_until TIMESTAMPTZ,
                data_handoff_status VARCHAR(20) NOT NULL DEFAULT 'not_required'
                    CHECK (data_handoff_status IN ('not_required', 'pending', 'in_progress', 'completed')),
                data_handoff_notes TEXT,
                started_at TIMESTAMPTZ,
                completed_at TIMESTAMPTZ,
                metadata JSONB DEFAULT '{}'::jsonb,
                created_by UUID REFERENCES users(id),
                updated_by UUID REFERENCES users(id),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_broker_company_transitions_broker_company
            ON broker_company_transitions(broker_id, company_id, status)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_broker_company_transitions_transfer_target
            ON broker_company_transitions(transfer_target_broker_id)
        """)
        await conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_broker_company_transitions_active_single
            ON broker_company_transitions(broker_id, company_id)
            WHERE status IN ('planned', 'in_progress')
        """)

        await conn.execute("""
            DO $$
            DECLARE existing_constraint TEXT;
            BEGIN
                SELECT c.conname INTO existing_constraint
                FROM pg_constraint c
                WHERE c.conrelid = 'brokers'::regclass
                  AND c.contype = 'c'
                  AND pg_get_constraintdef(c.oid) ILIKE '%post_termination_mode%';
                IF existing_constraint IS NOT NULL THEN
                    EXECUTE format('ALTER TABLE brokers DROP CONSTRAINT %I', existing_constraint);
                END IF;
                ALTER TABLE brokers
                    ADD CONSTRAINT brokers_post_termination_mode_check
                    CHECK (post_termination_mode IS NULL OR post_termination_mode IN ('convert_to_direct', 'transfer_to_broker', 'sunset', 'matcha_managed'));
            EXCEPTION WHEN undefined_table THEN
                NULL;
            END $$;
        """)

        await conn.execute("""
            DO $$
            DECLARE existing_constraint TEXT;
            BEGIN
                SELECT c.conname INTO existing_constraint
                FROM pg_constraint c
                WHERE c.conrelid = 'broker_company_links'::regclass
                  AND c.contype = 'c'
                  AND pg_get_constraintdef(c.oid) ILIKE '%post_termination_mode%';
                IF existing_constraint IS NOT NULL THEN
                    EXECUTE format('ALTER TABLE broker_company_links DROP CONSTRAINT %I', existing_constraint);
                END IF;
                ALTER TABLE broker_company_links
                    ADD CONSTRAINT broker_company_links_post_termination_mode_check
                    CHECK (post_termination_mode IS NULL OR post_termination_mode IN ('convert_to_direct', 'transfer_to_broker', 'sunset', 'matcha_managed'));
            EXCEPTION WHEN undefined_table THEN
                NULL;
            END $$;
        """)

        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'broker_company_links_current_transition_id_fkey'
                ) THEN
                    ALTER TABLE broker_company_links
                        ADD CONSTRAINT broker_company_links_current_transition_id_fkey
                        FOREIGN KEY (current_transition_id)
                        REFERENCES broker_company_transitions(id)
                        ON DELETE SET NULL;
                END IF;
            EXCEPTION WHEN undefined_table THEN
                NULL;
            END $$;
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS broker_client_setups (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                broker_id UUID NOT NULL REFERENCES brokers(id) ON DELETE CASCADE,
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                status VARCHAR(20) NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'invited', 'activated', 'expired', 'cancelled')),
                contact_name VARCHAR(255),
                contact_email VARCHAR(320),
                contact_phone VARCHAR(50),
                company_size_hint VARCHAR(50),
                headcount_hint INTEGER,
                preconfigured_features JSONB DEFAULT '{}'::jsonb,
                onboarding_template JSONB DEFAULT '{}'::jsonb,
                invite_token VARCHAR(128) UNIQUE,
                invite_expires_at TIMESTAMPTZ,
                invited_at TIMESTAMPTZ,
                activated_at TIMESTAMPTZ,
                expired_at TIMESTAMPTZ,
                cancelled_at TIMESTAMPTZ,
                created_by UUID REFERENCES users(id),
                updated_by UUID REFERENCES users(id),
                metadata JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE (broker_id, company_id)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_broker_client_setups_broker_status
            ON broker_client_setups(broker_id, status)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_broker_client_setups_invite_token
            ON broker_client_setups(invite_token)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_broker_client_setups_invite_expires_at
            ON broker_client_setups(invite_expires_at)
        """)

        # ===========================================
        # Provisioning and Integrations Tables
        # ===========================================
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS integration_connections (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                provider VARCHAR(50) NOT NULL
                    CHECK (provider IN ('google_workspace', 'slack')),
                status VARCHAR(20) NOT NULL DEFAULT 'disconnected'
                    CHECK (status IN ('disconnected', 'connected', 'error', 'needs_action')),
                config JSONB DEFAULT '{}'::jsonb,
                secrets JSONB DEFAULT '{}'::jsonb,
                last_tested_at TIMESTAMPTZ,
                last_error TEXT,
                created_by UUID REFERENCES users(id),
                updated_by UUID REFERENCES users(id),
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE (company_id, provider)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_integration_connections_company_provider
            ON integration_connections(company_id, provider)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_integration_connections_status
            ON integration_connections(status)
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS onboarding_runs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
                provider VARCHAR(50) NOT NULL
                    CHECK (provider IN ('google_workspace', 'slack')),
                status VARCHAR(20) NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'running', 'completed', 'failed', 'needs_action', 'rolled_back', 'cancelled')),
                trigger_source VARCHAR(30) NOT NULL DEFAULT 'manual'
                    CHECK (trigger_source IN ('manual', 'employee_create', 'scheduled', 'retry', 'api')),
                triggered_by UUID REFERENCES users(id),
                started_at TIMESTAMPTZ,
                completed_at TIMESTAMPTZ,
                last_error TEXT,
                metadata JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_onboarding_runs_company_provider_status
            ON onboarding_runs(company_id, provider, status)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_onboarding_runs_employee_provider
            ON onboarding_runs(employee_id, provider, created_at DESC)
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS onboarding_steps (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                run_id UUID NOT NULL REFERENCES onboarding_runs(id) ON DELETE CASCADE,
                step_key VARCHAR(100) NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'running', 'completed', 'failed', 'needs_action', 'rolled_back', 'cancelled')),
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                last_response JSONB DEFAULT '{}'::jsonb,
                started_at TIMESTAMPTZ,
                completed_at TIMESTAMPTZ,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE (run_id, step_key)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_onboarding_steps_run_status
            ON onboarding_steps(run_id, status)
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS external_identities (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                employee_id UUID NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
                provider VARCHAR(50) NOT NULL
                    CHECK (provider IN ('google_workspace', 'slack')),
                external_user_id VARCHAR(255),
                external_email VARCHAR(320),
                status VARCHAR(20) NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'suspended', 'deprovisioned', 'error')),
                raw_profile JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW(),
                UNIQUE (employee_id, provider)
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_external_identities_company_provider
            ON external_identities(company_id, provider)
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS provisioning_audit_logs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                employee_id UUID REFERENCES employees(id) ON DELETE SET NULL,
                run_id UUID REFERENCES onboarding_runs(id) ON DELETE SET NULL,
                step_id UUID REFERENCES onboarding_steps(id) ON DELETE SET NULL,
                actor_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                provider VARCHAR(50) NOT NULL
                    CHECK (provider IN ('google_workspace', 'slack')),
                action VARCHAR(100) NOT NULL,
                status VARCHAR(20) NOT NULL
                    CHECK (status IN ('success', 'error', 'info')),
                error_code VARCHAR(80),
                detail TEXT,
                payload JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_provisioning_audit_logs_company_created
            ON provisioning_audit_logs(company_id, created_at DESC)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_provisioning_audit_logs_run
            ON provisioning_audit_logs(run_id)
        """)

        # ===========================================
        # HR News Articles Table
        # ===========================================
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS hr_news_articles (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                item_hash VARCHAR(64) NOT NULL UNIQUE,
                title TEXT NOT NULL,
                description TEXT,
                link TEXT,
                author VARCHAR(255),
                pub_date TIMESTAMP,
                source_name VARCHAR(100),
                source_feed_url TEXT,
                image_url TEXT,
                full_content TEXT,
                content_fetched_at TIMESTAMP,
                content_error TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_hr_news_articles_pub_date ON hr_news_articles(pub_date DESC)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_hr_news_articles_source_name ON hr_news_articles(source_name)
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_hr_news_articles_created_at ON hr_news_articles(created_at DESC)
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
