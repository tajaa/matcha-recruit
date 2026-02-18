"""add company_id to projects for per-project rankings

Revision ID: b8c9d0e1f2a
Revises: a7b8c9d0e1f
Create Date: 2026-02-18
"""

from alembic import op


def upgrade():
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'projects' AND column_name = 'company_id'
            ) THEN
                ALTER TABLE projects
                ADD COLUMN company_id UUID REFERENCES companies(id) ON DELETE SET NULL;
            END IF;
        END$$;
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_projects_company_id ON projects(company_id)"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS idx_projects_company_id")
    op.execute("ALTER TABLE projects DROP COLUMN IF EXISTS company_id")
