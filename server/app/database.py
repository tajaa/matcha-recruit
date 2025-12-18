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

        # Interviews table
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS interviews (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
                interviewer_name VARCHAR(255),
                interviewer_role VARCHAR(255),
                transcript TEXT,
                raw_culture_data JSONB,
                status VARCHAR(50) DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT NOW(),
                completed_at TIMESTAMP
            )
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

        print("[DB] Tables initialized")
