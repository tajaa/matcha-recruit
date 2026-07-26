"""bootstrap.identity — auth/users, admins, companies, SSO, clients, interviews, candidates (verbatim split of app/database.py lines 674-1135).
"""


async def create_identity(conn):
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

        # Admin-suspend flag — separate from is_active so we don't conflate
        # "never activated" with "suspended by admin."
        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'users' AND column_name = 'is_suspended'
                ) THEN
                    ALTER TABLE users ADD COLUMN is_suspended BOOLEAN NOT NULL DEFAULT FALSE;
                END IF;
            END $$;
        """)

        # Session-revocation watermark: any token with iat < tokens_valid_after
        # is rejected. Logout + password change/reset bump it. See authsess01.
        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'users' AND column_name = 'tokens_valid_after'
                ) THEN
                    ALTER TABLE users ADD COLUMN tokens_valid_after TIMESTAMPTZ;
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

        # Add mw_last_active column to users table (Matcha Work presence)
        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'users' AND column_name = 'mw_last_active'
                ) THEN
                    ALTER TABLE users ADD COLUMN mw_last_active TIMESTAMPTZ;
                END IF;
            END $$;
        """)

        # Add avatar_url column to users table
        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'users' AND column_name = 'avatar_url'
                ) THEN
                    ALTER TABLE users ADD COLUMN avatar_url VARCHAR(500);
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
                headquarters_state VARCHAR(50),
                headquarters_city VARCHAR(100),
                work_arrangement VARCHAR(30),
                default_employment_type VARCHAR(30),
                benefits_summary TEXT,
                pto_policy_summary TEXT,
                compensation_notes TEXT,
                company_values TEXT,
                ai_guidance_notes TEXT,
                healthcare_specialties TEXT[],
                report_email_token VARCHAR(32) UNIQUE,
                report_token_used_at TIMESTAMPTZ,
                policy_suggestions_dismissed JSONB DEFAULT '[]'::jsonb,
                seat_limit INTEGER,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)

        # Soft-delete column for admin tenant removal.
        await conn.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'companies' AND column_name = 'deleted_at'
                ) THEN
                    ALTER TABLE companies ADD COLUMN deleted_at TIMESTAMPTZ;
                END IF;
            END $$;
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_companies_deleted_at
                ON companies(deleted_at) WHERE deleted_at IS NULL
        """)

        # SSO/SAML configuration per company
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS company_sso_configs (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID NOT NULL UNIQUE REFERENCES companies(id) ON DELETE CASCADE,
                enabled BOOLEAN DEFAULT false,
                idp_entity_id TEXT NOT NULL,
                idp_sso_url TEXT NOT NULL,
                idp_x509_cert TEXT NOT NULL,
                email_domain VARCHAR(255) NOT NULL,
                default_role VARCHAR(20) DEFAULT 'employee',
                auto_provision BOOLEAN DEFAULT true,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_company_sso_configs_domain
            ON company_sso_configs(email_domain)
            WHERE enabled = true
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
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'companies' AND column_name = 'next_risk_assessment') THEN
                    ALTER TABLE companies ADD COLUMN next_risk_assessment TIMESTAMPTZ;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'companies' AND column_name = 'risk_assessment_interval_days') THEN
                    ALTER TABLE companies ADD COLUMN risk_assessment_interval_days INTEGER DEFAULT 7;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'companies' AND column_name = 'healthcare_specialties') THEN
                    ALTER TABLE companies ADD COLUMN healthcare_specialties TEXT[];
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'companies' AND column_name = 'deleted_at') THEN
                    ALTER TABLE companies ADD COLUMN deleted_at TIMESTAMP;
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

