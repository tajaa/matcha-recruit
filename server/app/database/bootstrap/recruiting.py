"""bootstrap.recruiting — matching/ATS, offer_letters, recruiting/projects, job_applications (verbatim split of app/database.py lines 1136-1640).
"""


async def create_recruiting(conn):
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

        # Migration: Add salary range negotiation columns to offer_letters
        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'offer_letters' AND column_name = 'salary_range_min') THEN
                    ALTER TABLE offer_letters ADD COLUMN salary_range_min DECIMAL(10,2);
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'offer_letters' AND column_name = 'salary_range_max') THEN
                    ALTER TABLE offer_letters ADD COLUMN salary_range_max DECIMAL(10,2);
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'offer_letters' AND column_name = 'candidate_range_min') THEN
                    ALTER TABLE offer_letters ADD COLUMN candidate_range_min DECIMAL(10,2);
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'offer_letters' AND column_name = 'candidate_range_max') THEN
                    ALTER TABLE offer_letters ADD COLUMN candidate_range_max DECIMAL(10,2);
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'offer_letters' AND column_name = 'matched_salary') THEN
                    ALTER TABLE offer_letters ADD COLUMN matched_salary DECIMAL(10,2);
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'offer_letters' AND column_name = 'range_match_status') THEN
                    ALTER TABLE offer_letters ADD COLUMN range_match_status VARCHAR(50);
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'offer_letters' AND column_name = 'candidate_token') THEN
                    ALTER TABLE offer_letters ADD COLUMN candidate_token VARCHAR(64) UNIQUE;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'offer_letters' AND column_name = 'candidate_email') THEN
                    ALTER TABLE offer_letters ADD COLUMN candidate_email VARCHAR(255);
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'offer_letters' AND column_name = 'candidate_token_expires_at') THEN
                    ALTER TABLE offer_letters ADD COLUMN candidate_token_expires_at TIMESTAMP;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'offer_letters' AND column_name = 'negotiation_round') THEN
                    ALTER TABLE offer_letters ADD COLUMN negotiation_round INTEGER DEFAULT 1;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'offer_letters' AND column_name = 'max_negotiation_rounds') THEN
                    ALTER TABLE offer_letters ADD COLUMN max_negotiation_rounds INTEGER DEFAULT 3;
                END IF;
            END $$;
        """)
        # Huume offer-letter sign/accept columns — migration huume01
        # (offer->thread linkage reuses the existing mw_threads.linked_offer_letter_id,
        # not a new column here)
        await conn.execute("""
            ALTER TABLE offer_letters
                ADD COLUMN IF NOT EXISTS signed_name VARCHAR(255),
                ADD COLUMN IF NOT EXISTS signed_at TIMESTAMPTZ,
                ADD COLUMN IF NOT EXISTS signer_ip VARCHAR(64),
                ADD COLUMN IF NOT EXISTS declined_at TIMESTAMPTZ,
                ADD COLUMN IF NOT EXISTS decline_reason TEXT,
                ADD COLUMN IF NOT EXISTS signed_pdf_storage_path TEXT,
                ADD COLUMN IF NOT EXISTS employee_id UUID REFERENCES employees(id) ON DELETE SET NULL;
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

