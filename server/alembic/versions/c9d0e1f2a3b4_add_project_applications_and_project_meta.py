"""add project_applications table and project meta fields

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a
Create Date: 2026-02-18
"""

from alembic import op


def upgrade():
    # Add new columns to projects table
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'projects' AND column_name = 'closing_date'
            ) THEN
                ALTER TABLE projects ADD COLUMN closing_date TIMESTAMP;
            END IF;
        END$$;
    """)

    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'projects' AND column_name = 'salary_hidden'
            ) THEN
                ALTER TABLE projects ADD COLUMN salary_hidden BOOLEAN DEFAULT false;
            END IF;
        END$$;
    """)

    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'projects' AND column_name = 'is_public'
            ) THEN
                ALTER TABLE projects ADD COLUMN is_public BOOLEAN DEFAULT false;
            END IF;
        END$$;
    """)

    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'projects' AND column_name = 'description'
            ) THEN
                ALTER TABLE projects ADD COLUMN description TEXT;
            END IF;
        END$$;
    """)

    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'projects' AND column_name = 'currency'
            ) THEN
                ALTER TABLE projects ADD COLUMN currency VARCHAR(10) DEFAULT 'USD';
            END IF;
        END$$;
    """)

    # Create project_applications table
    op.execute("""
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

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_project_applications_project_id ON project_applications(project_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_project_applications_status ON project_applications(status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_project_applications_candidate_id ON project_applications(candidate_id)"
    )


def downgrade():
    op.execute("DROP TABLE IF EXISTS project_applications")
    op.execute("ALTER TABLE projects DROP COLUMN IF EXISTS closing_date")
    op.execute("ALTER TABLE projects DROP COLUMN IF EXISTS salary_hidden")
    op.execute("ALTER TABLE projects DROP COLUMN IF EXISTS is_public")
    op.execute("ALTER TABLE projects DROP COLUMN IF EXISTS description")
    op.execute("ALTER TABLE projects DROP COLUMN IF EXISTS currency")
